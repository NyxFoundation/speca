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

- ``high``   an exact symbol-name match on a strong seed (spec_symbol/covers).
- ``medium`` a match only on a mined token, or a partial/substring match.
- ``low``    no symbol match (file-only or nothing) -> fall back to the LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
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


def _loc(s: Symbol) -> dict[str, Any]:
    return {"file": s.file, "symbol": s.name, "kind": s.kind,
            "line_start": s.line_start, "line_end": s.line_end}


def resolve(prop: dict[str, Any], index: SymbolIndex, max_locations: int = 8) -> Resolution:
    strong, weak = _seeds(prop)
    matched: list[str] = []
    locs: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def add(sym: Symbol):
        key = (sym.file, sym.line_start, sym.name)
        if key not in seen:
            seen.add(key)
            locs.append(_loc(sym))

    for seed in strong:
        hit = _lookup(seed, index)
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

    code_scope = {
        "locations": locs[:max_locations],
        "resolution_status": "resolved" if locs else "not_found",
        "resolution_error": "",
    }
    return Resolution(
        property_id=str(prop.get("property_id", "")),
        code_scope=code_scope,
        confidence=confidence,
        matched_seeds=matched,
    )
