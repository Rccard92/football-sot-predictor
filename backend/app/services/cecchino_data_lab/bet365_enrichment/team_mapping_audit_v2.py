"""Audit HTML/CSV dei mapping squadra CSV→DB dopo simulazione Alias Discovery V2.

Solo reporting: zero DB writes, zero modifiche a TEAM_ALIASES / matching / bootstrap.
"""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery_v2 import (
    CONF_CONFLICT,
    CONF_CONFLICT_STATIC,
    CONF_LOW,
    CONF_SCHEDULE_ONLY,
    AliasDiscoveryV2Result,
)
from app.services.cecchino_data_lab.bet365_enrichment.constants import MATCHED_STATUSES
from app.services.cecchino_data_lab.bet365_enrichment.matching import MatchResult
from app.services.cecchino_data_lab.bet365_enrichment.normalize import (
    normalize_name,
    team_names_equal,
)

STATUS_IDENTITY = "IDENTITY"
STATUS_STATIC_ALIAS = "STATIC_ALIAS"
STATUS_V2_TRUSTED_ALIAS = "V2_TRUSTED_ALIAS"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_SCHEDULE_ONLY = "SCHEDULE_ONLY"
STATUS_LOW_EVIDENCE = "LOW_EVIDENCE"
STATUS_CONFLICT = "CONFLICT"
STATUS_MULTI_TARGET = "MULTI_TARGET"

COVERAGE_FULL = "FULL"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_NONE = "NONE"

RESOLVED_STATUSES = frozenset(
    {STATUS_IDENTITY, STATUS_STATIC_ALIAS, STATUS_V2_TRUSTED_ALIAS}
)
DUBIOUS_STATUSES = frozenset(
    {
        STATUS_SCHEDULE_ONLY,
        STATUS_LOW_EVIDENCE,
        STATUS_CONFLICT,
        STATUS_MULTI_TARGET,
    }
)
PROBLEM_STATUSES = DUBIOUS_STATUSES | {STATUS_UNRESOLVED}

AUDIT_CSV_COLUMNS = [
    "competition_name",
    "csv_team_name",
    "db_team_name",
    "resolution_status",
    "csv_occurrences",
    "matched_fixture_count",
    "unmatched_fixture_count",
    "match_coverage_pct",
    "coverage_status",
    "seasons",
    "first_seen",
    "last_seen",
    "evidence_count",
    "distinct_dates",
    "bootstrap_iteration",
    "notes",
]


@dataclass
class _SideOcc:
    csv_raw: str
    db_raw: str | None
    side_status: str | None
    season: str
    kickoff: datetime | None
    matched: bool


@dataclass
class _AggBucket:
    competition_name: str
    csv_norm: str
    csv_raws: Counter[str] = field(default_factory=Counter)
    sides: list[_SideOcc] = field(default_factory=list)


def classify_side_status(
    csv_team: str | None,
    db_team: str | None,
    *,
    trusted_aliases: dict[str, str] | None = None,
) -> str | None:
    """Classifica un singolo lato CSV→DB. None se db assente o non matcha."""
    if not db_team or not str(db_team).strip():
        return None
    if normalize_name(csv_team) == normalize_name(db_team) and normalize_name(csv_team):
        return STATUS_IDENTITY
    matched, used_static, used_temp = team_names_equal(
        csv_team, db_team, extra_aliases=trusted_aliases
    )
    if not matched:
        return None
    if used_static:
        return STATUS_STATIC_ALIAS
    if used_temp:
        return STATUS_V2_TRUSTED_ALIAS
    # Match senza alias e senza identity: non dovrebbe accadere; tratta come identity
    return STATUS_IDENTITY


def _competition_display(result: MatchResult) -> str:
    row = result.csv_row
    return str(row.competition_name or row.competition_api_name or "").strip() or "(unknown)"


def _season_display(result: MatchResult) -> str:
    row = result.csv_row
    if row.season:
        return str(row.season).strip()
    if row.season_start_year is not None:
        return str(row.season_start_year)
    return ""


def _kickoff_date(result: MatchResult) -> date | None:
    ko = result.csv_row.kickoff_utc
    if ko is None:
        return None
    return ko.date() if isinstance(ko, datetime) else None


