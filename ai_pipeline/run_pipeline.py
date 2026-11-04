"""Codebase Onboarding Companion - AI pipeline, terminal runner.

    python run_pipeline.py https://github.com/psf/requests

Steps: clone -> store file tree -> detect stack -> chunk+embed into Chroma -> generate summary.
Use --skip-summary to avoid any Gemini call (no tokens used), --query to test the vector DB.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ai_pipeline import detect_tech_stack, index_repo
from ai_pipeline.repo import cleanup, clone_repo, save_file_tree, scan_files


def banner(t):
    print(f"\n{'=' * 8} {t} {'=' * 8}")


def print_summary(s):
    banner("REPOSITORY SUMMARY")
    print(f"{s.title}: {s.one_line}\n\n{s.description}\n\nArchitecture:\n{s.architecture}")
    print("\nTech highlights: " + ", ".join(s.tech_highlights))
    print("Start reading: " + ", ".join(s.key_files))
    print(f"\nHow to run:\n{s.how_to_run}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_url", nargs="?", help="public GitHub URL (not needed with --query on an existing store)")
    ap.add_argument("--branch", default="")
    ap.add_argument("--work-dir", default="repo_work")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--skip-embed", action="store_true", help="skip chunking/embedding (no vector DB)")
    ap.add_argument("--skip-summary", action="store_true", help="skip the Gemini summary (uses no tokens)")
    ap.add_argument("--module-map", action="store_true", help="also run the module-map LLM call (extra tokens)")
    ap.add_argument("--keep-clone", action="store_true", help="keep the cloned files (DR-03 says delete)")
    ap.add_argument("--query", default="", help="search the stored vector DB, e.g. --query 'where is auth handled'")
    args = ap.parse_args()

    load_dotenv()
    out = Path(args.out_dir)
    out.mkdir(exist_ok=True)

    if args.query:  # search-only mode: no clone, no LLM
        from ai_pipeline.indexer import open_store
        rep = json.loads((out / "index_report.json").read_text())
        store = open_store(rep["persist_dir"], rep["collection"].removeprefix("repo-"))
        for d in store.similarity_search(args.query, k=4):
            m = d.metadata
            print(f"\n--- {m['source']}  lines {m['start_line']}-{m['end_line']}\n{d.page_content[:400]}")
        return
    if not args.repo_url:
        ap.error("repo_url is required")
    if not (args.skip_summary and not args.module_map) and not os.environ.get("GOOGLE_API_KEY"):
        sys.exit("GOOGLE_API_KEY is not set. Put it in a .env file, or run with --skip-summary.")

    work = Path(args.work_dir)
    repo_name = args.repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    banner(f"1/4 Cloning {args.repo_url}")
    try:
        clone_repo(args.repo_url, args.branch, work)
    except RuntimeError as e:
        sys.exit(str(e))
    try:
        all_files, safe_files = scan_files(work)
        info = save_file_tree(work, all_files, safe_files, out)
        print(f"{info['files']} files in {info['folders']} folders stored -> {out}/file_tree.json, tree.txt "
              f"({len(all_files) - len(safe_files)} sensitive files excluded from embedding)")

        banner("2/4 Tech stack")
        stack = detect_tech_stack(work, all_files)
        (out / "tech_stack.json").write_text(json.dumps(stack, indent=2))
        print(json.dumps({k: stack[k] for k in ("languages", "frameworks", "package_managers")}, indent=2))

        store, report = None, None
        if not args.skip_embed:
            banner("3/4 Chunking + embeddings -> vector DB (first run downloads the model)")
            report = index_repo(work, safe_files, repo_name, persist_dir=str(out / "vector_store"))
            (out / "index_report.json").write_text(json.dumps(report, indent=2))
            print(report)
            from ai_pipeline.indexer import open_store
            store = open_store(report["persist_dir"], repo_name)

        if not args.skip_summary:
            banner("4/4 Generating summary (1 Gemini call)")
            from ai_pipeline.summary import generate_summary
            try:
                summary, warns = generate_summary(work, all_files, stack, store)
            except Exception as e:
                sys.exit(f"Gemini call failed: {type(e).__name__}: {e}\n"
                         "Check GOOGLE_API_KEY and GEMINI_MODEL (ai_pipeline/config.py or env var).")
            (out / "summary.json").write_text(summary.model_dump_json(indent=2))
            (out / "summary_warnings.json").write_text(json.dumps(warns, indent=2))
            print_summary(summary)
            if warns:
                print(f"\n({len(warns)} warning(s) in summary_warnings.json)")

        if args.module_map:
            from ai_pipeline import generate_module_map
            mm, warns = generate_module_map(work, all_files, stack)
            (out / "module_map.json").write_text(mm.model_dump_json(indent=2))
            (out / "module_map_warnings.json").write_text(json.dumps(warns, indent=2))
            print(f"\nmodule map: {len(mm.modules)} modules, {len(warns)} warning(s)")
        print(f"\nDone. Outputs in {out}/")
    finally:
        if not args.keep_clone:
            cleanup(work)


if __name__ == "__main__":
    main()
