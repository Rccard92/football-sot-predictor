"""Orchestrazione dry-run enrichment Bet365: SELECT + report, zero scritture DB."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    BOOKMAKER_BET365,
    MATCH_STATUS_AMBIGUOUS,
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    CsvMatchRow,
    LabMatchCandidate,
    MatchResult,
    CandidateIndex,
    match_csv_row,
    parse_csv_row,
)
from app.services.cecchino_data_lab.bet365_enrichment.report import (
    build_summary,
    write_reports,
)

logger = logging.getLogger(__name__)


def is_bet365_bookmaker(value: str | None) -> bool:
    return str(value or "").strip().lower() == BOOKMAKER_BET365


def enable_read_only_transaction(session: Session) -> bool:
    """Attiva SET TRANSACTION READ ONLY se il dialetto è PostgreSQL.

    Returns:
        True se il comando è stato eseguito, False altrimenti (es. SQLite nei test).
    """
    bind = session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "") or ""
    if dialect_name != "postgresql":
        logger.info(
            "dry-run: dialetto %s — SKIP SET TRANSACTION READ ONLY",
            dialect_name or "unknown",
        )
        return False
    # Con SessionLocal (autocommit=False) la prima execute apre la transazione.
    session.execute(text("SET TRANSACTION READ ONLY"))
    logger.info("dry-run: SET TRANSACTION READ ONLY attivo")
    return True


def load_lab_candidates(session: Session) -> list[LabMatchCandidate]:
    """SELECT read-only: match JOIN dataset. Nessun flush/commit."""
    stmt = (
        select(
            CecchinoLabMatch.id,
            CecchinoLabMatch.dataset_id,
            CecchinoLabMatch.home_team,
            CecchinoLabMatch.away_team,
            CecchinoLabMatch.kickoff_at,
            CecchinoLabDataset.competition_name,
            CecchinoLabDataset.season_label,
            CecchinoLabDataset.start_year,
        )
        .join(
            CecchinoLabDataset,
            CecchinoLabMatch.dataset_id == CecchinoLabDataset.id,
        )
        .order_by(CecchinoLabMatch.id)
    )
    rows = session.execute(stmt).all()
    return [
        LabMatchCandidate(
            id=int(r.id),
            dataset_id=int(r.dataset_id),
            competition_name=str(r.competition_name or ""),
            season_label=str(r.season_label or ""),
            start_year=int(r.start_year) if r.start_year is not None else None,
            home_team=r.home_team,
            away_team=r.away_team,
            kickoff_at=r.kickoff_at,
        )
        for r in rows
    ]


def iter_csv_dicts(csv_path: Path) -> Iterable[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {str(k): ("" if v is None else str(v)) for k, v in row.items() if k}


def run_matching(
    csv_rows: list[CsvMatchRow],
    candidates: list[LabMatchCandidate],
    *,
    fuzzy_suggestions: bool = False,
    index: CandidateIndex | None = None,
) -> tuple[list[MatchResult], CandidateIndex]:
    idx = index if index is not None else CandidateIndex.build(candidates)
    total = len(csv_rows)
    results: list[MatchResult] = []
    exact = safe_alias = ambiguous = not_found = 0

    for i, row in enumerate(csv_rows, start=1):
        result = match_csv_row(
            row,
            candidates,
            index=idx,
            fuzzy_suggestions=fuzzy_suggestions,
        )
        results.append(result)
        status = result.match_status
        if status == MATCH_STATUS_EXACT:
            exact += 1
        elif status == MATCH_STATUS_SAFE_ALIAS:
            safe_alias += 1
        elif status == MATCH_STATUS_AMBIGUOUS:
            ambiguous += 1
        elif status == MATCH_STATUS_NOT_FOUND:
            not_found += 1

        if i % 1000 == 0 or i == total:
            logger.info(
                "processed=%d/%d, exact=%d, safe_alias=%d, ambiguous=%d, not_found=%d",
                i,
                total,
                exact,
                safe_alias,
                ambiguous,
                not_found,
            )
    return results, idx


def run_bet365_enrichment_dry_run(
    *,
    csv_path: str | Path,
    output_dir: str | Path,
    session: Session,
    fuzzy_suggestions: bool = False,
    discover_aliases: bool = False,
) -> dict[str, Any]:
    """Esegue dry-run completo.

    - Solo SELECT sul DB (più SET TRANSACTION READ ONLY su PostgreSQL)
    - Vietati INSERT/UPDATE/DELETE/flush/commit
    - Report su filesystem in output_dir
    - Fuzzy suggestions diagnostici solo se ``fuzzy_suggestions=True``
    - Alias discovery diagnostica se ``discover_aliases=True`` (non modifica TEAM_ALIASES)
    """
    path = Path(csv_path)
    out = Path(output_dir)
    if not path.is_file():
        raise FileNotFoundError(f"CSV non trovato: {path}")

    # Protezione aggiuntiva: disabilita autoflush per questa sessione
    previous_autoflush = session.autoflush
    session.autoflush = False

    read_only_enabled = False
    try:
        read_only_enabled = enable_read_only_transaction(session)
        all_raw = list(iter_csv_dicts(path))
        csv_rows_total = len(all_raw)

        bet365_raw = [r for r in all_raw if is_bet365_bookmaker(r.get("bookmaker"))]
        bet365_rows = [parse_csv_row(r) for r in bet365_raw]

        candidates = load_lab_candidates(session)
        results, index = run_matching(
            bet365_rows,
            candidates,
            fuzzy_suggestions=fuzzy_suggestions,
        )

        summary = build_summary(
            csv_rows_total=csv_rows_total,
            bet365_rows=len(bet365_rows),
            results=results,
        )
        summary["read_only_transaction"] = read_only_enabled
        summary["lab_candidates_loaded"] = len(candidates)
        summary["fuzzy_suggestions"] = fuzzy_suggestions
        summary["discover_aliases"] = discover_aliases

        paths = write_reports(out, summary=summary, results=results)
        summary["output_files"] = paths

        if discover_aliases:
            from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery import (
                run_alias_discovery,
                write_alias_discovery_reports,
            )

            discovery = run_alias_discovery(results, candidates, index=index)
            alias_paths = write_alias_discovery_reports(out, discovery)
            summary["alias_discovery"] = discovery.summary
            summary["output_files"] = {**paths, **alias_paths}

        # Rollback esplicito della transazione read-only (nessun commit)
        session.rollback()
        return summary
    finally:
        session.autoflush = previous_autoflush
        # Garantisce chiusura senza commit anche in caso di errore
        try:
            session.rollback()
        except Exception:  # noqa: BLE001 — dry-run: best-effort cleanup
            logger.exception("dry-run: rollback fallito in cleanup")
