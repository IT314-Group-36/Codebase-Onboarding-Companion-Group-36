"""C4: the Git child process gets an allow-listed environment and a GitHub-scoped credential header."""
from ai_pipeline import repo

SECRETS = {
    "SESSION_SECRET": "s" * 40, "TOKEN_ENCRYPTION_KEY": "encryption-key", "LLM_API_KEY": "llm-key",
    "CF_API_TOKEN": "cloudflare-token", "DATABASE_URL": "postgresql://user:pw@host/db",
    "GITHUB_CLIENT_SECRET": "client-secret", "GITHUB_TOKEN": "server-token",
}


def _record_git_calls(monkeypatch):
    seen = []

    def fake_run_git(cmd, root, env, deadline, limits):
        seen.append(dict(env))
        if "ls-tree" in cmd:
            return b""
        return b"0" * 40 + b"\n" if "rev-parse" in cmd else b""

    monkeypatch.setattr(repo, "run_git", fake_run_git)
    monkeypatch.setattr(repo, "_check_github_size", lambda *args, **kwargs: None)
    return seen


def test_git_child_never_sees_server_secrets(monkeypatch, tmp_path):
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)
    seen = _record_git_calls(monkeypatch)
    sha = repo.clone_repo("https://github.com/o/r", "", tmp_path / "job" / "clone", "gho_token")
    assert sha == "0" * 40 and len(seen) == 4
    for env in seen:
        assert not set(SECRETS) & set(env)
        assert not any(value in " ".join(env.values()) for value in SECRETS.values())
        assert env["HOME"] == str(tmp_path / "job") and env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"


def test_credential_header_is_scoped_to_github(monkeypatch, tmp_path):
    seen = _record_git_calls(monkeypatch)
    repo.clone_repo("https://github.com/o/r", "", tmp_path / "job" / "clone", "gho_token")
    assert all(env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader" for env in seen)
    assert all(env["GIT_CONFIG_KEY_0"] != "http.extraheader" for env in seen)


def test_anonymous_clone_has_no_credential_header(monkeypatch, tmp_path):
    seen = _record_git_calls(monkeypatch)
    repo.clone_repo("https://github.com/o/r", "", tmp_path / "job" / "clone", None)
    assert all("GIT_CONFIG_COUNT" not in env and "GIT_CONFIG_KEY_0" not in env for env in seen)
