#!/usr/bin/env bash
# End-to-end smoke test against a running MGTS Infrastructure Intelligence stack
# (docker compose, worker in rq mode). Exercises the full path:
# health -> login -> upload (synthetic JPEG + GPS) -> job -> poll -> observations
# -> assets -> map -> CSV export -> metrics -> logout.
#
# Usage:
#   BASE_URL=http://localhost:8000 ADMIN_USERNAME=admin ADMIN_PASSWORD=... ./scripts/smoke.sh
# Credentials fall back to demo-operator/demo-operator-password (scripts/seed_demo.py).
# Exit code 1 on any failed step.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-admin}"
FALLBACK_USERNAME="${FALLBACK_USERNAME:-demo-operator}"
FALLBACK_PASSWORD="${FALLBACK_PASSWORD:-demo-operator-password}"
POLL_TIMEOUT_SECONDS="${POLL_TIMEOUT_SECONDS:-120}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
step() { printf '==> %s\n' "$1"; }

json_field() {
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"
}

step "health/live"
code="$(curl -sS -o "$WORK_DIR/live.json" -w '%{http_code}' "$BASE_URL/health/live")" \
    || fail "health/live unreachable ($BASE_URL)"
[ "$code" = "200" ] || fail "health/live returned HTTP $code"
pass "health/live"

step "login ($ADMIN_USERNAME, fallback $FALLBACK_USERNAME)"
login() {
    curl -sS -o "$WORK_DIR/login.json" -w '%{http_code}' \
        -X POST "$BASE_URL/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$1\",\"password\":\"$2\"}"
}
code="$(login "$ADMIN_USERNAME" "$ADMIN_PASSWORD")" || fail "login request failed"
if [ "$code" != "200" ]; then
    code="$(login "$FALLBACK_USERNAME" "$FALLBACK_PASSWORD")" || fail "fallback login request failed"
fi
[ "$code" = "200" ] || fail "login returned HTTP $code for both credential sets"
TOKEN="$(json_field "$WORK_DIR/login.json" access_token)"
[ -n "$TOKEN" ] || fail "login response has no access_token"
AUTH="Authorization: Bearer $TOKEN"
pass "login"

step "synthetic JPEG (embedded base64, 320x240, passes quality gate)"
base64 -d > "$WORK_DIR/smoke.jpg" <<'JPEG_B64'
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a
HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy
MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCADwAUADASIA
AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA
AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3
ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm
p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA
AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx
BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK
U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3
uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDNooq/
pOi6hrdwYLC3aVlGWOQFUe5PFAFCiui1PwRrmlWjXU1srwoMu0Thto9SOtU7Xw5qV7os+rW8Svaw
kh8MN3ABJx+NAGTRVixsrjUb2GztU3zSttVasajol9pepjTp4t1yQu1Izu3Z6YxQBn0V1K/DzxG0
HmfZYw3/ADzMy7v54/Wsey0O/vtX/suOHZeAsCkh24wMnNAGdRWrB4c1O61qXSYYA91ESJAG+Vcd
yfSrEHhLVLrWLjS4RA9zbpvkAlGB04z680AYVFdb/wAK48Q/88rf/v8ACuVliaGZ4nGHRirD3HFA
DKK09F0C/wBfmlisURmiXc299vGcVtf8K48Q/wDPK3/7/CgDkqK6O38Ea1c313ZxxRebaFRLmUY+
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
BRRRQAUUUUAFFFFABRRRQAUUUUAf/9k=
JPEG_B64
[ -s "$WORK_DIR/smoke.jpg" ] || fail "embedded JPEG decoded to an empty file"
pass "synthetic JPEG ready ($(wc -c < "$WORK_DIR/smoke.jpg") bytes)"

step "upload multipart with gps_track metadata"
METADATA="$(python3 - <<'PY'
import json
from datetime import datetime, timedelta, timezone

start = datetime.now(timezone.utc)
track = [
    {
        "timestamp": (start + timedelta(seconds=i)).isoformat(),
        "longitude": round(37.6173 + i * 0.00013, 7),
        "latitude": round(55.7558 + i * 0.00007, 7),
        "accuracy_m": 4.0,
    }
    for i in range(3)
]
print(json.dumps({"capture_started_at": start.isoformat(), "gps_track": track, "smoke": True}))
PY
)"
code="$(curl -sS -o "$WORK_DIR/upload.json" -w '%{http_code}' \
    -X POST "$BASE_URL/api/v1/uploads" -H "$AUTH" \
    -F "file=@$WORK_DIR/smoke.jpg;type=image/jpeg" \
    -F "metadata=$METADATA")" || fail "upload request failed"
