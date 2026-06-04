"""Isolamento Cecchino dal motore SOT."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from fastapi.testclient import TestClient

from app.main import app

ENGINE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino" / "cecchino_engine.py"
SERVICE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino" / "cecchino_service.py"


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_cecchino_engine_does_not_import_sot_prediction_modules():
    imports = _module_imports(ENGINE_PATH)
    forbidden = [m for m in imports if "sot_prediction" in m or "predictions_v2" in m]
    assert forbidden == [], f"Forbidden imports in engine: {forbidden}"


def test_cecchino_engine_does_not_import_v20_v21():
    imports = _module_imports(ENGINE_PATH)
    forbidden = [m for m in imports if "predictions_v20" in m or "predictions_v21" in m]
    assert forbidden == []


def test_recalculate_does_not_touch_team_sot_predictions():
    client = TestClient(app)
    mock_comp = MagicMock()
    mock_comp.id = 1

    with (
        patch(
            "app.routes.cecchino.CompetitionService.get_by_id_or_raise",
            return_value=mock_comp,
        ),
        patch(
            "app.routes.cecchino.recalculate_for_competition",
            return_value={"status": "ok", "recalculated_count": 0},
        ) as mock_recalc,
        patch("app.models.TeamSotPrediction") as mock_tsp,
    ):
        resp = client.post(
            "/api/admin/competitions/1/cecchino/recalculate",
            json={"fixture_id": 99},
        )
        assert resp.status_code == 200
        mock_recalc.assert_called_once()
        mock_tsp.query.filter.assert_not_called()
