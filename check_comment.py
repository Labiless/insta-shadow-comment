#!/usr/bin/env python3
"""Versione da riga di comando: verifica se un account ha commentato un post.

Le credenziali vengono lette da config.ini.

Esempi:
    python check_comment.py https://www.instagram.com/p/ABC123/ utente_target
    python check_comment.py ABC123 utente_target --all
"""

import argparse
import sys

from instacheck import create_logged_loader, find_comments


def print_match(match):
    kind = f"Risposta a @{match['reply_to']}" if match["reply_to"] else "Commento"
    print("-" * 60)
    print(f"{kind} di @{match['author']}")
    print(f"Data:  {match['date']}")
    print(f"Like:  {match['likes']}")
    if match["hidden"]:
        print("Stato: nascosto da Instagram (tra i \"commenti nascosti\")")
    print(f"Link:  {match['url']}")
    print(f"Testo: {match['text']}")


def main():
    parser = argparse.ArgumentParser(description="Cerca il commento di un account sotto un post Instagram.")
    parser.add_argument("post", help="URL del post o shortcode")
    parser.add_argument("target", help="username dell'account da cercare (senza @)")
    parser.add_argument("--all", action="store_true",
                        help="non fermarti al primo: mostra tutti i commenti dell'account")
    parser.add_argument("--no-replies", action="store_true",
                        help="ignora le risposte ai commenti (più veloce)")
    args = parser.parse_args()

    loader = create_logged_loader()
    result = find_comments(loader, args.post, args.target,
                           include_replies=not args.no_replies, find_all=args.all)

    print(f"Post di @{result['post_owner']} — {result['declared_comments']} commenti dichiarati", file=sys.stderr)
    for match in result["matches"]:
        print_match(match)
    print("-" * 60)
    if result["matches"]:
        print(f"Trovati {len(result['matches'])} commenti di @{result['target']} ({result['scanned']} analizzati).")
    else:
        print(f"Nessun commento di @{result['target']} trovato ({result['scanned']} analizzati).")
    return 0 if result["matches"] else 1


if __name__ == "__main__":
    sys.exit(main())
