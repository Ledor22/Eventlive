# Eventlive — progetto con aggiornamento automatico

Questo repository contiene il sito Eventlive e gli script Python che aggiornano i dati.

## Struttura

- `index.html` — sito web originale.
- `data/towns.json`, `data/links.json`, `data/sources.json` — dati di configurazione originali.
- `data/eventi.json` — eventi raccolti automaticamente.
- `data/orari.json` — orari dei collegamenti, generati dai feed GTFS.
- `data/eventi_manuali.json` — eventuali eventi inseriti manualmente.
- `scripts/build_eventi.py` — raccoglie eventi da calendari iCal e, se configurato, Ticketmaster.
- `scripts/build_orari.py` — legge i feed GTFS di ARST e Trenitalia.
- `.github/workflows/aggiorna-eventlive.yml` — esegue gli aggiornamenti e pubblica il sito.

Gli script usano solo la libreria standard di Python: non serve installare pacchetti con pip.

## 1. Crea il repository GitHub

1. Accedi a <https://github.com/> e crea un account, se non ne hai già uno.
2. Premi **New repository**.
3. Dai un nome, per esempio `eventlive`.
4. Per il modo più semplice con GitHub Pages gratuito, scegli **Public**.
5. Crea il repository senza aggiungere README, `.gitignore` o licenza (sono già inclusi in questo progetto).

## 2. Carica TUTTO il progetto

1. Scarica ed estrai lo ZIP del progetto sul computer.
2. Apri il repository appena creato su GitHub.
3. Seleziona **Add file → Upload files**.
4. Trascina dentro tutti i file e le cartelle estratti, compresa la cartella nascosta `.github`.
5. Attendi il caricamento e premi **Commit changes**.

Controlla che nella pagina principale del repository si vedano `index.html`, `README.md`, `data`, `scripts` e `.github`. È importante caricare la cartella `.github/workflows`: senza di essa l'automazione non parte.

## 3. Attiva GitHub Pages

1. Nel repository apri **Settings → Pages**.
2. In **Build and deployment → Source**, scegli **GitHub Actions**.
3. Non scegliere “Deploy from a branch”: il workflow di questo progetto pubblica il sito tramite Actions.

Dopo il primo avvio riuscito, GitHub mostrerà l'indirizzo pubblico del sito nella sezione **Settings → Pages** e nella pagina dell'esecuzione del workflow.

## 4. Avvia e controlla l'automazione

1. Apri la scheda **Actions** del repository.
2. Se richiesto, abilita i workflow.
3. Apri **Aggiorna e pubblica Eventlive**.
4. Premi **Run workflow → Run workflow** per fare il primo avvio manuale.
5. Apri l'esecuzione per vedere i passaggi e gli eventuali errori.

Il workflow è programmato ogni giorno alle **03:30 UTC**. In Italia corrisponde alle **04:30 in ora solare** e alle **05:30 in ora legale**. GitHub può avviare i processi programmati con un po' di ritardo: non è un orario garantito al minuto.

A ogni esecuzione, il workflow prova ad aggiornare gli eventi e gli orari, salva i JSON se cambiano e pubblica nuovamente il sito. Se una fonte non è raggiungibile, i passaggi di aggiornamento sono tollerati e il sito viene comunque pubblicato usando i dati disponibili più recenti.

## 5. Configura le fonti degli eventi (IMPORTANTE)

Il file `data/sources.json` incluso nello ZIP originale contiene attualmente soltanto un esempio di calendario iCal disattivato (`enabled: false`) con un URL segnaposto. Quindi, senza configurare fonti reali, il raccoglitore non può trovare eventi da quei calendari.

Per aggiungere una fonte:

1. Apri `data/sources.json` su GitHub e premi la matita per modificarlo.
2. Sostituisci l'esempio con i calendari iCal pubblici reali dei comuni, Pro Loco, teatri o musei che vuoi usare.
3. Per ogni fonte indica `name`, `url`, `town` ed `enabled: true`.
4. Salva con **Commit changes**.

Esempio di struttura (sostituisci URL e comune con valori reali):

```json
{
  "ticketmaster": true,
  "ics": [
    {
      "name": "Nome calendario",
      "url": "https://indirizzo-reale/calendario.ics",
      "town": "Cagliari",
      "enabled": true
    }
  ]
}
```

Non usare un normale indirizzo di pagina web: serve l'URL diretto di un calendario iCal/ICS accessibile pubblicamente. Se una fonte non fornisce un calendario ICS, questo script non la può leggere così com'è.

## 6. (Facoltativo) Attiva Ticketmaster

Per raccogliere anche gli eventi disponibili tramite Ticketmaster:

1. Richiedi una chiave API tramite il portale sviluppatori Ticketmaster: <https://developer.ticketmaster.com/>.
2. Nel repository vai su **Settings → Secrets and variables → Actions**.
3. Premi **New repository secret**.
4. Nome: `TICKETMASTER_KEY`.
5. Valore: incolla la chiave API e salva.

Non inserire mai la chiave direttamente nei file del repository o nel codice HTML. Senza questo secret, Ticketmaster viene saltato; le altre fonti iCal configurate possono comunque essere elaborate.

## 7. Aggiornamento degli orari dei trasporti

Lo script usa i feed GTFS configurati al suo interno:

- ARST: `https://www.arstspa.info/arst-cagliari-it.zip`
- Trenitalia Sardegna: `http://www.sardegnamobilita.it/opendata/dati_trenitalia.zip`

Prova a scaricarli entrambi. Se una fonte non è disponibile, viene saltata; se nessuna fonte è scaricabile, il JSON esistente viene lasciato invariato e il workflow continua comunque con la pubblicazione.

## 8. Cosa viene aggiornato davvero

- Gli orari vengono ricalcolati quando i feed GTFS sono scaricabili e contengono dati validi.
- Gli eventi vengono aggiornati dalle fonti iCal che avrai configurato e da Ticketmaster se avrai aggiunto la chiave.
- Gli eventi manuali si possono inserire in `data/eventi_manuali.json`, nell'array `events`, rispettando il formato usato dallo script.
- Il sito pubblicato legge `data/orari.json` e `data/eventi.json` a ogni apertura.

**Nota:** l'automazione non garantisce che tutte le fonti pubblichino dati ogni giorno, né che ogni evento della Sardegna sia presente. Controlla la scheda Actions dopo i primi avvii e verifica i messaggi dei singoli passaggi.

## Esecuzione locale facoltativa

Con Python 3 installato, dalla cartella principale del progetto:

```bash
python scripts/build_eventi.py
python scripts/build_orari.py
```

Apri il sito tramite un server statico locale (non necessariamente con doppio clic sul file) per verificare il caricamento dei JSON dalla cartella `data`.
