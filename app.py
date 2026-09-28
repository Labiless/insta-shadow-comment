#!/usr/bin/env python3
"""Pagina web locale per cercare il commento di un account sotto un post.

Avvio:
    python app.py
poi apri http://127.0.0.1:8000 nel browser.
"""

import threading

import instaloader
from flask import Flask, render_template, request

from instacheck import create_logged_loader, find_comments

HOST = "127.0.0.1"  # solo questo computer: la pagina non è raggiungibile da altri
PORT = 8000

app = Flask(__name__)

# Login una sola volta all'avvio (qui, nel terminale, si può inserire l'eventuale codice 2FA).
loader = create_logged_loader()
# Instaloader non è pensato per richieste in parallelo: una ricerca alla volta.
search_lock = threading.Lock()


def error_message(exc):
    if isinstance(exc, instaloader.exceptions.TooManyRequestsException):
        return "Instagram ha limitato le richieste (troppe in poco tempo). Riprova tra qualche minuto."
    if isinstance(exc, instaloader.exceptions.LoginRequiredException):
        return "La sessione non è più valida: cancella il file di sessione e riavvia l'app."
    if isinstance(exc, (instaloader.exceptions.BadResponseException,
                        instaloader.exceptions.QueryReturnedNotFoundException)):
        return "Post non trovato: controlla il link (o il post è privato/eliminato)."
    return f"Errore da Instagram: {exc}"


@app.route("/", methods=["GET", "POST"])
def index():
    form = {"post": "", "target": "", "replies": True, "all": False}
    result = None
    error = None

    if request.method == "POST":
        form = {
            "post": request.form.get("post", "").strip(),
            "target": request.form.get("target", "").strip(),
            "replies": "replies" in request.form,
            "all": "all" in request.form,
        }
        if not form["post"] or not form["target"]:
            error = "Inserisci sia il link del post sia l'account da cercare."
        elif not search_lock.acquire(blocking=False):
            error = "C'è già una ricerca in corso: attendi che finisca."
        else:
            try:
                result = find_comments(loader, form["post"], form["target"],
                                       include_replies=form["replies"], find_all=form["all"])
            except instaloader.exceptions.InstaloaderException as exc:
                error = error_message(exc)
            finally:
                search_lock.release()

    return render_template("index.html", form=form, result=result, error=error)


if __name__ == "__main__":
    print(f"Apri http://{HOST}:{PORT} nel browser (Ctrl+C per fermare)")
    app.run(host=HOST, port=PORT, threaded=True)
