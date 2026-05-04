"""Limitazioni del modello baseline SOT (solo metadati API, non logica predittiva)."""

MODEL_LIMITATIONS_NOTE_IT = (
    "Questa versione baseline usa solo statistiche squadra storiche. "
    "Formazioni, assenze e quote bookmaker automatiche non sono ancora considerate."
)


def default_model_limitations_dict() -> dict[str, str | bool]:
    return {
        "lineups_considered": False,
        "injuries_considered": False,
        "odds_automatically_imported": False,
        "note": MODEL_LIMITATIONS_NOTE_IT,
    }
