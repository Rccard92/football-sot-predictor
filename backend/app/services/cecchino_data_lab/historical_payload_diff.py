"""Deep diff ricorsivo per payload pre-match (diagnostica gate)."""

from __future__ import annotations

from typing import Any


def deep_diff_payload(
    a: Any,
    b: Any,
    *,
    path: str = "",
) -> dict[str, Any] | None:
    """Restituisce il primo campo divergente con path JSON-like."""
    if type(a) is not type(b):
        return {"path": path or "$", "run_a": a, "run_b": b, "reason": "type_mismatch"}

    if isinstance(a, dict):
        if not isinstance(b, dict):
            return {"path": path or "$", "run_a": type(a).__name__, "run_b": type(b).__name__}
        keys = sorted(set(a.keys()) | set(b.keys()))
        for key in keys:
            sub = f"{path}.{key}" if path else str(key)
            if key not in a:
                return {"path": sub, "run_a": None, "run_b": b[key], "reason": "missing_in_a"}
            if key not in b:
                return {"path": sub, "run_a": a[key], "run_b": None, "reason": "missing_in_b"}
            found = deep_diff_payload(a[key], b[key], path=sub)
            if found:
                return found
        return None

    if isinstance(a, list):
        if not isinstance(b, list):
            return {"path": path or "$", "run_a": "list", "run_b": type(b).__name__}
        if len(a) != len(b):
            return {"path": path or "$", "run_a_len": len(a), "run_b_len": len(b), "reason": "list_len"}
        for i, (av, bv) in enumerate(zip(a, b)):
            found = deep_diff_payload(av, bv, path=f"{path}[{i}]")
            if found:
                return found
        return None

    if a != b:
        return {"path": path or "$", "run_a": a, "run_b": b, "reason": "value_mismatch"}
    return None
