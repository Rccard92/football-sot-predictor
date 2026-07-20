# Goal Intensity v5 — Audit classificazione artifact (Fase 3/3)

Snapshot architettura all'avvio consolidamento. Runtime counts: leggere dal DB, non hardcodare.

| Artifact | Classe | Note |
|----------|--------|------|
| cecchino_goal_intensity_v5_preview.py + models | canonical_active | Motore frozen; accesso via facade |
| cecchino_goal_intensity_v5.py (nuovo) | canonical_active | Facade pubblico |
| cecchino_goal_intensity_v5_readiness*.py (nuovo) | canonical_active | Readiness/governance monitoraggio |
| cecchino_goal_intensity_v5_candidate_indices.py | canonical_active / research_internal | Freeze + scoring |
| cecchino_goal_intensity_v5_audit_common.py | canonical_active | Feature extract |
| cecchino_goal_intensity_analysis.py (v4) | rollback_engine | Today JSON; non UI |
| CecchinoGoalIntensityAnalysisPanel.tsx | removable | Orfano |
| Lab research hooks/API | research_internal | Deprecati verso workspace |
| Tabelle *_preview_* | compatibility_required | Non rinominare |
