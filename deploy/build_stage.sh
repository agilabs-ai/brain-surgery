#!/usr/bin/env bash
# Build deployment bytes locally. No network access and no production mutation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="${1:?usage: deploy/build_stage.sh EMPTY_OUTPUT_DIRECTORY}"

mkdir -p "$STAGE"
if find "$STAGE" -mindepth 1 -print -quit | grep -q .; then
  echo "refusing to overwrite non-empty stage directory: $STAGE" >&2
  exit 1
fi

python3 "$ROOT/scripts/build_landing.py" --source "$ROOT/ui/landing.html" \
  --out "$STAGE/index.html"
mkdir -p "$STAGE/assets"
cp -R "$ROOT/ui/assets/brand" "$STAGE/assets/brand"
cp "$ROOT/assets/approved-cloud.js" "$STAGE/assets/approved-cloud.js"
"$ROOT/scripts/package.sh" "$STAGE" >/dev/null

shasum -a 256 "$STAGE/brain-surgery.zip" | awk '{print $1}' > "$STAGE/brain-surgery.zip.sha256"
