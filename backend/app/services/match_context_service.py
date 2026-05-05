from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, StandingEntry, StandingsSnapshot, Team

competition_context_config = {
    "title_zone_rank": 1,
    "champions_zone_max_rank": 4,
    "europe_zone_max_rank": 7,
    "relegation_zone_min_rank": 18,
    "late_season_round_threshold": 33,
    "points_gap_practically_out": 7,
    "points_gap_close": 3,
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
            return "incerto"
        r = int(entry.rank)
        if r == self.config["title_zone_rank"]:
            return "titolo"
        if r <= self.config["champions_zone_max_rank"]:
            return "champions"
        if r <= self.config["europe_zone_max_rank"]:
            return "europa"
        if r >= self.config["relegation_zone_min_rank"]:
            return "salvezza"
        return "nessun_obiettivo_chiaro"

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
                "competition_objective": "incerto",
                "turnover_risk": "incerto",
                "motivation_reasons": ["Squadra non trovata nel database."],
                "context_warning": "Dati squadra non disponibili.",
                "late_season_risk": False,
            }
        if entry is None:
            return {
                "team_id": team.id,
                "team_name": team.name,
                "motivation_level": "incerta",
                "competition_objective": "incerto",
                "turnover_risk": "incerto",
                "motivation_reasons": ["Classifica non disponibile per la squadra."],
                "context_warning": "Classifica non disponibile: contesto motivazionale non valutabile.",
                "late_season_risk": False,
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
                objective = "gia_campione"
                motivation = "media"
                turnover = "medio"
                reasons.append("Vantaggio ampio in testa: titolo quasi definito.")
        if rank is not None and rank >= self.config["relegation_zone_min_rank"] and eighteenth is not None:
            motivation = "alta"
            objective = "salvezza"
            turnover = "basso"
            reasons.append("Squadra in zona retrocessione: partita ad alta pressione.")
        elif points is not None and eighteenth is not None and eighteenth.points is not None:
            if abs(points - int(eighteenth.points)) <= close:
                motivation = "alta"
                objective = "salvezza"
                turnover = "basso"
                reasons.append("Squadra vicina alla zona retrocessione.")

        if points is not None and fourth is not None and fourth.points is not None:
            if abs(points - int(fourth.points)) <= close:
                motivation = "alta"
                if objective in ("nessun_obiettivo_chiaro", "europa"):
                    objective = "champions"
                turnover = "basso"
                reasons.append("Squadra in corsa ravvicinata per la zona Champions.")
        if points is not None and seventh is not None and seventh.points is not None:
            if abs(points - int(seventh.points)) <= close and motivation != "alta":
                motivation = "media"
                if objective == "nessun_obiettivo_chiaro":
                    objective = "europa"
                reasons.append("Squadra vicina alla zona europea.")

        if points is not None and first is not None and eighteenth is not None:
            title_gap = int(first.points) - points if first.points is not None else None
            rel_gap = points - int(eighteenth.points) if eighteenth.points is not None else None
            if (
                title_gap is not None
                and rel_gap is not None
                and title_gap > practically_out
                and rel_gap > practically_out
                and objective == "nessun_obiettivo_chiaro"
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
            objective = "incerto"

        return {
            "team_id": team.id,
            "team_name": team.name,
            "rank": rank,
            "points": points,
            "played": entry.played,
            "motivation_level": motivation,
            "motivation_reasons": reasons,
            "competition_objective": objective,
            "turnover_risk": turnover,
            "context_warning": warning,
            "late_season_risk": late_risk,
        }

    def build_match_context(self, db: Session, fixture_id: int) -> dict[str, Any]:
        fx = db.get(Fixture, fixture_id)
        if fx is None:
            return {"fixture_id": fixture_id, "context_status": "not_found"}

        standings = self._latest_standings(db, fx.season_id)
        if standings is None:
            return {
                "fixture_id": fixture_id,
                "context_status": "not_available",
                "home_team_context": None,
                "away_team_context": None,
                "match_context": {
                    "overall_match_importance": "incerta",
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
        if home_ctx.get("late_season_risk") or away_ctx.get("late_season_risk"):
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

        summary = (
            "Partita di fine stagione con rischio turnover/rotazioni. "
            "La previsione statistica va letta con prudenza."
            if "fine_stagione" in risk_flags
            else "Contesto motivazionale calcolato in modo prudente; usare comunque conferme da news/formazioni."
        )
        return {
            "fixture_id": fixture_id,
            "context_status": "available",
            "snapshot_at": standings.snapshot.snapshot_at,
            "home_team_context": home_ctx,
            "away_team_context": away_ctx,
            "match_context": {
                "overall_match_importance": overall,
                "risk_flags": risk_flags,
                "summary": summary,
            },
        }
