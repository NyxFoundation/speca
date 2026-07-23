"""Deterministic property -> code_scope resolver (speca#157 Step 2).

Given a property and a :class:`SymbolIndex`, resolve the code locations to audit
WITHOUT an LLM. Seeds come from the property's own fields (the same signals the
LLM 02c uses, but applied by rule):

- ``spec_symbol`` — the client function a label maps to (anchor_map's join,
  e.g. ``process_attestation``); the strongest seed.
- ``covers`` / ``covers_hint`` — element/function names the property names.
- identifier-like tokens mined from ``text`` / ``assertion``.

Each seed is looked up in the symbol index. A confidence is attached so the
02c phase can fall back to the LLM only on low-confidence properties (which
guarantees system recall >= the LLM baseline — speca#157):

- ``high``   an exact symbol-name match on a strong seed (spec_symbol/covers),
  or a *unique long-prefix* match (client added a suffix, e.g. prysm
  ``ProcessJustificationAndFinalizationPreCompute``).
- ``medium`` a match only on a mined token, or a partial/substring match.
- ``low``    no symbol match (file-only or nothing) -> fall back to the LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .symbols import Symbol, SymbolIndex, norm as _norm

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# generic words that are not useful symbol seeds
_STOP = {
    "the", "and", "must", "not", "any", "all", "for", "with", "that", "this",
    "code", "path", "value", "check", "audit", "before", "after", "each",
    "every", "into", "from", "when", "which", "should", "field", "fields",
}


@dataclass
class Resolution:
    property_id: str
    code_scope: dict[str, Any]
    confidence: str          # high | medium | low
    matched_seeds: list[str] = field(default_factory=list)


def _seeds(prop: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(strong_seeds, weak_seeds). Strong = spec_symbol/covers; weak = text tokens."""
    strong: list[str] = []
    for key in ("spec_symbol", "covers"):
        v = prop.get(key)
        if isinstance(v, str) and v.strip():
            strong.append(v.strip())
    for v in prop.get("covers_hint", []) or []:
        if isinstance(v, str) and v.strip():
            strong.append(v.strip())
    weak: list[str] = []
    for key in ("text", "assertion"):
        for tok in _IDENT.findall(str(prop.get(key, ""))):
            if tok.lower() not in _STOP and tok not in weak:
                weak.append(tok)
    # de-dup strong, keep order
    seen, strong2 = set(), []
    for s in strong:
        if s.lower() not in seen:
            seen.add(s.lower())
            strong2.append(s)
    return strong2, weak




def _lookup(seed: str, index: SymbolIndex) -> list[Symbol]:
    hits = index.lookup(_norm(seed))
    if hits:
        return hits
    # substring / snake<->camel tolerant: exact normalized already tried; try
    # matching a symbol whose normalized name equals the seed's normalized form
    n = _norm(seed)
    return [s for s in index.symbols if _norm(s.name) == n]


# a strong seed's normalized form must be at least this long before we allow a
# prefix match — shorter seeds prefix-match too many unrelated symbols.
_MIN_PREFIX_LEN = 12
# a spec function may have a small number of client-side variants (fork phases,
# plural naming); audit them all. Above this, the prefix is too ambiguous.
_SIBLING_CAP = 4


def _prefix_lookup(seed: str, index: SymbolIndex) -> list[Symbol]:
    """Long-prefix match for a strong seed (client renamed the spec function).

    Ordered by decreasing precision:

    * the normalized seed is a prefix of exactly ONE symbol name -> that symbol
      (prysm ``ProcessJustificationAndFinalizationPreCompute`` for pyspec
      ``process_justification_and_finalization``);
    * several candidates but the shortest is a prefix of all the others -> the
      shortest is the canonical impl (``…PreCompute`` vs an auto-generated
      ``…PreComputeWrapper``);
    * up to ``_SIBLING_CAP`` sibling variants that all extend the seed -> ALL of
      them, because they are the spec function's client-side variants and an
      audit wants every one (lodestar ``processAttestations`` /
      ``processAttestationPhase0`` / ``processAttestationsAltair`` for pyspec
      ``process_attestation``).

    Otherwise (short seed, or too many divergent candidates) return [] so the
    property falls back to the LLM tail — keeping the deterministic tier precise.
    """
    n = _norm(seed)
    if len(n) < _MIN_PREFIX_LEN:
        return []
    matches = {k: syms for k, syms in index.by_name.items()
               if k != n and k.startswith(n)}
    if not matches:
        return []
    if len(matches) == 1:
        return next(iter(matches.values()))
    shortest = min(matches, key=len)
    if all(k.startswith(shortest) for k in matches):
        return matches[shortest]
    if len(matches) <= _SIBLING_CAP:
        return [s for syms in matches.values() for s in syms]
    return []


