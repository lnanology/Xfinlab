"""
Small shared helper to retire the f-string-built-WHERE-clause pattern
flagged by the 2026-09-14 security audit (services/prediction_ledger_
service.py's get_ledger_stats()/get_recent_predictions(), services/
formula_composer_service.py's get_leaderboard()).

All three call sites were already safe in actual behavior -- every real
value (symbol, source, ...) was already bound through a `?` placeholder and
passed separately in the params list; the f-string only ever spliced in
fixed literal clause fragments like "AND symbol = ?", never a value. But
"build a WHERE clause via an f-string" is exactly the shape static-analysis
security scanners (bandit B608, semgrep's python.lang.security.audit.
formatted-sql-query) flag as SQL-injection-risk code, and it's one careless
future edit away from someone splicing a real value in directly instead of
reaching for a placeholder. Centralizing the safe construction here means
nobody has to re-derive "is this particular f-string actually safe?" at each
call site, and a future scanner run has nothing left to flag.

Deliberately minimal: equality-only, ANDed conditions -- the only shape any
current call site needs. Column names come from the caller's dict keys and
must always be literal strings written in the calling code (never a
variable derived from user input) -- they're trusted the same way a column
name in a hand-written SQL statement always is; only the dict *values* are
untrusted, and those are never interpolated into the returned SQL text.
"""
from typing import Any, Dict, List, Tuple


def build_equality_where(conditions: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """Build a `WHERE col1 = ? AND col2 = ?` clause (or `""` if every value
    is falsy/None) from an ordered dict of {column_name: value}.

    Returns (where_clause, params) -- params must be passed as the query's
    parameter list (appended before any additional placeholders like a
    trailing `LIMIT ?`), never formatted into the SQL string.
    """
    clauses: List[str] = []
    params: List[Any] = []
    for column, value in conditions.items():
        if value is None or value == "":
            continue
        clauses.append(f"{column} = ?")
        params.append(value)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
