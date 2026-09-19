#!/usr/bin/env bash
# Push the agilabs.cc preview content to Hetzner.
#
#   deploy/publish.sh            build and sync
#   deploy/publish.sh --dry-run  show what would change, touch nothing
#
# Content only. It never enables a site, never reloads nginx and never touches
# DNS or the certificate: enable-agilabs.sh owns those, and it is run once.
# Re-running this against a live site is therefore safe and is how an updated
# report ships.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=hetzner
REMOTE=/var/www/agilabs-brain-surgery
DRY=(); [[ "${1:-}" == "--dry-run" ]] && DRY=(--dry-run)

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/agilabs-publish.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

# Built fresh rather than copied from out/, so what ships is what the current
# result.json and the current renderer produce, not whatever was left in the
# working tree from the last thing someone was looking at.
python3 "$ROOT/scripts/render_grid_report.py" --input "$ROOT/eval/result.json" \
  --out "$STAGE/report.html"

# The landing page is the site root. The file is named landing.html in the repo
# because that is what it is; on the server it has to be index.html because that
# is what nginx serves for /.
cp "$ROOT/ui/landing.html" "$STAGE/index.html"
mkdir -p "$STAGE/assets"
cp -R "$ROOT/ui/assets/brand" "$STAGE/assets/brand"

"$ROOT/scripts/package.sh" "$STAGE" >/dev/null
sha=$(shasum -a 256 "$STAGE/brain-surgery.zip" | awk '{print $1}')

# --delete is what removes files that no longer belong, which is the only way a
# page that was taken out of the site actually stops being served. The remote
# directory holds nothing but this content, so there is nothing else to lose.
rsync -a --delete "${DRY[@]}" --itemize-changes "$STAGE/" "$HOST:$REMOTE/"

if [[ ${#DRY[@]} -eq 0 ]]; then
  # Ownership and modes are fixed here rather than with rsync's --chmod, because
  # the rsync macOS ships is 2.6.9 and rejects the D/F prefixes outright. They
  # are not cosmetic: -a carries this machine's modes across, and a directory
  # that lands as 0700 owned by an unknown uid is one nginx cannot traverse.
  # Every request then answers 403 while the files look correct in a listing.
  ssh "$HOST" "chown -R root:www-data $REMOTE && \
               find $REMOTE -type d -exec chmod 755 {} + && \
               find $REMOTE -type f -exec chmod 644 {} +"
  # Proof, not assumption: ask the server whether the user nginx runs as can
  # actually read the page, rather than trusting that the chown above did it.
  ssh "$HOST" "sudo -u www-data test -r $REMOTE/index.html && \
               sudo -u www-data test -r $REMOTE/report.html && \
               echo 'www-data can read index.html and report.html'"
fi

echo
echo "zip sha256: $sha"
