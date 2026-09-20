#!/usr/bin/env bash
# LEGACY PREVIEW CONFIG — DISABLED.
#
# This targeted the former agilabs.cc preview. Brain Surgery now uses the approved
# Edge presentation, but no Edge production domain or host has been authorized.
# Keep this historical setup inert until the destination decision is explicit.
#
# Turn on the gated agilabs.cc preview. One command, run on Hetzner as a user
# with sudo, after agilabs.cc's A record points at this host.
#
#   ssh hetzner 'sudo bash /root/enable-agilabs.sh'
#
# Everything it touches was staged beforehand: the site configs are already in
# sites-available and the content is already in /var/www/agilabs-brain-surgery.
# This only sets the password, enables the two sites, and gets the certificate.
#
# The password is typed here rather than stored anywhere. It never reaches a
# command argument, a log, a file or the shell history: read -s holds it in the
# shell and htpasswd -i takes it on stdin.
set -euo pipefail

echo "Disabled: agilabs.cc is a legacy preview target; no Edge destination is approved." >&2
exit 2

DOMAIN=agilabs.cc
WEBROOT=/var/www/certbot
EXPECT_IP=91.99.110.206
AUTH_USER=agilabs

command -v nginx >/dev/null || { echo "nginx missing"; exit 1; }
command -v certbot >/dev/null || { echo "certbot missing"; exit 1; }
command -v htpasswd >/dev/null || { echo "htpasswd missing: apt install apache2-utils"; exit 1; }

# A certbot run against a domain that still points at the parking IP burns a
# rate-limit slot and fails anyway. Check first, and say which answer came back.
got=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
if [[ "$got" != "$EXPECT_IP" ]]; then
  echo "$DOMAIN resolves to '${got:-nothing}', expected $EXPECT_IP."
  echo "Point the A record at this host first, then run this again."
  exit 1
fi

if [[ ! -s /etc/nginx/agilabs.htpasswd ]]; then
  read -rsp "Password for user '$AUTH_USER': " pw; echo
  [[ -n "$pw" ]] || { echo "empty password, nothing written"; exit 1; }
  printf '%s' "$pw" | htpasswd -i -c /etc/nginx/agilabs.htpasswd "$AUTH_USER"
  unset pw
  chmod 640 /etc/nginx/agilabs.htpasswd
  chown root:www-data /etc/nginx/agilabs.htpasswd
  echo "password set for user '$AUTH_USER'"
else
  echo "htpasswd already present, leaving it alone"
fi

ln -sfn /etc/nginx/sites-available/agilabs-cc-http /etc/nginx/sites-enabled/agilabs-cc-http
if ! nginx -t; then echo "nginx config rejected, nothing reloaded"; exit 1; fi
systemctl reload nginx

certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN" -d "www.$DOMAIN" \
  --non-interactive --agree-tos -m fede@floom.dev

ln -sfn /etc/nginx/sites-available/agilabs-cc /etc/nginx/sites-enabled/agilabs-cc
if ! nginx -t; then echo "nginx config rejected, nothing reloaded"; exit 1; fi
systemctl reload nginx

echo
echo "https://$DOMAIN is live behind basic auth (user: $AUTH_USER)."
curl -sS -o /dev/null -w "no-auth   -> %{http_code} (expect 401)\n" "https://$DOMAIN/"
curl -sS -o /dev/null -w "robots    -> %{http_code} (expect 200)\n" "https://$DOMAIN/robots.txt"
# The whole point of the vanity path: it has to land on the page, not 404.
curl -sS -u "$AUTH_USER" -o /dev/null -w "/brain-surgery -> %{http_code} (expect 301)\n" \
  "https://$DOMAIN/brain-surgery" || true
