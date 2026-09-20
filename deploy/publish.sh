#!/usr/bin/env bash
# Build or atomically publish the AGI Labs Brain Surgery site.
#
#   deploy/publish.sh --build-only /absolute/empty/output
#   deploy/publish.sh --dry-run
#   deploy/publish.sh --publish
#
# Publishing changes content only. It does not touch nginx, DNS, TLS, access
# policy, credentials, or the dormant htpasswd file on Hetzner.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=hetzner
LIVE=/var/www/agilabs-brain-surgery
MODE="${1:-}"

[[ "$MODE" == "--publish" || "$MODE" == "--dry-run" || "$MODE" == "--build-only" ]] || {
  echo "usage: $0 --publish | --dry-run | --build-only /absolute/empty/output" >&2
  exit 2
}

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/agilabs-publish.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
"$ROOT/deploy/build_stage.sh" "$STAGE"

require_text() {
  grep -q "$2" "$STAGE/$1" || { echo "refusing release: $1 lacks $2" >&2; exit 1; }
}
reject_text() {
  if grep -qi "$2" "$STAGE/$1"; then
    echo "refusing release: $1 contains forbidden pattern $2" >&2
    exit 1
  fi
}

require_text index.html 'Brain Surgery by AGI Labs'
require_text index.html 'agi labs'
require_text index.html 'href="/brain-surgery.zip"'
require_text index.html 'href="/report.html"'
require_text report.html 'Brain Surgery, by AGI Labs'
require_text report.html 'Illustrative example'
require_text report.html 'MODEL × SETUP'
require_text report.html 'The tasks behind the result'
reject_text index.html 'Brain Surgery by Edge'
reject_text index.html 'getedge\.cc'
reject_text report.html 'id="local-data"'
reject_text report.html '/Users/'
reject_text report.html '/home/'

if [[ "$MODE" == "--build-only" ]]; then
  OUT="${2:-}"
  [[ "$OUT" == /* && -z "${3:-}" ]] || {
    echo "usage: $0 --build-only /absolute/empty/output" >&2; exit 2;
  }
  mkdir -p "$OUT"
  [[ -z "$(find "$OUT" -mindepth 1 -print -quit)" ]] || {
    echo "refusing to overwrite non-empty output directory: $OUT" >&2; exit 1;
  }
  cp -R "$STAGE/." "$OUT/"
  echo "preview: $OUT/index.html"
  echo "zip sha256: $(cat "$STAGE/brain-surgery.zip.sha256")"
  exit 0
fi

if [[ "$MODE" == "--dry-run" ]]; then
  rsync -a --delete --dry-run --itemize-changes "$STAGE/" "$HOST:$LIVE/"
  echo "dry run only; live site unchanged"
  exit 0
fi

[[ "$MODE" == "--publish" ]] || exit 2

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE="/var/www/.agilabs-brain-surgery.stage.$STAMP"
REMOTE_BACKUP="/var/www/.agilabs-brain-surgery.backup.$STAMP"

ssh "$HOST" "test ! -e '$REMOTE_STAGE' && mkdir '$REMOTE_STAGE'"
rsync -a --delete "$STAGE/" "$HOST:$REMOTE_STAGE/"
ssh "$HOST" "set -e
  chown -R root:www-data '$REMOTE_STAGE'
  find '$REMOTE_STAGE' -type d -exec chmod 755 {} +
  find '$REMOTE_STAGE' -type f -exec chmod 644 {} +
  sudo -u www-data test -r '$REMOTE_STAGE/index.html'
  sudo -u www-data test -r '$REMOTE_STAGE/report.html'
  sudo -u www-data test -r '$REMOTE_STAGE/brain-surgery.zip'
  test \"\$(sha256sum '$REMOTE_STAGE/brain-surgery.zip' | awk '{print \$1}')\" = \"$(cat "$STAGE/brain-surgery.zip.sha256")\"
  mv '$LIVE' '$REMOTE_BACKUP'
  mv '$REMOTE_STAGE' '$LIVE'"

echo "published: https://agilabs.cc/"
echo "rollback:  $REMOTE_BACKUP"
echo "zip sha256: $(cat "$STAGE/brain-surgery.zip.sha256")"
