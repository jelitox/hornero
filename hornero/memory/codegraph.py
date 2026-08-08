"""Deterministic repository knowledge graph.

This is Hornero's stdlib-only version of ai-parrot's FEAT-260 wiki
retrieval plane: source files become ``file:<path>`` pages, directories
become ``dir:<path>`` pages, and typed edges capture containment plus Python
imports. The graph is derived state under ``.hornero/knowledge/graph/`` and
is rebuilt by ``hornero reindex``.
"""

from __future__ import annotations

import ast
import hashlib
import html
import json
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from hornero.redact import redact

CODE_SUFFIXES = frozenset({
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".c", ".h", ".cpp", ".hpp", ".sh", ".bash", ".sql", ".svelte",
})
DOC_SUFFIXES = frozenset({".md", ".rst", ".txt", ".vtt"})
CONFIG_SUFFIXES = frozenset({".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"})
DEFAULT_SUFFIXES = CODE_SUFFIXES | DOC_SUFFIXES | CONFIG_SUFFIXES

EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules",
    ".tox", "build", "dist", ".eggs", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".uv-cache", "wiki",
})
EXCLUDE_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock",
    "poetry.lock", "Cargo.lock",
})
EXCLUDE_PREFIXES = ("sdd/reports/", ".hornero/knowledge/", ".hornero/runs/")
MAX_FILE_BYTES = 512 * 1024
BODY_MAX_CHARS = 16_000

GRAPH_DIR = Path(".hornero") / "knowledge" / "graph"
DB_NAME = "wiki.db"
HTML_REPORT = "knowledge-graph.html"

_WORD = re.compile(r"\w+", re.UNICODE)
_SUMMARY_MAX = 240


@dataclass(frozen=True)
class GraphHit:
    concept_id: str
    path: str
    title: str
    category: str
    summary: str
    body: str
    score: float
    token_count: int


@dataclass(frozen=True)
class Page:
    concept_id: str
    path: str
    title: str
    category: str
    summary: str
    body: str
    token_count: int
    sha256: str = ""
    mtime: float = 0.0
    imports: tuple[str, ...] = ()


@dataclass
class GraphBuild:
    pages: list[Page] = field(default_factory=list)
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    sources: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    fts_enabled: bool = False
    html_report: Path | None = None
    semantic_entities: int = 0
    semantic_relations: int = 0
    provenance_records: int = 0


def db_path(root: Path) -> Path:
    return root / GRAPH_DIR / DB_NAME


def html_report_path(root: Path) -> Path:
    from hornero import layout

    return layout.reports_dir(root) / HTML_REPORT


def _estimate_tokens(text: str) -> int:
    return 0 if not text else max(1, len(text) // 4)


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_SUMMARY_MAX]
    return ""


def _kind_for_path(rel: str, category: str) -> str:
    name = PurePosixPath(rel).name
    if name.startswith("SPEC-"):
        return "spec"
    if name.startswith(("ADR-", "DR-")):
        return "decision"
    return category


def _category_for(rel: str) -> str:
    suffix = PurePosixPath(rel).suffix.lower()
    if suffix in DOC_SUFFIXES:
        return _kind_for_path(rel, "document")
    if suffix in CONFIG_SUFFIXES:
        return "config"
    return "module"


def is_relevant(rel: str, suffixes: Iterable[str] | None = None) -> bool:
    rel = PurePosixPath(rel).as_posix()
    p = PurePosixPath(rel)
    if not p.parts:
        return False
    if rel in {".gitignore"}:
        return True
    if any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
        return False
    if p.parts[0] == ".hornero" and not rel.startswith(".hornero/processed/"):
        return False
    if any(part in EXCLUDE_DIRS for part in p.parts):
        return False
    if p.name in EXCLUDE_NAMES:
        return False
    keep = frozenset(suffixes) if suffixes else DEFAULT_SUFFIXES
    return p.suffix.lower() in keep


def _git_ls_files(root: Path) -> list[str] | None:
    try:
        proc = subprocess.run(
            [
                "git", "-C", str(root), "ls-files", "-z",
                "--cached", "--others", "--exclude-standard",
            ],
            capture_output=True, check=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]


