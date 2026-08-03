"""
Post-hoc checks for detecting possible truncation in streaming extraction.

Checks:
- Monthly row counts for abrupt cutoffs
- ID/date consistency at the data tail
- Coverage of expected dump dates
- Cross-file consistency between votes and posts

The checks use existing Parquet files only and do not re-read the archive.
They provide indirect completeness evidence; direct verification requires
byte reconciliation with the source archive.

Usage:
    python scripts/check_stream_completeness.py

Output:
    logs/stream_completeness.txt
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

import duckdb

# Uncompressed member sizes for the 2025-03-31 Stack Overflow archive,
# as reported by `7z l data/raw/stackoverflow.com.7z`. Used only to generate
# the byte-assertion snippet; this script does not read the archive.
MEMBER_BYTES = {
    "posts": 105_661_126_290,
    "votes": 23_869_760_941,
    "posthistory": 184_794_992_826,
}

# A truncated stream loses the most RECENT records (Id-ordered dump).
# If the final month holds this share or more of the preceding months' mean
# volume, the series ends on a cliff rather than a taper.
CLIFF_RATIO = 0.80


class Report:
    """Collects console output and check outcomes for the log file."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.results: list[tuple[str, str, str]] = []  # (check, status, detail)

    def say(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def check(self, name: str, status: str, detail: str = "") -> None:
        """status: PASS | WARN | FAIL | INFO"""
        self.results.append((name, status, detail))
        self.say(f"  [{status:4s}] {name}" + (f"  -- {detail}" if detail else ""))

    def overall(self) -> str:
        statuses = [s for _, s, _ in self.results]
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")
        print(f"\n  Report written -> {path}")


def q(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchall()


def q1(con: duckdb.DuckDBPyConnection, sql: str):
    row = con.execute(sql).fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------
# Check 1 + 2 + 3: per-file tail diagnostics
# --------------------------------------------------------------------------
def check_file_tail(con, rpt: Report, label: str, path: str,
                    date_col: str, id_col: str, dump_max_date: str) -> None:
    rpt.say(f"\n{'-' * 66}")
    rpt.say(f"FILE: {label}  ({path})")
    rpt.say(f"{'-' * 66}")

    if not os.path.isfile(path):
        rpt.check(f"{label}_file_exists", "FAIL", "file not found")
        return

    con.execute(
        f"CREATE OR REPLACE VIEW t AS SELECT * FROM read_parquet('{path}')"
    )

    n_rows = q1(con, "SELECT COUNT(*) FROM t")
    size_gb = os.path.getsize(path) / 1e9
    rpt.say(f"  rows: {n_rows:,}   file size: {size_gb:.2f} GB")

    # ---- Check 3: date coverage --------------------------------------------
    max_date = q1(
        con,
        f"SELECT MAX(TRY_CAST({date_col} AS TIMESTAMP)) FROM t"
    )
    min_date = q1(
        con,
        f"SELECT MIN(TRY_CAST({date_col} AS TIMESTAMP)) FROM t"
    )
    rpt.say(f"  date range: {min_date}  ..  {max_date}")

    if max_date is None:
        rpt.check(f"{label}_date_coverage", "FAIL", "no parseable dates")
        return

    max_date_s = str(max_date)[:10]
    # The dump's own cutoff. Data should reach close to it.
    if max_date_s >= dump_max_date:
        rpt.check(f"{label}_reaches_dump_cutoff", "PASS",
                  f"max {max_date_s} >= dump cutoff {dump_max_date}")
    else:
        gap_note = f"max {max_date_s} < dump cutoff {dump_max_date}"
        # Small shortfall is normal (dumps are cut mid-month); large is not.
        rpt.check(f"{label}_reaches_dump_cutoff", "WARN", gap_note)

    # ---- Check 1: tail taper vs cliff --------------------------------------
    monthly = q(
        con,
        f"""
        SELECT strftime(TRY_CAST({date_col} AS TIMESTAMP), '%Y-%m') AS m,
               COUNT(*) AS n
        FROM t
        WHERE {date_col} IS NOT NULL
        GROUP BY m
        HAVING m IS NOT NULL
        ORDER BY m DESC
        LIMIT 13
        """,
    )
    if len(monthly) < 4:
        rpt.check(f"{label}_tail_taper", "WARN",
                  "too few months to assess taper")
    else:
        rpt.say("  last months (most recent first):")
        for month, count in monthly:
            rpt.say(f"      {month}   {count:>12,}")

        last_month, last_n = monthly[0]
        # Compare final month against the mean of the preceding 6 (or fewer).
        prior = [c for _, c in monthly[1:7]]
        prior_mean = sum(prior) / len(prior) if prior else 0
        ratio = (last_n / prior_mean) if prior_mean else 0.0

        if prior_mean == 0:
            rpt.check(f"{label}_tail_taper", "WARN", "cannot compute baseline")
        elif ratio >= CLIFF_RATIO:
            rpt.check(
                f"{label}_tail_taper", "WARN",
                f"final month {last_month} holds {ratio:.0%} of prior-6 mean "
                f"-- series ends on a CLIFF, the truncation signature. "
                f"Confirm the dump cutoff falls here before dismissing."
            )
        else:
            rpt.check(
                f"{label}_tail_taper", "PASS",
                f"final month {last_month} at {ratio:.0%} of prior-6 mean "
                f"(tapers, consistent with a natural cutoff)"
            )

    # ---- Check 2: Id / date coherence at the tail ---------------------------
    # Sequential Ids mean the highest-Id rows should carry the latest dates.
    coherence = q(
        con,
        f"""
        SELECT MAX(TRY_CAST({date_col} AS TIMESTAMP)) AS max_date_in_top_ids
        FROM (
            SELECT {date_col}
            FROM t
            WHERE {id_col} IS NOT NULL
            ORDER BY TRY_CAST({id_col} AS BIGINT) DESC
            LIMIT 100000
        )
        """,
    )
    top_id_max_date = coherence[0][0] if coherence else None
    max_id = q1(con, f"SELECT MAX(TRY_CAST({id_col} AS BIGINT)) FROM t")
    rpt.say(f"  max {id_col}: {max_id:,}" if max_id else f"  max {id_col}: n/a")

    if top_id_max_date is None:
        rpt.check(f"{label}_id_date_coherence", "WARN", "cannot evaluate")
    else:
        # Highest-Id rows should reach within a few days of the global max date.
        delta_days = (max_date - top_id_max_date).days
        if abs(delta_days) <= 7:
            rpt.check(
                f"{label}_id_date_coherence", "PASS",
                f"highest-Id rows reach {str(top_id_max_date)[:10]}, "
                f"within {abs(delta_days)}d of global max -- tail was reached"
            )
        else:
            rpt.check(
                f"{label}_id_date_coherence", "WARN",
                f"highest-Id rows reach only {str(top_id_max_date)[:10]}, "
                f"{delta_days}d before global max -- inspect ordering"
            )


# --------------------------------------------------------------------------
# Check 4: cross-file acceptance match (reported, NOT interpreted)
# --------------------------------------------------------------------------
def check_cross_file(con, rpt: Report, posts_path: str, votes_path: str) -> None:
    rpt.say(f"\n{'-' * 66}")
    rpt.say("CROSS-FILE: acceptance votes vs posts")
    rpt.say(f"{'-' * 66}")

    if not (os.path.isfile(posts_path) and os.path.isfile(votes_path)):
        rpt.check("cross_file_match", "WARN", "posts or votes parquet missing")
        return

    con.execute(
        f"CREATE OR REPLACE VIEW p AS SELECT * FROM read_parquet('{posts_path}')"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW v AS SELECT * FROM read_parquet('{votes_path}')"
    )

    total = q1(con, "SELECT COUNT(DISTINCT PostId) FROM v WHERE VoteTypeId = '1'")
    matched = q1(
        con,
        """
        SELECT COUNT(DISTINCT v.PostId)
        FROM v JOIN p ON v.PostId = p.Id
        WHERE v.VoteTypeId = '1'
        """,
    )
    if not total:
        rpt.check("cross_file_match", "FAIL", "no acceptance votes found")
        return

    unmatched = total - matched
    pct = unmatched / total * 100

    rpt.say(f"  acceptance-vote PostIds:     {total:,}")
    rpt.say(f"  matched to a post row:       {matched:,}")
    rpt.say(f"  unmatched:                   {unmatched:,}  ({pct:.3f}%)")

    rpt.check("cross_file_match", "INFO", f"{pct:.3f}% unmatched")

    rpt.say("")
    rpt.say("  NOTE -- this figure is deliberately NOT interpreted here.")
    rpt.say("  It has two indistinguishable causes:")
    rpt.say("    (i)  answers deleted from the platform  -> a SUBSTANTIVE finding")
    rpt.say("         reported in the paper's Limitations;")
    rpt.say("    (ii) posts.parquet truncated by a broken stream -> an ARTIFACT.")
    rpt.say("  Both produce the same signal. Do not report this as a deleted-")
    rpt.say("  content rate until stream completeness is established directly")
    rpt.say("  (byte reconciliation). The tail checks above bound, but do not")
    rpt.say("  eliminate, cause (ii).")

    # A distributional hint: truncation concentrates unmatched ids at the TOP
    # of the id range; deletion scatters them across the whole range.
    spread = q(
        con,
        """
        WITH unmatched AS (
            SELECT DISTINCT TRY_CAST(v.PostId AS BIGINT) AS pid
            FROM v LEFT JOIN p ON v.PostId = p.Id
            WHERE v.VoteTypeId = '1' AND p.Id IS NULL
        ),
        bounds AS (SELECT MAX(TRY_CAST(Id AS BIGINT)) AS max_pid FROM p)
        SELECT
            SUM(CASE WHEN pid > b.max_pid THEN 1 ELSE 0 END) AS above_max,
            COUNT(*) AS total_unmatched
        FROM unmatched, bounds b
        """,
    )
    if spread and spread[0][1]:
        above_max, tot_un = spread[0]
        share = (above_max or 0) / tot_un * 100
        rpt.say("")
        rpt.say(f"  distributional hint: {share:.1f}% of unmatched PostIds lie")
        rpt.say("  ABOVE the maximum Id present in posts.parquet.")
        if share > 20:
            rpt.check(
                "unmatched_id_distribution", "WARN",
                f"{share:.1f}% of unmatched ids exceed max post Id -- "
                "concentration at the top of the Id range is the truncation "
                "pattern, not the deletion pattern"
            )
        else:
            rpt.check(
                "unmatched_id_distribution", "PASS",
                f"only {share:.1f}% of unmatched ids exceed max post Id -- "
                "unmatched ids are scattered, consistent with deletion "
                "rather than truncation"
            )


# --------------------------------------------------------------------------
# Byte-assertion snippet (the direct fix this script cannot substitute for)
# --------------------------------------------------------------------------
BYTE_SNIPPET = '''
# ---------------------------------------------------------------------------
# Add to src/data_processing/extract_stream.py to convert indirect evidence
# into a direct completeness guarantee. Uncompressed member sizes come from
# `7z l data/raw/stackoverflow.com.7z` and are archive-specific.
# ---------------------------------------------------------------------------
EXPECTED_BYTES = {
    "posts":       105_661_126_290,
    "votes":        23_869_760_941,
    "posthistory": 184_794_992_826,
}

class CountingReader:
    """Wraps a byte stream and records how many bytes were actually consumed."""
    def __init__(self, stream):
        self._s = stream
        self.n = 0
    def read(self, size=-1):
        b = self._s.read(size)
        self.n += len(b)
        return b

# in main(), replace `stream(sys.stdin.buffer, ...)` with:
reader = CountingReader(sys.stdin.buffer)
stream(reader, out_path, FIELDS[args.which], args.which, args.limit)

expected = EXPECTED_BYTES.get(args.which)
if args.limit is None and expected is not None and reader.n != expected:
    # Remove the partial output so a truncated file cannot be mistaken for good.
    if os.path.exists(out_path):
        os.rename(out_path, out_path + ".TRUNCATED")
    raise SystemExit(
        f"INCOMPLETE STREAM for {args.which}: consumed {reader.n:,} bytes, "
        f"expected {expected:,}. Output renamed to *.TRUNCATED. "
        f"Re-run the extraction."
    )
print(f"stream completeness verified: {reader.n:,} bytes consumed", file=sys.stderr)
'''


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Post-hoc stream-completeness diagnostics for the "
                    "streaming extraction stage."
    )
    ap.add_argument("--posts", default="data/interim/posts.parquet")
    ap.add_argument("--votes", default="data/interim/votes.parquet")
    ap.add_argument("--posthistory", default="data/interim/posthistory.parquet")
    ap.add_argument("--dump-max-date", default="2025-03-01",
                    help="date the dump should reach (YYYY-MM-DD). The "
                         "2025-03-31 release is cut at end of March 2025.")
    ap.add_argument("--out", default="logs/stream_completeness.txt")
    ap.add_argument("--emit-byte-assertion", action="store_true",
                    help="print the extractor patch that gives direct proof")
    args = ap.parse_args()

    if args.emit_byte_assertion:
        print(BYTE_SNIPPET)
        return 0

    rpt = Report()
    rpt.say("=" * 66)
    rpt.say("STREAM COMPLETENESS DIAGNOSTICS")
    rpt.say(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    rpt.say("Method:    post-hoc inspection of extracted Parquet. Nothing is")
    rpt.say("           re-streamed; the source archive is not read.")
    rpt.say("=" * 66)

    con = duckdb.connect()

    check_file_tail(con, rpt, "posts", args.posts,
                    "CreationDate", "Id", args.dump_max_date)
    check_file_tail(con, rpt, "votes", args.votes,
                    "CreationDate", "Id", args.dump_max_date)
    if os.path.isfile(args.posthistory):
        check_file_tail(con, rpt, "posthistory", args.posthistory,
                        "CreationDate", "Id", args.dump_max_date)
    else:
        rpt.say("\n  (posthistory.parquet not present -- skipped)")

    check_cross_file(con, rpt, args.posts, args.votes)

    # ---- summary -----------------------------------------------------------
    rpt.say(f"\n{'=' * 66}")
    rpt.say("SUMMARY")
    rpt.say(f"{'=' * 66}")
    for name, status, detail in rpt.results:
        rpt.say(f"  {status:4s}  {name}")
    overall = rpt.overall()
    rpt.say("")
    rpt.say(f"  OVERALL: {overall}")
    rpt.say("")
    if overall == "PASS":
        rpt.say("  Interpretation: no truncation signature detected. This is")
        rpt.say("  INDIRECT evidence and bounds the risk; it does not prove")
        rpt.say("  completeness. Describe as 'consistent with a complete")
        rpt.say("  stream', not 'verified complete', unless byte")
        rpt.say("  reconciliation has been added to the extractor")
        rpt.say("  (run with --emit-byte-assertion).")
    else:
        rpt.say("  Interpretation: at least one check flagged. Review the")
        rpt.say("  detail above before treating the extraction as frozen.")
        rpt.say("  A WARN on tail_taper may simply reflect the dump's own")
        rpt.say("  cutoff -- confirm against the release date before re-running.")

    rpt.save(args.out)
    con.close()
    return 0 if overall != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
