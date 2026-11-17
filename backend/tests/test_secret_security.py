"""Credential regressions shared by indexing, README prompts, issues and source viewing."""
import pytest

from ai_pipeline.secrets import REDACTED, redact_secrets


@pytest.mark.parametrize("text, secret", [
    ("API_TOKEN=abcDEF1234567890ZYX987654321", "abcDEF1234567890ZYX987654321"),
    ('{"api_key": "abcDEF1234567890ZYX987654321"}', "abcDEF1234567890ZYX987654321"),
    ("password: 'short'", "short"),
    ('DB_PASSWORD = "contains spaces and punctuation!"', "contains spaces and punctuation!"),
    ("Password=abc123;Server=db;Database=app", "abc123"),
    ("token = 'abc_example_def_1234567890'", "abc_example_def_1234567890"),
    ('DATABASE_URL = "postgresql://admin:S3cur3-Pass-987@db.example/app"', "admin:S3cur3-Pass-987"),
    ("postgresql+psycopg://user:p%40ss%3Aword@db/app?sslmode=require", "user:p%40ss%3Aword"),
    ("redis://:abc123@localhost:6379", ":abc123"),
    ("mongodb+srv://user:abc123@cluster/app", "user:abc123"),
    ("https://user:abc123@example.com/path", "user:abc123"),
    ("Authorization: Bearer abcDEF1234567890", "abcDEF1234567890"),
    ('{"Authorization": "Basic dXNlcjpwYXNz"}', "dXNlcjpwYXNz"),
    ("key: sk-proj-" + "aB2_" * 12, "sk-proj-" + "aB2_" * 12),
])
def test_redacts_common_credentials(text, secret):
    out, count = redact_secrets(text)
    assert secret not in out and REDACTED in out and count >= 1
    assert out.count("\n") == text.count("\n")
    assert redact_secrets(out) == (out, 0)


@pytest.mark.parametrize("text", [
    'api_key = "your_api_key_here_please"',
    "token=example_token",
    "password: changeme",
    'token = "${GITHUB_TOKEN}"',
    "token = process.env.GITHUB_TOKEN",
    "token = None",
    "https://example.com/path",
    "postgresql://localhost/app",
    "postgresql://${DB_USER}:${DB_PASSWORD}@localhost/app",
    "Authorization: Bearer YOUR_TOKEN",
])
def test_preserves_placeholders_and_noncredential_urls(text):
    assert redact_secrets(text) == (text, 0)


def test_keeps_quotes_comments_separators_and_line_numbers():
    text = '{"password": "short"}\nTOKEN=short # comment\nPassword=short;Server=db\n'
    out, count = redact_secrets(text)
    assert out == (
        '{"password": "[REDACTED_SECRET]"}\nTOKEN=[REDACTED_SECRET] # comment\n'
        'Password=[REDACTED_SECRET];Server=db\n'
    )
    assert count == 3


def test_readme_and_analysis_use_extended_redaction(tmp_path):
    from ai_pipeline.pipeline import analyze_checkout
    from ai_pipeline.readme import read_readme

    secret = "abcDEF1234567890ZYX987654321"
    (tmp_path / "README.md").write_text(f"# App\nAPI_TOKEN={secret}\nRun the app.\n")
    assert secret not in read_readme(tmp_path, ["README.md"])
    analysis = analyze_checkout(tmp_path)
    assert analysis.report["secrets_redacted"] == 1
    assert all(secret not in chunk.page_content for chunk in analysis.chunks)
