"""
This is to Validate extracted Votes Parquet data.

Checks schema, acceptance events, date coverage, and links with
posts data before downstream analysis.

Usage:
    python scripts/validate_votes.py
"""

import argparse, os, sys, duckdb
sys.path.insert(0, os.path.dirname(__file__))
from _common import con, q1, qdf, ValidationReport, PASS_S, FAIL_S, WARN_S

REQUIRED_COLS  = ["Id","PostId","VoteTypeId","CreationDate"]
STUDY_END      = "2024-11-30"
MIN_ACCEPTANCE = 10_000_000   # SO has tens of millions of accepted answers

def run(path: str, posts_path: str = "data/interim/posts.parquet", out_dir: str = "logs"):
    print(f"\n{'='*60}")
    print(f"VALIDATING: votes")
    print(f"PATH:       {path}")
    print(f"{'='*60}")

    rpt = ValidationReport("votes", path)

    exists = os.path.isfile(path)
    rpt.record("file_exists", PASS_S if exists else FAIL_S, exists)
    if not exists:
        rpt.save(out_dir); return rpt

    size_bytes = os.path.getsize(path)
    rpt.metadata["file_size_bytes"] = size_bytes
    rpt.record("file_size", PASS_S if size_bytes > 1e6 else FAIL_S,
               f"{size_bytes/1e9:.3f} GB")

    c = con(path)

    # Schema
    schema = qdf(c, "DESCRIBE data")
    actual_cols = [r[0] for r in schema]
    rpt.metadata["schema"] = {r[0]: r[1] for r in schema}
    missing = [col for col in REQUIRED_COLS if col not in actual_cols]
    rpt.record("schema_required_columns", FAIL_S if missing else PASS_S,
               f"missing={missing if missing else 'none'}")

    # Row count
    n = q1(c, "SELECT COUNT(*) FROM data")
    rpt.metadata["row_count"] = n
    rpt.record("row_count", PASS_S if n > 1_000_000 else WARN_S, f"{n:,}")

    # VoteTypeId distribution
    vt_dist = qdf(c, "SELECT VoteTypeId, COUNT(*) AS n FROM data GROUP BY VoteTypeId ORDER BY CAST(VoteTypeId AS INT) NULLS LAST")
    rpt.metadata["votetype_distribution"] = {r[0]: r[1] for r in vt_dist}
    print(f"    VoteType distribution: { {r[0]: r[1] for r in vt_dist} }")

    # *** THE MOST CRITICAL CHECK: VoteTypeId=1 (AcceptedByOriginator) ***
    n_accept = q1(c, "SELECT COUNT(*) FROM data WHERE VoteTypeId = '1'")
    rpt.metadata["acceptance_vote_count"] = n_accept
    rpt.record("acceptance_votes_exist",
               FAIL_S if n_accept == 0 else (PASS_S if n_accept >= MIN_ACCEPTANCE else WARN_S),
               f"{n_accept:,}",
               "CRITICAL: zero here means NO conversion events can be reconstructed")

    # Nulls on critical fields OF acceptance votes specifically
    acc_null_pid = q1(c, "SELECT COUNT(*) FROM data WHERE VoteTypeId='1' AND PostId IS NULL")
    rpt.record("acceptance_null_PostId", FAIL_S if acc_null_pid > 0 else PASS_S,
               acc_null_pid, "null PostId on acceptance vote = lost conversion event")

    acc_null_date = q1(c, "SELECT COUNT(*) FROM data WHERE VoteTypeId='1' AND CreationDate IS NULL")
    rpt.record("acceptance_null_CreationDate", FAIL_S if acc_null_date > 0 else PASS_S,
               acc_null_date, "null date = option(b) sensitivity timing fails")

    # Re-accepted posts (PostId appears more than once in acceptance votes)
    multi = q1(c, "SELECT COUNT(*) FROM (SELECT PostId, COUNT(*) AS n FROM data WHERE VoteTypeId='1' GROUP BY PostId HAVING n > 1)")
    rpt.metadata["re_accepted_posts"] = multi
    rpt.record("re_accepted_posts", PASS_S, f"{multi:,}",
               "expected; Votes-based reconstruction handles these correctly")

    # Date coverage
    max_date = q1(c, "SELECT MAX(CreationDate) FROM data WHERE VoteTypeId='1'")
    rpt.metadata["acceptance_max_date"] = str(max_date)
    rpt.record("acceptance_dates_cover_study_window",
               PASS_S if max_date and str(max_date) >= STUDY_END else FAIL_S,
               f"max_date={max_date}  need>={STUDY_END}")

    # Cross-file: how many acceptance-vote PostIds exist in posts.parquet?
    if os.path.isfile(posts_path):
        c2 = con(posts_path)
        # write a temp DuckDB db for the join
        cj = duckdb.connect()
        cj.execute(f"CREATE VIEW votes AS SELECT * FROM read_parquet('{path}')")
        cj.execute(f"CREATE VIEW posts AS SELECT * FROM read_parquet('{posts_path}')")
        total_acc = q1(cj, "SELECT COUNT(DISTINCT PostId) FROM votes WHERE VoteTypeId='1'")
        matched   = q1(cj, """
            SELECT COUNT(DISTINCT v.PostId)
            FROM votes v
            JOIN posts p ON v.PostId = p.Id
            WHERE v.VoteTypeId = '1'
        """)
        deleted = total_acc - matched
        pct_del = deleted / total_acc * 100 if total_acc else 0
        rpt.metadata["acceptance_postids_total"]   = total_acc
        rpt.metadata["acceptance_postids_matched"] = matched
        rpt.metadata["acceptance_postids_deleted"] = deleted
        rpt.metadata["acceptance_deleted_pct"]     = round(pct_del, 4)
        rpt.record("cross_file_acceptance_match",
                   PASS_S if pct_del < 10 else WARN_S,
                   f"{matched:,}/{total_acc:,} matched ({pct_del:.2f}% deleted/unmatched)",
                   "unmatched = deleted answers; feeds Limitations §deleted-content")
        cj.close()
    else:
        rpt.record("cross_file_acceptance_match", WARN_S, "skipped",
                   "posts.parquet not found; run validate_posts first")

    # Sample
    sample = qdf(c, "SELECT * FROM data WHERE VoteTypeId='1' LIMIT 3")
    rpt.metadata["sample_acceptance_rows"] = sample
    rpt.record("sample_rows_readable", PASS_S if len(sample) > 0 else FAIL_S,
               f"{len(sample)} acceptance rows returned")
    print(f"    Sample acceptance votes: {sample[:2]}")

    rpt.save(out_dir)
    print(f"\n  OVERALL: {rpt.overall()}")
    return rpt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path",       default="data/interim/votes.parquet")
    ap.add_argument("--posts-path", default="data/interim/posts.parquet")
    ap.add_argument("--outdir",     default="logs")
    a = ap.parse_args()
    run(a.path, a.posts_path, a.outdir)
