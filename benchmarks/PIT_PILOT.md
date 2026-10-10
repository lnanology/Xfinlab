# Point-in-time (PIT) fundamentals pilot: design

Goal: answer "what financial data was publicly available on date D?" for a small set of US companies, so backtests and AI research cannot use information from the future.

Hypothesis to verify first (not yet confirmed): SEC EDGAR filings carry an acceptance timestamp and amendments appear as separate filings, so facts can be stamped with the time they became public. Check this on 5 companies before writing code.

Scope: 20 US large caps, quarterly and annual statements, 2018 onwards. No other markets, no claim of full coverage.

Output per fact: value, period, filed_at (public time), accession number, and whether later amended.

Pass criteria for the pilot:
1. For 20 companies x 8 historical dates, a query returns only facts with filed_at <= D.
2. At least one amended filing is shown to change the answer between two dates.
3. A reviewer can re-check any returned fact against the filing by accession number.

Stop if: the acceptance timestamp is missing for a material share of filings, or amendments cannot be linked to originals.
Licence: SEC filings are public; still record the source for each fact.
