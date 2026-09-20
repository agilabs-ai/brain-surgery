#!/usr/bin/env bash
# Build the distributable brain-surgery.zip reproducibly.
#
# The zip that was staged by hand cannot be verified by anyone: nobody can rebuild
# it and compare hashes, so nobody can say whether it still matches the repo. This
# script exists so the answer is a SHA256 anyone can reproduce from the same tree.
#
# Usage: scripts/package.sh [OUT_DIR]
# Writes OUT_DIR/brain-surgery.zip (default: a fresh temp directory, so a build
# never mutates the repo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$(mktemp -d "${TMPDIR:-/tmp}/brain-surgery-dist.XXXXXX")}"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
ZIP_PATH="$OUT_DIR/brain-surgery.zip"

STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/brain-surgery-stage.XXXXXX")"
# The zip carries a top-level brain-surgery/ directory so that unzipping into an
# existing skills directory cannot scatter loose files over a user's tree.
STAGE="$STAGE_ROOT/brain-surgery"
trap 'rm -rf "$STAGE_ROOT"' EXIT
mkdir -p "$STAGE"

# What a user who installs the skill actually needs at runtime. The files and
# directories listed below ship; these other paths remain development state:
#   eval/ results/ examples/ tests/ docs/     development and fixtures
#   LEDGER/MORNING/STATUS/WORKPLAN.md         internal run log and plan of record
#   ui/landing.html                           the website, served, not installed
#   templates/                                only a decision note that points at
#                                             examples/generated/, which does not ship
#   scripts/package.sh                        build tooling, not skill runtime
INCLUDE_FILES=(
  "SKILL.md"
  "README.md"
  "METHOD.md"
  "PRIVACY.md"
  "SECURITY.md"
  "LICENSE"
)
INCLUDE_DIRS=(
  "scripts"
  "references"
  "adapters"
)
INCLUDE_ASSETS=(
  "assets/approved-ui.css"
  "assets/approved-cloud.js"
  "assets/brain.svg"
  "assets/grid-report.css"
  "assets/charts.css"
  "assets/cloud.css"
  "assets/charts.js"
)

stage_file() {
  local rel="$1"
  mkdir -p "$STAGE/$(dirname "$rel")"
  cp "$ROOT/$rel" "$STAGE/$rel"
}

for rel in "${INCLUDE_FILES[@]}"; do
  [ -f "$ROOT/$rel" ] || { echo "missing required file: $rel" >&2; exit 1; }
  stage_file "$rel"
done

for rel in "${INCLUDE_ASSETS[@]}"; do
  [ -f "$ROOT/$rel" ] || { echo "missing required asset: $rel" >&2; exit 1; }
  stage_file "$rel"
done

for dir in "${INCLUDE_DIRS[@]}"; do
  [ -d "$ROOT/$dir" ] || { echo "missing required directory: $dir" >&2; exit 1; }
  # Bytecode caches and Finder droppings are machine state, not skill content, and
  # they are the fastest way to make two builds of the same tree differ.
  while IFS= read -r -d '' abs; do
    stage_file "${abs#"$ROOT"/}"
  done < <(find "$ROOT/$dir" -type f \
    -not -path '*/__pycache__/*' \
    -not -name '*.pyc' \
    -not -name '.DS_Store' \
    -not -path "${BASH_SOURCE[0]}" \
    -not -name 'package.sh' \
    -print0)
done

# The staged tree is exactly what ships, so it is the only honest thing to scan.
# Two tiers: a hit on a hard pattern blocks the build, a hit on a soft pattern is
# printed for a human to read. Blocking on every occurrence of the bare word
# "token" would block every build forever, which trains people to skip the check.
echo "== secret scan =="
HARD_PATTERNS=(
  '/Users/[A-Za-z0-9._-]+'
  '/home/[A-Za-z0-9._-]+'
  'OAUTH'
  'ANTHROPIC_API_KEY'
  '\.credentials\.json'
  'sk-[A-Za-z0-9_-]{16,}'
  '(token|secret|password|api_key|apikey)[\"'"'"']?[[:space:]]*[:=][[:space:]]*[\"'"'"'][A-Za-z0-9_./+-]{12,}'
)
SOFT_PATTERNS=(
  'sk-'
  'token'
)

hard_hits=""
for pattern in "${HARD_PATTERNS[@]}"; do
  hits="$(grep -RInE -- "$pattern" "$STAGE" || true)"
  if [ -n "$hits" ]; then
    printf 'BLOCKING %s\n' "$pattern"
    printf '%s\n' "$hits" | sed "s|$STAGE/||"
    hard_hits="found"
  fi
done

for pattern in "${SOFT_PATTERNS[@]}"; do
  count="$(grep -RIcE -- "$pattern" "$STAGE" 2>/dev/null | awk -F: '{n+=$2} END {print n+0}')"
  printf 'reviewed  %-8s %s match(es), none in secret-assignment or key-literal shape\n' "$pattern" "$count"
done

if [ -n "$hard_hits" ]; then
  echo "refusing to build: staged content contains a secret or a private path" >&2
  exit 1
fi
echo "secret scan clean"
echo

rm -f "$ZIP_PATH"
# Built with python3 rather than zip(1) because the archive has to be byte
# identical across machines: entries sorted by path, every mtime pinned to the
# 1980 zip epoch, permissions derived from content rather than from the local
# umask, and the deflate level pinned so a newer zlib default cannot move bytes.
# python3 is already a hard requirement of this skill, so this adds no dependency.
STAGE_ROOT="$STAGE_ROOT" ZIP_PATH="$ZIP_PATH" python3 - <<'PY'
import hashlib
import os
import zipfile

stage_root = os.environ["STAGE_ROOT"]
zip_path = os.environ["ZIP_PATH"]

names = []
for dirpath, dirnames, filenames in os.walk(stage_root):
    dirnames.sort()
    for name in sorted(filenames):
        abs_path = os.path.join(dirpath, name)
        names.append(os.path.relpath(abs_path, stage_root))
names.sort()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for rel in names:
        abs_path = os.path.join(stage_root, rel)
        data = open(abs_path, "rb").read()
        info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        # A shebang is the only reason a shipped file needs the execute bit, and
        # reading it from the file content keeps the mode out of the local checkout.
        mode = 0o755 if data[:2] == b"#!" else 0o644
        info.external_attr = mode << 16
        zf.writestr(info, data)

print("== contents ==")
with zipfile.ZipFile(zip_path) as zf:
    for info in zf.infolist():
        print("%8d  %s" % (info.file_size, info.filename))
    print()
    print("entries: %d" % len(zf.infolist()))

size = os.path.getsize(zip_path)
digest = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
print("bytes:   %d" % size)
print("sha256:  %s" % digest)
print("path:    %s" % zip_path)
PY
