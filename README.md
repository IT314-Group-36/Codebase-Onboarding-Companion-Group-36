# Codebase Onboarding Companion - AI / LangChain pipeline

Give it a GitHub URL. It stores the file tree, embeds the code into a Chroma vector DB, and generates a repository summary.

| Step | Function | LLM? | Output |
|---|---|---|---|
| Store files/folders | `repo.save_file_tree(root, all_files, safe_files, out_dir)` | No | `file_tree.json`, `tree.txt` |
| Tech stack | `detect_tech_stack(root, all_files)` | No | `tech_stack.json` |
| Chunk + embed | `index_repo(root, safe_files, repo_name, persist_dir)` | No (local model) | `vector_store/`, `index_report.json` |
| Re-open vector DB | `open_store(persist_dir, repo_name)` | No | Chroma store (`similarity_search`) |
| Summary | `summary.generate_summary(root, all_files, stack, store)` | 1 Gemini call | `summary.json` |
| Module map (optional) | `generate_module_map(root, all_files, stack)` | 1 Gemini call | `module_map.json` |

## Setup
```
python -m venv venv && venv\Scripts\activate      # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env     # then put your real GOOGLE_API_KEY in .env  (Mac/Linux: cp)
```

## Run (terminal)
```
python run_pipeline.py https://github.com/psf/requests                 # everything
python run_pipeline.py <url> --skip-summary                            # no Gemini call, zero tokens
python run_pipeline.py <url> --skip-summary --skip-embed               # tree + stack only (seconds)
python run_pipeline.py --query "where are sessions handled"            # search the stored vector DB, no LLM
python run_pipeline.py <url> --module-map                              # also run module-map call
pytest -q                                                              # offline tests
```
The first embedding run downloads the model (~90 MB). Outputs go to `output/`.

## Token usage
Summary = one Gemini call: README (3000 chars) + trimmed file tree + max ~9000 chars of code chunks fetched from the vector DB. The module map is off unless `--module-map`.

## Hand-off contract (for Backend)
- Backend passes `all_files` (every file) and `safe_files` (secrets removed; only these are embedded). `repo.scan_files` is a stand-in with a second-line filter.
- Every chunk has metadata `source`, `start_line`, `end_line` (FR-06 citations).
- Run `index_repo` as a background job, not in a web request (slow on big repos).
- Delete the clone after analysis (DR-03): `repo.cleanup(path)`; the file tree JSON and vector DB are what remain.
- Paths invented by the LLM are removed and listed in `summary_warnings.json`.

## Known limits
- Repos above `MAX_CHUNKS` (5000) are randomly sampled (`index_report.json` has `sampled: true`).
- Files over 200 KB, binaries, lockfiles and minified files are not embedded.
- Gemini free tier may not give Zero Data Retention (FR-22): use public/dummy repos.
- Confirm `GEMINI_MODEL` (env var or `ai_pipeline/config.py`) in Google AI Studio.