def _walk_files(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        found.append(rel)
    return found


def discover_files(root: Path, *, use_git: bool = True) -> list[str]:
    root = root.resolve()
    rels = _git_ls_files(root) if use_git else None
    if rels is None:
        rels = _walk_files(root)
    return sorted({rel for rel in rels if is_relevant(rel)})


def source_files(root: Path) -> list[Path]:
    return [root / rel for rel in discover_files(root)]


def _python_outline(text: str) -> tuple[str, list[str], list[str]]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return "", [], []
    summary = _first_line(ast.get_docstring(tree) or "")
    outline: list[str] = []
    imports: list[str] = []

    def _sig(node: ast.AST) -> str:
        args = getattr(node, "args", None)
        names = [a.arg for a in args.args] if args else []
        return f"({', '.join(names)})"

    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            doc = _first_line(ast.get_docstring(node) or "")
            outline.append(f"class {node.name}: {doc}".rstrip(": "))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = _first_line(ast.get_docstring(item) or "")
                    outline.append(f"    def {item.name}{_sig(item)}: {doc}".rstrip(": "))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = _first_line(ast.get_docstring(node) or "")
            outline.append(f"def {node.name}{_sig(node)}: {doc}".rstrip(": "))
    return summary, outline, imports


def _document_summary(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:_SUMMARY_MAX]
    return ""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_file_page(root: Path, rel: str) -> Page | None:
    path = root / rel
    try:
        st = path.stat()
        if st.st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:1024]:
        return None
    text = redact(data.decode("utf-8", "replace"))
    suffix = PurePosixPath(rel).suffix.lower()
    category = _category_for(rel)
    imports: list[str] = []
    sections: list[str] = []

    if suffix in {".py", ".pyi"}:
        summary, outline, imports = _python_outline(text)
        summary = summary or f"Python module {rel}"
        if outline:
            sections.append("## API outline\n" + "\n".join(outline))
    elif suffix in DOC_SUFFIXES:
        summary = _document_summary(text) or rel
    else:
        summary = _first_line(text) or rel

    body_head = text[:BODY_MAX_CHARS]
    sections.append(
        "## Content" + (" (truncated)" if len(text) > BODY_MAX_CHARS else "")
        + "\n" + body_head
    )
    body = f"# {rel}\n\n" + "\n\n".join(sections)
    return Page(
        concept_id=f"file:{rel}",
        path=rel,
        title=rel,
        category=category,
        summary=summary,
        body=body,
        token_count=_estimate_tokens(body),
        sha256=_sha256_bytes(data),
        mtime=st.st_mtime,
        imports=tuple(imports),
    )


def _dir_id(rel: str) -> str:
    return f"dir:{rel or '.'}"


