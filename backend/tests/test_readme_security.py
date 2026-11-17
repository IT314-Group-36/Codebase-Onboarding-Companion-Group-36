"""README handling must use the same protections as indexed source."""
import os

import pytest

from ai_pipeline.readme import MAX_README_BYTES, read_readme
from ai_pipeline.secrets import REDACTED


@pytest.mark.parametrize("name", ["README.pem", "README.key", "README.env", "README.png"])
def test_sensitive_or_non_text_readmes_are_not_read(tmp_path, name):
    (tmp_path / name).write_text("private material")
    assert read_readme(tmp_path, [name]) == "(no README found)"


def test_redacts_before_truncating_and_preserves_lines(tmp_path):
    secret = "AKIAABCDEFGHIJKLMNOP"
    text = "# App\ncredential: " + secret + "\nSetup instructions\n"
    (tmp_path / "README.md").write_text(text)
    out = read_readme(tmp_path, ["README.md"], limit=1000)
    assert secret not in out and REDACTED in out
    assert out.count("\n") == text.count("\n")
    assert read_readme(tmp_path, ["README.md"], limit=22) == out[:22]


def test_skips_oversized_binary_and_missing_candidates(tmp_path):
    (tmp_path / "README-large.md").write_bytes(b"x" * (MAX_README_BYTES + 1))
    (tmp_path / "README-binary.md").write_bytes(b"text\x00hidden")
    (tmp_path / "README.txt").write_text("Safe documentation")
    assert read_readme(tmp_path, [
        "README-large.md", "README-binary.md", "README-missing.md", "README.txt",
    ]) == "Safe documentation"


def test_does_not_read_outside_root(tmp_path):
    assert read_readme(tmp_path, ["README/../secret", "README\\..\\secret"]) == "(no README found)"


def test_skips_symlink(tmp_path):
    target = tmp_path / "private.txt"
    target.write_text("private material")
    try:
        os.symlink(target, tmp_path / "README.md")
    except OSError:
        pytest.skip("Creating symlinks requires privileges on this platform")
    assert read_readme(tmp_path, ["README.md"]) == "(no README found)"


def test_limit_and_empty_file_list(tmp_path):
    assert read_readme(tmp_path, []) == "(no README found)"
    assert read_readme(tmp_path, ["README.md"], limit=0) == ""


def test_both_llm_paths_share_safe_reader():
    from ai_pipeline import module_map, summary

    assert module_map.read_readme is read_readme
    assert summary.read_readme is read_readme
