#!/usr/bin/env python3
"""Cancel exactly one explicitly selected, still pending Pages deployment."""
import json
import os
import re
import urllib.request


def main():
    deployment_id = os.environ.get("DEPLOYMENT_ID", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    # deploy-pages can return a numeric ID or fall back to its 40-hex build ID.
    if not re.fullmatch(r"(?:[1-9][0-9]*|[a-fA-F0-9]{40})", deployment_id):
        raise SystemExit("Supply the exact numeric or 40-hex Pages deployment ID from the failed run")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise SystemExit("Invalid repository")
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Missing GitHub runtime token")
    url = f"https://api.github.com/repos/{repository}/pages/deployments/{deployment_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        status = json.load(response).get("status")
    if status not in {"queued", "deployment_in_progress", "syncing_files"}:
        raise SystemExit(f"Deployment is {status!r}; cancellation refused")
    request = urllib.request.Request(url + "/cancel", headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 204:
            raise SystemExit(f"Unexpected Pages cancellation response {response.status}")
    print(f"Cancellation requested for Pages deployment {deployment_id}")


if __name__ == "__main__":
    main()
