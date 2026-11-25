#!/usr/bin/env bash
# Tests for preflight.sh (Phase 6). Runs in CI as root on Linux:  sudo deploy/scripts/test_preflight.sh
# Uses throwaway values in a temporary directory; nothing here is a real secret.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(mktemp -d)"
trap 'rm -rf "$BASE"' EXIT
mkdir -p "$BASE/production" "$BASE/staging"
failures=0

write_env() {  # write_env <env> <secret-suffix> [extra lines...]
  local env="$1" suffix="$2"; shift 2
  local file="$BASE/$env/.env"
  local engage_env=prod; [[ "$env" == staging ]] && engage_env=staging
  local host=engage; [[ "$env" == staging ]] && host=staging-engage
  cat > "$file" <<EOF
ENGAGE_ENV=$engage_env
ENGAGE_ENV_FILE=$file
ENGAGE_EDGE_NETWORK=engage-edge-$engage_env
ENGAGE_EDGE_SUBNET=10.73.0.0/24
ENGAGE_INTERNAL_SUBNET=10.73.1.0/24
FORWARDED_ALLOW_IPS=10.73.0.0/24,10.73.1.0/24
APP_ENV=$env
DASHBOARD_URL=https://$host.example.com
API_CORS_ORIGINS=https://$host.example.com
PUBLIC_API_URL=https://api-$host.example.com
SUPABASE_URL=https://project-$suffix.example.com
SUPABASE_PUBLISHABLE_KEY=sb_publishable_test_$suffix
SUPABASE_SECRET_KEY=test-secret-$suffix
DATABASE_URL=postgresql://engage_api:test-$suffix@db.example.com:5432/postgres
WIDGET_TOKEN_SECRET=test-widget-secret-$suffix-0123456789abcdefghijklmnop
INTEGRATIONS_ENCRYPTION_KEY=test-key-$suffix
EMAIL_DELIVERY=resend
RESEND_API_KEY=test-resend-$suffix
EMAIL_FROM=ZUVOORA Engage <no-reply@example.com>
EMAIL_ALLOWED_RECIPIENTS=
AI_ENABLED=false
EOF
  local line
  for line in "$@"; do printf '%s\n' "$line" >> "$file"; done
  chown root:root "$file"; chmod 600 "$file"
}

expect() {  # expect <ok|fail> <description> <env>
  local want="$1" what="$2" env="$3" out
  if out="$(ENGAGE_BASE="$BASE" "$HERE/preflight.sh" "$env" 2>&1)"; then got=ok; else got=fail; fi
  if [[ "$got" == "$want" ]]; then echo "ok   - $what"; else
    echo "FAIL - $what (expected $want, got $got)"; echo "$out" | sed 's/^/       /'
    failures=$((failures + 1)); fi
  # Values must never appear in the output.
  if grep -q "test-secret-\|test-resend-\|test-widget-secret" <<<"$out"; then
    echo "FAIL - $what: a value was printed"; failures=$((failures + 1)); fi
}

write_env production a; rm -f "$BASE/staging/.env"
expect ok   "complete production settings pass" production

chmod 644 "$BASE/production/.env"
expect fail "readable by others is refused" production
chmod 600 "$BASE/production/.env"

write_env production a "SUPABASE_SECRET_KEY=REPLACE"
expect fail "placeholder left in is refused" production

write_env production a "DASHBOARD_URL=http://engage.example.com"
expect fail "http dashboard URL is refused" production

write_env production a "EMAIL_DELIVERY=log"
expect fail "production without real email is refused" production

write_env production a "AI_ENABLED=true"
expect fail "AI on without a key is refused" production

write_env production a "WIDGET_TOKEN_SECRET=short"
expect fail "short widget secret is refused" production

write_env production a; write_env staging b "EMAIL_ALLOWED_RECIPIENTS=tester@example.com"
expect ok   "staging with its own secrets passes" staging

write_env staging a "EMAIL_ALLOWED_RECIPIENTS=tester@example.com"
expect fail "staging sharing production secrets is refused" staging

if (( failures > 0 )); then echo "$failures preflight test(s) failed"; exit 1; fi
echo "all preflight tests passed"
