#!/usr/bin/env bash
# Fetches the latest Antigravity IDE Linux (.tar.gz) download URL.
# Uses the official auto-updater releases API that antigravity.google itself
# queries; the download URL is constructed from version + execution_id.

set -euo pipefail

RELEASES_API="https://antigravity-ide-auto-updater-974169037036.us-central1.run.app/releases"
DOWNLOAD_BASE="https://edgedl.me.gvt1.com/edgedl/release2/j0qc3/antigravity/stable"

release=$(curl -fsSL "$RELEASES_API" | jq -r '.[0] | "\(.version)-\(.execution_id)"')
# Some entries have a stray trailing slash in execution_id
release="${release%/}"

if [[ -z "$release" || "$release" == null* || "$release" == *null ]]; then
  echo "Error: could not resolve latest release from $RELEASES_API" >&2
  exit 1
fi

download_url="${DOWNLOAD_BASE}/${release}/linux-x64/Antigravity%20IDE.tar.gz"

# Verify the URL actually resolves before handing it to the build
if ! curl -fsIL "$download_url" >/dev/null; then
  echo "Error: constructed URL is not downloadable: $download_url" >&2
  exit 1
fi

echo "$download_url"
