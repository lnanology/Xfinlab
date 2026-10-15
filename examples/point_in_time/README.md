# Point-in-Time fundamentals: first request

Question answered: **"What was actually knowable about this company on date T?"**

1. Get a free key: https://www.xfinlab.com/intelligence-api.html (issued by email).
2. `export XFINLAB_API_KEY=xfl_...`
3. Pick one:
   - `./curl.sh AAPL 2023-06-30`
   - `python python_example.py AAPL 2023-06-30`
   - `python mcp_example.py AAPL 2023-06-30`

If a ticker has no stored history for that date you get a standard error (`success: false`, `meta.error_code: NO_POINT_IN_TIME_DATA`), never zeros. Each fact carries `data_time` (the period it describes), `publication_time` (SEC filing date) and `available_at` (filing date + 2 business days, weekends only). A value is only returned if `available_at` is on or before your date, so later restatements never leak into earlier dates.

Every valid answer also carries a `research_id` (`XF-YYYY-NNNNNN`), an `evidence` block (method version, sources, data status, newest filing date used, limitations) and `source` with its licence status. Save the `research_id` and the `publication_time` values next to your result to reproduce it.

Coverage is not global: US SEC filers that XFINLAB has ingested, annual (10-K) figures only. Not investment advice.
