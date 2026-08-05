#!/usr/bin/env python3
"""
watch_page_cloud.py — Check a web page for changes and push a phone
notification via ntfy.sh. Designed to run as a single check per invocation
(e.g. triggered on a schedule by GitHub Actions).

Env vars (set as GitHub Actions "secrets" or "variables"):
    WATCH_URL       - the page to watch (required)
    NTFY_TOPIC      - your unique ntfy.sh topic name (required)
    WATCH_SELECTOR  - optional CSS selector to narrow the watched content

State is stored in a file (state.hash) inside the repo, which the workflow
commits back after each run so state persists between scheduled runs.
"""

import hashlib
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STATE_FILE = Path("state.hash")


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


def main():
    url = os.environ.get("WATCH_URL")
    topic = os.environ.get("NTFY_TOPIC")
    selector = os.environ.get("WATCH_SELECTOR") or None

    if not url or not topic:
        print("Error: WATCH_URL and NTFY_TOPIC must be set.", file=sys.stderr)
        sys.exit(1)

    try:
        text = get_page_text(url, selector)
    except Exception as e:
        print(f"Error fetching page: {e}", file=sys.stderr)
        sys.exit(1)

    current_hash = hash_text(text)

    if STATE_FILE.exists():
        previous_hash = STATE_FILE.read_text().strip()
        if previous_hash != current_hash:
            STATE_FILE.write_text(current_hash)
            print("Change detected — sending notification.")
            send_push(topic, "Page changed!", url, url)
        else:
            print("No change.")
    else:
        STATE_FILE.write_text(current_hash)
        print("Baseline recorded.")


if __name__ == "__main__":
    main()
