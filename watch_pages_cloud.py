#!/usr/bin/env python3
"""
watch_pages_cloud.py — Check MULTIPLE web pages for changes and push a
phone notification (via ntfy.sh) for each one that changed.

Env vars:
    WATCH_PAGES  - required. A JSON array of page configs, e.g.:
        [
          {"name": "disney-deal", "url": "https://example.com/deals", "topic": "timadden-cruisepage-a83k"},
          {"name": "princess-price", "url": "https://example.com/cabin123", "topic": "timadden-cruisepage-a83k", "selector": "div.price"}
        ]

        Fields per page:
          name      - required, short unique id (used for the state filename)
          url       - required, the page to check
          topic     - required, ntfy.sh topic to notify on this page's changes
                      (can be the same topic for every page, or different per page)
          selector  - optional, CSS selector to narrow what's checked

State is stored in a "state/" folder (one file per page, named after "name"),
committed back to the repo after each run so it persists between scheduled runs.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STATE_DIR = Path("state")
STATE_DIR.mkdir(exist_ok=True)


def get_page_text(url: str, selector: str | None) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PageWatcher/1.0)"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    if selector:
        elements = soup.select(selector)
        if not elements:
            raise ValueError(f"Selector '{selector}' matched nothing on the page.")
        text = "\n".join(el.get_text(strip=True) for el in elements)
    else:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

    return text


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def send_push(topic: str, title: str, message: str, url: str):
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Click": url,
            "Priority": "default",
        },
        timeout=10,
    )


def safe_filename(name: str) -> str:
    # Keep it simple and filesystem-safe
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def process_page(page: dict) -> None:
    name = page.get("name")
    url = page.get("url")
    topic = page.get("topic")
    selector = page.get("selector")

    if not name or not url or not topic:
        print(f"Skipping invalid entry (needs name, url, topic): {page}", file=sys.stderr)
        return

    state_file = STATE_DIR / f"{safe_filename(name)}.hash"

    try:
        text = get_page_text(url, selector)
    except Exception as e:
        print(f"[{name}] Error fetching page: {e}", file=sys.stderr)
        return

    current_hash = hash_text(text)

    if state_file.exists():
        previous_hash = state_file.read_text().strip()
        if previous_hash != current_hash:
            state_file.write_text(current_hash)
            print(f"[{name}] Change detected — sending notification.")
            send_push(topic, f"Page changed: {name}", url, url)
        else:
            print(f"[{name}] No change.")
    else:
        state_file.write_text(current_hash)
        print(f"[{name}] Baseline recorded.")


def main():
    raw = os.environ.get("WATCH_PAGES")
    if not raw:
        print("Error: WATCH_PAGES env var not set.", file=sys.stderr)
        sys.exit(1)

    try:
        pages = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: WATCH_PAGES is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(pages, list):
        print("Error: WATCH_PAGES must be a JSON array.", file=sys.stderr)
        sys.exit(1)

    for page in pages:
        process_page(page)


if __name__ == "__main__":
    main()
