"""Validazione pesi manifest v2.1."""

from __future__ import annotations

from app.services.predictions_v21.v21_manifest_definitions import V21MacroAreaSpec, V21_MANIFEST_DEFINITIONS


def validate_v21_manifest(definitions: tuple[V21MacroAreaSpec, ...] | None = None) -> None:
    """Solleva ValueError se macro/micro pesi non rispettano i vincoli."""
    defs = definitions if definitions is not None else V21_MANIFEST_DEFINITIONS
    if not defs:
        raise ValueError("Manifest v2.1 vuoto.")

    macro_sum = sum(m.macro_weight for m in defs)
    if macro_sum != 100:
        raise ValueError(f"Somma pesi macro v2.1 = {macro_sum}, atteso 100.")

    seen_micro_keys: set[str] = set()
    for macro in defs:
        if not macro.key.strip():
            raise ValueError("Macroarea v2.1 con key vuota.")
        if not macro.label.strip():
            raise ValueError(f"Macroarea {macro.key}: label vuota.")

        if macro.is_quality_only:
            for micro in macro.micros:
                if micro.micro_weight is not None:
                    raise ValueError(
                        f"Macro qualità {macro.key}/{micro.key}: micro_weight non ammesso.",
                    )
        else:
            micro_sum = sum(m.micro_weight or 0 for m in macro.micros)
            if micro_sum != 100:
                raise ValueError(
                    f"Macro {macro.key}: somma micro-pesi = {micro_sum}, atteso 100.",
                )

        for micro in macro.micros:
            if not micro.key.strip():
                raise ValueError(f"Macro {macro.key}: micro key vuota.")
            if not micro.label.strip():
                raise ValueError(f"Macro {macro.key}/{micro.key}: label vuota.")
            if not micro.source_path.strip():
                raise ValueError(f"Macro {macro.key}/{micro.key}: source_path mancante.")
            if micro.key in seen_micro_keys:
                raise ValueError(f"Micro key duplicata: {micro.key}.")
            seen_micro_keys.add(micro.key)

            if not macro.is_quality_only and micro.micro_weight is None:
                raise ValueError(f"Macro {macro.key}/{micro.key}: micro_weight richiesto.")
