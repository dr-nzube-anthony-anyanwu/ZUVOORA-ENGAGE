#!/usr/bin/env bash
# ZUVOORA Engage — return an environment to its previous release (Phase 6).
#   sudo deploy/scripts/rollback.sh production|staging
# Swaps release.env with release.env.previous and restarts, waiting for health checks. Database
# migrations are NOT undone (they are written to be backward compatible; see
# docs/operations/ROLLBACK_AND_RECOVERY.md).
set -euo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  production) PROJECT=engage-prod ;;
  staging)    PROJECT=engage-staging ;;
  *) echo "usage: $0 production|staging" >&2; exit 2 ;;
esac
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DIR="${ENGAGE_BASE:-/opt/zuvoora-engage}/$ENV_NAME"
RELEASE="$DIR/release.env"; PREVIOUS="$DIR/release.env.previous"

[[ -f "$PREVIOUS" ]] || { echo "no previous release recorded for $ENV_NAME" >&2; exit 1; }
tmp="$(mktemp)"
cp -p "$RELEASE" "$tmp"; cp -p "$PREVIOUS" "$RELEASE"; cp -p "$tmp" "$PREVIOUS"; rm -f "$tmp"
echo "Returning $ENV_NAME to:"; sed 's/^/  /' "$RELEASE"
docker compose -p "$PROJECT" --env-file "$DIR/.env" --env-file "$RELEASE" \
  -f "$REPO/deploy/compose.yml" up -d --wait --wait-timeout 300
echo "$(date -u +%FT%TZ) ${SUDO_USER:-root} ROLLBACK $(tr '\n' ' ' < "$RELEASE")" >> "$DIR/releases.log"
echo "Rolled back. Run the smoke checks: sudo deploy/scripts/deploy.sh $ENV_NAME --current"
