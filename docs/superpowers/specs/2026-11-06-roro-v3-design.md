# RoRo Yield Optimizer v3: strumento per planner e gioco

Data: 2026-11-06. Stato: bozza da approvare. Branch: `v3`.
Riferimenti: `README.md` (Roadmap), `docs/superpowers/specs/2026-11-03-roro-yield-optimizer-v2-design.md`.

## 1. Perché

La v2 è una demo giocabile su Streamlit. Dimostra che accettare le richieste con criterio rende più del primo arrivato, ma ha quattro limiti:

- non si può usare su prenotazioni vere;
- l'Advisor non ha una previsione legata al singolo sailing e, con domanda bassa, a volte rifiuta clienti per piccoli guadagni attesi: un collega l'ha definito "gioco d'azzardo";
- l'Advisor conosce il numero esatto di richieste, cosa impossibile nella realtà;
- Streamlit limita grafica e interazione.

La v3 trasforma il progetto in uno **strumento per planner**, conserva il **gioco** come demo e diventa la base di una possibile startup. Il link v2 per la candidatura DFDS resta stabile: la v3 ha un link proprio e non ha scadenza legata all'8 novembre.

Risultati già misurati (90 sailing simulati, K = 20, punteggio medio):

| Metodo | Punteggio |
|---|---|
| FCFS | 39.616 |
| Planner v2 | 42.287 |
| Volume esatto noto | 42.447 |
| Previsione semplice dal ritmo | 41.836 |
| Informazione perfetta | 46.338 |

Il planner perde contro FCFS soprattutto con domanda bassa (9 sailing su 30), molto meno con domanda alta (1 su 30). Conclusione: la prima leva è una regola di decisione prudente; la previsione del solo volume, da sola, rende poco.

## 2. Obiettivi

1. **Planner:** caricare un Excel di prenotazioni accettate, ottenere un piano del ponte, valutare nuove richieste e aggiornare il piano.
2. **Gioco:** mantenere Game, Reveal e Lab, aggiungendo gli spostamenti suggeriti dall'Advisor.
3. **Sei funzioni:** spazio perso; spazio riservato per cliente; PDF e link condivisibile; navi predefinite; più porti di scarico; altezze, carico ponte e assi.
4. **Decisioni con rischio misurato:** l'Advisor mostra incertezza e dice "decidi tu" quando i futuri simulati non sono d'accordo.
5. **Previsione a 3 livelli**, tenuta solo se migliora un riferimento semplice.
6. **Pubblicazione gratuita** su Hugging Face Spaces.

## 3. Non obiettivi

- Sostituire un loading computer certificato o decidere la sicurezza della nave.
- Ponti sollevabili (hoistable) e car carrier.
- Più porti di carico: la v3 gestisce **un porto di carico e più porti di scarico**.
- Overbooking, prezzi dinamici, rete di più sailing.
- Griglia dettagliata del ponte, percorsi, ostacoli e reinforcement learning: restano in "Later" nel README.
- Account utenti, multi-azienda, database persistente.

**Anti-obiettivi.** Il progetto fallisce, anche se funziona tecnicamente, se:

- presenta risultati simulati come risultati reali;
- nasconde i casi in cui il planner perde;
- rifiuta o toglie in silenzio una prenotazione accettata;
- copia codice, testi, tabelle o grafica di Logisoft o di altri prodotti.

## 4. Vincoli

- **Hosting (aggiornato 2026-11-09):** Hugging Face ha reso a pagamento le Space Docker ($9/mese), quindi il proprietario ha scelto Google Cloud Run, gratuito entro le soglie, con avviso di budget a 1 €, fatturazione basata sulle istanze e massimo 1 istanza. Misure dal vivo: verdetto mediano 2,5 s (max 2,7 s), primo piano 3,3 s. Il trigger pubblica ogni push su `v3`, quindi il lavoro di ogni tappa avviene su un branch dedicato e arriva su `v3` solo con l'ok del proprietario. Testo originale: solo Hugging Face Spaces gratuito (2 vCPU, 16 GB, Docker). Lo spazio va in pausa dopo un periodo senza visite. Da verificare: tempo di riavvio e conservazione dei file. Il progetto non deve dipendere da file salvati sul server.
- **Costi:** nessuna spesa senza ok esplicito del proprietario.
- **Solver:** HiGHS. Gurobi resta fuori dalla v3: la licenza sul PC è accademica e non commerciale.
- **Lingua:** app, README e commenti del codice in inglese. Questo documento è in italiano perché il proprietario deve approvarlo.
- **Metodo:** Superpowers per tutto il lavoro. Interfaccia con UI UX Pro Max se installata.
- **Dati:** niente dati DFDS o di clienti reali nel repository. Un Excel caricato resta in memoria per la sessione e non viene salvato.
- **`main` e `v2`:** non ricevono commit della v3.

