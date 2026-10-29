"""S1-7: split files into chunks and embed them locally into a vector store.

Every chunk carries: source (file path), start_line, end_line 
Only pass files that Backend/repo.scan_files marked as safe (no secrets).
"""
import random
import re
from collections import Counter
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from .repo import safe_rmtree
from .config import CHUNK_OVERLAP, CHUNK_SIZE, EMBED_MODEL, MAX_CHUNKS, MAX_FILE_BYTES

SPLIT_LANG = {".py": "PYTHON", ".js": "JS", ".jsx": "JS", ".mjs": "JS", ".ts": "TS", ".tsx": "TS",
              ".java": "JAVA", ".kt": "KOTLIN", ".go": "GO", ".rs": "RUST", ".rb": "RUBY",
              ".php": "PHP", ".cs": "CSHARP", ".cpp": "CPP", ".cc": "CPP", ".hpp": "CPP",
              ".c": "C", ".h": "C", ".swift": "SWIFT", ".scala": "SCALA",
              ".md": "MARKDOWN", ".html": "HTML"}

SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
              "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock"}
SKIP_SUFFIXES = (".min.js", ".min.css", ".map", ".svg")

_splitters: dict = {}


def _get_splitter(ext: str) -> RecursiveCharacterTextSplitter:
    lang = getattr(Language, SPLIT_LANG.get(ext, ""), None)
    if lang not in _splitters:
        kwargs = dict(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True)
        _splitters[lang] = (RecursiveCharacterTextSplitter.from_language(language=lang, **kwargs)
                            if lang else RecursiveCharacterTextSplitter(**kwargs))
    return _splitters[lang]


def _read_text_file(path: Path):
    """Returns (text, None) or (None, reason_skipped)."""
    if path.name in SKIP_NAMES or path.name.lower().endswith(SKIP_SUFFIXES):
        return None, "lockfile/minified"
    if path.stat().st_size > MAX_FILE_BYTES:
        return None, "too large"
    raw = path.read_bytes()
    if b"\x00" in raw[:1024]:
        return None, "binary"
    text = raw.decode("utf-8", errors="ignore")
    return (text, None) if text.strip() else (None, "empty")


def chunk_text(text: str, rel_path: str) -> list[Document]:
    """Split one file's text and attach source + start_line + end_line to each chunk."""
    ext = Path(rel_path).suffix.lower()
    docs = _get_splitter(ext).create_documents([text], metadatas=[{"source": rel_path}])
    for d in docs:
        start = d.metadata["start_index"]
        d.metadata["start_line"] = text.count("\n", 0, start) + 1
        d.metadata["end_line"] = d.metadata["start_line"] + d.page_content.count("\n")
    return docs


def build_chunks(root, safe_files: list[str]) -> tuple[list[Document], Counter]:
    chunks, skipped = [], Counter()
    for rel in safe_files:
        try:
            text, reason = _read_text_file(Path(root) / rel)
        except OSError:
            skipped["unreadable"] += 1
            continue
        if reason:
            skipped[reason] += 1
            continue
        chunks += chunk_text(text, rel)
    return chunks, skipped


def get_embeddings():
    """Local embedding model (free, no API key). First run downloads ~90 MB from HuggingFace."""
    from langchain_huggingface import HuggingFaceEmbeddings
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
    return HuggingFaceEmbeddings(model_name=EMBED_MODEL, model_kwargs={"device": device},
                                 encode_kwargs={"normalize_embeddings": True})


def collection_name(repo_name: str) -> str:
    return ("repo-" + re.sub(r"[^a-zA-Z0-9_-]", "-", repo_name))[:60].rstrip("-_") or "repo-chunks"


def open_store(persist_dir: str, repo_name: str, embeddings=None):
    """Re-open a stored vector DB (used by the summary step and by Sprint 2 Q&A)."""
    from langchain_chroma import Chroma
    return Chroma(collection_name=collection_name(repo_name), embedding_function=embeddings or get_embeddings(),
                  persist_directory=persist_dir)


def index_repo(root, safe_files: list[str], repo_name: str, persist_dir: str = "vector_store",
               max_chunks: int = MAX_CHUNKS, embeddings=None) -> dict:
    """Chunk + embed + store in a persistent Chroma DB. Returns a small report.
    `embeddings` can be injected (tests); default is the local HuggingFace model."""
    from langchain_chroma import Chroma

    chunks, skipped = build_chunks(root, safe_files)
    total_chunks = len(chunks)
    if total_chunks == 0:
        raise RuntimeError("No embeddable text files found in this repository.")
    sampled = total_chunks > max_chunks
    if sampled:  # never silent: reported back to the caller
        chunks = random.Random(0).sample(chunks, max_chunks)

    embeddings = embeddings or get_embeddings()
    collection = collection_name(repo_name)
    safe_rmtree(persist_dir)
    store = Chroma(collection_name=collection, embedding_function=embeddings,
                   persist_directory=persist_dir, collection_metadata={"embedding_model": EMBED_MODEL})
    for i in range(0, len(chunks), 200):
        store.add_documents(chunks[i:i + 200])

    return {"collection": collection, "persist_dir": persist_dir, "chunks_total": total_chunks,
            "chunks_stored": len(chunks), "sampled": sampled, "files_skipped": dict(skipped)}
