"""Static settings for the analysis pipeline.

Runtime settings (API keys, models, DB) live in app/core/config.py; this module has no env access
so the pipeline stays easy to test on its own.
"""

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", "__pycache__", ".venv", "venv",
             ".idea", ".vscode", ".next", ".tox", ".mypy_cache", ".pytest_cache", "site-packages",
             ".ruff_cache", ".gradle", "coverage", ".cache"}

# Filename patterns whose CONTENT is never read (they still appear as nodes in the file tree).
SENSITIVE_PATTERNS = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
                      "id_rsa*", "id_ed25519*", "credentials*", "*.tfvars", "secrets.*", "*.secret",
                      "*.secrets", "*.kdbx", ".npmrc", ".pypirc", ".netrc"]

SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock",
              "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock"}
SKIP_SUFFIXES = (".min.js", ".min.css", ".map", ".svg", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico",
                 ".pdf", ".zip", ".gz", ".woff", ".woff2", ".ttf", ".mp4", ".mp3", ".so", ".dll", ".exe",
                 ".pyc", ".class", ".jar")

MAX_FILES = 20_000               # safety cap on files walked
MAX_TOTAL_BYTES = 60_000_000     # safety cap on text read per repo

CHUNK_MAX_CHARS = 1800           # keeps chunks inside the embedding model's token window
WINDOW_LINES = 60                # window size for files we cannot parse
WINDOW_OVERLAP = 6
MIN_CHUNK_CHARS = 15
