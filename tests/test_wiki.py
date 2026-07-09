"""F7 gate (wiki half): fixture repo + FakeLLM — init produces quickstart
with valid links; update after a scoped commit edits only the impacted page;
a second update no-ops without calling the model."""

import json
import subprocess

import pytest

from hornero import watermarks
from hornero.cli import main
from hornero.reconciler.testing import FakeLLM
from hornero.wiki import WikiError, wiki_init, wiki_update

QUICKSTART = """# Quickstart

Hornero demo repo. The exporter lives in [src/exporter.py](../src/exporter.py).

- [Architecture](architecture/overview.md)
- Start with the tests, then read the spec.
"""

OVERVIEW = """# Architecture overview

One module, one job: exporting usage as CSV. Watch out for the header row —
tests pin its exact order. Back to [quickstart](../quickstart.md).
"""

INIT_RESPONSE = json.dumps({"pages": [
    {"path": "quickstart.md", "content": QUICKSTART},
    {"path": "architecture/overview.md", "content": OVERVIEW},
]})


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "exporter.py").write_text("def export(): ...\n")
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.o"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    assert main(["init", "--no-wiki"]) == 0
    _commit(repo)
    return repo


def _commit(repo):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True)


def test_f7_gate_init_quickstart_and_valid_links(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    llm = FakeLLM({"Top-level tree": INIT_RESPONSE})
    assert wiki_init(repo, llm, model="fake") == 0
    assert (repo / "wiki" / "quickstart.md").is_file()
    assert (repo / "wiki" / "architecture" / "overview.md").is_file()
    wm = watermarks.get(repo, "wiki")
    assert wm is not None and wm["model"] == "fake"


def test_init_rejects_missing_quickstart_and_broken_links(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    no_qs = json.dumps({"pages": [{"path": "architecture/overview.md",
                                   "content": OVERVIEW}]})
    with pytest.raises(WikiError, match="quickstart"):
        wiki_init(repo, FakeLLM({"Top-level tree": no_qs}))
    broken = json.dumps({"pages": [{"path": "quickstart.md",
        "content": "# Q\n\nlong enough content here. [dead](nowhere/gone.md)"
                   " with some extra words to pass the stub check."}]})
    with pytest.raises(WikiError, match="broken wiki links"):
        wiki_init(repo, FakeLLM({"Top-level tree": broken}))
    assert not (repo / "wiki").exists()  # nothing lands on failure


def test_init_rejects_stub_pages_and_small_repo_cap(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    stub = json.dumps({"pages": [{"path": "quickstart.md", "content": "# Q"}]})
    with pytest.raises(WikiError, match="stub"):
        wiki_init(repo, FakeLLM({"Top-level tree": stub}))
    body = ("This page has plenty of real, substantive content to clear the "
            "anti-stub bar easily, with change-oriented guidance included.")
    many = json.dumps({"pages": [
        {"path": "quickstart.md", "content": f"# Q\n\n{body}"},
        *[{"path": f"{s}/x.md", "content": f"# X\n\n{body}"}
          for s in ("architecture", "workflows", "domain", "operations")],
    ]})
    with pytest.raises(WikiError, match="small repo"):
        wiki_init(repo, FakeLLM({"Top-level tree": many}))


def test_f7_gate_update_edits_only_impacted_page(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    wiki_init(repo, FakeLLM({"Top-level tree": INIT_RESPONSE}), model="fake")
    _commit(repo)
    # scoped change: exporter gains a JSON mode
    (repo / "src" / "exporter.py").write_text("def export(fmt='csv'): ...\n")
    _commit(repo)
    new_overview = OVERVIEW.replace("exporting usage as CSV",
                                    "exporting usage as CSV or JSON")
    update = json.dumps({
        "impact_plan": [{"change": "exporter gains fmt param",
                         "page": "architecture/overview.md",
                         "edit": "mention JSON", "why": "stale claim"}],
        "edits": [{"path": "architecture/overview.md", "content": new_overview}],
    })
    quickstart_before = (repo / "wiki" / "quickstart.md").read_bytes()
    assert wiki_update(repo, FakeLLM({"Changed files": update}), model="fake") == 0
    assert "CSV or JSON" in (repo / "wiki" / "architecture" / "overview.md").read_text()
    assert (repo / "wiki" / "quickstart.md").read_bytes() == quickstart_before


def test_update_noop_never_calls_model(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    wiki_init(repo, FakeLLM({"Top-level tree": INIT_RESPONSE}), model="fake")
    _commit(repo)
    # the commit that landed the wiki itself is never analysis input
    exploding = FakeLLM({})  # any call raises UnexpectedPromptError
    assert wiki_update(repo, exploding, model="fake") == 0
    assert "wiki already current" in capsys.readouterr().out
    assert exploding.calls == []
    # a real change answered with "no edits" advances the watermark...
    (repo / "src" / "exporter.py").write_text("def export(y): ...\n")
    _commit(repo)
    noop = json.dumps({"impact_plan": [], "edits": []})
    assert wiki_update(repo, FakeLLM({"Changed files": noop}), model="fake") == 0
    assert "wiki already current" in capsys.readouterr().out
    # ...so the SAME window is never re-analyzed
    exploding2 = FakeLLM({})
    assert wiki_update(repo, exploding2, model="fake") == 0
    assert exploding2.calls == []


def test_update_budget_and_formatting_guard(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    wiki_init(repo, FakeLLM({"Top-level tree": INIT_RESPONSE}), model="fake")
    _commit(repo)
    (repo / "src" / "exporter.py").write_text("def export(x): ...\n")
    _commit(repo)
    body = "Enough real content to clear the anti-stub bar with room to spare."
    over_budget = json.dumps({"impact_plan": [], "edits": [
        {"path": "quickstart.md", "content": f"# Q\n\n{body} v2"},
        {"path": "architecture/overview.md", "content": f"# A\n\n{body} v2"},
        {"path": "workflows/w.md", "content": f"# W\n\n{body}"},
    ]})
    with pytest.raises(WikiError, match="U2 violated"):
        wiki_update(repo, FakeLLM({"Changed files": over_budget}))
    # formatting-only edit (reordered lines) is reverted, leaving a no-op
    reordered = "\n".join(reversed(OVERVIEW.splitlines()))
    fmt_only = json.dumps({"impact_plan": [], "edits": [
        {"path": "architecture/overview.md", "content": reordered}]})
    before = (repo / "wiki" / "architecture" / "overview.md").read_bytes()
    assert wiki_update(repo, FakeLLM({"Changed files": fmt_only})) == 0
    out = capsys.readouterr().out
    assert "reverted formatting-only edit" in out
    assert (repo / "wiki" / "architecture" / "overview.md").read_bytes() == before


def test_wiki_cli_requires_model(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    assert main(["wiki", "init"]) == 3
    assert "models.wiki" in capsys.readouterr().err


def test_wiki_cli_with_fake_script(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    script = repo / ".hornero" / "wiki.fake.json"
    script.write_text(json.dumps({"Top-level tree": INIT_RESPONSE}))
    (repo / ".hornero" / "config.yaml").write_text(
        "models:\n  wiki: fake:.hornero/wiki.fake.json\n", encoding="utf-8"
    )
    assert main(["wiki", "init"]) == 0
    assert (repo / "wiki" / "quickstart.md").is_file()


def test_init_offers_wiki_hint(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "r2"
    repo.mkdir()
    monkeypatch.chdir(repo)
    assert main(["init"]) == 0
    assert "hornero wiki init" in capsys.readouterr().out
    assert main(["init", "--no-wiki"]) == 0
    assert "hornero wiki init" not in capsys.readouterr().out
