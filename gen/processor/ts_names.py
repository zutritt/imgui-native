"""Helpers for TypeScript-facing identifier names.

Keeps generated declaration parameter names:
- camelCase
- valid identifiers
- safe against JS/TS keywords (e.g. `in` -> `_in`)
- unique within one signature
"""

from __future__ import annotations

import re


_JS_TS_RESERVED = {
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "export", "extends",
    "false", "finally", "for", "function", "if", "import", "in",
    "instanceof", "new", "null", "return", "super", "switch", "this",
    "throw", "true", "try", "typeof", "var", "void", "while", "with",
    "as", "implements", "interface", "let", "package", "private",
    "protected", "public", "static", "yield", "any", "boolean",
    "constructor", "declare", "get", "module", "number", "require",
    "set", "string", "symbol", "type", "from", "of",
}


def to_camel_case(name: str) -> str:
    """Convert snake_case-ish names to camelCase.

    Examples:
      out_h -> outH
      sdl_gl_context -> sdlGlContext
      ID -> iD
    """
    if not name:
        return "arg"

    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name.strip())
    if not cleaned:
        return "arg"

    leading_underscores = ""
    while cleaned.startswith("_"):
        leading_underscores += "_"
        cleaned = cleaned[1:]

    if not cleaned:
        cleaned = "arg"

    parts = [p for p in cleaned.split("_") if p]
    if not parts:
        core = cleaned[0].lower() + cleaned[1:] if cleaned else "arg"
        return leading_underscores + core

    first = parts[0][0].lower() + parts[0][1:] if parts[0] else ""
    rest = "".join(p[:1].upper() + p[1:] for p in parts[1:])
    return leading_underscores + first + rest


def sanitize_ts_identifier(name: str) -> str:
    """Make a declaration-friendly TypeScript identifier from a raw C arg name."""
    ident = to_camel_case(name)

    if not ident:
        ident = "arg"

    if ident[0].isdigit():
        ident = f"_{ident}"

    if ident in _JS_TS_RESERVED:
        ident = f"_{ident}"

    return ident


def make_unique_ts_identifiers(raw_names: list[str]) -> list[str]:
    """Sanitize and deduplicate names while preserving order.

    If multiple names normalize to the same identifier, suffix with a counter:
      value, value -> value, value2
    """
    out: list[str] = []
    seen: dict[str, int] = {}

    for raw in raw_names:
        base = sanitize_ts_identifier(raw)
        count = seen.get(base, 0)
        if count == 0:
            out.append(base)
            seen[base] = 1
            continue

        while True:
            count += 1
            candidate = f"{base}{count}"
            if candidate not in seen:
                out.append(candidate)
                seen[base] = count
                seen[candidate] = 1
                break

    return out
