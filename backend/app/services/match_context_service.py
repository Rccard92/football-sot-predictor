from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, StandingEntry, StandingsSnapshot, Team

competition_context_config = {
    "title_zone_rank": 1,
    "champions_zone_max_rank": 4,
    "europe_zone_max_rank": 7,
    "relegation_zone_min_rank": 18,
    "late_season_round_threshold": 33,
    "final_rounds_threshold": 35,
    "points_gap_practically_out": 7,
    "points_gap_close": 3,
}

SeasonPhaseId = Literal["early", "middle", "late", "final_rounds", "unknown"]


def get_season_phase(round_value: str | None, season_year: int) -> dict[str, Any]:
    """
    Determina la fase stagione da `round` (Serie A 38 giornate) e produce un contesto rischio.

    Nota: `season_year` è incluso per future logiche season-specific; in questa versione non cambia la regola base.
    """
    _ = season_year

    def extract_round_number(rv: str | None) -> int | None:
        if not rv:
            return None
        digits = "".join(ch for ch in str(rv) if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    rn = extract_round_number(round_value)
    notes: list[str] = []
    if rn is None:
        return {
            "round_number": None,
            "season_phase": "unknown",
            "late_season_risk": False,
            "phase_context_applied": False,
            "notes": ["Round non parseabile: fase stagione non determinabile."],
        }

    phase: SeasonPhaseId
    late_season_risk = False
    if 1 <= rn <= 10:
        phase = "early"
        notes.append("Inizio stagione: campioni e trend possono essere meno stabili.")
    elif 11 <= rn <= 25:
        phase = "middle"
        notes.append("Fase centrale: contesto mediamente più stabile.")
    elif 26 <= rn <= 32:
        phase = "late"
        notes.append("Fase avanzata: aumentano segnali motivazionali e gestione energie.")
    else:
        phase = "final_rounds"
        late_season_risk = True
        notes.append("Ultime giornate: rischio contesto più alto (motivazione/turnover).")

    if rn >= 35:
        notes.append("Final rounds (≥35): massima sensibilità a obiettivi e rotazioni.")

    return {
        "round_number": rn,
        "season_phase": phase,
        "late_season_risk": late_season_risk,
        "phase_context_applied": True,
        "notes": notes,
    }


@dataclass
class _StandingsPack:
    snapshot: StandingsSnapshot
    by_team_id: dict[int, StandingEntry]
    ordered: list[StandingEntry]


class MatchContextService:
    # NOTE: soglie configurabili, verificare stagione per stagione.
    config = competition_context_config

    @staticmethod
    def _extract_round_number(round_value: str | None) -> int | None:
        if not round_value:
            return None
        digits = "".join(ch for ch in str(round_value) if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _latest_standings(self, db: Session, season_id: int) -> _StandingsPack | None:
        snap = db.scalar(
            select(StandingsSnapshot)
            .where(StandingsSnapshot.season_id == season_id)
            .order_by(StandingsSnapshot.snapshot_at.desc(), StandingsSnapshot.id.desc()),
        )
        if snap is None:
            return None
        entries = db.scalars(
            select(StandingEntry)
            .where(StandingEntry.snapshot_id == snap.id)
            .order_by(StandingEntry.rank.asc().nulls_last(), StandingEntry.team_id.asc()),
        ).all()
        by_team_id = {int(e.team_id): e for e in entries}
        return _StandingsPack(snapshot=snap, by_team_id=by_team_id, ordered=entries)

    def _objective(self, entry: StandingEntry | None) -> str:
        if entry is None or entry.rank is None:
            return "unknown"
        r = int(entry.rank)
        if r == self.config["title_zone_rank"]:
            return "title_race"
        if r <= self.config["champions_zone_max_rank"]:
            return "champions_race"
        if r <= self.config["europe_zone_max_rank"]:
            return "europe_race"
        if r >= self.config["relegation_zone_min_rank"]:
            return "relegation_race"
        return "mid_table_no_clear_objective"

    def _context_risk_adjustment(
        self,
        *,
        late_season_risk: bool,
        turnover_risk: str,
        motivation_level: str,
        standings_available: bool,
        season_phase: dict[str, Any],
    ) -> dict[str, Any]:
        # Impatta solo la confidence/risk, non expected_sot.
        adj = 0
        flags: list[str] = []

        if late_season_risk:
            adj -= 5
            flags.append("fine_stagione")
        if str(turnover_risk) == "alto":
            adj -= 8
            flags.append("turnover_risk_alto")
        if str(motivation_level) == "incerta":
            adj -= 5
            flags.append("motivazione_incerta")

        if not standings_available and bool(season_phase.get("late_season_risk")):
            flags.append("standings_not_available_late_season")

        abs_pen = abs(adj)
        if abs_pen >= 10:
            risk_label = "alto"
        elif abs_pen >= 5:
            risk_label = "medio"
        else:
            risk_label = "basso"

        return {
            "context_risk_score": abs_pen,
            "context_risk_label": risk_label,
            "confidence_adjustment": adj,
            "risk_flags": flags,
        }

    def _team_context(
        self,
        *,
        team: Team | None,
        entry: StandingEntry | None,
        standings: _StandingsPack,
        round_num: int | None,
    ) -> dict[str, Any]:
        if team is None:
            return {
                "team_id": None,
                "team_name": "",
                "motivation_level": "incerta",
                "competition_objective": "unknown",
                "turnover_risk": "incerto",
                "motivation_reasons": ["Squadra non trovata nel database."],
                "context_warning": "Dati squadra non disponibili.",
                "late_season_risk": False,
                "standings_context_applied": False,
                "standings_notes": ["Squadra non disponibile."],
            }
        if entry is None:
            return {
                "team_id": team.id,
                "team_name": team.name,
                "motivation_level": "incerta",
                "competition_objective": "unknown",
                "turnover_risk": "incerto",
                "motivation_reasons": ["Classifica non disponibile per la squadra."],
                "context_warning": "Classifica non disponibile: contesto motivazionale non valutabile.",
                "late_season_risk": False,
                "standings_context_applied": False,
                "standings_notes": ["Classifica non disponibile: importare standings."],
            }

        rank = int(entry.rank) if entry.rank is not None else None
        points = int(entry.points) if entry.points is not None else None
        late_risk = bool(
            round_num is not None and round_num >= int(self.config["late_season_round_threshold"])
        )
        reasons: list[str] = []
        objective = self._objective(entry)
        motivation = "media"
        turnover = "medio"
        warning: str | None = None
        close = int(self.config["points_gap_close"])
        practically_out = int(self.config["points_gap_practically_out"])

        teams_with_rank = [e for e in standings.ordered if e.rank is not None and e.points is not None]
        first = teams_with_rank[0] if teams_with_rank else None
        fourth = next((e for e in teams_with_rank if e.rank == 4), None)
        seventh = next((e for e in teams_with_rank if e.rank == 7), None)
        eighteenth = next((e for e in teams_with_rank if e.rank == 18), None)

        second = next((e for e in teams_with_rank if e.rank == 2), None)
        if rank == 1 and points is not None and second is not None:
            if second.points is not None and (points - int(second.points)) >= practically_out:
                objective = "already_champion_or_almost"
                motivation = "media"
                turnover = "medio"
                reasons.append("Vantaggio ampio in testa: titolo quasi definito.")
        if rank is not None and rank >= self.config["relegation_zone_min_rank"] and eighteenth is not None:
            motivation = "alta"
            objective = "relegation_race"
            turnover = "basso"
            reasons.append("Squadra in zona retrocessione: partita ad alta pressione.")
        elif points is not None and eighteenth is not None and eighteenth.points is not None:
            if abs(points - int(eighteenth.points)) <= close:
                motivation = "alta"
                objective = "relegation_race"
                turnover = "basso"
                reasons.append("Squadra vicina alla zona retrocessione.")

        if points is not None and fourth is not None and fourth.points is not None:
            if abs(points - int(fourth.points)) <= close:
                motivation = "alta"
                if objective in ("mid_table_no_clear_objective", "europe_race"):
                    objective = "champions_race"
                turnover = "basso"
                reasons.append("Squadra in corsa ravvicinata per la zona Champions.")
        if points is not None and seventh is not None and seventh.points is not None:
            if abs(points - int(seventh.points)) <= close and motivation != "alta":
                motivation = "media"
                if objective == "mid_table_no_clear_objective":
                    objective = "europe_race"
                reasons.append("Squadra vicina alla zona europea.")

        if points is not None and first is not None and eighteenth is not None:
            title_gap = int(first.points) - points if first.points is not None else None
            rel_gap = points - int(eighteenth.points) if eighteenth.points is not None else None
            if (
                title_gap is not None
                and rel_gap is not None
                and title_gap > practically_out
                and rel_gap > practically_out
                and objective == "mid_table_no_clear_objective"
            ):
                motivation = "bassa"
                turnover = "alto"
                reasons.append(
                    "Nessun obiettivo di classifica evidente: possibile rischio turnover più alto."
                )

        if late_risk:
            warning = (
                "Partita di fine stagione: il modello statistico può essere meno affidabile "
                "se una squadra ha già raggiunto o perso i propri obiettivi."
            )
            if turnover == "medio" and motivation in ("bassa", "media"):
                turnover = "alto"

        if not reasons:
            reasons.append("Contesto classifica non conclusivo: usare prudenza.")
            motivation = "incerta"
            turnover = "incerto"
            objective = "unknown"

        return {
            "team_id": team.id,
            "team_name": team.name,
            "rank": rank,
            "points": points,
            "played": entry.played,
            "goals_diff": entry.goals_diff,
            "form": entry.form,
            "description": entry.description,
            "motivation_level": motivation,
            "motivation_reasons": reasons,
            "competition_objective": objective,
            "standings_context_applied": True,
            "standings_notes": [],
            "turnover_risk": turnover,
            "context_warning": warning,
            "late_season_risk": late_risk,
        }

    def build_match_context(self, db: Session, fixture_id: int) -> dict[str, Any]:
        fx = db.get(Fixture, fixture_id)
        if fx is None:
            return {"fixture_id": fixture_id, "context_status": "not_found"}

        phase_ctx = get_season_phase(fx.round, season_year=0)
        standings = self._latest_standings(db, fx.season_id)
        if standings is None:
            return {
                "fixture_id": fixture_id,
                "context_status": "not_available",
                "home_team_context": None,
                "away_team_context": None,
                "season_phase_context": phase_ctx,
                "match_context": {
                    "overall_match_importance": "incerta",
                    "late_season_risk": bool(phase_ctx.get("late_season_risk")),
                    "risk_flags": ["standings_not_available"],
                    "summary": "Classifica non disponibile: contesto partita non calcolabile.",
                },
            }

        home_team = db.get(Team, fx.home_team_id)
        away_team = db.get(Team, fx.away_team_id)
        round_num = self._extract_round_number(fx.round)
        home_ctx = self._team_context(
            team=home_team,
            entry=standings.by_team_id.get(fx.home_team_id),
            standings=standings,
            round_num=round_num,
        )
        away_ctx = self._team_context(
            team=away_team,
            entry=standings.by_team_id.get(fx.away_team_id),
            standings=standings,
            round_num=round_num,
        )

        risk_flags: list[str] = []
        late_season_risk = bool(phase_ctx.get("late_season_risk")) or bool(home_ctx.get("late_season_risk")) or bool(away_ctx.get("late_season_risk"))
        if late_season_risk:
            risk_flags.append("fine_stagione")
        if home_ctx.get("turnover_risk") == "alto" and home_team is not None:
            risk_flags.append(f"possibile_turnover_{home_team.name.lower().replace(' ', '_')}")
        if away_ctx.get("turnover_risk") == "alto" and away_team is not None:
            risk_flags.append(f"possibile_turnover_{away_team.name.lower().replace(' ', '_')}")

        levels = [home_ctx.get("motivation_level"), away_ctx.get("motivation_level")]
        if "alta" in levels:
            overall = "alta"
        elif "media" in levels:
            overall = "media"
        elif "bassa" in levels:
            overall = "bassa"
        else:
            overall = "incerta"

        if home_ctx.get("motivation_level") != away_ctx.get("motivation_level"):
            risk_flags.append("asimmetria_motivazionale")

        summary = (
            "Partita di fine stagione: la previsione statistica non cambia, ma il contesto aumenta il rischio. "
            "Leggere con prudenza e verificare possibili rotazioni."
            if "fine_stagione" in risk_flags
            else "Contesto classifica calcolato in modo prudente; non modifica expected_sot, ma guida warning e prudenza."
        )

        ctx_adj_home = self._context_risk_adjustment(
            late_season_risk=late_season_risk,
            turnover_risk=str(home_ctx.get("turnover_risk")),
            motivation_level=str(home_ctx.get("motivation_level")),
            standings_available=True,
            season_phase=phase_ctx,
        )
        ctx_adj_away = self._context_risk_adjustment(
            late_season_risk=late_season_risk,
            turnover_risk=str(away_ctx.get("turnover_risk")),
            motivation_level=str(away_ctx.get("motivation_level")),
            standings_available=True,
            season_phase=phase_ctx,
        )
        conf_adj = min(int(ctx_adj_home["confidence_adjustment"]), int(ctx_adj_away["confidence_adjustment"]))
        ctx_risk_score = max(int(ctx_adj_home["context_risk_score"]), int(ctx_adj_away["context_risk_score"]))
        ctx_risk_label = "alto" if ctx_risk_score >= 10 else "medio" if ctx_risk_score >= 5 else "basso"
        return {
            "fixture_id": fixture_id,
            "context_status": "available",
            "snapshot_at": standings.snapshot.snapshot_at,
            "home_team_context": home_ctx,
            "away_team_context": away_ctx,
            "season_phase_context": phase_ctx,
            "match_context": {
                "overall_match_importance": overall,
                "late_season_risk": late_season_risk,
                "context_risk_score": ctx_risk_score,
                "context_risk_label": ctx_risk_label,
                "confidence_adjustment": conf_adj,
                "risk_flags": risk_flags,
                "summary": summary,
            },
        }