def _loc(s: Symbol, role: str = "primary") -> dict[str, Any]:
    # schema.CodeLocation shape: file / symbol / line_range{start,end} / role / note
    note = f"graph-resolved ({s.kind})" if role == "primary" else f"callee of primary ({s.kind})"
    return {
        "file": s.file,
        "symbol": s.name,
        "line_range": {"start": s.line_start, "end": s.line_end},
        "role": role,
        "note": note,
    }


# definition kinds that are *functions/methods* (callees worth auditing) — types,
# classes, enums, config getters etc. are excluded from call-graph expansion.
_FUNC_KINDS = {
    "function_declaration", "method_declaration", "function_item",
    "method_definition", "function_definition", "constructor_declaration",
    "routine", "method", "func",
}
_CALL = re.compile(r"([A-Za-z_]\w{2,})\s*\(")
_CALLEE_CAP = 6
# generic constructors / stdlib-ish methods that carry no audit signal as callees
# (matched on the normalized name — lowercased, separators dropped)
_CALLEE_STOP = {
    "new", "default", "from", "into", "clone", "unwrap", "expect", "tostring",
    "asref", "asmut", "len", "isempty", "get", "set", "push", "insert", "iter",
    "collect", "tovec", "format", "print", "println", "panic", "some", "none",
    "ok", "err", "min", "max", "append", "make", "string", "contains",
}


def _expand_callees(primaries: list[Symbol], index: SymbolIndex,
                    cap: int = _CALLEE_CAP) -> list[Symbol]:
    """1-hop call graph: the in-repo functions a primary calls in its body.

    A property's audit surface rarely ends at one function — lodestar's
    ``processJustificationAndFinalization`` delegates the core logic to
    ``weighJustificationAndFinalization``; prysm's ``ProcessSlashings`` calls
    ``ProportionalSlashingMultiplier`` / ``TotalActiveBalance``. We read each
    primary's body, extract call targets (``name(``), and add those that resolve
    to a *function/method* defined in this client. Same-file callees rank first
    (split-out helpers), then same top-level dir. Bounded by ``cap`` so the map
    stays focused; types/getters are excluded via ``_FUNC_KINDS``.
    """
    root = Path(index.root)
    prim_norm = {_norm(p.name) for p in primaries}
    prim_files = {p.file for p in primaries}
    prim_dirs = {p.file.split("/")[0] for p in primaries}
    scored: dict[tuple, tuple[int, Symbol]] = {}
    for p in primaries:
        try:
            lines = (root / p.file).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        body = "\n".join(lines[p.line_start - 1:p.line_end])
        for target in dict.fromkeys(_CALL.findall(body)):  # unique, order-preserving
            tn = _norm(target)
            if tn in prim_norm or tn in _CALLEE_STOP:
                continue
            for s in index.lookup(target):
                if s.kind not in _FUNC_KINDS:
                    continue
                rank = 0 if s.file in prim_files else 1 if s.file.split("/")[0] in prim_dirs else 2
                key = (s.file, s.line_start, s.name)
                if key not in scored or rank < scored[key][0]:
                    scored[key] = (rank, s)
    ranked = sorted(scored.values(), key=lambda rs: (rs[0], rs[1].file, rs[1].line_start))
    return [s for _, s in ranked[:cap]]


def resolve(prop: dict[str, Any], index: SymbolIndex, max_locations: int = 8,
            expand_callees: bool = True) -> Resolution:
    strong, weak = _seeds(prop)
    matched: list[str] = []
    locs: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    primaries: list[Symbol] = []

    def add(sym: Symbol, role: str = "primary"):
        key = (sym.file, sym.line_start, sym.name)
        if key not in seen:
            seen.add(key)
            locs.append(_loc(sym, role))
            if role == "primary":
                primaries.append(sym)

    for seed in strong:
        hit = _lookup(seed, index) or _prefix_lookup(seed, index)
        if hit:
            matched.append(seed)
            for s in hit[:max_locations]:
                add(s)

    confidence = "high" if matched else "low"

    if not matched:  # fall back to weak (mined) tokens -> medium at best
        for seed in weak:
            hit = index.lookup(_norm(seed))
            if hit:
                matched.append(seed)
                for s in hit[:3]:
                    add(s)
        confidence = "medium" if matched else "low"

    locs = locs[:max_locations]
    # call-graph 1-hop: add the functions the (strong-matched) primaries call, so
    # the code map spans the audit surface, not just the entry function.
    if expand_callees and confidence == "high" and primaries:
        for callee in _expand_callees(primaries, index):
            add(callee, role="callee")

    code_scope = {
        "locations": locs,
        "resolution_status": "resolved" if locs else "not_found",
        "resolution_error": "",
    }
    return Resolution(
        property_id=str(prop.get("property_id", "")),
        code_scope=code_scope,
        confidence=confidence,
        matched_seeds=matched,
    )
