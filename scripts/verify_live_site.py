#!/usr/bin/env python3
"""Verify that the public Pages response contains this run's generated snapshot."""
import json
import os
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


if __name__ == "__main__":
    verify(os.environ.get("SITE_URL", ""), os.environ.get("EXPECTED_GENERATED_AT", ""))
