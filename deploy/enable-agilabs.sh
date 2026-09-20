#!/usr/bin/env bash
# agilabs.cc is already enabled on Hetzner. Content releases must not rewrite
# nginx, DNS, TLS, credentials, or the current public access policy.
set -euo pipefail

echo "agilabs.cc is already enabled; use deploy/publish.sh --publish for content-only releases" >&2
exit 2
