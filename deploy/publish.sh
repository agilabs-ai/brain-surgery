#!/usr/bin/env bash
# Build the approved Edge design preview locally.
#
#   deploy/publish.sh --build-only /absolute/output/directory
#
# Remote publishing is deliberately disabled. The approved artifact is still a
# labeled design preview, and no Edge production domain or host has been approved.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" != "--build-only" || -z "${2:-}" || "${2:-}" != /* || -n "${3:-}" ]]; then
  echo "Remote publishing is disabled: no Edge production domain/host is approved." >&2
  echo "Build the labeled preview with: $0 --build-only /absolute/output/directory" >&2
  exit 2
fi
OUT="$2"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/brain-surgery-preview.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

# Derive the static staging artifact from the approved UI source. The source
# prototype remains intact for review, but its private fixture payload, router,
# preview dock, and simulated mutation/publishing controls never enter staging.
"$ROOT/deploy/build_stage.sh" "$STAGE"

grep -q 'Brain Surgery by Edge' "$STAGE/index.html" || {
  echo "refusing to stage: approved Edge title missing" >&2; exit 1;
}
grep -q 'DESIGN PREVIEW' "$STAGE/index.html" || {
  echo "refusing to stage: sample-data preview label missing" >&2; exit 1;
}

grep -q 'href="/brain-surgery.zip"' "$STAGE/index.html" || {
  echo "refusing to stage: package download link missing" >&2; exit 1;
}
sha=$(cat "$STAGE/brain-surgery.zip.sha256")
cp -R "$STAGE/." "$OUT/"

echo
echo "preview: $OUT/index.html"
echo "zip sha256: $sha"