def _suggestion_index(
    suggestions: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """(csv_norm, competition_norm) -> best suggestion row."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in suggestions:
        csv_norm = normalize_name(row.get("csv_team_name"))
        if not csv_norm:
            continue
        comps = str(row.get("competitions") or "")
        parts = [p.strip() for p in comps.split("|") if p.strip()] or [""]
        for comp in parts:
            key = (csv_norm, normalize_name(comp))
            prev = index.get(key)
            if prev is None:
                index[key] = row
    return index


def _lookup_suggestion(
    index: dict[tuple[str, str], dict[str, Any]],
    csv_norm: str,
    competition_name: str,
) -> dict[str, Any] | None:
    key = (csv_norm, normalize_name(competition_name))
    if key in index:
        return index[key]
    # fallback: any suggestion for this csv_norm
    for (n, _c), row in index.items():
        if n == csv_norm:
            return row
    return None


def _map_suggestion_status(conf: str | None) -> str | None:
    if conf == CONF_SCHEDULE_ONLY:
        return STATUS_SCHEDULE_ONLY
    if conf == CONF_LOW:
        return STATUS_LOW_EVIDENCE
    if conf in (CONF_CONFLICT, CONF_CONFLICT_STATIC):
        return STATUS_CONFLICT
    return None


def _coverage_status(matched: int, total: int) -> str:
    if total <= 0 or matched <= 0:
        return COVERAGE_NONE
    if matched >= total:
        return COVERAGE_FULL
    return COVERAGE_PARTIAL


def _majority_status(statuses: list[str]) -> str:
    if not statuses:
        return STATUS_UNRESOLVED
    counts = Counter(statuses)
    # Prefer resolved types by frequency, tie-break: IDENTITY > STATIC > V2
    order = {
        STATUS_IDENTITY: 0,
        STATUS_STATIC_ALIAS: 1,
        STATUS_V2_TRUSTED_ALIAS: 2,
    }
    return sorted(
        counts.keys(),
        key=lambda s: (-counts[s], order.get(s, 9)),
    )[0]


def build_team_mapping_audit_rows(
    discovery: AliasDiscoveryV2Result,
) -> list[dict[str, Any]]:
    """Aggrega competition + csv_norm da tutti i lati home/away della simulazione V2."""
    trusted = discovery.trusted_aliases or {}
    sug_index = _suggestion_index(discovery.suggestions)
    buckets: dict[tuple[str, str], _AggBucket] = {}

    for result in discovery.simulated_results:
        competition = _competition_display(result)
        season = _season_display(result)
        kickoff = result.csv_row.kickoff_utc
        fixture_matched = (
            result.match_status in MATCHED_STATUSES and result.matched is not None
        )
        pairs = [
            (
                result.csv_row.home_team,
                result.matched.home_team if fixture_matched and result.matched else None,
            ),
            (
                result.csv_row.away_team,
                result.matched.away_team if fixture_matched and result.matched else None,
            ),
        ]
        for csv_raw, db_raw in pairs:
            csv_disp = str(csv_raw or "").strip()
            csv_norm = normalize_name(csv_disp)
            if not csv_norm:
                continue
            key = (competition, csv_norm)
            bucket = buckets.get(key)
            if bucket is None:
                bucket = _AggBucket(competition_name=competition, csv_norm=csv_norm)
                buckets[key] = bucket
            bucket.csv_raws[csv_disp] += 1
            side_status = None
            matched_side = False
            db_recorded: str | None = None
            if fixture_matched and db_raw and str(db_raw).strip():
                db_recorded = str(db_raw).strip()
                matched_side = True
                side_status = classify_side_status(
                    csv_disp, db_recorded, trusted_aliases=trusted
                )
            bucket.sides.append(
                _SideOcc(
                    csv_raw=csv_disp,
                    db_raw=db_recorded,
                    side_status=side_status,
                    season=season,
                    kickoff=kickoff,
                    matched=matched_side,
                )
            )

    rows: list[dict[str, Any]] = []
    for (_comp, csv_norm), bucket in sorted(
        buckets.items(), key=lambda x: (x[0][0].lower(), x[0][1])
    ):
        csv_team_name = bucket.csv_raws.most_common(1)[0][0]
        occurrences = len(bucket.sides)
        matched_sides = [s for s in bucket.sides if s.matched and s.db_raw]
        matched_count = len(matched_sides)
        unmatched_count = occurrences - matched_count
        coverage_pct = (
            round(100.0 * matched_count / occurrences, 1) if occurrences else 0.0
        )
        cov_status = _coverage_status(matched_count, occurrences)

        db_targets = sorted({s.db_raw for s in matched_sides if s.db_raw})
        notes_parts: list[str] = []
        sug = _lookup_suggestion(sug_index, csv_norm, bucket.competition_name)

        if len(db_targets) > 1:
            resolution = STATUS_MULTI_TARGET
            db_team_name = ""
            notes_parts.append("targets=" + "|".join(db_targets))
        elif len(db_targets) == 1:
            db_team_name = db_targets[0]
            side_statuses = [
                s.side_status for s in matched_sides if s.side_status is not None
            ]
            # Riclassifica sul display aggregato vs unico target
            resolution = classify_side_status(
                csv_team_name, db_team_name, trusted_aliases=trusted
            ) or _majority_status([s for s in side_statuses if s])
        else:
            db_team_name = ""
            mapped = _map_suggestion_status(
                str(sug.get("confidence_status") or "") if sug else None
            )
            resolution = mapped or STATUS_UNRESOLVED
            if sug and sug.get("db_team_name") and resolution != STATUS_UNRESOLVED:
                notes_parts.append(
                    f"suggestion_target={sug.get('db_team_name')}"
                    f" ({sug.get('confidence_status')})"
                )

        seasons = sorted(
            {s.season for s in bucket.sides if s.season},
            key=lambda x: x,
        )
        dates = [s.kickoff.date() for s in bucket.sides if s.kickoff is not None]
        first_seen = min(dates).isoformat() if dates else ""
        last_seen = max(dates).isoformat() if dates else ""

        evidence_count = ""
        distinct_dates = ""
        bootstrap_iteration = ""
        if sug:
            if sug.get("evidence_count") not in (None, ""):
                evidence_count = sug.get("evidence_count")
            if sug.get("distinct_dates") not in (None, ""):
                distinct_dates = sug.get("distinct_dates")
            if sug.get("bootstrap_iteration") not in (None, ""):
                bootstrap_iteration = sug.get("bootstrap_iteration")

        rows.append(
            {
                "competition_name": bucket.competition_name,
                "csv_team_name": csv_team_name,
                "db_team_name": db_team_name,
                "resolution_status": resolution,
                "csv_occurrences": occurrences,
                "matched_fixture_count": matched_count,
                "unmatched_fixture_count": unmatched_count,
                "match_coverage_pct": coverage_pct,
                "coverage_status": cov_status,
                "seasons": "|".join(seasons),
                "first_seen": first_seen,
                "last_seen": last_seen,
                "evidence_count": evidence_count,
                "distinct_dates": distinct_dates,
                "bootstrap_iteration": bootstrap_iteration,
                "notes": "; ".join(notes_parts),
            }
        )
    return rows


def build_team_mapping_audit_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unique = len(rows)
    by_status: Counter[str] = Counter(str(r["resolution_status"]) for r in rows)
    resolved = sum(by_status[s] for s in RESOLVED_STATUSES)
    dubious = sum(by_status[s] for s in DUBIOUS_STATUSES)
    by_coverage: Counter[str] = Counter(str(r["coverage_status"]) for r in rows)
    per_comp: dict[str, int] = defaultdict(int)
    for r in rows:
        per_comp[str(r["competition_name"])] += 1
    return {
        "unique_csv_teams": unique,
        "resolved_teams": resolved,
        "identity": by_status[STATUS_IDENTITY],
        "static_aliases": by_status[STATUS_STATIC_ALIAS],
        "v2_trusted_aliases": by_status[STATUS_V2_TRUSTED_ALIAS],
        "unresolved": by_status[STATUS_UNRESOLVED],
        "dubious": dubious,
        "schedule_only": by_status[STATUS_SCHEDULE_ONLY],
        "low_evidence": by_status[STATUS_LOW_EVIDENCE],
        "conflict": by_status[STATUS_CONFLICT],
        "multi_target": by_status[STATUS_MULTI_TARGET],
        "overall_resolved_pct": round(100.0 * resolved / unique, 1) if unique else 0.0,
        "coverage_full": by_coverage[COVERAGE_FULL],
        "coverage_partial": by_coverage[COVERAGE_PARTIAL],
        "coverage_none": by_coverage[COVERAGE_NONE],
        "unique_teams_per_competition": dict(sorted(per_comp.items())),
        "db_writes": False,
        "team_aliases_modified": False,
    }


def _status_css_class(status: str) -> str:
    if status in RESOLVED_STATUSES:
        return "ok"
    if status in (STATUS_SCHEDULE_ONLY, STATUS_LOW_EVIDENCE):
        return "warn"
    return "bad"


def _coverage_css_class(status: str) -> str:
    if status == COVERAGE_FULL:
        return "cov-full"
    if status == COVERAGE_PARTIAL:
        return "cov-partial"
    return "cov-none"


def _coverage_label(row: dict[str, Any]) -> str:
    m = row["matched_fixture_count"]
    t = row["csv_occurrences"]
    pct = row["match_coverage_pct"]
    return f"{m}/{t} ({pct}%)"


def render_team_mapping_audit_html(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    esc = html.escape
    by_comp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_comp[str(r["competition_name"])].append(r)

    status_options = sorted({str(r["resolution_status"]) for r in rows})
    status_opts_html = "".join(
        f'<option value="{esc(s)}">{esc(s)}</option>' for s in status_options
    )
    comp_options = sorted(by_comp.keys())
    comp_opts_html = "".join(
        f'<option value="{esc(c)}">{esc(c)}</option>' for c in comp_options
    )

    sections: list[str] = []
    for comp in comp_options:
        team_rows = by_comp[comp]
        n = len(team_rows)
        n_res = sum(1 for r in team_rows if r["resolution_status"] in RESOLVED_STATUSES)
        n_un = sum(1 for r in team_rows if r["resolution_status"] == STATUS_UNRESOLVED)
        n_dub = sum(1 for r in team_rows if r["resolution_status"] in DUBIOUS_STATUSES)
        body_rows: list[str] = []
        for r in sorted(team_rows, key=lambda x: str(x["csv_team_name"]).lower()):
            st = str(r["resolution_status"])
            cov = str(r["coverage_status"])
            body_rows.append(
                "<tr"
                f' data-status="{esc(st)}"'
                f' data-competition="{esc(comp)}"'
                f' data-team="{esc(str(r["csv_team_name"]).lower())}"'
                f' data-problem="{"1" if st in PROBLEM_STATUSES else "0"}"'
                ">"
                f'<td class="team">{esc(str(r["csv_team_name"]))}</td>'
                f"<td>{esc(str(r['db_team_name']))}</td>"
                f'<td class="status {_status_css_class(st)}">{esc(st)}</td>'
                f'<td class="coverage {_coverage_css_class(cov)}">'
                f"{esc(_coverage_label(r))}</td>"
                f"<td>{esc(str(r['seasons']))}</td>"
                f"<td class=\"diag\">{esc(str(r.get('evidence_count') or ''))}</td>"
                f"<td class=\"diag\">{esc(str(r.get('distinct_dates') or ''))}</td>"
                f"<td class=\"diag\">{esc(str(r.get('bootstrap_iteration') or ''))}</td>"
                f"<td class=\"diag\">{esc(str(r.get('notes') or ''))}</td>"
                "</tr>"
            )
        sections.append(
            f'<details class="comp" data-competition="{esc(comp)}" open>'
            f"<summary><strong>{esc(comp)}</strong>"
            f" — squadre CSV: {n}, resolved: {n_res},"
            f" unresolved: {n_un}, dubious: {n_dub}</summary>"
            '<table class="teams">'
            "<thead><tr>"
            "<th data-sort=\"team\">CSV TEAM</th>"
            "<th>DB TEAM</th>"
            "<th data-sort=\"status\">STATUS</th>"
            "<th>COVERAGE</th>"
            "<th>SEASONS</th>"
            "<th class=\"diag\">evidence</th>"
            "<th class=\"diag\">dates</th>"
            "<th class=\"diag\">bootstrap</th>"
            "<th class=\"diag\">notes</th>"
            "</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
            "</table></details>"
        )

    s = summary
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Team Mapping Audit V2</title>
<style>
:root {{
  --bg: #f7f5f1;
  --ink: #1a1a1a;
  --muted: #5a5a5a;
  --ok: #1b6b3a;
  --ok-bg: #d9f0e2;
  --warn: #8a6a00;
  --warn-bg: #fff3bf;
  --bad: #8b1e1e;
  --bad-bg: #f8d7da;
  --partial: #b35c00;
  --partial-bg: #ffe0c2;
  --card: #fff;
  --border: #d6d0c6;
  --accent: #0b3d2e;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 1.25rem 1.5rem 3rem;
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  background: linear-gradient(180deg, #ebe6dc 0%, var(--bg) 220px);
  color: var(--ink); line-height: 1.4;
}}
h1 {{ margin: 0 0 0.35rem; font-size: 1.6rem; color: var(--accent); }}
.sub {{ color: var(--muted); margin-bottom: 1rem; }}
.summary {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.6rem; margin-bottom: 1.25rem;
}}
.metric {{
  background: var(--card); border: 1px solid var(--border);
  padding: 0.65rem 0.75rem; border-radius: 4px;
}}
.metric .label {{ font-size: 0.72rem; text-transform: uppercase; color: var(--muted); }}
.metric .value {{ font-size: 1.25rem; font-weight: 700; }}
.controls {{
  display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center;
  margin-bottom: 1rem; background: var(--card);
  border: 1px solid var(--border); padding: 0.75rem; border-radius: 4px;
}}
.controls input[type="search"], .controls select {{
  padding: 0.35rem 0.5rem; border: 1px solid var(--border); border-radius: 3px;
  min-width: 160px;
}}
.controls label {{ font-size: 0.9rem; display: inline-flex; gap: 0.35rem; align-items: center; }}
details.comp {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; margin-bottom: 0.75rem; padding: 0.35rem 0.6rem 0.6rem;
}}
details.comp summary {{ cursor: pointer; padding: 0.45rem 0.2rem; }}
table.teams {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-top: 0.4rem; }}
table.teams th, table.teams td {{
  border-bottom: 1px solid var(--border); padding: 0.35rem 0.45rem; text-align: left;
  vertical-align: top;
}}
table.teams th {{ font-size: 0.72rem; text-transform: uppercase; color: var(--muted); cursor: default; }}
table.teams th[data-sort] {{ cursor: pointer; text-decoration: underline dotted; }}
td.team {{ font-weight: 600; }}
.status.ok {{ background: var(--ok-bg); color: var(--ok); font-weight: 600; }}
.status.warn {{ background: var(--warn-bg); color: var(--warn); font-weight: 600; }}
.status.bad {{ background: var(--bad-bg); color: var(--bad); font-weight: 600; }}
.coverage.cov-full {{ color: var(--ok); }}
.coverage.cov-partial {{ background: var(--partial-bg); color: var(--partial); font-weight: 600; }}
.coverage.cov-none {{ color: var(--muted); }}
.diag {{ color: var(--muted); font-size: 0.8rem; max-width: 14rem; word-break: break-word; }}
tr.hidden {{ display: none; }}
details.comp.hidden {{ display: none; }}
</style>
</head>
<body>
<h1>Team Mapping Audit V2</h1>
<p class="sub">Report statico CSV Bet365 → CecchinoLabMatch dopo simulazione Alias Discovery V2 (solo lettura).</p>
<div class="summary">
  <div class="metric"><div class="label">Unique CSV teams</div><div class="value">{s.get("unique_csv_teams", 0)}</div></div>
  <div class="metric"><div class="label">Resolved</div><div class="value">{s.get("resolved_teams", 0)}</div></div>
  <div class="metric"><div class="label">Identity</div><div class="value">{s.get("identity", 0)}</div></div>
  <div class="metric"><div class="label">Static aliases</div><div class="value">{s.get("static_aliases", 0)}</div></div>
  <div class="metric"><div class="label">V2 trusted</div><div class="value">{s.get("v2_trusted_aliases", 0)}</div></div>
  <div class="metric"><div class="label">Unresolved</div><div class="value">{s.get("unresolved", 0)}</div></div>
  <div class="metric"><div class="label">Dubious</div><div class="value">{s.get("dubious", 0)}</div></div>
  <div class="metric"><div class="label">Resolved %</div><div class="value">{s.get("overall_resolved_pct", 0)}%</div></div>
  <div class="metric"><div class="label">FULL coverage</div><div class="value">{s.get("coverage_full", 0)}</div></div>
  <div class="metric"><div class="label">PARTIAL coverage</div><div class="value">{s.get("coverage_partial", 0)}</div></div>
  <div class="metric"><div class="label">NONE coverage</div><div class="value">{s.get("coverage_none", 0)}</div></div>
</div>
<div class="controls">
  <input id="search" type="search" placeholder="Cerca squadra…"/>
  <label>Status <select id="statusFilter"><option value="">Tutti</option>{status_opts_html}</select></label>
  <label>Campionato <select id="compFilter"><option value="">Tutti</option>{comp_opts_html}</select></label>
  <label><input id="problemsOnly" type="checkbox"/> Solo problemi</label>
</div>
{''.join(sections)}
<script>
(function() {{
  const search = document.getElementById('search');
  const statusFilter = document.getElementById('statusFilter');
  const compFilter = document.getElementById('compFilter');
  const problemsOnly = document.getElementById('problemsOnly');

  function applyFilters() {{
    const q = (search.value || '').trim().toLowerCase();
    const st = statusFilter.value || '';
    const comp = compFilter.value || '';
    const onlyProb = problemsOnly.checked;
    document.querySelectorAll('details.comp').forEach(function(sec) {{
      const secComp = sec.getAttribute('data-competition') || '';
      if (comp && secComp !== comp) {{
        sec.classList.add('hidden');
        return;
      }}
      let visible = 0;
      sec.querySelectorAll('tbody tr').forEach(function(tr) {{
        const team = tr.getAttribute('data-team') || '';
        const status = tr.getAttribute('data-status') || '';
        const problem = tr.getAttribute('data-problem') === '1';
        let ok = true;
        if (q && team.indexOf(q) === -1) ok = false;
        if (st && status !== st) ok = false;
        if (onlyProb && !problem) ok = false;
        tr.classList.toggle('hidden', !ok);
        if (ok) visible += 1;
      }});
      sec.classList.toggle('hidden', visible === 0 && (q || st || onlyProb || comp));
    }});
  }}
  [search, statusFilter, compFilter, problemsOnly].forEach(function(el) {{
    el.addEventListener('input', applyFilters);
    el.addEventListener('change', applyFilters);
  }});

  document.querySelectorAll('th[data-sort]').forEach(function(th) {{
    th.addEventListener('click', function() {{
      const key = th.getAttribute('data-sort');
      const table = th.closest('table');
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const asc = th.getAttribute('data-asc') !== '1';
      rows.sort(function(a, b) {{
        let av, bv;
        if (key === 'team') {{
          av = a.getAttribute('data-team') || '';
          bv = b.getAttribute('data-team') || '';
        }} else {{
          av = a.getAttribute('data-status') || '';
          bv = b.getAttribute('data-status') || '';
        }}
        if (av < bv) return asc ? -1 : 1;
        if (av > bv) return asc ? 1 : -1;
        return 0;
      }});
      th.setAttribute('data-asc', asc ? '1' : '0');
      rows.forEach(function(r) {{ tbody.appendChild(r); }});
    }});
  }});
}})();
</script>
</body>
</html>
"""


def write_team_mapping_audit_v2_reports(
    output_dir: str | Path,
    discovery: AliasDiscoveryV2Result,
) -> dict[str, str]:
    """Scrive team_mapping_audit_v2.csv/.html. Side-effect-free rispetto a DB/aliases."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = build_team_mapping_audit_rows(discovery)
    summary = build_team_mapping_audit_summary(rows)

    csv_path = out / "team_mapping_audit_v2.csv"
    html_path = out / "team_mapping_audit_v2.html"

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=AUDIT_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in AUDIT_CSV_COLUMNS})

    html_path.write_text(
        render_team_mapping_audit_html(rows, summary),
        encoding="utf-8",
    )
    return {
        "team_mapping_audit_v2_csv": str(csv_path),
        "team_mapping_audit_v2_html": str(html_path),
        "team_mapping_audit_v2_summary": summary,
    }
