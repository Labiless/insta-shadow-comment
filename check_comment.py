#!/usr/bin/env python3
"""Command-line version: checks whether an account has commented on a post.

Credentials are read from config.ini.

Examples:
    python check_comment.py https://www.instagram.com/p/ABC123/ target_user
    python check_comment.py ABC123 target_user --all
"""

import argparse
import sys

from instacheck import create_logged_loader, find_comments, get_post, post_info


def print_post(info, max_caption=300):
    caption = info["caption"].strip() or "(no caption)"
    if len(caption) > max_caption:
        caption = caption[:max_caption].rstrip() + "…"
    print("=" * 60)
    print(f"{info['type']} by @{info['owner']} — {info['date']}")
    print(f"{info['likes']} likes · {info['declared_comments']} comments declared · {info['url']}")
    print(caption)
    print("=" * 60)
    print("Searching comments...", file=sys.stderr)


def print_match(match):
    kind = f"Reply to @{match['reply_to']}" if match["reply_to"] else "Comment"
    print("-" * 60)
    print(f"{kind} by @{match['author']}")
    print(f"Date:   {match['date']}")
    print(f"Likes:  {match['likes']}")
    if match["hidden"]:
        print("Status: hidden by Instagram (under \"hidden comments\")")
    print(f"Link:   {match['url']}")
    print(f"Text:   {match['text']}")


def main():
    parser = argparse.ArgumentParser(description="Search for an account's comment under an Instagram post.")
    parser.add_argument("post", help="post URL or shortcode")
    parser.add_argument("target", help="username of the account to look for (without @)")
    parser.add_argument("--all", action="store_true",
                        help="don't stop at the first match: show all of the account's comments")
    parser.add_argument("--no-replies", action="store_true",
                        help="skip replies to comments (faster)")
    args = parser.parse_args()

    loader = create_logged_loader()
    post = get_post(loader, args.post)
    print_post(post_info(post))
    result = find_comments(loader, args.post, args.target,
                           include_replies=not args.no_replies, find_all=args.all, post=post)

    for match in result["matches"]:
        print_match(match)
    print("-" * 60)
    if result["matches"]:
        n = len(result["matches"])
        print(f"Found {n} comment{'s' if n != 1 else ''} by @{result['target']} ({result['scanned']} scanned).")
    else:
        print(f"No comments by @{result['target']} found ({result['scanned']} scanned).")
    return 0 if result["matches"] else 1


if __name__ == "__main__":
    sys.exit(main())