## 5. Approcci considerati

| Approccio | Vantaggi | Svantaggi | Esito |
|---|---|---|---|
| **React + FastAPI in un servizio** | un link e un deploy, grafica libera, buona base per un prodotto | più lavoro di Streamlit | **scelto** dal proprietario |
| React e FastAPI separati | scala meglio, pagina veloce anche col server in pausa | due deploy e configurazione aggiuntiva | scartato per ora; passaggio possibile in seguito |
| Solo Python (per esempio Reflex) | un linguaggio solo, partenza rapida | meno controllo grafico, base debole per un prodotto | scartato |

**Hosting.** Il proprietario ha scelto solo Hugging Face Spaces. Scartati: Fly.io, Hetzner e Render (a pagamento o meno adatti), Koyeb (0,25 vCPU), Oracle (gestione manuale), Cloudflare (i Workers gratuiti non reggono il solver; i Containers costano da $5 al mese).

**Profondità.** Il proprietario ha scelto la versione semplificata degli approcci Ränkeskog (2023) e Main (2024). La versione pesante resta in roadmap.

## 6. Decisioni

### Prese dal proprietario

- Link separato; `v2` stabile.
- FastAPI + React, un solo servizio, su Hugging Face Spaces.
- L'area Planner è il prodotto; il gioco resta.
- L'Excel contiene **solo prenotazioni accettate, tutte obbligatorie**. Non esiste lo stato "promessa".
- Oltre all'Excel possono arrivare nuove richieste.
- Anche nel gioco le unità si possono spostare e l'Advisor deve dire quale spostare.
- Tutte e 6 le funzioni entrano nella v3.
- Previsione con machine learning su dati pubblici, se disponibili, nei limiti di ciò che quei dati permettono.

### Proposte da Claude, da confermare leggendo

- Ponte standard 5 × 120 m (600 m), presentato come sailing ad alta domanda, sempre accanto ai risultati con domanda bassa, normale e alta.
- Ordine delle tappe della sezione 11.
- Il Planner è la pagina principale; il gioco è una sezione ben visibile.
- Costo di uno spostamento nel gioco: €80 a unità, pari a `HANDLING_PER_UNIT`.
- In modalità automatica "decidi tu" equivale ad accettare.

## 7. Architettura

```text
roro_yield/   engine Python, senza dipendenze dall'interfaccia
server/       API FastAPI, jobs, import ed export
web/          React + TypeScript (Vite), servito come file statici da FastAPI
benchmarks/   confronti ripetibili con seed fissi
data/public/  dati pubblici con fonte, data e licenza
Dockerfile    build multi-stage, porta 7860
```

- `app/` e `streamlit_app.py` non vengono portati nella v3 una volta raggiunta la parità della tappa 0. Le parti utili, come `JobRunner` e la cache, passano in `server/` senza dipendenze da Streamlit.
- **Stato:** il browser conserva piano e prenotazioni. Le chiamate API ricevono ciò che serve e restituiscono il risultato. Il server tiene solo job in corso e cache in memoria, con scadenza. Dopo un riavvio i job in corso si perdono: l'interfaccia lo segnala e propone di rilanciarli; il lavoro del planner resta nel browser.
- **Calcoli lunghi:** `POST` crea un job e una richiesta ripetuta ne legge stato e avanzamento. Al massimo 2 job di calcolo contemporanei, gli altri in coda. Con il limite di 2 vCPU, i job lunghi devono poter essere annullati.
- **Link condivisibile:** il piano viene compresso e messo nella parte `#` dell'URL, quindi non passa dal server. Se il piano è troppo grande per un link, l'app offre un file `.json` da scaricare e ricaricare.
- **Sicurezza:** Excel di massimo 5 MB e 500 righe, solo `.xlsx`, senza eseguire macro. Limiti di dimensione anche sulle richieste API.
- **Pagina di riavvio:** Hugging Face mostra la propria pagina durante il risveglio. Il tempo va misurato alla tappa 0 e indicato nel README.

