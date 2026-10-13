#!/usr/bin/env python3
"""Start the whole stack: AI engine (9000), backend (8000), frontend (3000).

    uv run python run.py          # or: python run.py
Ctrl-C stops everything.
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE_PORT, BACKEND_PORT, FRONTEND_PORT = 9000, 8000, 3000


def load_dotenv(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    env[k.strip()] = v.strip()
    return env


def wait_for(url: str, name: str, timeout: int = 40) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.4)
    print(f"!! {name} did not become ready at {url}")


def main() -> None:
    env = {**os.environ, **load_dotenv(ROOT / ".env")}
    engine_key = env.get("ENGINE_API_KEY", "")
    backend_env = {**env, "AI_API_URL": f"http://127.0.0.1:{ENGINE_PORT}/v1/generate"}
    if engine_key:
        backend_env["AI_API_KEY"] = engine_key
    uv = [sys.executable, "-m", "uvicorn"]
    reload_flag = ["--reload"] if "--reload" in sys.argv else []

    procs = [
        ("AI engine", subprocess.Popen(uv + ["app.main:app", "--port", str(ENGINE_PORT)] + reload_flag,
                                       cwd=ROOT / "ai_engine", env=env)),
        ("backend", subprocess.Popen(uv + ["app.main:app", "--port", str(BACKEND_PORT)] + reload_flag,
                                     cwd=ROOT / "backend", env=backend_env)),
        ("frontend", subprocess.Popen([sys.executable, "-m", "http.server", str(FRONTEND_PORT),
                                       "--bind", "127.0.0.1", "--directory", str(ROOT / "frontend")],
                                      cwd=ROOT, env=env, stdout=subprocess.DEVNULL)),
    ]

    def shutdown(*_):
        for _, p in procs:
            if p.poll() is None:
                p.terminate()
        for _, p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    wait_for(f"http://127.0.0.1:{ENGINE_PORT}/health", "AI engine")
    wait_for(f"http://127.0.0.1:{BACKEND_PORT}/health", "backend")
    print(f"""
  Codebase Onboarding Companion is running

    Frontend   http://localhost:{FRONTEND_PORT}
    API docs   http://localhost:{BACKEND_PORT}/docs
    AI engine  http://localhost:{ENGINE_PORT}/docs

  Press Ctrl-C to stop.
""")
    while True:
        for name, p in procs:
            if p.poll() is not None:
                print(f"!! {name} exited with code {p.returncode}; stopping everything.")
                shutdown()
        time.sleep(1)


if __name__ == "__main__":
    main()
