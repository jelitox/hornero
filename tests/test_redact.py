"""Redaction layer (SPEC-003 §9): planted fake secrets across env + files
produce zero secret bytes in any generated output."""

import subprocess

from hornero.cli import main
from hornero.redact import redact, scan_secrets

FAKE_ENV_TOKEN = "hunter2-super-secret-value-9000"
FAKE_GH = "ghp_" + "a1B2c3D4" * 4


def test_redact_shapes_and_idempotence():
    text = f"token {FAKE_GH} and key AKIA{'A' * 16} end"
    out = redact(text)
    assert FAKE_GH not in out and "AKIA" + "A" * 16 not in out
    assert "[REDACTED:GitHub token]" in out
    assert redact(out) == out  # idempotent
    assert redact("plain prose") == "plain prose"


def test_redact_env_values(monkeypatch):
    monkeypatch.setenv("ACME_API_TOKEN", FAKE_ENV_TOKEN)
    monkeypatch.setenv("SHORT_KEY", "x")  # too short: never redacted
    out = redact(f"config uses {FAKE_ENV_TOKEN} and x marks the spot")
    assert FAKE_ENV_TOKEN not in out
    assert "[REDACTED:ACME_API_TOKEN]" in out
    assert "x marks the spot" in out


def test_scan_secrets_reexported_for_push():
    from hornero.sdd_toolkit.push import scan_secrets as push_scan

    assert push_scan is scan_secrets


def test_generated_reports_leak_zero_secret_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTED_SECRET", FAKE_ENV_TOKEN)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert main(["init"]) == 0
    # a done spec whose body embeds both a shape-secret and the env value
    (repo / "sdd" / "specs" / "SPEC-001-leaky.md").write_text(
        "---\nspec: SPEC-001\ntitle: Leaky\nstatus: done\nkind: new_feature\n"
        "created: 2026-07-08\nsources: [sig-a]\nsupersedes: []\n"
        "acceptance_criteria: []\n---\n\n# SPEC-001 — Leaky\n\n"
        f"Connect with {FAKE_GH} or {FAKE_ENV_TOKEN}.\n",
        encoding="utf-8",
    )
    assert main(["report"]) == 0
    for page in (repo / "sdd" / "reports").glob("*.html"):
        blob = page.read_bytes()
        assert FAKE_GH.encode() not in blob
        assert FAKE_ENV_TOKEN.encode() not in blob
