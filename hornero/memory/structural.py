"""Deterministic, incremental source-structure index.

The index deliberately has two parser tiers.  ``tree_sitter_language_pack``
is used when it is already installed; stdlib/native analyzers remain a fully
tested fallback so ``hornero reindex`` never downloads a grammar or requires
the network.  Both tiers emit the same small fact schema.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

INDEX_PATH = Path(".hornero") / "knowledge" / "structural" / "index.json"
SCHEMA = 1

LANGUAGES = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".svelte": "svelte", ".sql": "sql",
}

_JS_IMPORT = re.compile(
    r"(?:import\s+(?:[^;]*?\s+from\s+)?|require\s*\()"
    r"[\"']([^\"']+)[\"']"
)
_JS_FUNCTION = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|"
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
_JS_CLASS = re.compile(
    r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+([A-Za-z_$][\w$.]*))?"
)
_JS_CALL = re.compile(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(")
_SQL_DEF = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(TABLE|VIEW|FUNCTION|PROCEDURE)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([\w.\"`\[\]]+)", re.IGNORECASE,
)
_SQL_REF = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([\w.\"`\[\]]+)", re.IGNORECASE)


@dataclass(frozen=True)
class IndexMetrics:
    analyzed: int
    reused: int
    removed: int


def index_path(root: Path) -> Path:
    return root / INDEX_PATH


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _symbol_id(path: str, qualified: str) -> str:
    return f"symbol:{path}#{qualified}"


def _line_col(node: ast.AST) -> tuple[int, int]:
    return int(getattr(node, "lineno", 1)), int(getattr(node, "col_offset", 0))


def _ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _ast_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.facts: list[dict[str, Any]] = []
        self.imports: list[str] = []

    def _source(self) -> str:
        return _symbol_id(self.path, ".".join(self.scope)) if self.scope else f"file:{self.path}"

    def _add_symbol(self, node: ast.AST, name: str, kind: str) -> None:
        qualified = ".".join([*self.scope, name])
        line, column = _line_col(node)
        self.symbols.append({
            "id": _symbol_id(self.path, qualified), "name": name,
            "qualified": qualified, "kind": kind, "line": line,
            "column": column,
        })

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_symbol(node, node.name, "class")
        source = _symbol_id(self.path, ".".join([*self.scope, node.name]))
        for base in node.bases:
            target = _ast_name(base)
            if target:
                line, column = _line_col(base)
                self.facts.append({
                    "kind": "inherits", "source": source, "target": target,
                    "line": line, "column": column,
                })
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        kind = "method" if self.scope else "function"
        self._add_symbol(node, node.name, kind)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Import(self, node: ast.Import) -> None:
        line, column = _line_col(node)
        for alias in node.names:
            self.imports.append(alias.name)
            self.facts.append({
                "kind": "imports", "source": f"file:{self.path}",
                "target": alias.name, "line": line, "column": column,
            })

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        if module:
            self.imports.append(module)
            line, column = _line_col(node)
            self.facts.append({
                "kind": "imports", "source": f"file:{self.path}",
                "target": module, "line": line, "column": column,
            })

    def visit_Call(self, node: ast.Call) -> None:
        target = _ast_name(node.func)
        if target:
            line, column = _line_col(node)
            self.facts.append({
                "kind": "calls", "source": self._source(), "target": target,
                "line": line, "column": column,
            })
        self.generic_visit(node)


def _python(path: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return [], [], []
    visitor = _PythonVisitor(path)
    visitor.visit(tree)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            for item in node.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    line, column = _line_col(item)
                    visitor.facts.append({
                        "kind": "exports", "source": f"file:{path}",
                        "target": item.value, "line": line, "column": column,
                    })
    return visitor.symbols, visitor.facts, sorted(set(visitor.imports))


def _line(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    previous = text.rfind("\n", 0, offset)
    return line, offset if previous < 0 else offset - previous - 1


def _javascript(path: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    symbols: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    imports: list[str] = []
    for match in _JS_IMPORT.finditer(text):
        target = match.group(1)
        imports.append(target)
        line, column = _line(text, match.start())
        facts.append({"kind": "imports", "source": f"file:{path}", "target": target,
                      "line": line, "column": column})
    for match in _JS_CLASS.finditer(text):
        name = match.group(1)
        line, column = _line(text, match.start())
        sid = _symbol_id(path, name)
        symbols.append({"id": sid, "name": name, "qualified": name, "kind": "class",
                        "line": line, "column": column})
        if match.group(2):
            facts.append({"kind": "inherits", "source": sid, "target": match.group(2),
                          "line": line, "column": column})
    for match in _JS_FUNCTION.finditer(text):
        name = match.group(1) or match.group(2)
        line, column = _line(text, match.start())
        symbols.append({"id": _symbol_id(path, name), "name": name, "qualified": name,
                        "kind": "function", "line": line, "column": column})
    keywords = {"if", "for", "while", "switch", "catch", "function", "require"}
    for match in _JS_CALL.finditer(text):
        target = match.group(1)
        if target in keywords:
            continue
        line, column = _line(text, match.start())
        facts.append({"kind": "calls", "source": f"file:{path}", "target": target,
                      "line": line, "column": column})
    for symbol in symbols:
        name = str(symbol["name"])
        if re.search(rf"\bexport\b[^\n;]*\b{re.escape(name)}\b", text):
            facts.append({"kind": "exports", "source": f"file:{path}", "target": name,
                          "line": symbol["line"], "column": symbol["column"]})
    return symbols, facts, sorted(set(imports))


def _sql(path: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    symbols: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    for match in _SQL_DEF.finditer(text):
        kind, name = match.group(1).lower(), match.group(2).strip('"`[]')
        line, column = _line(text, match.start())
        symbols.append({"id": _symbol_id(path, name), "name": name,
                        "qualified": name, "kind": kind, "line": line,
                        "column": column})
    for match in _SQL_REF.finditer(text):
        target = match.group(1).strip('"`[]')
        line, column = _line(text, match.start())
        facts.append({"kind": "references", "source": f"file:{path}", "target": target,
                      "line": line, "column": column})
    return symbols, facts, []


def _tree_sitter_available(language: str) -> bool:
    if language == "python":
        return False  # CPython's AST gives us richer, stable semantic fields.
    try:
        pack = importlib.import_module("tree_sitter_language_pack")
        pack.get_parser(language)
        return True
    except (ImportError, AttributeError, LookupError, TypeError, ValueError):
        return False


def _analyzer(language: str) -> str:
    if language == "python":
        return "python-ast"
    if _tree_sitter_available(language):
        return f"tree-sitter:{language}"
    return f"native:{language}"


def _analyze(path: str, language: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    # The native extractors define the contract.  When Tree-sitter is present
    # it first validates/parses the complete syntax tree, while extraction stays
    # language-stable across optional dependency versions.
    if _tree_sitter_available(language):
        try:
            pack = importlib.import_module("tree_sitter_language_pack")
            pack.get_parser(language).parse(text.encode("utf-8"))
        except (AttributeError, LookupError, TypeError, ValueError):
            pass
    if language == "python":
        return _python(path, text)
    if language in {"javascript", "typescript", "svelte"}:
        return _javascript(path, text)
    return _sql(path, text)


def _module_index(paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for rel in paths:
        p = PurePosixPath(rel)
        if p.suffix.lower() not in {".py", ".pyi"}:
            continue
        parts = list(p.parts)
        if "src" in parts:
            parts = parts[parts.index("src") + 1:]
        parts[-1] = PurePosixPath(parts[-1]).stem
        if parts[-1] == "__init__":
            parts.pop()
        if parts:
            result.setdefault(".".join(parts), rel)
    return result


def _resolve_import(source: str, target: str, paths: set[str], modules: dict[str, str]) -> str | None:
    if target.startswith(".") and PurePosixPath(source).suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".svelte"}:
        base = PurePosixPath(source).parent
        candidate = (base / target).as_posix()
        choices = [candidate, *(candidate + suffix for suffix in (".ts", ".tsx", ".js", ".jsx", ".svelte")),
                   *(f"{candidate}/index{suffix}" for suffix in (".ts", ".js"))]
        return next((item for item in choices if item in paths), None)
    clean = target.lstrip(".")
    pieces = clean.split(".")
    for depth in range(len(pieces), 0, -1):
        found = modules.get(".".join(pieces[:depth]))
        if found:
            return found
    return None


def _edges(files: list[dict[str, Any]]) -> tuple[list[list[str]], dict[str, str]]:
    paths = {str(item["path"]) for item in files}
    modules = _module_index(sorted(paths))
    symbols = [symbol for item in files for symbol in item["symbols"]]
    by_name: dict[str, list[str]] = {}
    for symbol in symbols:
        by_name.setdefault(str(symbol["name"]), []).append(str(symbol["id"]))
    edges: set[tuple[str, str, str]] = set()
    import_map: dict[str, str] = {}
    for item in files:
        path = str(item["path"])
        for symbol in item["symbols"]:
            edges.add((f"file:{path}", str(symbol["id"]), "contains"))
        for target in item["imports"]:
            resolved = _resolve_import(path, str(target), paths, modules)
            if resolved:
                import_map[f"{path}\0{target}"] = resolved
                edges.add((f"file:{path}", f"file:{resolved}", "imports"))
        for fact in item["facts"]:
            kind = str(fact["kind"])
            target_name = str(fact["target"]).split(".")[-1]
            candidates = by_name.get(target_name, [])
            same_file = [candidate for candidate in candidates if candidate.startswith(f"symbol:{path}#")]
            target_id = same_file[0] if len(same_file) == 1 else (candidates[0] if len(candidates) == 1 else None)
            if kind == "exports" and target_id:
                edges.add((f"file:{path}", target_id, "exports"))
            elif kind in {"calls", "inherits", "references"} and target_id:
                edges.add((str(fact["source"]), target_id, kind))
    return [list(edge) for edge in sorted(edges)], dict(sorted(import_map.items()))


def _old_files(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if data.get("schema") != SCHEMA or not isinstance(data.get("files"), list):
        return {}
    return {
        str(item.get("path")): item for item in data["files"]
        if isinstance(item, dict) and item.get("path")
    }


def build_index(root: Path, paths: list[str]) -> tuple[dict[str, Any], IndexMetrics]:
    """Analyze ``paths``, reusing unchanged per-file facts, and persist JSON."""
    destination = index_path(root)
    old = _old_files(destination)
    files: list[dict[str, Any]] = []
    analyzed = reused = 0
    for rel in sorted(set(paths)):
        language = LANGUAGES.get(PurePosixPath(rel).suffix.lower())
        if not language:
            continue
        path = root / rel
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:1024]:
            continue
        digest = _sha(data)
        analyzer = _analyzer(language)
        previous = old.get(rel)
        if previous and previous.get("sha256") == digest and previous.get("analyzer") == analyzer:
            files.append(previous)
            reused += 1
            continue
        symbols, facts, imports = _analyze(rel, language, data.decode("utf-8", "replace"))
        files.append({
            "path": rel, "sha256": digest, "language": language,
            "analyzer": analyzer,
            "symbols": sorted(symbols, key=lambda item: (item["line"], item["column"], item["id"])),
            "facts": sorted(facts, key=lambda item: (
                item["line"], item["column"], item["kind"], item["source"], item["target"]
            )),
            "imports": sorted(set(imports)),
        })
        analyzed += 1
    files.sort(key=lambda item: item["path"])
    edges, import_map = _edges(files)
    payload = {
        "schema": SCHEMA, "files": files, "edges": edges,
        "import_map": import_map,
        "languages": dict(sorted({
            language: sum(1 for item in files if item["language"] == language)
            for language in LANGUAGES.values()
        }.items())),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    removed = len(set(old) - {str(item["path"]) for item in files})
    return payload, IndexMetrics(analyzed, reused, removed)


def load_index(root: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(index_path(root).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if data.get("schema") == SCHEMA else None
