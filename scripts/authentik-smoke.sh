#!/usr/bin/env bash
# Manual reachability check for a locally running Authentik instance.
# NOT run by CI or pytest -- see deploy/authentik/README.md. Checks that
# the OIDC discovery, device, token, and JWKS endpoints all respond; does
# not exercise the actual device-code login flow (gateway.auth.cli does
# that).
set -euo pipefail

ISSUER="${PLATFORMOPS_OIDC_ISSUER:?set PLATFORMOPS_OIDC_ISSUER, e.g. http://localhost:9000/application/o/<slug>/}"
DISCOVERY_URL="${ISSUER%/}/.well-known/openid-configuration"

echo "Discovery: ${DISCOVERY_URL}"
discovery_json="$(curl -fsS "${DISCOVERY_URL}")" || {
    echo "FAIL: discovery endpoint unreachable or returned an error" >&2
    exit 1
}

device_endpoint="$(printf '%s' "${discovery_json}" | python3 -c \
    'import json, sys; print(json.load(sys.stdin).get("device_authorization_endpoint", ""))')"
token_endpoint="$(printf '%s' "${discovery_json}" | python3 -c \
    'import json, sys; print(json.load(sys.stdin).get("token_endpoint", ""))')"
jwks_uri="$(printf '%s' "${discovery_json}" | python3 -c \
    'import json, sys; print(json.load(sys.stdin).get("jwks_uri", ""))')"

status=0

# device/token endpoints are POST-only -- a plain GET returning any HTTP
# response (even 405) still proves the endpoint is reachable, so this
# only checks curl's own connection-level exit status, not the HTTP code.
check_reachable() {
    local name="$1" url="$2"
    if [ -z "${url}" ]; then
        echo "FAIL: discovery document did not advertise ${name}" >&2
        status=1
        return
    fi
    echo "${name}: ${url}"
    if curl -sS -o /dev/null "${url}"; then
        echo "  OK"
    else
        echo "  FAIL: unreachable" >&2
        status=1
    fi
}

check_reachable "device_authorization_endpoint" "${device_endpoint}"
check_reachable "token_endpoint" "${token_endpoint}"

echo "jwks_uri: ${jwks_uri}"
if [ -z "${jwks_uri}" ] || ! curl -fsS -o /dev/null "${jwks_uri}"; then
    echo "  FAIL: unreachable or did not return 200" >&2
    status=1
else
    echo "  OK"
fi

if [ "${status}" -eq 0 ]; then
    echo "OK: discovery, device, token, and JWKS endpoints all reachable"
fi
exit "${status}"
