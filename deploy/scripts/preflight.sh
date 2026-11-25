#!/usr/bin/env bash
# ZUVOORA Engage — check an environment's settings BEFORE deploying (Phase 6).
#   sudo deploy/scripts/preflight.sh production|staging
# Never prints a value: only setting NAMES and OK/problem lines. Exit 0 = ready, 1 = problems.
# The env file is parsed as text, never executed (no `source`).
set -euo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  production) ENGAGE_ENV_EXPECTED=prod; OTHER=staging ;;
  staging)    ENGAGE_ENV_EXPECTED=staging; OTHER=production ;;
  *) echo "usage: $0 production|staging" >&2; exit 2 ;;
esac
BASE="${ENGAGE_BASE:-/opt/zuvoora-engage}"
FILE="$BASE/$ENV_NAME/.env"
OTHER_FILE="$BASE/$OTHER/.env"
problems=0
fail() { echo "  PROBLEM: $*"; problems=$((problems + 1)); }

value() {  # value NAME FILE -> prints the value (internal use only; never echoed to the user)
  grep -E "^$1=" "$2" 2>/dev/null | tail -n1 | cut -d= -f2- || true
}

echo "Checking $FILE"
if [[ ! -f "$FILE" ]]; then
  echo "  PROBLEM: file not found"; exit 1
fi
owner="$(stat -c %U "$FILE")"; mode="$(stat -c %a "$FILE")"
[[ "$owner" == "root" ]] || fail "owner must be root (is $owner): sudo chown root:root $FILE"
[[ "$mode" == "600" ]] || fail "mode must be 600 (is $mode): sudo chmod 600 $FILE"

REQUIRED=(ENGAGE_ENV ENGAGE_ENV_FILE ENGAGE_EDGE_NETWORK ENGAGE_EDGE_SUBNET ENGAGE_INTERNAL_SUBNET
  FORWARDED_ALLOW_IPS APP_ENV DASHBOARD_URL API_CORS_ORIGINS PUBLIC_API_URL SUPABASE_URL
  SUPABASE_PUBLISHABLE_KEY SUPABASE_SECRET_KEY DATABASE_URL WIDGET_TOKEN_SECRET
  INTEGRATIONS_ENCRYPTION_KEY EMAIL_DELIVERY EMAIL_FROM)
for name in "${REQUIRED[@]}"; do
  v="$(value "$name" "$FILE")"
  if [[ -z "$v" ]]; then fail "$name is missing or empty"
  elif [[ "$v" == *REPLACE* ]]; then fail "$name still contains a placeholder"
  fi
done

[[ "$(value ENGAGE_ENV "$FILE")" == "$ENGAGE_ENV_EXPECTED" ]] || fail "ENGAGE_ENV must be $ENGAGE_ENV_EXPECTED"
[[ "$(value APP_ENV "$FILE")" == "$ENV_NAME" ]] || fail "APP_ENV must be $ENV_NAME"
[[ "$(value ENGAGE_ENV_FILE "$FILE")" == "$FILE" ]] || fail "ENGAGE_ENV_FILE must be $FILE"
for name in DASHBOARD_URL PUBLIC_API_URL SUPABASE_URL; do
  [[ "$(value "$name" "$FILE")" == https://* ]] || fail "$name must start with https://"
done
if [[ "$ENV_NAME" == production ]]; then
  [[ "$(value EMAIL_DELIVERY "$FILE")" == resend ]] || fail "EMAIL_DELIVERY must be resend"
  [[ -z "$(value EMAIL_ALLOWED_RECIPIENTS "$FILE")" ]] || fail "EMAIL_ALLOWED_RECIPIENTS must be empty"
fi
if [[ "$(value AI_ENABLED "$FILE")" == true || "$(value AI_VISION_ENABLED "$FILE")" == true ]]; then
  v="$(value OPENROUTER_API_KEY "$FILE")"
  [[ -n "$v" && "$v" != *REPLACE* ]] || fail "AI is on but OPENROUTER_API_KEY is missing"
fi
if [[ "$(value EMAIL_DELIVERY "$FILE")" == resend ]]; then
  v="$(value RESEND_API_KEY "$FILE")"
  [[ -n "$v" && "$v" != *REPLACE* ]] || fail "EMAIL_DELIVERY=resend but RESEND_API_KEY is missing"
fi
w="$(value WIDGET_TOKEN_SECRET "$FILE")"
(( ${#w} >= 32 )) || fail "WIDGET_TOKEN_SECRET must be at least 32 characters"

# Staging and production must never share a secret (compared by hash, never printed).
if [[ -f "$OTHER_FILE" ]]; then
  for name in SUPABASE_SECRET_KEY DATABASE_URL WIDGET_TOKEN_SECRET INTEGRATIONS_ENCRYPTION_KEY \
              RESEND_API_KEY OPENROUTER_API_KEY; do
    a="$(value "$name" "$FILE")"; b="$(value "$name" "$OTHER_FILE")"
    if [[ -n "$a" && -n "$b" ]] && \
       [[ "$(printf %s "$a" | sha256sum)" == "$(printf %s "$b" | sha256sum)" ]]; then
      fail "$name is the same in staging and production"
    fi
  done
fi

if (( problems > 0 )); then
  echo "Preflight FAILED: $problems problem(s). Nothing was deployed."
  exit 1
fi
echo "Preflight OK"
