#!/usr/bin/env bash
set -euo pipefail
# Pinned upstream release and SHA256; downloads no credential-bearing content.
lint_version=1.7.11
lint_sha=900919a84f2229bac68ca9cd4103ea297abc35e9689ebb842c6e34a3d1b01b0a
lint_tmp="$(mktemp -d)"
trap 'rm -rf "$lint_tmp"' EXIT
curl --fail --silent --show-error --location --retry 2 \
  "https://github.com/rhysd/actionlint/releases/download/v${lint_version}/actionlint_${lint_version}_linux_amd64.tar.gz" \
  --output "$lint_tmp/actionlint.tar.gz"
printf '%s  %s\n' "$lint_sha" "$lint_tmp/actionlint.tar.gz" | sha256sum --check --status
tar -xzf "$lint_tmp/actionlint.tar.gz" -C "$lint_tmp" actionlint
"$lint_tmp/actionlint" -color
