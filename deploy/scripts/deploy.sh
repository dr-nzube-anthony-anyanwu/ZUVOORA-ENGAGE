#!/usr/bin/env bash
# ZUVOORA Engage — deploy one release to one environment (Phase 6; started by a person only).
#
#   sudo deploy/scripts/deploy.sh staging    <api-image@sha256:...> <web-image@sha256:...>
#   sudo deploy/scripts/deploy.sh production <api-image@sha256:...> <web-image@sha256:...>
#   sudo deploy/scripts/deploy.sh production --current      # recreate with the current release
#
# Steps (stops at the first failure):
#   1. preflight.sh (settings, permissions, no shared secrets; values never printed)
#   2. the environment's edge network exists (created with its fixed subnet if missing)
#   3. the release (image digests) is written to release.env; the previous one is kept
#   4. pull, then `docker compose up -d --wait` (waits for every health check)
#   5. smoke checks inside the containers
#   6. on any failure after step 3: automatic rollback to the previous release
#   7. one line appended to releases.log (time, operator, digests, result)
set -euo pipefail

ENV_NAME="${1:-}"; API_IMAGE="${2:-}"; WEB_IMAGE="${3:-}"
case "$ENV_NAME" in
  production) PROJECT=engage-prod ;;
  staging)    PROJECT=engage-staging ;;
  *) echo "usage: $0 production|staging <api-image@sha256:...> <web-image@sha256:...> | --current" >&2; exit 2 ;;
esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BASE="${ENGAGE_BASE:-/opt/zuvoora-engage}"
DIR="$BASE/$ENV_NAME"
ENV_FILE="$DIR/.env"
RELEASE="$DIR/release.env"
PREVIOUS="$DIR/release.env.previous"
LOG="$DIR/releases.log"
COMPOSE=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" --env-file "$RELEASE" -f "$REPO/deploy/compose.yml")

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 2; }
value() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }

echo "== 1. Preflight"
ENGAGE_BASE="$BASE" "$HERE/preflight.sh" "$ENV_NAME"

echo "== 2. Edge network"
EDGE="$(value ENGAGE_EDGE_NETWORK)"; EDGE_SUBNET="$(value ENGAGE_EDGE_SUBNET)"
if ! docker network inspect "$EDGE" >/dev/null 2>&1; then
  docker network create --driver bridge --subnet "$EDGE_SUBNET" "$EDGE" >/dev/null
  echo "created $EDGE ($EDGE_SUBNET)"
else
  echo "$EDGE exists"
fi

echo "== 3. Release"
if [[ "$API_IMAGE" == "--current" ]]; then
  [[ -f "$RELEASE" ]] || { echo "no current release to recreate" >&2; exit 1; }
else
  for image in "$API_IMAGE" "$WEB_IMAGE"; do
    [[ "$image" =~ ^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$ ]] || {
      echo "images must be given by digest (name@sha256:<64 hex>)" >&2; exit 2; }
  done
  [[ -f "$RELEASE" ]] && cp -p "$RELEASE" "$PREVIOUS"
  umask 077
  printf 'ENGAGE_API_IMAGE=%s\nENGAGE_WEB_IMAGE=%s\n' "$API_IMAGE" "$WEB_IMAGE" > "$RELEASE"
fi
grep -E '^ENGAGE_(API|WEB)_IMAGE=' "$RELEASE" | sed 's/^/  /'

rollback() {
  echo "!! Deployment failed — rolling back"
  if [[ -f "$PREVIOUS" && "$API_IMAGE" != "--current" ]]; then
    cp -p "$PREVIOUS" "$RELEASE"
    "${COMPOSE[@]}" up -d --wait --wait-timeout 300 || echo "!! rollback did not become healthy — investigate now"
    echo "$(date -u +%FT%TZ) ${SUDO_USER:-root} ROLLED-BACK $(tr '\n' ' ' < "$RELEASE")" >> "$LOG"
  else
    echo "!! no previous release to return to — investigate now"
  fi
  echo "$(date -u +%FT%TZ) ${SUDO_USER:-root} FAILED $API_IMAGE $WEB_IMAGE" >> "$LOG"
  exit 1
}
trap rollback ERR

echo "== 4. Pull and start (waits for health checks)"
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" pull --quiet
"${COMPOSE[@]}" up -d --wait --wait-timeout 300 --remove-orphans

echo "== 5. Smoke checks"
"${COMPOSE[@]}" exec -T api python -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:8073/health/ready', timeout=5); assert r.status==200" \
  && echo "  api ready (database reachable)"
"${COMPOSE[@]}" exec -T api python -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:8073/widget/v1/loader.js', timeout=5); assert r.status==200" \
  && echo "  widget loader served"
"${COMPOSE[@]}" exec -T api python -c "
import urllib.request as u, urllib.error as e
try:
    u.urlopen('http://127.0.0.1:8073/docs', timeout=5); raise SystemExit('docs exposed')
except e.HTTPError as x:
    assert x.code == 404" && echo "  API docs not exposed"
"${COMPOSE[@]}" exec -T worker python -m app.healthcheck worker >/dev/null && echo "  worker heartbeat"
"${COMPOSE[@]}" exec -T web node -e "fetch('http://127.0.0.1:3073/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
  && echo "  dashboard answering"

trap - ERR
echo "$(date -u +%FT%TZ) ${SUDO_USER:-root} OK $(tr '\n' ' ' < "$RELEASE")" >> "$LOG"
echo "== Deployed $ENV_NAME. Now check from outside: https://$( [[ $ENV_NAME == production ]] && echo engage || echo staging-engage ).zuvoora.com"