[ "$code" = "200" ] || [ "$code" = "201" ] || fail "upload returned HTTP $code: $(cat "$WORK_DIR/upload.json")"
UPLOAD_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upload"]["id"])' "$WORK_DIR/upload.json")"
pass "upload (id=$UPLOAD_ID)"

step "create processing job"
code="$(curl -sS -o "$WORK_DIR/job.json" -w '%{http_code}' \
    -X POST "$BASE_URL/api/v1/jobs" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"upload_id\":\"$UPLOAD_ID\"}")" || fail "job create request failed"
[ "$code" = "200" ] || [ "$code" = "201" ] \
    || fail "job create returned HTTP $code: $(cat "$WORK_DIR/job.json")"
JOB_ID="$(json_field "$WORK_DIR/job.json" id)"
pass "job created (id=$JOB_ID)"

step "poll job until terminal (<= ${POLL_TIMEOUT_SECONDS}s, rq worker mode)"
deadline=$(( $(date +%s) + POLL_TIMEOUT_SECONDS ))
STATUS=""
while [ "$(date +%s)" -lt "$deadline" ]; do
    code="$(curl -sS -o "$WORK_DIR/job_status.json" -w '%{http_code}' \
        "$BASE_URL/api/v1/jobs/$JOB_ID" -H "$AUTH")" || fail "job poll request failed"
    [ "$code" = "200" ] || fail "job poll returned HTTP $code"
    STATUS="$(json_field "$WORK_DIR/job_status.json" status)"
    case "$STATUS" in
        COMPLETED|PARTIALLY_COMPLETED|FAILED|CANCELLED) break ;;
    esac
    sleep 2
done
case "$STATUS" in
    COMPLETED|PARTIALLY_COMPLETED) pass "job terminal: $STATUS" ;;
    FAILED|CANCELLED) fail "job ended with status $STATUS: $(cat "$WORK_DIR/job_status.json")" ;;
    *) fail "job not terminal after ${POLL_TIMEOUT_SECONDS}s (last status: ${STATUS:-unknown})" ;;
esac

step "list observations for the job"
code="$(curl -sS -o "$WORK_DIR/observations.json" -w '%{http_code}' \
    "$BASE_URL/api/v1/observations?job_id=$JOB_ID&page_size=5" -H "$AUTH")" \
    || fail "observations request failed"
[ "$code" = "200" ] || fail "observations returned HTTP $code"
pass "observations (total=$(json_field "$WORK_DIR/observations.json" total))"

step "list assets (page_size=1)"
code="$(curl -sS -o "$WORK_DIR/assets.json" -w '%{http_code}' \
    "$BASE_URL/api/v1/assets?page_size=1" -H "$AUTH")" || fail "assets request failed"
[ "$code" = "200" ] || fail "assets returned HTTP $code"
pass "assets (total=$(json_field "$WORK_DIR/assets.json" total))"

step "map/assets GeoJSON layer"
code="$(curl -sS -o "$WORK_DIR/map.json" -w '%{http_code}' \
    "$BASE_URL/api/v1/map/assets" -H "$AUTH")" || fail "map request failed"
[ "$code" = "200" ] || fail "map/assets returned HTTP $code"
[ "$(json_field "$WORK_DIR/map.json" type)" = "FeatureCollection" ] \
    || fail "map/assets is not a FeatureCollection"
pass "map/assets"

step "export defects CSV (header row)"
code="$(curl -sS -o "$WORK_DIR/defects.csv" -w '%{http_code}' \
    "$BASE_URL/api/v1/exports/defects?format=csv" -H "$AUTH")" || fail "export request failed"
[ "$code" = "200" ] || fail "exports/defects returned HTTP $code"
head -1 "$WORK_DIR/defects.csv" | grep -q 'defect_type' \
    || fail "CSV header missing defect_type column: $(head -1 "$WORK_DIR/defects.csv")"
pass "exports/defects csv"

step "metrics expose pipeline/http counters"
curl -fsS -o "$WORK_DIR/metrics.txt" "$BASE_URL/metrics" || fail "metrics endpoint unreachable"
grep -Eq 'pipeline_|http_requests' "$WORK_DIR/metrics.txt" \
    || fail "metrics contain neither pipeline_ nor http_requests series"
pass "metrics"

step "logout"
code="$(curl -sS -o "$WORK_DIR/logout.json" -w '%{http_code}' \
    -X POST "$BASE_URL/api/v1/auth/logout" -H "$AUTH")" || fail "logout request failed"
[ "$code" = "200" ] || fail "logout returned HTTP $code"
pass "logout"

printf 'SMOKE OK: %s\n' "$BASE_URL"
