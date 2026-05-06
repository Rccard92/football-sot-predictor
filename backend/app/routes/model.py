from fastapi import APIRouter

from app.core.constants import BASELINE_SOT_MODEL_VERSION, BASELINE_SOT_MODEL_VERSION_V02
from app.schemas.model import ModelLegendResponse
from app.services.sot_prediction_service import WEIGHTS_BASELINE_V0_1

router = APIRouter(prefix="/model", tags=["model"])


@router.get("/legend", response_model=ModelLegendResponse)
def get_model_legend() -> ModelLegendResponse:
    w = WEIGHTS_BASELINE_V0_1
    return ModelLegendResponse(
        model_version="baseline_v0_2_player_adjusted",
        title="Legenda modello tiri in porta",
        description=(
            "Questa legenda mostra quali fattori vengono usati per stimare "
            "i tiri in porta attesi di una squadra."
        ),
        expected_sot_formula=(
            "baseline_expected_sot (v0.1) = 0.30 × media stagionale squadra + 0.25 × media concessa avversario "
            "+ 0.15 × media casa/fuori squadra + 0.10 × media concessa casa/fuori avversario "
            "+ 0.10 × ultime 5 squadra + 0.10 × ultime 5 concesse avversario\n"
            "adjusted_expected_sot (v0.2 player adjusted) = baseline_expected_sot + player_adjustment"
        ),
        sections=[
            {
                "id": "baseline_formula",
                "title": "Baseline v0.1 (modello squadra puro)",
                "status": "applicata",
                "description": "Questa sezione è la formula storica della baseline v0.1 e resta invariata.",
                "variables": [
                    {
                        "technical_key": "season_avg_sot_for",
                        "name": "Media stagionale tiri in porta fatti",
                        "description": (
                            "Misura quanti tiri in porta produce mediamente la squadra "
                            "nella stagione prima della partita."
                        ),
                        "weight": w["season_avg_sot_for"],
                        "weight_label": "30%",
                        "status": "applicata",
                        "impact": "Aumenta expected_sot quando la produzione media è alta.",
                        "interpretation": "Più è alta, più aumenta la previsione.",
                    },
                    {
                        "technical_key": "opponent_season_avg_sot_conceded",
                        "name": "Tiri in porta concessi dall’avversario",
                        "description": "Misura quanti tiri in porta concede mediamente l’avversario.",
                        "weight": w["opponent_season_avg_sot_conceded"],
                        "weight_label": "25%",
                        "status": "applicata",
                        "impact": "Aumenta expected_sot se l’avversario concede tanto.",
                        "interpretation": (
                            "Se l’avversario concede tanto, la previsione della squadra aumenta."
                        ),
                    },
                    {
                        "technical_key": "home_away_avg_sot_for",
                        "name": "Media casa/fuori della squadra",
                        "description": (
                            "Misura il rendimento della squadra nello stesso contesto "
                            "della partita: casa o trasferta."
                        ),
                        "weight": w["home_away_avg_sot_for"],
                        "weight_label": "15%",
                        "status": "applicata",
                        "impact": "Corregge expected_sot sul contesto casa/trasferta.",
                        "interpretation": "Serve a distinguere squadre più forti in casa o fuori.",
                    },
                    {
                        "technical_key": "opponent_home_away_avg_sot_conceded",
                        "name": "Tiri concessi dall’avversario casa/fuori",
                        "description": (
                            "Misura quanto concede l’avversario quando gioca nello stesso "
                            "contesto della partita."
                        ),
                        "weight": w["opponent_home_away_avg_sot_conceded"],
                        "weight_label": "10%",
                        "status": "applicata",
                        "impact": "Regola expected_sot sul comportamento contestuale dell’avversario.",
                        "interpretation": "Aiuta a capire se l’avversario concede di più in casa o fuori.",
                    },
                    {
                        "technical_key": "last5_avg_sot_for",
                        "name": "Forma recente della squadra",
                        "description": (
                            "Media dei tiri in porta prodotti dalla squadra "
                            "nelle ultime 5 partite disponibili."
                        ),
                        "weight": w["last5_avg_sot_for"],
                        "weight_label": "10%",
                        "status": "applicata",
                        "impact": "Adatta expected_sot al trend più recente.",
                        "interpretation": "Serve a intercettare trend recenti.",
                    },
                    {
                        "technical_key": "opponent_last5_avg_sot_conceded",
                        "name": "Forma recente difensiva dell’avversario",
                        "description": (
                            "Media dei tiri in porta concessi dall’avversario nelle ultime 5 partite."
                        ),
                        "weight": w["opponent_last5_avg_sot_conceded"],
                        "weight_label": "10%",
                        "status": "applicata",
                        "impact": "Aumenta expected_sot quando l’avversario concede tanto di recente.",
                        "interpretation": (
                            "Se l’avversario concede tanto di recente, la previsione aumenta."
                        ),
                    },
                ],
            },
            {
                "id": "baseline_v02_context_player",
                "title": "Modello live v0.2 Player Adjusted",
                "status": "applicata",
                "description": (
                    "Il modello live parte dalla baseline v0.1 e applica una correzione prudente "
                    "basata sull’impatto giocatori."
                ),
                "variables": [
                    {
                        "technical_key": "model_version_v01",
                        "name": "Versione baseline storica",
                        "description": "Versione di partenza del calcolo.",
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata",
                        "impact": "Mantiene compatibilità con la baseline originale.",
                        "interpretation": f"Valore: {BASELINE_SOT_MODEL_VERSION}",
                    },
                    {
                        "technical_key": "model_version_v02",
                        "name": "Versione adjustment contestuali",
                        "description": "Nuova versione con correzioni spiegabili.",
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata",
                        "impact": "Aggiunge correzioni prudenti senza sostituire v0.1.",
                        "interpretation": f"Valore: {BASELINE_SOT_MODEL_VERSION_V02}",
                    },
                    {
                        "technical_key": "expected_sot_v02_formula",
                        "name": "Formula v0.2",
                        "description": (
                            "adjusted_expected_sot = baseline_expected_sot + player_adjustment"
                        ),
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata",
                        "impact": "Calcola il valore aggiustato finale per team.",
                        "interpretation": "Somma baseline v0.1 + correzione giocatori (prudente).",
                    },
                    {
                        "technical_key": "adjustment_caps",
                        "name": "Cap adjustment",
                        "description": "Cap player_adjustment: ±0.35 (gli altri layer non sono ancora applicati).",
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata",
                        "impact": "Evita correzioni eccessive e migliora robustezza.",
                        "interpretation": "Le correzioni restano prudenti e tracciabili.",
                    },
                ],
            },
            {
                "id": "player_impact",
                "title": "Impatto giocatori",
                "status": "applicata",
                "description": (
                    "La correzione giocatori è applicata nel modello live v0.2 Player Adjusted. "
                    "Non è applicata nella baseline storica v0.1."
                ),
                "variables": [
                    {
                        "technical_key": "shots_on_target_per90",
                        "name": "Tiri in porta per 90 minuti",
                        "description": "Misura quanti tiri in porta produce il giocatore ogni 90 minuti.",
                        "weight": 0.60,
                        "weight_label": "60%",
                        "status": "applicata",
                        "impact": "Aiuta a stimare il contributo offensivo individuale.",
                        "interpretation": "Valori più alti indicano giocatori più presenti al tiro.",
                    },
                    {
                        "technical_key": "team_sot_share_pct",
                        "name": "Quota dei tiri in porta della squadra",
                        "description": (
                            "Indica quanto il giocatore pesa sulla produzione totale "
                            "di tiri in porta della squadra."
                        ),
                        "weight": 0.25,
                        "weight_label": "25%",
                        "status": "applicata",
                        "impact": "Misura centralità del giocatore nel volume offensivo.",
                        "interpretation": (
                            "Percentuali alte suggeriscono dipendenza della squadra da quel giocatore."
                        ),
                    },
                    {
                        "technical_key": "reliability_score",
                        "name": "Affidabilità del campione",
                        "description": "Tiene conto di minuti giocati e presenze.",
                        "weight": 0.15,
                        "weight_label": "15%",
                        "status": "applicata",
                        "impact": "Riduce il peso di campioni piccoli o poco stabili.",
                        "interpretation": (
                            "Più è alto, più il profilo è statisticamente affidabile."
                        ),
                    },
                    {
                        "technical_key": "impact_score_formula",
                        "name": "Formula player impact",
                        "description": (
                            "impact_score = 0.60 × tiri in porta per 90 normalizzati + "
                            "0.25 × quota tiri squadra + 0.15 × affidabilità"
                        ),
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata",
                        "impact": "Usata per stimare la correzione giocatori nel modello live v0.2.",
                        "interpretation": (
                            "Nei match futuri la correzione è prudente e tracciabile nel breakdown."
                        ),
                    },
                ],
            },
            {
                "id": "h2h",
                "title": "Scontri diretti",
                "status": "solo_debug",
                "description": (
                    "Gli scontri diretti aiutano a leggere il contesto storico tra due squadre, "
                    "ma al momento non modificano matematicamente expected_sot."
                ),
                "variables": [
                    {
                        "technical_key": "matches_total",
                        "name": "Partite H2H nel campione",
                        "description": "Numero di scontri diretti conclusi considerati nel riepilogo.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Solo lettura del contesto storico.",
                        "interpretation": "Campione più ampio rende il riepilogo più robusto.",
                    },
                    {
                        "technical_key": "home_team_wins",
                        "name": "Vittorie squadra casa negli H2H",
                        "description": "Conteggio vittorie lato casa nel campione storico.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Nessun impatto diretto sul calcolo expected_sot.",
                        "interpretation": "Aiuta a contestualizzare l'equilibrio storico.",
                    },
                    {
                        "technical_key": "away_team_wins",
                        "name": "Vittorie squadra trasferta negli H2H",
                        "description": "Conteggio vittorie lato trasferta nel campione storico.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Nessun impatto diretto sul calcolo expected_sot.",
                        "interpretation": "Aiuta a leggere eventuali trend storici sfavorevoli/favorevoli.",
                    },
                    {
                        "technical_key": "draws",
                        "name": "Pareggi negli H2H",
                        "description": "Conteggio pareggi nel campione storico.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Nessun impatto diretto sul calcolo expected_sot.",
                        "interpretation": "Indica livello di equilibrio storico tra le squadre.",
                    },
                    {
                        "technical_key": "avg_total_goals",
                        "name": "Media gol totali H2H",
                        "description": "Media gol totali nelle partite H2H concluse del campione.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Indicatore descrittivo, non usato nella formula baseline.",
                        "interpretation": "Suggerisce se gli scontri storici sono stati più o meno aperti.",
                    },
                    {
                        "technical_key": "avg_total_sot",
                        "name": "Media tiri in porta totali H2H",
                        "description": "Media tiri in porta totali H2H se il dato è disponibile nel DB.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Indicatore descrittivo, non usato nella formula baseline.",
                        "interpretation": "Utile solo come contesto aggiuntivo.",
                    },
                    {
                        "technical_key": "h2h_sample_limited",
                        "name": "Campione H2H limitato",
                        "description": "Flag che segnala un numero ridotto di match storici disponibili.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Aumenta cautela interpretativa sul riepilogo H2H.",
                        "interpretation": "Se vero, leggere i dati H2H con prudenza.",
                    },
                ],
            },
            {
                "id": "match_context",
                "title": "Contesto e motivazione partita",
                "status": "solo_debug",
                "description": (
                    "Questo layer valuta il peso reale della partita, soprattutto a fine stagione. "
                    "Al momento genera warning e note di prudenza, ma non modifica ancora expected_sot."
                ),
                "variables": [
                    {
                        "technical_key": "motivation_level",
                        "name": "Livello motivazione",
                        "description": "Stima qualitativa della motivazione della squadra.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Warning qualitativo, nessun impatto matematico.",
                        "interpretation": "Aiuta a capire quanto la classifica può influire sull'approccio gara.",
                    },
                    {
                        "technical_key": "competition_objective",
                        "name": "Obiettivo competitivo",
                        "description": (
                            "Classifica l'obiettivo principale: titolo, champions, europa, salvezza o incerto."
                        ),
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Solo contesto qualitativo.",
                        "interpretation": "Fornisce un quadro sintetico della posta in palio.",
                    },
                    {
                        "technical_key": "turnover_risk",
                        "name": "Rischio turnover",
                        "description": "Stima prudenziale del rischio di rotazioni.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Solo warning di prudenza.",
                        "interpretation": "Non implica certezze sulle formazioni.",
                    },
                    {
                        "technical_key": "late_season_risk",
                        "name": "Rischio fine stagione",
                        "description": "Flag che segnala round avanzato e maggiore variabilità del contesto.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Solo warning di affidabilità contestuale.",
                        "interpretation": "A fine stagione il modello va letto con maggiore cautela.",
                    },
                    {
                        "technical_key": "risk_flags",
                        "name": "Flag di rischio partita",
                        "description": "Elenco sintetico di segnali di rischio estratti dal contesto.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Solo warning in UI.",
                        "interpretation": "Aiuta a individuare partite da interpretare con prudenza.",
                    },
                    {
                        "technical_key": "overall_match_importance",
                        "name": "Importanza complessiva partita",
                        "description": "Valutazione complessiva dell'importanza competitiva del match.",
                        "weight": None,
                        "weight_label": None,
                        "status": "solo_debug",
                        "impact": "Informazione contestuale, non entra nella formula.",
                        "interpretation": "Sintesi finale del contesto motivazionale.",
                    },
                ],
            },
            {
                "id": "confidence",
                "title": "Affidabilità della previsione",
                "status": "applicata_alla_lettura",
                "description": (
                    "Queste metriche aiutano a leggere il risultato, ma non cambiano expected_sot."
                ),
                "variables": [
                    {
                        "technical_key": "data_quality_score",
                        "name": "Qualità dati",
                        "description": "Misura la completezza dei dati disponibili.",
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata_alla_lettura",
                        "impact": "Migliora o riduce la fiducia nella lettura del risultato.",
                        "interpretation": "Può essere alta anche se la previsione non è perfetta.",
                    },
                    {
                        "technical_key": "prediction_confidence_score",
                        "name": "Affidabilità previsione",
                        "description": (
                            "Misura quanto leggere con fiducia la previsione, considerando anche il backtest."
                        ),
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata_alla_lettura",
                        "impact": "Guida l'interpretazione finale del numero previsto.",
                        "interpretation": (
                            "Nel modello baseline_v0_1 è limitata in modo prudente perché il MAE è circa 1.76."
                        ),
                    },
                    {
                        "technical_key": "mae",
                        "name": "MAE",
                        "description": "Errore medio assoluto del modello.",
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata_alla_lettura",
                        "impact": "Riferimento chiave per valutare l'errore medio atteso.",
                        "interpretation": (
                            "Sotto 1.50 = buono; 1.50-2.00 = accettabile; sopra 2.00 = da migliorare."
                        ),
                    },
                    {
                        "technical_key": "rmse",
                        "name": "RMSE",
                        "description": "Errore che penalizza maggiormente gli scostamenti grandi.",
                        "weight": None,
                        "weight_label": None,
                        "status": "applicata_alla_lettura",
                        "impact": "Evidenzia presenza di partite con errori più ampi.",
                        "interpretation": "Serve a capire se ci sono partite in cui il modello sbaglia molto.",
                    },
                ],
            },
            {
                "id": "not_yet_applied",
                "title": "Fattori non ancora applicati",
                "status": "non_applicata",
                "description": (
                    "Questi fattori sono monitorati o pianificati, ma non entrano "
                    "ancora nel calcolo matematico della baseline."
                ),
                "variables": [
                    {
                        "technical_key": "expected_lineups",
                        "name": "Probabili formazioni",
                        "description": "Probabili pre-partita da integrare in versioni future.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Per ora da verificare con fonti esterne.",
                    },
                    {
                        "technical_key": "official_lineups",
                        "name": "Formazioni ufficiali",
                        "description": "Formazioni confermate poco prima del match.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Non ancora integrate nella formula.",
                    },
                    {
                        "technical_key": "injuries_absences",
                        "name": "Infortuni/assenze/squalifiche",
                        "description": "Eventi disponibilità giocatori durante la stagione.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Per ora solo contesto informativo.",
                    },
                    {
                        "technical_key": "bookmaker_odds_auto",
                        "name": "Quote bookmaker automatiche",
                        "description": "Import automatico quote e segnali mercato.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "La linea bookmaker resta un input manuale di lettura.",
                    },
                    {
                        "technical_key": "player_impact_in_formula",
                        "name": "Player impact nella formula finale",
                        "description": "Integrazione diretta di impact_score nel calcolo expected_sot.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Previsto in evoluzioni future del modello.",
                    },
                    {
                        "technical_key": "h2h_in_formula",
                        "name": "H2H nella formula finale",
                        "description": "Uso quantitativo del contesto scontri diretti.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Per ora H2H resta solo supporto di lettura.",
                    },
                    {
                        "technical_key": "motivation_context_in_formula",
                        "name": "Motivation context nella formula finale",
                        "description": "Integrazione quantitativa del layer motivazionale.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Per ora il layer motivation produce solo warning.",
                    },
                    {
                        "technical_key": "turnover_estimated_in_formula",
                        "name": "Turnover stimato nella formula finale",
                        "description": "Correzione numerica da rischio rotazioni.",
                        "weight": None,
                        "weight_label": None,
                        "status": "non_applicata",
                        "impact": "Nessun impatto su expected_sot baseline.",
                        "interpretation": "Stima non ancora incorporata matematicamente.",
                    },
                ],
            },
        ],
    )
