"""Shared settings for the Sprint 1 AI pipeline"""
import os

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")  # verify in Google AI Studio
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
MAX_FILE_BYTES = 200_000     # bigger files are skipped for embedding
MAX_CHUNKS = 5000            # safety cap for huge repos

LLM_TIMEOUT_SECONDS = 60     # NFR-11: bounded timeout
LLM_MAX_RETRIES = 3          # NFR-11: retry with backoff

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", "__pycache__",
             ".venv", "venv", ".idea", ".vscode", ".next", ".tox", ".mypy_cache",
             ".pytest_cache", "site-packages"}

# Second line of defence. Backend's S1-5 filter is the main one (FR-20 / DR-02).
SENSITIVE_PATTERNS = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks",
                      "*.keystore", "id_rsa*", "id_ed25519*", "credentials*",
                      "*.tfvars", "secrets.*", "*.secret", "*.secrets"]
