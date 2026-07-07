"""Reindex: determinism, manifest, staleness, persisted-index equivalence."""

import hashlib
import subprocess

from hornero.cli import main
from hornero.memory.knowledge import TokenOverlapKnowledge, knowledge_roots
from hornero.memory.reindex import index_staleness, load_persisted, reindex


def _repo(tmp_path, monkeypatch, git=False):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    specs = tmp_path / "product" / "specs"
    (specs / "SPEC-001-csv.md").write_text(
        "---\nspec: SPEC-001\ntitle: CSV export\nstatus: done\n---\n\n"
        "Export usage as CSV for finance.\n",
        encoding="utf-8",
    )
    (tmp_path / ".hornero" / "processed").mkdir(exist_ok=True)
    (tmp_path / ".hornero" / "processed" / "note.md").write_text(
        "finance asked for CSV", encoding="utf-8"
    )
    if git:
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
            subprocess.run(
                ["git", "-C", str(tmp_path), *args],
                check=True, capture_output=True,
                env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.o",
                     "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.o",
                     "PATH": "/usr/bin:/bin"},
            )
    return tmp_path


def _knowledge_hash(root):
    digest = hashlib.sha256()
    base = root / ".hornero" / "knowledge"
    for p in sorted(base.rglob("*")):
        if p.is_file():
            digest.update(str(p.relative_to(base)).encode() + p.read_bytes())
    return digest.hexdigest()


def test_reindex_deterministic_bytes(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    reindex(root)
    first = _knowledge_hash(root)
    reindex(root)
    assert _knowledge_hash(root) == first


def test_manifest_contents(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    manifest = reindex(root)
    assert manifest["model"] is None and manifest["prompt_hash"] is None
    assert manifest["layers"]["fallback"] is True
    paths = [s["path"] for s in manifest["sources"]]
    assert ".hornero/processed/note.md" in paths
    assert "product/specs/SPEC-001-csv.md" in paths
    assert all(len(s["sha256"]) == 64 for s in manifest["sources"])


def test_head_ref_recorded_in_git_repo(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, git=True)
    manifest = reindex(root)
    assert manifest["head_ref"] and len(manifest["head_ref"]) == 40


def test_non_git_dir_tolerated(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    assert reindex(root)["head_ref"] is None


def test_status_staleness_lifecycle(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    assert index_staleness(root) == "absent"
    assert main(["reindex"]) == 0
    assert index_staleness(root) == "fresh"
    (root / "product" / "specs" / "SPEC-001-csv.md").write_text(
        "---\nspec: SPEC-001\ntitle: CSV export\nstatus: done\n---\n\nEdited.\n",
        encoding="utf-8",
    )
    assert index_staleness(root) == "stale"
    assert main(["status"]) == 0
    assert "knowledge index: stale" in capsys.readouterr().out


def test_persisted_index_matches_live_scan(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    reindex(root)
    persisted = load_persisted(root)
    live = TokenOverlapKnowledge(knowledge_roots(root))
    assert persisted is not None
    p_hits = persisted.retrieve("finance CSV usage", k=3)
    l_hits = live.retrieve("finance CSV usage", k=3)
    assert [(h.score, h.excerpt, h.kind) for h in p_hits] == [
        (h.score, h.excerpt, h.kind) for h in l_hits
    ]


def test_reconcile_and_build_do_not_write_knowledge(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    reindex(root)
    before = _knowledge_hash(root)
    main(["build"])  # no approved specs: no-op, and must not touch knowledge
    assert main(["reconcile"]) == 3  # no model configured: refuses pre-poll
    assert _knowledge_hash(root) == before
