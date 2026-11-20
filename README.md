# Event live · aggiornamento automatico degli orari

Ogni notte GitHub scarica gli **orari ufficiali** (open data GTFS) di:
- **ARST** (autobus, e le linee ferroviarie ARST): https://www.arstspa.info/arst-cagliari-it.zip
- **Trenitalia Sardegna**: http://www.sardegnamobilita.it/opendata/dati_trenitalia.zip

e crea `data/orari.json`. L'app (`index.html`) lo legge all'apertura e lo usa al posto degli orari simulati.
I collegamenti per cui non esiste una corsa diretta nei dati ufficiali restano con orari stimati.

## Come attivarlo (una volta sola, ~5 minuti)
1. Crea un repository su GitHub e carica **tutti i file di questa cartella** (compresa la cartella nascosta `.github`).
2. Repository → **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main` / `(root)` → Save.
   L'app sarà online su `https://TUONOME.github.io/NOMEREPO/`.
3. Repository → **Settings → Actions → General → Workflow permissions** → *Read and write permissions* → Save.
4. Repository → **Actions → Aggiorna orari → Run workflow** per la prima esecuzione.
   Poi parte da solo ogni notte.

Nel log dell'esecuzione trovi quanti collegamenti hanno orari ufficiali (`links_with_real_data` in `data/orari.json`).

## Cose da sapere
- Il file di Trenitalia ha una data di scadenza (oggi fino al 12/12/2026): quando scade, i treni tornano agli orari stimati
  finché non viene pubblicato quello nuovo. Si aggiorna da solo alla prima esecuzione utile.
- `data/towns.json` e `data/links.json` descrivono le località e i collegamenti dell'app: se aggiungi località all'app vanno rigenerati.
- Gli orari sono quelli programmati, non il tempo reale (ritardi, soppressioni).
- Prezzi e tariffe restano simulati (nei dati ufficiali non ci sono).
