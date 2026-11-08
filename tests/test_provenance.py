"""pipeline/provenance.py: run fingerprint (audit F-06, F-24). No Docker needed."""
from pathlib import Path

from pipeline import provenance


def make_pipeline(root: Path, files: dict[str, bytes]) -> Path:
    (root / "pipeline").mkdir(parents=True)
    for name, data in files.items():
        (root / "pipeline" / name).write_bytes(data)
    return root


def test_code_hash_changes_when_code_changes(tmp_path):
    a = make_pipeline(tmp_path / "a", {"x.py": b"print(1)\n"})
    b = make_pipeline(tmp_path / "b", {"x.py": b"print(2)\n"})
    c = make_pipeline(tmp_path / "c", {"x.py": b"print(1)\n", "y.py": b""})
    assert len({provenance.code_sha256(a), provenance.code_sha256(b), provenance.code_sha256(c)}) == 3


def test_code_hash_ignores_line_endings(tmp_path):
    lf = make_pipeline(tmp_path / "lf", {"x.py": b"a = 1\nb = 2\n"})
    crlf = make_pipeline(tmp_path / "crlf", {"x.py": b"a = 1\r\nb = 2\r\n"})
    assert provenance.code_sha256(lf) == provenance.code_sha256(crlf)


def test_collect_records_model_but_never_the_api_key(tmp_path):
    repo = make_pipeline(tmp_path / "r", {"x.py": b"pass\n"})
    env = {"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "m", "LLM_API_KEY": "sk-SECRET-123"}
    p = provenance.collect({"max_diff_lines": 20}, repo=repo, env=env)
    assert (p["llm_base_url"], p["llm_model"]) == ("http://localhost:11434/v1", "m")
    assert "SECRET" not in repr(p)
    assert p["git_head"] is None and p["git_dirty"] is None      # not a git repo: unknown, not "clean"
    assert len(p["config_sha256"]) == 64 and len(p["prompts_sha256"]) == 64


def test_config_hash_is_order_independent():
    assert provenance.config_sha256({"a": 1, "b": 2}) == provenance.config_sha256({"b": 2, "a": 1})
    assert provenance.config_sha256({"a": 1}) != provenance.config_sha256({"a": 2})
