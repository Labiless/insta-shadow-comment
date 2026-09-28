#!/usr/bin/env python3
"""Local web page to search for an account's comment under a post.

Start:
    python app.py
then open http://127.0.0.1:8000 in your browser.
"""

import threading

import instaloader
from flask import Flask, jsonify, render_template, request

from instacheck import create_logged_loader, find_comments, get_post, parse_shortcode, post_info

HOST = "127.0.0.1"  # this computer only: the page is not reachable from other devices
PORT = 8000

app = Flask(__name__)

# Log in once at startup (here, in the terminal, you can enter a 2FA code if needed).
loader = create_logged_loader()
# Instaloader is not designed for parallel requests: one request to Instagram at a time.
instagram_lock = threading.Lock()
# Posts already fetched for the preview, reused by the search to avoid a second request.
post_cache = {}


def error_message(exc):
    if isinstance(exc, instaloader.exceptions.TooManyRequestsException):
        return "Instagram is rate-limiting requests (too many in a short time). Try again in a few minutes."
    if isinstance(exc, instaloader.exceptions.LoginRequiredException):
        return "The session is no longer valid: delete the session file and restart the app."
    if isinstance(exc, (instaloader.exceptions.BadResponseException,
                        instaloader.exceptions.QueryReturnedNotFoundException)):
        return "Post not found: check the link (or the post is private/deleted)."
    return f"Error from Instagram: {exc}"


def with_instagram(action):
    """Runs `action` holding the lock and turns errors into a JSON response."""
    if not instagram_lock.acquire(blocking=False):
        return jsonify(error="A search is already running: wait for it to finish."), 409
    try:
        return jsonify(action())
    except instaloader.exceptions.InstaloaderException as exc:
        return jsonify(error=error_message(exc)), 502
    finally:
        instagram_lock.release()


def cached_post(post_ref):
    shortcode = parse_shortcode(post_ref)
    if shortcode not in post_cache:
        if len(post_cache) > 50:
            post_cache.clear()
        post_cache[shortcode] = get_post(loader, post_ref)
    return post_cache[shortcode]


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/post")
def api_post():
    post_ref = (request.get_json(silent=True) or {}).get("post", "").strip()
    if not post_ref:
        return jsonify(error="Enter the post link."), 400
    return with_instagram(lambda: post_info(cached_post(post_ref)))


@app.post("/api/search")
def api_search():
    data = request.get_json(silent=True) or {}
    post_ref = data.get("post", "").strip()
    target = data.get("target", "").strip()
    if not post_ref or not target:
        return jsonify(error="Enter both the post link and the account to look for."), 400
    return with_instagram(lambda: find_comments(
        loader, post_ref, target,
        include_replies=bool(data.get("replies")), find_all=bool(data.get("all")),
        post=cached_post(post_ref),
    ))


if __name__ == "__main__":
    print(f"Open http://{HOST}:{PORT} in your browser (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, threaded=True)
