# Asset visivi — SOT Predictor

Cartella per screenshot e immagini usate nel README principale e nella documentazione pubblica del repository.

## File attesi

| File | Descrizione | Uso |
|------|-------------|-----|
| `sot-dashboard-preview.png` | Vista Prossima giornata / overview turno | README — colonna 1 Preview |
| `sot-audit-preview.png` | Spiegazione previsione / audit variabili | README — colonna 2 Preview |
| `sot-admin-preview.png` | Pannello Admin / pipeline ingestion | README — colonna 3 Preview |

## Linee guida

- **Formato:** PNG o WebP
- **Larghezza consigliata:** 1200–1600 px (GitHub ridimensiona automaticamente)
- **Contenuto:** evitare API key, URL con token, dati personali o quote reali visibili
- **Naming:** minuscolo, trattini (`sot-*-preview.png`)

## Come aggiungere screenshot

1. Catturare lo screenshot dall'app in esecuzione (locale o staging).
2. Salvare il file in questa cartella con il nome dalla tabella sopra.
3. Verificare che i path nel [README.md](../../README.md) corrispondano.
4. Committare solo immagini necessarie; evitare file troppo pesanti (> 500 KB se possibile).

## Stato attuale

Le immagini sono **placeholder**: finché i file PNG non vengono aggiunti, GitHub mostrerà link rotti nella sezione Preview del README. È intenzionale fino alla prima cattura screenshot.
