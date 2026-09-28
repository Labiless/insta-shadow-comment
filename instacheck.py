"""Logica condivisa: configurazione, login e ricerca del commento di un account.

I commenti vengono letti in streaming (pagina per pagina) e la ricerca si ferma
al primo commento trovato: nulla viene salvato su disco.
"""

import configparser
import os
import re
import sys
import time
import warnings

# Avviso innocuo di urllib3 con il Python di sistema del Mac (LibreSSL): lo nascondiamo.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import instaloader  # noqa: E402
import requests  # noqa: E402
from instaloader.instaloader import get_default_session_filename  # noqa: E402

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


def load_config(path=CONFIG_PATH):
    """Legge la sezione [instagram] di config.ini."""
    if not os.path.exists(path):
        sys.exit(f"File di configurazione mancante: {path}\n"
                 f"Copia config.example.ini in config.ini e inserisci le tue credenziali.")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    section = parser["instagram"] if parser.has_section("instagram") else {}
    config = {key: section.get(key, "").strip() for key in ("username", "password", "sessionid", "csrftoken")}
    config["username"] = config["username"].lstrip("@")
    if not config["username"]:
        sys.exit(f"Manca 'username' nella sezione [instagram] di {path}")
    return config


def login_with_browser_cookies(loader, config):
    """Usa i cookie copiati dal browser: evita i blocchi "checkpoint" del login da script."""
    if not config["csrftoken"]:
        sys.exit("In config.ini c'è 'sessionid' ma manca 'csrftoken': copia anche quel cookie dal browser.")
    loader.load_session(config["username"], {"sessionid": config["sessionid"], "csrftoken": config["csrftoken"]})
    logged_as = loader.test_login()
    if not logged_as:
        sys.exit("I cookie in config.ini non sono validi o sono scaduti: ricopiali dal browser.")
    loader.context.username = logged_as


def login_with_password(loader, config):
    try:
        if config["password"]:
            try:
                loader.login(config["username"], config["password"])
            except instaloader.TwoFactorAuthRequiredException:
                loader.two_factor_login(input("Codice 2FA: ").strip())
        else:
            loader.interactive_login(config["username"])
    except instaloader.exceptions.BadCredentialsException:
        sys.exit("Password errata: controlla config.ini.")
    except instaloader.exceptions.LoginException as exc:
        if "checkpoint" in str(exc).lower():
            sys.exit("Instagram ha bloccato il login da script (verifica di sicurezza \"checkpoint\").\n"
                     "Soluzione: accedi a instagram.com dal browser e copia i cookie 'sessionid' e\n"
                     "'csrftoken' in config.ini (istruzioni in config.example.ini), poi riavvia.")
        sys.exit(f"Login non riuscito: {exc}")


def create_logged_loader(config_path=CONFIG_PATH):
    """Crea un Instaloader autenticato usando config.ini.

    Ordine: sessione già salvata, cookie del browser (sessionid), password.
    Dopo un nuovo login la sessione viene salvata per le volte successive.
    """
    config = load_config(config_path)
    loader = instaloader.Instaloader(quiet=True)
    try:
        loader.load_session_from_file(config["username"])
        print(f"Sessione caricata per @{config['username']}", file=sys.stderr)
        return loader
    except FileNotFoundError:
        pass

    if config["sessionid"]:
        login_with_browser_cookies(loader, config)
    else:
        login_with_password(loader, config)
    loader.save_session_to_file(get_default_session_filename(config["username"]))
    print(f"Login effettuato come @{loader.context.username}, sessione salvata", file=sys.stderr)
    return loader


def parse_shortcode(value):
    match = SHORTCODE_RE.search(value)
    return match.group(1) if match else value.strip().strip("/")


WEB_API = "https://www.instagram.com/api/v1"
WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "X-IG-App-ID": "936619743392459",  # ID pubblico della web app di Instagram
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Dest": "empty",
}
PAGE_DELAY = 1.0  # secondi di pausa tra una pagina e l'altra, per non farsi limitare