## 8. Modello dei dati

Le modifiche estendono i tipi esistenti e mantengono i valori di default, così il comportamento della v2 si riproduce nei test.

- `Booking`: aggiunge `discharge_port`, `height_m`, `axle_count`, `on_board` (bool). Le ultime tre derivano da `UNIT_TYPES` se assenti.
- `Lane`: aggiunge `deck_id`. `Slot(lane_id, zone)` resta invariato; gli identificativi delle corsie diventano unici su tutta la nave (per esempio `D2-L3`).
- `Deck` (nuovo): `id`, `clear_height_m`, `max_load_t_per_m2`, `max_axle_t`.
- `Vessel`: aggiunge `decks`, `broken_stowage_pct`, `ports`. I valori di default rappresentano un solo ponte senza spazio perso.
- `Reservation` (nuovo): `customer`, `metres`.
- `Move` (nuovo): `booking_id`, `from_slot`, `to_slot`, `cost_eur`.
- `Verdict`: `accept: bool` diventa `decision: "accept" | "reject" | "your_call"`. Aggiunge `pays_off_share`, `gain_low`, `gain_high`, `moves`. Il `text` esistente viene aggiornato.
- `DemandModel` (nuovo): sostituisce l'uso diretto di `ScenarioParams` nell'Advisor. Espone il campionamento del futuro (richieste rimanenti comprese) dopo un dato momento. Quindi il numero di richieste rimanenti non è più un valore noto.
- `PolicyView`: `n_total` non viene più letto dall'Advisor quando usa un `DemandModel` incerto.

## 9. Comportamento

### 9.1 Planner

1. Il planner sceglie una nave predefinita o modifica la propria, imposta i porti e lo spazio perso.
2. Carica l'Excel. Il server verifica ogni riga e restituisce tutti gli errori con numero di riga e motivo, senza importare parzialmente. L'app offre un modello `.xlsx`.
3. L'ottimizzatore cerca un piano con tutte le prenotazioni caricate.
4. **Se le accettate non ci stanno:** nessuna viene tolta in silenzio. L'app mostra il miglior piano parziale, l'elenco delle unità escluse con il motivo e chiede al planner di decidere. Tecnicamente: una variabile di esclusione con penale molto alta nel modello, usata solo per trovare il minimo numero di metri non caricabili.
5. Una nuova richiesta passa dall'Advisor, che mostra decisione, guadagno atteso con intervallo e quota di futuri favorevoli.
6. Se il planner accetta, il piano viene rifatto. Le unità con `on_board = true` restano ferme; le altre possono cambiare posizione senza costo fisico, perché esistono solo sulla carta.
7. Il planner può segnare un'unità come a bordo e può spostare a mano un'unità, se i vincoli lo permettono.
8. Esporta PDF, CSV o link.

L'ipotesi di domanda futura è sempre visibile: "Assumption: high demand, 45% contract".

### 9.2 Gioco

- Game, Reveal e Lab mantengono il comportamento v2.
- Il giocatore può spostare un'unità già caricata: ogni spostamento costa €80 e riduce il punteggio.
- Se una richiesta non entra o rende di più con un riordino, l'Advisor propone al massimo 2 spostamenti. Li mostra solo se il guadagno atteso supera il costo: "Move B012 from L2-Z1 to L4-Z3: fits this trailer, about +€X".
- `objective` include il costo degli spostamenti, così tutti i metodi restano confrontabili.
- Il gioco continua a usare il simulatore e mostra "Synthetic data".
- Il gioco mantiene "request k of n", dato che fa parte delle regole. Il Reveal indica se il planner confrontato conosceva n.

### 9.3 Advisor a tre risposte

Per ogni futuro campionato si calcola il guadagno, come nella v2. Poi:

- **accept** se media > 0 e la quota di futuri favorevoli è almeno `ACCEPT_SHARE`;
- **reject** se media < 0 e la quota di futuri sfavorevoli è almeno `REJECT_SHARE`;
- **your_call** negli altri casi.

Soglie iniziali: `ACCEPT_SHARE = 0,6`, `REJECT_SHARE = 0,8`, poi calibrate alla tappa 3 con seed diversi da quelli di verifica.