def _module_index(paths: Iterable[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for rel in paths:
        p = PurePosixPath(rel)
        if p.suffix not in {".py", ".pyi"}:
            continue
        parts = list(p.parts)
        if "src" in parts:
            parts = parts[parts.index("src") + 1:]
        if not parts:
            continue
        parts[-1] = PurePosixPath(parts[-1]).stem
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            index.setdefault(".".join(parts), rel)
    return index


def _dir_pages(files: list[Page]) -> tuple[list[Page], list[tuple[str, str, str]]]:
    children: dict[str, set[tuple[str, str]]] = {}
    summaries = {p.path: p.summary for p in files}
    for page in files:
        p = PurePosixPath(page.path)
        parent = "" if p.parent.as_posix() == "." else p.parent.as_posix()
        children.setdefault(parent, set()).add(("file", page.path))
        current = parent
        while current:
            up = PurePosixPath(current).parent.as_posix()
            up = "" if up == "." else up
            children.setdefault(up, set()).add(("dir", current))
            current = up

    pages: list[Page] = []
    edges: list[tuple[str, str, str]] = []
    for rel, kids in sorted(children.items()):
        lines: list[str] = []
        for kind, child in sorted(kids):
            cid = f"file:{child}" if kind == "file" else _dir_id(child)
            edges.append((_dir_id(rel), cid, "contains"))
            label = summaries.get(child, "directory")
            lines.append(f"- [{cid}] {PurePosixPath(child).name} - {label}")
        title = rel or "."
        body = f"# Directory {title}\n\n" + "\n".join(lines)
        pages.append(Page(
            concept_id=_dir_id(rel),
            path=rel,
            title=f"{title}/",
            category="overview",
            summary=f"Directory overview of {title} ({len(kids)} entries)",
            body=body,
            token_count=_estimate_tokens(body),
        ))
    return pages, edges


def _import_edges(files: list[Page], all_paths: Iterable[str]) -> list[tuple[str, str, str]]:
    index = _module_index(all_paths)
    edges: set[tuple[str, str, str]] = set()
    for page in files:
        for module in page.imports:
            parts = module.split(".")
            target = None
            for depth in range(len(parts), 0, -1):
                target = index.get(".".join(parts[:depth]))
                if target:
                    break
            if target and target != page.path:
                edges.add((page.concept_id, f"file:{target}", "references"))
    return sorted(edges)


def _structural_projection(root: Path) -> tuple[list[Page], list[tuple[str, str, str]]]:
    """Project the optional structural JSON into graph pages and edges."""
    from hornero.memory.structural import load_index

    index = load_index(root)
    if index is None:
        return [], []
    pages: list[Page] = []
    for item in index.get("files", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        digest = str(item.get("sha256", ""))
        for symbol in item.get("symbols", []):
            if not isinstance(symbol, dict) or not symbol.get("id"):
                continue
            qualified = str(symbol.get("qualified") or symbol.get("name") or "symbol")
            kind = str(symbol.get("kind") or "symbol")
            line = int(symbol.get("line") or 1)
            summary = f"{kind} {qualified} defined at {path}:L{line}"
            body = (
                f"# {qualified}\n\n- Kind: {kind}\n- Source: {path}:L{line}\n"
                f"- Analyzer: {item.get('analyzer', 'unknown')}\n"
            )
            pages.append(Page(
                concept_id=str(symbol["id"]), path=path,
                title=f"{path}#{qualified}", category="symbol",
                summary=summary, body=body, token_count=_estimate_tokens(body),
                sha256=digest,
            ))
    known = {page.concept_id for page in pages}
    known.update(
        f"file:{item.get('path')}" for item in index.get("files", [])
        if isinstance(item, dict) and item.get("path")
    )
    edges = [
        (str(edge[0]), str(edge[1]), str(edge[2]))
        for edge in index.get("edges", [])
        if isinstance(edge, list) and len(edge) == 3
        and str(edge[0]) in known and str(edge[1]) in known
    ]
    return sorted(pages, key=lambda page: page.concept_id), sorted(set(edges))


def scan(root: Path) -> GraphBuild:
    rels = discover_files(root)
    build = GraphBuild(sources=[root / rel for rel in rels])
    file_pages: list[Page] = []
    for rel in rels:
        page = build_file_page(root, rel)
        if page is None:
            build.skipped.append(rel)
        else:
            file_pages.append(page)
    dir_pages, dir_edges = _dir_pages(file_pages)
    structural_pages, structural_edges = _structural_projection(root)
    build.pages = [*file_pages, *dir_pages, *structural_pages]
    build.edges = sorted({
        *dir_edges, *_import_edges(file_pages, rels), *structural_edges,
    })
    return build


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def build_graph(root: Path) -> GraphBuild:
    root = root.resolve()
    graph_dir = root / GRAPH_DIR
    graph_dir.mkdir(parents=True, exist_ok=True)
    tmp = graph_dir / f"{DB_NAME}.tmp"
    if tmp.exists():
        tmp.unlink()

    build = scan(root)
    conn = _connect(tmp)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode = DELETE;
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE pages (
                concept_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                body TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                mtime REAL NOT NULL
            );
            CREATE INDEX idx_pages_category ON pages(category);
            CREATE TABLE edges (
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                rel TEXT NOT NULL,
                PRIMARY KEY (src, dst, rel)
            );
            CREATE INDEX idx_edges_src ON edges(src, rel);
            CREATE INDEX idx_edges_dst ON edges(dst, rel);
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                properties_json TEXT NOT NULL
            );
            CREATE INDEX idx_entities_kind ON entities(kind);
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                rel TEXT NOT NULL,
                evidence TEXT NOT NULL
            );
            CREATE INDEX idx_relations_src ON relations(src, rel);
            CREATE INDEX idx_relations_dst ON relations(dst, rel);
            CREATE TABLE provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id TEXT NOT NULL,
                subject_kind TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                origin TEXT NOT NULL,
                generator TEXT NOT NULL,
                confidence REAL NOT NULL,
                locator TEXT NOT NULL,
                UNIQUE(subject_id, source_path, source_hash)
            );
            CREATE INDEX idx_provenance_subject ON provenance(subject_id);
            """
        )
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE pages_fts USING fts5("
                "concept_id UNINDEXED, title, summary, body, tokenize='unicode61')"
            )
            build.fts_enabled = True
        except sqlite3.OperationalError:
            build.fts_enabled = False
        conn.executemany(
            "INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    p.concept_id, p.path, p.title, p.category, p.summary,
                    p.body, p.token_count, p.sha256, p.mtime,
                )
                for p in build.pages
            ],
        )
        if build.fts_enabled:
            conn.executemany(
                "INSERT INTO pages_fts (concept_id, title, summary, body) VALUES (?,?,?,?)",
                [(p.concept_id, p.title, p.summary, p.body) for p in build.pages],
            )
        conn.executemany("INSERT OR IGNORE INTO edges VALUES (?,?,?)", build.edges)
        from hornero.memory.semantic import derive

        semantic = derive(root, build.pages)
        conn.executemany(
            "INSERT INTO entities VALUES (?,?,?,?,?)",
            [
                (
                    item.entity_id, item.kind, item.title, item.summary,
                    json.dumps(item.properties, sort_keys=True, ensure_ascii=False),
                )
                for item in semantic.entities
            ],
        )
        conn.executemany(
            "INSERT INTO relations VALUES (?,?,?,?,?)",
            [
                (item.relation_id, item.src, item.dst, item.rel, item.evidence)
                for item in semantic.relations
            ],
        )
        conn.executemany(
            "INSERT INTO provenance "
            "(subject_id, subject_kind, source_path, source_hash, origin, "
            "generator, confidence, locator) VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    item.subject_id, item.subject_kind, item.source_path,
                    item.source_hash, item.origin, item.generator,
                    item.confidence, item.locator,
                )
                for item in semantic.provenance
            ],
        )
        build.semantic_entities = len(semantic.entities)
        build.semantic_relations = len(semantic.relations)
        build.provenance_records = len(semantic.provenance)
        conn.executemany(
            "INSERT INTO meta VALUES (?,?)",
            [
                ("schema", "2"),
                ("fts", "1" if build.fts_enabled else "0"),
                ("pages", str(len(build.pages))),
                ("edges", str(len(build.edges))),
                ("sources", str(len(build.sources))),
                ("semantic_entities", str(build.semantic_entities)),
                ("semantic_relations", str(build.semantic_relations)),
                ("provenance", str(build.provenance_records)),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    final = db_path(root)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(final) + suffix)
        if p.exists():
            p.unlink()
    shutil.move(str(tmp), final)
    build.html_report = write_graph_html(root)
    return build


def _match_expr(query: str) -> str:
    tokens = _WORD.findall(query)
    return " OR ".join(f'"{token}"' for token in tokens)


def _row_to_hit(row: sqlite3.Row, score: float) -> GraphHit:
    return GraphHit(
        concept_id=str(row["concept_id"]),
        path=str(row["path"]),
        title=str(row["title"]),
        category=str(row["category"]),
        summary=str(row["summary"]),
        body=str(row["body"]),
        token_count=int(row["token_count"]),
        score=score,
    )


def search(root: Path, query: str, *, limit: int = 5, category: str | None = None) -> list[GraphHit]:
    path = db_path(root)
    if not path.is_file() or not query.strip():
        return []
    try:
        conn = _connect(path)
    except sqlite3.DatabaseError:
        return []
    try:
        fts = conn.execute("SELECT value FROM meta WHERE key='fts'").fetchone()
        has_fts = bool(fts and fts["value"] == "1")
        args: list[object] = []
        cat_filter = ""
        if category:
            cat_filter = " AND p.category = ?"
        if has_fts:
            expr = _match_expr(query)
            if not expr:
                return []
            args = [expr]
            if category:
                args.append(category)
            args.append(limit)
            rows = conn.execute(
                "SELECT p.*, bm25(pages_fts) AS rank FROM pages_fts "
                "JOIN pages p ON p.concept_id = pages_fts.concept_id "
                f"WHERE pages_fts MATCH ?{cat_filter} ORDER BY rank LIMIT ?",
                args,
            ).fetchall()
            return [_row_to_hit(row, 1.0 / (1.0 + abs(float(row["rank"])))) for row in rows]

        terms = [t.lower() for t in _WORD.findall(query)]
        if not terms:
            return []
        rows = conn.execute(
            "SELECT * FROM pages" + (" WHERE category = ?" if category else ""),
            [category] if category else [],
        ).fetchall()
        hits: list[GraphHit] = []
        for row in rows:
            haystack = " ".join([row["title"], row["summary"], row["body"]]).lower()
            score = sum(1 for term in terms if term in haystack) / len(terms)
            if score:
                hits.append(_row_to_hit(row, score))
        hits.sort(key=lambda h: (-h.score, h.path, h.concept_id))
        return hits[:limit]
    except sqlite3.DatabaseError:
        return []
    finally:
        conn.close()


def get_page(root: Path, concept_id: str) -> GraphHit | None:
    path = db_path(root)
    if not path.is_file():
        return None
    try:
        conn = _connect(path)
    except sqlite3.DatabaseError:
        return None
    try:
        row = conn.execute("SELECT * FROM pages WHERE concept_id = ?", (concept_id,)).fetchone()
        return _row_to_hit(row, 1.0) if row else None
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()


def related(root: Path, concept_id: str, *, rel: str | None = None, direction: str = "both") -> list[dict[str, str]]:
    path = db_path(root)
    if not path.is_file():
        return []
    try:
        conn = _connect(path)
    except sqlite3.DatabaseError:
        return []
    try:
        rows: list[sqlite3.Row] = []
        if direction in ("out", "both"):
            rows.extend(conn.execute(
                "SELECT 'out' AS direction, e.rel, p.* FROM edges e "
                "JOIN pages p ON p.concept_id = e.dst "
                "WHERE e.src = ?" + (" AND e.rel = ?" if rel else ""),
                (concept_id, rel) if rel else (concept_id,),
            ).fetchall())
        if direction in ("in", "both"):
            rows.extend(conn.execute(
                "SELECT 'in' AS direction, e.rel, p.* FROM edges e "
                "JOIN pages p ON p.concept_id = e.src "
                "WHERE e.dst = ?" + (" AND e.rel = ?" if rel else ""),
                (concept_id, rel) if rel else (concept_id,),
            ).fetchall())
        return [
            {
                "direction": str(row["direction"]),
                "rel": str(row["rel"]),
                "concept_id": str(row["concept_id"]),
                "path": str(row["path"]),
                "title": str(row["title"]),
                "category": str(row["category"]),
                "summary": str(row["summary"]),
            }
            for row in sorted(rows, key=lambda r: (r["direction"], r["rel"], r["concept_id"]))
        ]
    except sqlite3.DatabaseError:
        return []
    finally:
        conn.close()


def get_entity(root: Path, entity_id: str) -> dict[str, object] | None:
    path = db_path(root)
    if not path.is_file():
        return None
    try:
        conn = _connect(path)
        try:
            row = conn.execute(
                "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["properties"] = json.loads(result.pop("properties_json"))
            result["provenance"] = [
                dict(item) for item in conn.execute(
                    "SELECT source_path, source_hash, origin, generator, "
                    "confidence, locator FROM provenance WHERE subject_id = ? "
                    "ORDER BY source_path, source_hash",
                    (entity_id,),
                )
            ]
            return result
        finally:
            conn.close()
    except (json.JSONDecodeError, sqlite3.DatabaseError):
        return None


def semantic_related(
    root: Path, entity_id: str, *, rel: str | None = None,
    direction: str = "both",
) -> list[dict[str, object]]:
    path = db_path(root)
    if not path.is_file():
        return []
    try:
        conn = _connect(path)
        try:
            rows: list[sqlite3.Row] = []
            if direction in ("out", "both"):
                rows.extend(conn.execute(
                    "SELECT 'out' direction, r.relation_id, r.rel, r.evidence, "
                    "e.* FROM relations r JOIN entities e ON e.entity_id = r.dst "
                    "WHERE r.src = ?" + (" AND r.rel = ?" if rel else ""),
                    (entity_id, rel) if rel else (entity_id,),
                ))
            if direction in ("in", "both"):
                rows.extend(conn.execute(
                    "SELECT 'in' direction, r.relation_id, r.rel, r.evidence, "
                    "e.* FROM relations r JOIN entities e ON e.entity_id = r.src "
                    "WHERE r.dst = ?" + (" AND r.rel = ?" if rel else ""),
                    (entity_id, rel) if rel else (entity_id,),
                ))
            return [
                {
                    "direction": row["direction"],
                    "relation_id": row["relation_id"],
                    "rel": row["rel"],
                    "evidence": row["evidence"],
                    "entity_id": row["entity_id"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "properties": json.loads(row["properties_json"]),
                }
                for row in sorted(
                    rows, key=lambda item: (
                        item["direction"], item["rel"], item["entity_id"]
                    )
                )
            ]
        finally:
            conn.close()
    except (json.JSONDecodeError, sqlite3.DatabaseError):
        return []


def stats(root: Path) -> dict[str, object]:
    path = db_path(root)
    if not path.is_file():
        return {"built": False}
    try:
        conn = _connect(path)
    except sqlite3.DatabaseError:
        return {"built": False, "corrupt": True, "path": str(path)}
    try:
        categories = {
            str(r["category"]): int(r["n"])
            for r in conn.execute(
                "SELECT category, COUNT(*) n FROM pages GROUP BY category ORDER BY category"
            )
        }
        meta = {
            str(r["key"]): str(r["value"])
            for r in conn.execute("SELECT key, value FROM meta ORDER BY key")
        }
        return {
            "built": True,
            "path": str(path),
            "pages": int(meta.get("pages", 0)),
            "edges": int(meta.get("edges", 0)),
            "sources": int(meta.get("sources", 0)),
            "fts": meta.get("fts") == "1",
            "categories": categories,
            "semantic_entities": int(meta.get("semantic_entities", 0)),
            "semantic_relations": int(meta.get("semantic_relations", 0)),
            "provenance": int(meta.get("provenance", 0)),
        }
    except sqlite3.DatabaseError:
        return {"built": False, "corrupt": True, "path": str(path)}
    finally:
        conn.close()


def pack_hits(hits: Iterable[GraphHit], *, budget_tokens: int = 1200) -> tuple[str, int, int]:
    lines: list[str] = []
    used = 0
    total = 0
    seen: set[str] = set()
    for hit in hits:
        total += 1
        if hit.concept_id in seen:
            continue
        seen.add(hit.concept_id)
        lead = " ".join((hit.summary or hit.body[:240]).split())
        line = (
            f"- [{hit.concept_id}] {hit.title} - {lead} "
            f"(score={hit.score:.2f}, ~{hit.token_count}tok)"
        )
        cost = _estimate_tokens(line)
        if lines and used + cost > budget_tokens:
            break
        lines.append(line)
        used += cost
    return "\n".join(lines), used, total


def write_graph_html(root: Path) -> Path:
    from hornero.redact import redact
    from hornero.reports import explorer

    report = html_report_path(root)
    report.parent.mkdir(parents=True, exist_ok=True)
    st = stats(root)
    rows: list[str] = []
    edge_rows: list[str] = []
    entity_rows: list[str] = []
    relation_rows: list[str] = []
    requirement_rows: list[str] = []
    dependency_rows: list[str] = []
    dashboard_nodes: list[dict[str, object]] = []
    dashboard_edges: list[dict[str, str]] = []
    if st.get("built"):
        conn = _connect(db_path(root))
        try:
            pages = conn.execute(
                "SELECT concept_id, title, category, summary, token_count FROM pages "
                "ORDER BY category, title LIMIT 200"
            ).fetchall()
            edges = conn.execute(
                "SELECT rel, COUNT(*) n FROM edges GROUP BY rel ORDER BY rel"
            ).fetchall()
            entity_kinds = conn.execute(
                "SELECT kind, COUNT(*) n FROM entities GROUP BY kind ORDER BY kind"
            ).fetchall()
            relations = conn.execute(
                "SELECT rel, COUNT(*) n FROM relations GROUP BY rel ORDER BY rel"
            ).fetchall()
            requirements = conn.execute(
                "SELECT entity_id, title, summary, properties_json FROM entities "
                "WHERE kind='requirement' ORDER BY entity_id"
            ).fetchall()
            dependencies = conn.execute(
                "SELECT src, dst FROM relations WHERE rel='depends_on' "
                "ORDER BY src, dst"
            ).fetchall()
            page_nodes = conn.execute(
                "SELECT concept_id, path, title, category, summary FROM pages "
                "ORDER BY category, concept_id LIMIT 500"
            ).fetchall()
            semantic_nodes = conn.execute(
                "SELECT entity_id, kind, title, summary, properties_json FROM entities "
                "ORDER BY kind, entity_id LIMIT 500"
            ).fetchall()
            page_links = conn.execute(
                "SELECT src, dst, rel FROM edges ORDER BY rel, src, dst LIMIT 1500"
            ).fetchall()
            semantic_links = conn.execute(
                "SELECT src, dst, rel FROM relations ORDER BY rel, src, dst LIMIT 1500"
            ).fetchall()
        finally:
            conn.close()
        for row in pages:
            rows.append(
                "<tr>"
                f"<td><code>{html.escape(row['concept_id'])}</code></td>"
                f"<td>{html.escape(row['category'])}</td>"
                f"<td>{html.escape(row['summary'])}</td>"
                f"<td>{int(row['token_count'])}</td>"
                "</tr>"
            )
        for row in edges:
            edge_rows.append(
                f"<tr><td>{html.escape(row['rel'])}</td><td>{int(row['n'])}</td></tr>"
            )
        for row in entity_kinds:
            entity_rows.append(
                f"<tr><td>{html.escape(row['kind'])}</td><td>{int(row['n'])}</td></tr>"
            )
        for row in relations:
            relation_rows.append(
                f"<tr><td>{html.escape(row['rel'])}</td><td>{int(row['n'])}</td></tr>"
            )
        for row in requirements:
            try:
                properties = json.loads(row["properties_json"])
            except (json.JSONDecodeError, TypeError):
                properties = {}
            status = properties.get("status", "") if isinstance(properties, dict) else ""
            requirement_rows.append(
                "<tr>"
                f"<td><code>{html.escape(row['entity_id'])}</code></td>"
                f"<td>{html.escape(str(status))}</td>"
                f"<td>{html.escape(row['title'])}</td>"
                f"<td>{html.escape(row['summary'])}</td>"
                "</tr>"
            )
        for row in dependencies:
            dependency_rows.append(
                "<tr>"
                f"<td><code>{html.escape(row['src'])}</code></td>"
                f"<td><code>{html.escape(row['dst'])}</code></td>"
                "</tr>"
            )
        node_map: dict[str, dict[str, object]] = {}
        for row in page_nodes:
            node_map[str(row["concept_id"])] = {
                "id": str(row["concept_id"]), "title": str(row["title"]),
                "kind": "symbol" if str(row["concept_id"]).startswith("symbol:") else str(row["category"]),
                "group": str(row["category"]), "summary": str(row["summary"]),
                "source": str(row["path"]),
            }
        for row in semantic_nodes:
            try:
                properties = json.loads(row["properties_json"])
            except (json.JSONDecodeError, TypeError):
                properties = {}
            entity_id = str(row["entity_id"])
            source = str(properties.get("path", "")) if isinstance(properties, dict) else ""
            node_map[entity_id] = {
                "id": entity_id, "title": str(row["title"]),
                "kind": str(row["kind"]), "group": str(row["kind"]),
                "summary": str(row["summary"]), "source": source,
            }
        dashboard_nodes = [node_map[key] for key in sorted(node_map)]
        known = set(node_map)
        dashboard_edges = [
            {"source": str(row["src"]), "target": str(row["dst"]), "rel": str(row["rel"])}
            for row in [*page_links, *semantic_links]
            if str(row["src"]) in known and str(row["dst"]) in known
        ]
    def _as_int(value: object) -> int:
        return value if isinstance(value, int) else 0

    pages_n = _as_int(st.get("pages", 0))
    edges_n = _as_int(st.get("edges", 0))
    sources_n = _as_int(st.get("sources", 0))
    entities_n = _as_int(st.get("semantic_entities", 0))
    relations_n = _as_int(st.get("semantic_relations", 0))
    provenance_n = _as_int(st.get("provenance", 0))
    cats_obj = st.get("categories", {})
    cats = cats_obj if isinstance(cats_obj, dict) else {}
    body = (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Hornero Knowledge Graph</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:72rem;margin:2rem auto;"
        "padding:0 1rem;line-height:1.45;color:#1a1a1a}h1{border-bottom:2px solid #b45309;"
        "padding-bottom:.3rem}table{border-collapse:collapse;width:100%;margin:1rem 0}"
        "th,td{border:1px solid #d4d4d4;padding:.4rem .6rem;text-align:left;vertical-align:top}"
        "th{background:#fef3c7}code{background:#f5f5f5;padding:.1rem .3rem;border-radius:3px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.75rem}"
        ".metric{border:1px solid #d4d4d4;padding:.75rem}.metric b{display:block;font-size:1.5rem}"
        + explorer.CSS + "</style>"
        + "</head><body><h1>Hornero Knowledge Graph</h1>"
        "<div class=\"grid\">"
        f"<div class=\"metric\"><b>{pages_n}</b>pages</div>"
        f"<div class=\"metric\"><b>{edges_n}</b>edges</div>"
        f"<div class=\"metric\"><b>{sources_n}</b>sources</div>"
        f"<div class=\"metric\"><b>{entities_n}</b>semantic entities</div>"
        f"<div class=\"metric\"><b>{relations_n}</b>semantic relations</div>"
        f"<div class=\"metric\"><b>{provenance_n}</b>provenance records</div>"
        f"<div class=\"metric\"><b>{'yes' if st.get('fts') else 'no'}</b>FTS5</div>"
        "</div>"
        + explorer.section(dashboard_nodes, dashboard_edges)
        + "<h2>Categories</h2><table><tr><th>Category</th><th>Pages</th></tr>"
        + "".join(
            f"<tr><td>{html.escape(str(k))}</td><td>{_as_int(v)}</td></tr>"
            for k, v in sorted(cats.items())
        )
        + "</table><h2>Edges</h2><table><tr><th>Relation</th><th>Count</th></tr>"
        + "".join(edge_rows)
        + "</table><h2>Semantic Entities</h2><table><tr><th>Kind</th><th>Count</th></tr>"
        + "".join(entity_rows)
        + "</table><h2>Semantic Relations</h2><table><tr><th>Relation</th><th>Count</th></tr>"
        + "".join(relation_rows)
        + "</table><h2>Requirements</h2><table><tr><th>ID</th><th>Status</th>"
        "<th>Title</th><th>Summary</th></tr>"
        + "".join(requirement_rows)
        + "</table><h2>Requirement Dependencies</h2><table><tr><th>Requirement</th>"
        "<th>Depends on</th></tr>"
        + "".join(dependency_rows)
        + "</table><h2>Page Sample</h2><table><tr><th>ID</th><th>Category</th>"
        "<th>Summary</th><th>Tokens</th></tr>"
        + "".join(rows)
        + "</table><footer>Generated by hornero reindex from the local repository. "
        "No LLM, network, or external service is used.</footer></body></html>\n"
    )
    report.write_text(redact(body), encoding="utf-8")
    return report
