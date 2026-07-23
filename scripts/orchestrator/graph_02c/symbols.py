"""Deterministic Tree-sitter symbol index for graph-based 02c (speca#157 Step 2).

Walks a target client's source tree and extracts *definitions* (functions,
methods, types, classes) with their file + line range, using Tree-sitter — the
same polyglot parser SPECA already relies on via MCP, here driven directly in
Python so 02c can resolve code locations deterministically (no LLM, no MCP
agent loop). Building the index is O(source) and done once per client/commit;
all properties then resolve against it.

Grammar sourcing: ``tree_sitter_language_pack`` for most languages, with
dedicated grammar packages (e.g. ``tree_sitter_c_sharp``) where the pack does
not bundle one. Languages without an available grammar are skipped (logged),
never crash the build.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# file extension -> (language pack name, definition node types, name child type)
_LANG = {
    ".cs": ("c_sharp", {"class_declaration", "interface_declaration", "struct_declaration",
                         "method_declaration", "constructor_declaration", "property_declaration"}),
    ".go": ("go", {"function_declaration", "method_declaration", "type_declaration"}),
    ".rs": ("rust", {"function_item", "struct_item", "enum_item", "trait_item", "impl_item"}),
    ".java": ("java", {"class_declaration", "interface_declaration", "method_declaration",
                       "record_declaration", "enum_declaration"}),
    ".ts": ("typescript", {"function_declaration", "method_definition", "class_declaration",
                           "interface_declaration"}),
    ".js": ("javascript", {"function_declaration", "method_definition", "class_declaration"}),
    # tree-sitter-nim models every proc/func/method/template/iterator/converter
    # as a single `routine` node (name in a `symbol` child); types are `typeDef`.
    ".nim": ("nim", {"routine", "typeDef"}),
    ".py": ("python", {"function_definition", "class_definition"}),
}

_SKIP_DIRS = {".git", "node_modules", "target", "bin", "obj", "vendor", "testdata",
              "test", "tests", "dist", "build", ".venv", "__pycache__"}


def norm(name: str) -> str:
    """Convention-insensitive key: last dotted component, lowercased, with
    separators dropped. Collapses pyspec snake_case (``process_attestation``,
    the property `covers`) onto client camelCase (Go ``ProcessAttestation``, TS
    ``processAttestation``) so a seed matches regardless of the client's style.
    """
    tail = name.strip().replace(" ", "").split(".")[-1]
    return tail.replace("_", "").replace("-", "").lower()


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    file: str          # repo-relative, posix
    line_start: int    # 1-based
    line_end: int


@dataclass
class SymbolIndex:
    root: str
    symbols: list[Symbol] = field(default_factory=list)
    by_name: dict[str, list[Symbol]] = field(default_factory=dict)
    skipped_langs: set[str] = field(default_factory=set)

    def add(self, s: Symbol) -> None:
        self.symbols.append(s)
        self.by_name.setdefault(norm(s.name), []).append(s)

    def lookup(self, name: str) -> list[Symbol]:
        return self.by_name.get(norm(name), [])


def _get_parser(lang: str):
    """Parser for a language pack name, with dedicated-package fallbacks."""
    try:
        from tree_sitter_language_pack import get_parser
        return get_parser(lang)
    except Exception:
        pass
    # dedicated grammar fallbacks (the pack doesn't bundle every language)
    import tree_sitter as ts
    mod = {"c_sharp": "tree_sitter_c_sharp"}.get(lang)
    if not mod:
        raise KeyError(lang)
    grammar = __import__(mod)
    return ts.Parser(ts.Language(grammar.language()))


def _name_of(node) -> str | None:
    """The name of a definition node.

    Tree-sitter grammars expose a ``name`` field (``type`` for some Rust items);
    use it — the first bare ``identifier`` child is often the RETURN TYPE, not
    the name (e.g. C# ``public AcceptTxResult Accept(...)``), which would index
    the wrong symbol.
    """
    def _from(n):
        # a qualified / explicit-interface name: take the trailing identifier
        ident = None
        for c in [n, *n.children]:
            if c.type in ("identifier", "type_identifier", "field_identifier", "ident"):
                ident = c
        return (ident or n).text.decode("utf-8", "replace")

    for field in ("name", "type"):
        n = node.child_by_field_name(field)
        if n is not None:
            return _from(n)
    # wrapper nodes carry the name on a nested spec (e.g. Go type_declaration ->
    # type_spec.name); look one level down for a name field.
    for c in node.children:
        n = c.child_by_field_name("name")
        if n is not None:
            return _from(n)
    # Nim: `routine`/`typeDef` name lives in a `symbol` child wrapping an `ident`
    # (the grammar exposes no `name` field). Take the first such symbol's ident.
    for c in node.children:
        if c.type == "symbol":
            for gc in [c, *c.children]:
                if gc.type == "ident":
                    return gc.text.decode("utf-8", "replace")
    # last-resort heuristic: the trailing identifier child
    idents = [c for c in node.children
              if c.type in ("identifier", "type_identifier", "ident")]
    return idents[-1].text.decode("utf-8", "replace") if idents else None


def _extract_file(path: Path, rel: str, lang: str, defn_types: set[str],
                  index: SymbolIndex) -> None:
    try:
        parser = _get_parser(lang)
    except Exception:
        index.skipped_langs.add(lang)
        return
    try:
        src = path.read_bytes()
        tree = parser.parse(src)
    except Exception:
        return

    def walk(node):
        if node.type in defn_types:
            name = _name_of(node)
            if name:
                index.add(Symbol(
                    name=name, kind=node.type, file=rel,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                ))
        for c in node.children:
            walk(c)

    walk(tree.root_node)


def build_index(root: str | Path, max_files: int | None = None) -> SymbolIndex:
    """Build a symbol index for a source tree. Deterministic (sorted walk)."""
    root = Path(root)
    index = SymbolIndex(root=str(root))
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            ext = Path(fn).suffix
            spec = _LANG.get(ext)
            if not spec:
                continue
            lang, defn_types = spec
            p = Path(dirpath) / fn
            rel = p.relative_to(root).as_posix()
            _extract_file(p, rel, lang, defn_types, index)
            n += 1
            if max_files and n >= max_files:
                return index
    return index