L'intervallo mostrato è tra il 10° e il 90° percentile dei guadagni.

Test separato (nessuna modifica al prodotto se non convince): confrontare i K futuri con una regola a valore atteso, in linea con Main (2024). Se regge, può ridurre i tempi.

### 9.4 Spazio perso

`broken_stowage_pct` riduce la lunghezza utile di ogni zona. Valore di default per il planner: 15%; la demo gioco mantiene 0 per restare confrontabile con la v2, salvo decisione diversa dopo i test. Il Lab lo mostra come cursore.

### 9.5 Spazio riservato

Una `Reservation` tiene metri per un cliente su tutta la nave. Il modello impone: metri caricati + quota riservata non ancora usata ≤ capacità. Il cliente riservatario consuma la propria quota; gli altri non possono usarla. La riserva è un vincolo rigido finché il planner non la rilascia. Non è legata a una zona o a un ponte nella v3.

### 9.6 Navi predefinite

Valori arrotondati e scritti da noi, mai riferiti a navi con nome: la demo da 600 m, un RoPax merci e un RoRo short-sea. Tutti i valori sono modificabili. Se nave e prenotazioni rendono il modello troppo grande per i tempi della sezione 12, l'app lo dice.

### 9.7 Più porti di scarico

- Un porto di carico, N porti di scarico in ordine (massimo 5).
- La rampa è a poppa: zona 0 più vicina all'uscita.
- Un'unità che scarica prima, ma sta dietro un'unità che scarica dopo, genera uno spostamento atteso.
- Il modello aggiunge un costo per ogni blocco stimato, così preferisce un ordine di scarico pulito senza renderlo obbligatorio. Il piano mostra il numero di blocchi.
- La stabilità viene verificata alla partenza. Il controllo dopo ogni scarico è fuori dalla v3 ed è dichiarato nell'app.

### 9.8 Altezze, carico ponte e assi

- Più ponti, ciascuno con le proprie corsie.
- Un'unità può andare su un ponte solo se `height_m` + margine ≤ `clear_height_m` e il carico per asse è entro `max_axle_t`.
- Il carico per zona rispetta `max_load_t_per_m2`, usando l'area della zona.
- La stabilità resta lineare e non considera l'altezza verticale del carico: limite dichiarato nell'app.
- `why_not` spiega ogni rifiuto (altezza, assi, carico ponte).

### 9.9 PDF

Generato sul server con ReportLab: nave, porti, KPI, piano per ponte, unità escluse, ipotesi usate e l'avviso "Planning estimate, not a loading computer".

### 9.10 Previsione

**Livello 1: ipotesi.** Il planner sceglie domanda bassa, normale o alta, quota contract e prezzi. L'Advisor campiona da questo `DemandModel`.

**Livello 2: dati pubblici.** Fonti candidate: volumi mensili DFDS, statistiche portuali UK, Eurostat. Prima dell'uso vanno verificati formato, copertura e licenza di ognuna. Una serie viene scartata se non può essere usata legalmente o non è adatta.

- Obiettivo: stimare il livello mensile atteso rispetto alla media dell'anno.
- Riferimento da battere: lo stesso mese dell'anno prima, corretto per il trend.
- Verifica: test su periodi futuri in sequenza, mai dati mescolati.
- Modello: LightGBM o modello più semplice, scelto dal test. Se nessuno batte il riferimento, si usa il riferimento e lo si dichiara.
- Uso: il livello stimato sceglie il `DemandModel` iniziale, che il planner può cambiare. Il dettaglio del sailing resta simulato e viene etichettato così.

**Livello 3: storico aziendale.** Fuori dalla prima consegna. La v3 definisce e documenta il formato del file storico. Il training con LightGBM, compresa la stima delle prenotazioni che non partono (Ränkeskog, 2023), parte quando c'è un dataset reale. La stima resta un indicatore di rischio, senza overbooking.

**Criterio generale:** una previsione entra nell'app solo se il benchmark mostra un miglioramento; altrimenti resta un'ipotesi visibile, non una promessa di risultato.

### 9.11 Regole di dettaglio (scelte di Claude dopo la revisione)

