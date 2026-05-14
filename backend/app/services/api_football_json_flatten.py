"""Flatten ricorsivo di JSON API-Football (response) per catalogazione campi diretti."""

from __future__ import annotations

import math
import re
from typing import Any


def _is_finite_number(x: Any) -> bool:
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float):
        return not math.isnan(x) and not math.isinf(x)
    return False


def classify_sample_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "numero"
    if _is_finite_number(value):
        return "numero"
    if isinstance(value, float):
        return "numero"
    if isinstance(value, str):
        if re.fullmatch(r"\d+%", value.strip()):
            return "percentuale"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value.strip()):
            return "data"
        return "stringa"
    return "stringa"


def _escape_path_segment(seg: str) -> str:
    return seg.replace("\\", "\\\\").replace('"', '\\"')


def _is_kv_stat_list(items: list[Any]) -> bool:
    if not items or len(items) > 200:
        return False
    n = min(5, len(items))
    ok = 0
    for it in items[:n]:
        if not isinstance(it, dict):
            return False
        if "type" not in it or "value" not in it:
            return False
        if not isinstance(it.get("type"), (str, int, float, type(None))):
            return False
        ok += 1
    return ok == n


def flatten_json(
    obj: Any,
    *,
    prefix: str = "",
    max_paths: int = 6000,
    _counter: list[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Restituisce lista di {json_path, sample_value, sample_type, examples_count=1}.
    Per liste di statistiche {type, value} aggiunge path `...["Tipo"]` oltre ai path indicizzati.
    """
    acc: list[dict[str, Any]] = []
    c = _counter if _counter is not None else [0]

    def bump() -> bool:
        c[0] += 1
        return c[0] <= max_paths

    def add_leaf(path: str, val: Any) -> None:
        if not bump():
            return
        st = classify_sample_type(val)
        # serializza sample per JSON output
        if isinstance(val, (dict, list)):
            return
        acc.append(
            {
                "json_path": path,
                "sample_value": val,
                "sample_type": st,
                "examples_count": 1,
            },
        )

    def walk(node: Any, pfx: str) -> None:
        if not bump():
            return
        if isinstance(node, dict):
            for k, v in node.items():
                key = str(k)
                seg = f"{pfx}.{key}" if pfx else key
                if isinstance(v, dict):
                    walk(v, seg)
                elif isinstance(v, list):
                    walk_list(v, seg)
                else:
                    add_leaf(seg, v)
        elif isinstance(node, list):
            walk_list(node, pfx)

    def walk_list(items: list[Any], pfx: str) -> None:
        if not bump():
            return
        if _is_kv_stat_list(items):
            for it in items:
                if not isinstance(it, dict):
                    continue
                t_raw = it.get("type")
                val = it.get("value")
                if t_raw is None:
                    continue
                t = str(t_raw).strip()
                if not t:
                    continue
                qp = f'{pfx}["{_escape_path_segment(t)}"]' if pfx else f'["{_escape_path_segment(t)}"]'
                add_leaf(qp, val)
            return
        for i, it in enumerate(items):
            if not bump():
                return
            seg = f"{pfx}[{i}]"
            if isinstance(it, dict):
                walk(it, seg)
            elif isinstance(it, list):
                walk_list(it, seg)
            else:
                add_leaf(seg, it)

    if isinstance(obj, dict):
        walk(obj, prefix)
    elif isinstance(obj, list):
        walk_list(obj, prefix)
    elif prefix and not isinstance(obj, (dict, list)):
        add_leaf(prefix, obj)
    return acc


def merge_flattened_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggrega per json_path: mantiene primo sample, incrementa examples_count."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        jp = str(r["json_path"])
        if jp not in out:
            out[jp] = {
                "json_path": jp,
                "sample_value": r.get("sample_value"),
                "sample_type": r.get("sample_type"),
                "examples_count": int(r.get("examples_count") or 1),
            }
        else:
            out[jp]["examples_count"] = int(out[jp]["examples_count"]) + int(r.get("examples_count") or 1)
    return out


def merge_path_maps(*maps: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for m in maps:
        for jp, row in m.items():
            if jp not in acc:
                acc[jp] = dict(row)
            else:
                acc[jp]["examples_count"] = int(acc[jp].get("examples_count") or 1) + int(
                    row.get("examples_count") or 1,
                )
    return acc


def flatten_response_union(
    body: dict[str, Any],
    *,
    max_list_items: int = 4,
    max_paths_per_item: int = 4000,
) -> list[dict[str, Any]]:
    """
    Appiattisce il campo `response` della body API-Sports.
    Liste: unione dei path sui primi `max_list_items` elementi.
    """
    resp = body.get("response")
    maps: list[dict[str, dict[str, Any]]] = []
    if isinstance(resp, list):
        n = min(max_list_items, len(resp))
        per = max(256, max_paths_per_item // max(1, n))
        for it in resp[:n]:
            if isinstance(it, (dict, list)):
                rows = flatten_json(it, prefix="", max_paths=per)
                maps.append(merge_flattened_counts(rows))
    elif isinstance(resp, dict):
        rows = flatten_json(resp, prefix="", max_paths=max_paths_per_item * 2)
        maps.append(merge_flattened_counts(rows))
    elif resp is not None:
        rows = flatten_json(resp, prefix="", max_paths=max_paths_per_item)
        maps.append(merge_flattened_counts(rows))
    merged = merge_path_maps(*maps) if maps else {}
    return list(merged.values())