class WebComments:
    """Legge i commenti con la stessa API usata dal sito instagram.com.

    L'endpoint "iPad" usato da instaloader per i post con molti commenti oggi
    risponde "something went wrong"; quello web invece funziona con gli stessi cookie.
    """

    def __init__(self, loader):
        cookies = loader.context._session.cookies.get_dict()
        self.session = requests.Session()
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=".instagram.com")
        self.session.headers.update(WEB_HEADERS)
        self.session.headers["X-CSRFToken"] = cookies.get("csrftoken", "")

    def _get(self, path, params):
        resp = self.session.get(f"{WEB_API}/{path}", params=params, timeout=30)
        if resp.status_code == 429:
            raise instaloader.exceptions.TooManyRequestsException("429 Too Many Requests")
        if resp.status_code in (401, 403):
            raise instaloader.exceptions.LoginRequiredException(f"{resp.status_code} su {path}")
        if resp.status_code == 404:
            raise instaloader.exceptions.QueryReturnedNotFoundException(path)
        try:
            data = resp.json()
        except ValueError:
            raise instaloader.exceptions.LoginRequiredException(
                f"risposta non valida da {path} (sessione scaduta?)") from None
        if data.get("status") != "ok":
            raise instaloader.exceptions.ConnectionException(data.get("message") or f"errore su {path}")
        return data

    def _replies(self, media_id, comment):
        """Tutte le risposte a un commento (usa l'anteprima se è già completa)."""
        preview = comment.get("preview_child_comments") or []
        if comment.get("child_comment_count", 0) <= len(preview):
            yield from preview
            return
        cursor = ""
        while True:
            data = self._get(f"media/{media_id}/comments/{comment['pk']}/child_comments/", {"max_id": cursor})
            yield from data.get("child_comments", [])
            cursor = data.get("next_max_child_cursor")
            if not data.get("has_more_tail_child_comments") or not cursor:
                return
            time.sleep(PAGE_DELAY)

    def iter_comments(self, media_id, include_replies=True):
        """Genera (commento, commento_padre) pagina per pagina, senza salvare nulla."""
        params = {"can_support_threading": "true", "permalink_enabled": "false"}
        seen_cursors = set()
        while True:
            data = self._get(f"media/{media_id}/comments/", params)
            comments = data.get("comments", [])
            for comment in comments:
                yield comment, None
                if include_replies and comment.get("child_comment_count"):
                    for reply in self._replies(media_id, comment):
                        yield reply, comment
            cursor = data.get("next_min_id")
            if not comments or not data.get("has_more_headload_comments") or not cursor or cursor in seen_cursors:
                return
            seen_cursors.add(cursor)
            params["min_id"] = cursor
            time.sleep(PAGE_DELAY)


def format_comment(node, parent, shortcode):
    return {
        "author": node["user"]["username"],
        "reply_to": parent["user"]["username"] if parent else None,
        "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(node["created_at"])),
        "likes": node.get("comment_like_count", 0),
        "id": node["pk"],
        "text": node.get("text", ""),
        "hidden": bool(node.get("is_covered")),
        "url": f"https://www.instagram.com/p/{shortcode}/c/{node['pk']}/",
    }


def find_comments(loader, post_ref, target, include_replies=True, find_all=False):
    """Cerca i commenti di `target` sotto il post indicato da URL o shortcode.

    Restituisce un dizionario con i dati del post, i commenti trovati e il
    numero di commenti analizzati.
    """
    target = target.strip().lstrip("@").lower()
    shortcode = parse_shortcode(post_ref)
    post = instaloader.Post.from_shortcode(loader.context, shortcode)

    matches = []
    scanned = 0
    for node, parent in WebComments(loader).iter_comments(post.mediaid, include_replies):
        scanned += 1
        if scanned % 100 == 0:
            print(f"  ...{scanned} commenti analizzati", file=sys.stderr)
        if node["user"]["username"].lower() == target:
            matches.append(format_comment(node, parent, shortcode))
            if not find_all:
                break

    return {
        "shortcode": shortcode,
        "post_owner": post.owner_username,
        "declared_comments": post.comments,
        "target": target,
        "scanned": scanned,
        "matches": matches,
    }
