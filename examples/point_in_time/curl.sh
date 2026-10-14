#!/usr/bin/env bash
# What did an investor actually know about a company on a past date?
# Usage: XFINLAB_API_KEY=xfl_... ./curl.sh AAPL 2023-06-30
# Free key: https://www.xfinlab.com/intelligence-api.html
TICKER="${1:-AAPL}"
AS_OF="${2:-2023-06-30}"
BASE="https://api.xfinlab.com/api/intelligence/v1"

curl -s -G -H "X-API-Key: ${XFINLAB_API_KEY:?set XFINLAB_API_KEY}" \
  --data-urlencode "as_of_date=${AS_OF}" \
  "${BASE}/fundamentals/${TICKER}/as-of"
echo