**Excel.** Colonne obbligatorie: `booking_id`, `customer`, `unit_type`, `length_m`, `weight_t`, `discharge_port`. Facoltative: `segment`, `is_reefer`, `rate_per_m`, `reefer_fee`, `height_m`, `axle_count`, `on_board`. Le accettate sono obbligatorie, quindi il prezzo serve solo ai KPI: se manca, l'app mostra i ricavi come non disponibili. Il minimo contrattuale v2 non si applica al Planner: il suo posto è preso dalle riserve per cliente.

**Nuova richiesta.** Il planner deve indicare anche prezzo per metro e segmento, perché senza un valore l'Advisor non può confrontarla con i futuri.

**Obiettivo del Planner.** In ordine: massimizzare i metri caricati; ridurre blocchi di scarico; ridurre il costo di zavorra; ridurre i cambi rispetto al piano precedente. Le prime due fasi sono solve successivi, con il tempo totale entro i limiti della sezione 12. Le unità escluse non contano in capacità, stabilità e ricavi.

**Rifacimento del piano.** Nessun limite al numero di unità non a bordo che possono cambiare posizione, ma il modello preferisce il minimo cambiamento. L'app mostra sempre l'elenco delle unità spostate.

**Futuro di un sailing reale.** Il planner indica l'apertura delle prenotazioni e l'orario di partenza, per default 14 giorni di finestra. La posizione nella finestra equivale a `arrival_frac`. Il `DemandModel` campiona solo le richieste che arrivano dopo quel momento, in aggiunta a quelle già nel piano.

**Blocchi di scarico.** Ogni unità bloccata conta una volta e costa €80. Il costo entra in `objective`; con un solo porto di scarico vale zero, quindi non cambia i risultati v2.

**Spazio perso.** È un attributo di `Vessel`: si applica prima alla lunghezza di zona, poi resta il `lashing_gap_m` di ogni unità. Non serve una modalità separata: gioco e Planner partono solo con navi configurate diversamente.

**Clienti nei link.** Di default il link e il file `.json` contengono il piano senza nomi cliente, sostituiti da codici. Il planner può includerli con una scelta esplicita. Il PDF li include, perché è un documento interno, e lo dichiara nella finestra di download.

## 10. Modifiche all'engine

| File | Modifica |
|---|---|
| `models.py` | nuovi tipi e campi della sezione 8 |
| `deck.py` | spazio perso, ponti, altezze, carichi, riserve, spostamenti, `on_board` |
| `optimizer.py` | esclusione tracciata, riserve, ponti, blocchi di scarico, unità ferme, piano con tutte le accettate |
| `advisor.py` | tre risposte, intervalli, spostamenti, `DemandModel` |
| `simulator.py` | `DemandModel`, dati dei nuovi campi, volume incerto |
| `kpis.py` | costo spostamenti e blocchi nell'`objective` |
| `manifest.py` | nuovi campi, export |
| `explain.py` | nuovi motivi di esclusione |
| `stability.py` | carico su più ponti, stesso modello lineare |
| nuovi | `demand.py`, `planning.py`, `importer.py` |

## 11. Tappe

Ogni tappa è rilasciabile e passa test e benchmark prima della successiva.

| Tappa | Contenuto | Fine tappa |
|---|---|---|
| **0. Base** | FastAPI, React, gioco alla pari con la v2, Docker, primo deploy, ponte 5 × 120 m e tabella su 3 livelli di domanda | link HF attivo; tempi e riavvio misurati |
| **1. Funzioni rapide** | spazio perso, navi predefinite, PDF, CSV, link | export verificati |
| **2. Planner** (fatta 2026-11-09: il gioco è su `/game`, la sessione si salva in un file `.json` invece che in un link) | modello Excel, validazione, primo piano, esclusioni spiegate, nuove richieste, rifacimento piano | un Excel d'esempio completa il flusso |
| **3. Decisioni** | Advisor a tre risposte, intervalli, spostamenti nel gioco e nel planner, test del valore atteso | criteri della sezione 12 |
| **4. Riserve** | spazio riservato per cliente | test con e senza riserve |
| **5. Porti** | più porti di scarico e blocchi | ordine di scarico verificato su casi costruiti |
| **6. Ponti** | più ponti, altezze, assi, carico | vincoli verificati su casi costruiti |
| **7. Previsione** | `DemandModel` livello 1, poi livello 2, formato del livello 3 | backtest pubblicato, anche se negativo |

