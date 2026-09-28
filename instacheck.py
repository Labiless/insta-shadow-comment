"""Shared logic: configuration, login and searching for an account's comment.

Comments are streamed (one page at a time) and the search stops at the first
match: nothing is saved to disk.
"""

import configparser
import os
import re
import sys
import time
import warnings

# Harmless urllib3 warning with macOS's system Python (LibreSSL): silence it.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import instaloader  # noqa: E402
import requests  # noqa: E402
from instaloader.instaloader import get_default_session_filename  # noqa: E402

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


def load_config(path=CONFIG_PATH):
    """Reads the [instagram] section of config.ini."""
    if not os.path.exists(path):
        sys.exit(f"Missing configuration file: {path}\n"
                 f"Copy config.example.ini to config.ini and fill in your credentials.")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    section = parser["instagram"] if parser.has_section("instagram") else {}
    config = {key: section.get(key, "").strip() for key in ("username", "password", "sessionid", "csrftoken")}
    config["username"] = config["username"].lstrip("@")
    if not config["username"]:
        sys.exit(f"'username' is missing from the [instagram] section of {path}")
    return config


def login_with_browser_cookies(loader, config):
    """Uses cookies copied from the browser: avoids "checkpoint" blocks on scripted logins."""
    if not config["csrftoken"]:
        sys.exit("config.ini has 'sessionid' but no 'csrftoken': copy that cookie from the browser too.")
    loader.load_session(config["username"], {"sessionid": config["sessionid"], "csrftoken": config["csrftoken"]})
    logged_as = loader.test_login()
    if not logged_as:
        sys.exit("The cookies in config.ini are invalid or expired: copy them from the browser again.")
    loader.context.username = logged_as


def login_with_password(loader, config):
    try:
        if config["password"]:
            try:
                loader.login(config["username"], config["password"])
            except instaloader.TwoFactorAuthRequiredException:
                loader.two_factor_login(input("2FA code: ").strip())
        else:
            loader.interactive_login(config["username"])
    except instaloader.exceptions.BadCredentialsException:
        sys.exit("Wrong password: check config.ini.")
    except instaloader.exceptions.LoginException as exc:
        if "checkpoint" in str(exc).lower():
            sys.exit("Instagram blocked the scripted login (\"checkpoint\" security check).\n"
                     "Fix: log in to instagram.com in your browser and copy the 'sessionid' and\n"
                     "'csrftoken' cookies into config.ini (see config.example.ini), then restart.")
        sys.exit(f"Login failed: {exc}")


def create_logged_loader(config_path=CONFIG_PATH):
    """Creates an authenticated Instaloader using config.ini.

    Order: previously saved session, browser cookies (sessionid), password.
    After a new login the session is saved for next time.
    """
    config = load_config(config_path)
    loader = instaloader.Instaloader(quiet=True)
    try:
        loader.load_session_from_file(config["username"])
        print(f"Session loaded for @{config['username']}", file=sys.stderr)
        return loader
    except FileNotFoundError:
        pass

    if config["sessionid"]:
        login_with_browser_cookies(loader, config)
    else:
        login_with_password(loader, config)
    loader.save_session_to_file(get_default_session_filename(config["username"]))
    print(f"Logged in as @{loader.context.username}, session saved", file=sys.stderr)
    return loader


def parse_shortcode(value):
    match = SHORTCODE_RE.search(value)
    return match.group(1) if match else value.strip().strip("/")


WEB_API = "https://www.instagram.com/api/v1"
WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "X-IG-App-ID": "936619743392459",  # public ID of Instagram's web app
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Dest": "empty",
}
PAGE_DELAY = 1.0  # seconds to wait between pages, to avoid rate limiting


class WebComments:
    """Reads comments through the same API used by the instagram.com website.

    The "iPad" endpoint instaloader uses for posts with many comments currently
    answers "something went wrong"; the web one works with the same cookies.
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
            raise instaloader.exceptions.LoginRequiredException(f"{resp.status_code} on {path}")
        if resp.status_code == 404:
            raise instaloader.exceptions.QueryReturnedNotFoundException(path)
        try:
            data = resp.json()
        except ValueError:
            raise instaloader.exceptions.LoginRequiredException(
                f"invalid response from {path} (expired session?)") from None
        if data.get("status") != "ok":
            raise instaloader.exceptions.ConnectionException(data.get("message") or f"error on {path}")
        return data

    def _replies(self, media_id, comment):
        """All replies to a comment (uses the preview when it is already complete)."""
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
        """Yields (comment, parent_comment) page by page, without saving anything."""
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


def get_post(loader, post_ref):
    """Fetches the post given by URL or shortcode."""
    return instaloader.Post.from_shortcode(loader.context, parse_shortcode(post_ref))


def post_info(post):
    """Details that help confirm it is the right post."""
    return {
        "shortcode": post.shortcode,
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "owner": post.owner_username,
        "caption": post.caption or "",
        "date": f"{post.date_utc:%Y-%m-%d %H:%M} UTC",
        "type": {"GraphImage": "Photo", "GraphVideo": "Video", "GraphSidecar": "Carousel"}.get(post.typename, "Post"),
        "likes": post.likes,
        "declared_comments": post.comments,
    }


def find_comments(loader, post_ref, target, include_replies=True, find_all=False, post=None):
    """Searches for comments by `target` under the post given by URL or shortcode.

    Pass `post` if it has already been fetched, to avoid a second request.
    Returns a dict with the post details, the matching comments and the
    number of comments scanned.
    """
    target = target.strip().lstrip("@").lower()
    post = post or get_post(loader, post_ref)
    shortcode = post.shortcode

    matches = []
    scanned = 0
    for node, parent in WebComments(loader).iter_comments(post.mediaid, include_replies):
        scanned += 1
        if scanned % 100 == 0:
            print(f"  ...{scanned} comments scanned", file=sys.stderr)
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
