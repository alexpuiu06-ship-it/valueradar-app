#!/usr/bin/env python3
"""Verify that the public Pages response contains this run's generated snapshot."""
import json
import hashlib
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request


def verify(url, expected, attempts=6):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Expected an HTTPS Pages URL without credentials")
    if not expected:
        raise ValueError("Expected snapshot timestamp is missing")
    endpoint = url.rstrip("/") + "/latest.json?verification=" + urllib.parse.quote(expected)
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(endpoint, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=15) as response:
                snapshot = json.load(response)
            if snapshot.get("generated_at") == expected:
                print("Public Pages snapshot verified:", expected)
                return
        except (OSError, ValueError):
            pass
        if attempt + 1 < attempts:
            time.sleep(5)
    raise RuntimeError("Pages deployment returned success but the public snapshot could not be verified")

def verify_assets(url,docs,attempts=6):
    """Verify the actual HTML and scripts, not only a newer JSON on an old page."""
    names=("index.html","common.js","dashboard.js","odds_ui.js","model_lab_ui.js","elo_ui.js")
    if (docs/"ro_feed_status.json").is_file():names+=("ro_feed_status.json",)
    expected={name:hashlib.sha256((docs/name).read_bytes()).hexdigest() for name in names}
    for attempt in range(attempts):
        try:
            for name,digest in expected.items():
                request=urllib.request.Request(url.rstrip("/")+"/"+name+"?verification="+digest,
                    headers={"Cache-Control":"no-cache"})
                with urllib.request.urlopen(request,timeout=15) as response:
                    if hashlib.sha256(response.read(3000000)).hexdigest()!=digest:
                        raise ValueError("Stale public asset: "+name)
            print("Public HTML, scripts and available RO report match the saved source revision")
            return
        except (OSError,ValueError):
            if attempt+1<attempts:time.sleep(5)
    raise RuntimeError("Public site assets do not match the saved source revision")


if __name__ == "__main__":
    verify(os.environ.get("SITE_URL", ""), os.environ.get("EXPECTED_GENERATED_AT", ""))
    verify_assets(os.environ["SITE_URL"],Path(__file__).resolve().parents[1]/"docs")