Il proprietario decide dopo ogni tappa se pubblicare il nuovo link.

## 12. Criteri di successo

**Prodotto**

- Il flusso Excel → piano → richiesta → piano aggiornato funziona senza errori su un esempio con 60 prenotazioni.
- Nessuna prenotazione accettata viene esclusa senza messaggio esplicito (test automatico).

**Decisioni** (nave di riferimento 6 × 120 m, come i test già fatti; 30 seed di verifica per 40, 60 e 90 richieste, confronto a coppie)

- Con 40 richieste il planner non perde più dello 0,5% rispetto a FCFS (oggi −1,8%).
- Con 90 richieste il vantaggio resta almeno 13% (oggi +14,9%).
- Con 60 richieste non scende sotto il +5%.
- Per raggiungerli si possono cambiare soglie e regola di decisione, non i seed di verifica.
- **Risultato (2026-11-10):** soglia di rifiuto calibrata a 0,9 (quella di accettazione, 0,6, non incide nel piano automatico e non è stata verificata); sui seed 1-30 con 40, 60 e 90 richieste: 0,0% (0 persi), +6,1% (3 persi), +16,5% (0 persi). Tutti e tre i criteri rispettati. Il test del valore atteso, corretto dopo la revisione (limite 1/K per prenotazione, non per zona), dà un punteggio quasi uguale (43.829 contro 43.790, accordo 81%) ma è 4 volte più lento (7,5 s contro 1,9 s per verdetto): resta la regola a futuri campionati.
- Se i criteri non si raggiungono dopo la calibrazione, la tappa 3 non si blocca: si pubblicano i numeri reali, si indica il limite e il proprietario decide se rilasciare.

**Tabella della tappa 0.** Sul ponte 5 × 120 m: domanda bassa, normale e alta corrispondono a 35, 50 e 60 richieste, circa 0,75, 1,08 e 1,30 volte lo spazio. Gli altri parametri restano quelli di `ScenarioParams`.

**Tempi su Hugging Face, demo da 600 m e 60 prenotazioni**

- Primo piano: massimo 30 secondi, con avanzamento visibile.
- Verdetto Advisor: massimo 5 secondi.
- Spostamenti suggeriti: massimo 10 secondi.

Se il modello cresce oltre questi limiti, l'ordine delle soluzioni è: ridurre K; usare la regola a valore atteso; raggruppare le zone per l'Advisor; infine una tappa per togliere PuLP. Un piano più potente o a pagamento richiede l'ok del proprietario.

**Qualità**

- I 195 test esistenti restano verdi o vengono aggiornati con motivo.
- Test sull'API e flusso end-to-end nel browser.
- Con i nuovi valori di default a zero, l'engine riproduce gli stessi risultati della v2 su seed fissi.

## 13. Rischi

| Rischio | Effetto | Risposta |
|---|---|---|
| Modello grande su 2 vCPU | piani lenti o incompleti | limiti, avvisi, soluzioni della sezione 12 |
| Più ponti con navi grandi | molte più variabili | restare sulla demo; indicare quando il piano è approssimato |
| Hugging Face in pausa o con limiti diversi | demo lenta | misura alla tappa 0, nota nel README, Docker per cambiare hosting |
| Dati pubblici poco utili | previsione non migliore del riferimento | si dichiara, si resta al livello 1 |
| Tre risposte troppo prudenti | meno vantaggio con domanda alta | calibrazione e criteri della sezione 12 |
| Percentuali gonfiate dal ponte piccolo | perdita di credibilità | etichetta alta domanda e tabella completa |
| Interpretazione come strumento di sicurezza | uso improprio | avviso in app, PDF e README |

## 14. Deploy

Claude prepara Dockerfile, istruzioni e prove locali. Il proprietario crea account e Space su Hugging Face e conserva il proprio token. Ogni pubblicazione del nuovo link richiede il suo ok. Il livello 2 di previsione può chiudersi con un risultato negativo pubblicato: in quel caso l'app resta al livello 1.

## 15. Lasciato al builder

Struttura interna di API e componenti, libreria di stato React, grafica del ponte (SVG o Canvas), scelta della libreria di grafici, linearizzazione del blocco di scarico, dettagli di compressione del link, nomi dei file di test, valori numerici delle navi predefinite entro quanto descritto.
