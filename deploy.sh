#!/usr/bin/env bash
# deploy.sh — Deploy neighborhood events to pihole.lan
#
# Copies the HTML page to the getit-homepage nginx container on pihole.lan.
# Requires: sshpass with sudo password 'g'
#
# Usage:
#   ./deploy.sh                        # Deploy HTML only
#   ./deploy.sh --host pihole.lan      # Custom host
#   ./deploy.sh --path /path/on/pihole # Custom path
#
set -euo pipefail

HOST="${1:-pihole.lan}"
SSH_PASS="${SSH_PASS:-g}"
DEST_HOST="/home/bill/.docker/getit/html/neighborhood"
SITE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📦 Deploying neighborhood events to ${HOST}..."

# Create directory if needed
sshpass -p "${SSH_PASS}" ssh "bill@${HOST}" "mkdir -p ${DEST_HOST}"

# Copy the HTML file
sshpass -p "${SSH_PASS}" scp "${SITE_DIR}/index.html" "bill@${HOST}:${DEST_HOST}/index.html"

# Verify
sshpass -p "${SSH_PASS}" ssh "bill@${HOST}" "ls -la ${DEST_HOST}/index.html"

echo "✅ Deployed to http://getit.lan/neighborhood/"
echo "   (served via getit-homepage nginx container bind-mounted at ${DEST_HOST})"
