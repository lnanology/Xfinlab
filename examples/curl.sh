#!/usr/bin/env bash
# Usage: XFINLAB_API_KEY=xfl_... ./curl.sh AAPL
TICKER="${1:-AAPL}"
BASE="https://api.xfinlab.com/api/intelligence/v1"
H="X-API-Key: ${XFINLAB_API_KEY:?set XFINLAB_API_KEY}"

echo "== Technical =="; curl -s -H "$H" "$BASE/technical/$TICKER"
echo; echo "== Sentiment =="; curl -s -H "$H" "$BASE/sentiment?ticker=$TICKER&limit=5"
echo; echo "== Events =="; curl -s -H "$H" "$BASE/events"
echo
# Remaining quota is in the response headers:
curl -s -D - -o /dev/null -H "$H" "$BASE/technical/$TICKER" | grep -i '^x-ratelimit'
