# insta-shadow-comment

Verifica se un account ha commentato un post Instagram e, se il commento c'è, lo mostra.
I commenti vengono letti pagina per pagina e la ricerca si ferma appena trova quello cercato:
nulla viene salvato su disco.

Si usa da una pagina web locale oppure dal terminale.

## Requisiti

- macOS o Linux con **Python 3.9+** (su Mac è già presente: verifica con `python3 --version`)
- Un account Instagram con cui fare l'accesso, **diverso** da quello di cui cerchi il commento
  (chi scrive un commento lo vede sempre, anche quando agli altri è nascosto)

## Installazione (una volta sola)

```bash
cd insta-shadow-comment
python3 -m venv .venv                     # crea l'ambiente virtuale del progetto
source .venv/bin/activate                 # lo attiva (il prompt mostra "(.venv)")
pip install -r requirements.txt           # installa instaloader e flask
```

## Configurazione

Copia il file di esempio e aprilo con un editor:

```bash
cp config.example.ini config.ini
```

Compila `username` e poi **uno** dei due metodi di accesso.

### Metodo 1 (consigliato): cookie del browser

Instagram blocca spesso il login con password fatto da uno script ("Checkpoint required").
Usare la sessione del browser evita il problema.

1. Accedi a https://www.instagram.com dal browser con l'account da usare.
2. Apri gli strumenti sviluppatore (**Cmd+Option+I**) e vai ai cookie di `https://www.instagram.com`:
   - **Chrome**: scheda *Application* → *Cookies*
   - **Safari**: scheda *Storage* → *Cookies* (prima abilita il menu Sviluppo in Impostazioni → Avanzate)
   - **Firefox**: scheda *Archiviazione* → *Cookie*
3. Copia i valori di `sessionid` e `csrftoken` in `config.ini`:

```ini
[instagram]
username = tuo_username
sessionid = 1234567%3AAbCdEf...
csrftoken = xYz123...
password =
```

Non fare logout da quel browser: invaliderebbe anche la sessione usata dal tool.

### Metodo 2: password

Lascia vuoto `sessionid` e compila `password`. Se hai la verifica in due passaggi, il codice
viene chiesto nel terminale all'avvio.

---

Al primo avvio riuscito la sessione viene salvata in `~/.config/instaloader/session-<username>`:
da lì in poi i dati di accesso in `config.ini` non servono più.
`config.ini` contiene dati personali: non condividerlo (è già escluso in `.gitignore`).

## Avvio

Ogni volta che apri un nuovo terminale, attiva prima l'ambiente:

```bash
cd insta-shadow-comment
source .venv/bin/activate
```

### Pagina web

```bash
python app.py
```

Apri **http://127.0.0.1:8000** nel browser, incolla il link del post, scrivi l'account da cercare
e premi **Cerca**. Il risultato compare sotto il modulo. Opzioni disponibili:

- **Includi le risposte**: cerca anche tra le risposte ai commenti
- **Trova tutti i commenti dell'account**: non si ferma al primo trovato

Per chiudere il server premi **Ctrl+C** nel terminale. La pagina è raggiungibile solo dal tuo computer.

### Terminale

```bash
python check_comment.py https://www.instagram.com/p/XXXXXXX/ account_da_cercare
python check_comment.py XXXXXXX account_da_cercare --all          # tutti i commenti dell'account
python check_comment.py XXXXXXX account_da_cercare --no-replies   # ignora le risposte (più veloce)
```

## Come leggere il risultato

| Risultato | Significato |
|---|---|
| Trovato | il commento è visibile agli altri utenti |
| Trovato, con **"nascosto da Instagram"** | è tra i "commenti nascosti" (di solito filtro offensivi/spam) |
| Non trovato | non è visibile agli altri: eliminato, nascosto dall'autore del post (account limitato, parole nascoste, ...) o filtrato da Instagram |

Il numero di commenti dichiarato dal post è spesso più alto di quelli analizzati: la differenza
sono commenti che Instagram non mostra a chi guarda.

Per capire se il problema riguarda un solo post o l'account in generale, prova a commentare
il post di un altro profilo e controllalo con il tool.

## Problemi comuni

| Messaggio | Cosa fare |
|---|---|
| `File di configurazione mancante` | crea `config.ini` partendo da `config.example.ini` |
| `Checkpoint required` / login bloccato | usa il metodo dei cookie del browser |
| `I cookie ... non sono validi o sono scaduti` | ricopia `sessionid` e `csrftoken` dal browser |
| `La sessione non è più valida` | cancella `~/.config/instaloader/session-<username>` e riavvia |
| `Instagram ha limitato le richieste` | aspetta qualche minuto prima di riprovare |
| `Address already in use` all'avvio di `app.py` | c'è già un'istanza aperta: chiudila o cambia `PORT` in `app.py` |

## Struttura del progetto

```
app.py               pagina web (Flask)
templates/index.html aspetto della pagina
check_comment.py     versione da terminale
instacheck.py        logica comune: configurazione, login, lettura dei commenti
config.example.ini   modello del file di configurazione
requirements.txt     librerie necessarie
```
