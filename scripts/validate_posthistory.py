"""
This is to validate extracted PostHistory Parquet data.

Checks schema, history records, and deleted-post visibility signals
used for the study's limitation analysis.

Usage:
    python scripts/validate_posthistory.py
"""
import argparse, os, sys, array
sys.path.insert(0, os.path.dirname(__file__))
from _common import con, q1, qdf, ValidationReport, PASS_S, FAIL_S, WARN_S
import duckdb

REQUIRED_COLS = ["Id","PostHistoryTypeId","PostId","CreationDate","UserId"]
# PostHistoryType IDs from SE documentation
CREATION_TYPES  = ("1","2","3")     # Initial title/body/tags
DELETION_TYPES  = ("12","13")       # PostTombstoned, PostDeleted-like

def run(path: str, posts_path: str = "data/interim/posts.parquet",
        ids_cache: str = "logs/surviving_post_ids.bin", out_dir: str = "logs"):
    print(f"\n{'='*60}")
    print(f"VALIDATING: posthistory (Lock 4)")
    print(f"PATH:       {path}")
    print(f"{'='*60}")

    rpt = ValidationReport("posthistory", path)

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
    rpt.record("row_count", PASS_S if n > 10_000_000 else WARN_S, f"{n:,}",
               "full SO posthistory should be hundreds of millions of rows")

    # PostHistoryTypeId distribution
    ph_dist = qdf(c, "SELECT PostHistoryTypeId, COUNT(*) AS n FROM data GROUP BY PostHistoryTypeId ORDER BY CAST(PostHistoryTypeId AS INT) NULLS LAST")
    rpt.metadata["posthistorytype_distribution"] = {r[0]: r[1] for r in ph_dist}
    print(f"    Top PostHistoryTypes: {dict(list({r[0]: r[1] for r in ph_dist}.items())[:8])}")
    rpt.record("posthistorytype_distribution_computed", PASS_S, f"{len(ph_dist)} distinct types",
               "see metadata for full distribution")

    # Lock 4: unmatched PostIds (the core deleted-post visibility check)
    if os.path.isfile(posts_path):
        cj = duckdb.connect()
        cj.execute(f"CREATE VIEW ph  AS SELECT * FROM read_parquet('{path}')")
        cj.execute(f"CREATE VIEW pst AS SELECT * FROM read_parquet('{posts_path}')")

        total_ph = q1(cj, "SELECT COUNT(DISTINCT PostId) FROM ph WHERE PostId IS NOT NULL")
        matched  = q1(cj, """
            SELECT COUNT(DISTINCT ph.PostId)
            FROM ph JOIN pst ON ph.PostId = pst.Id
        """)
        unmatched = total_ph - matched
        pct = unmatched / total_ph * 100 if total_ph else 0
        rpt.metadata["lock4_total_ph_postids"]  = total_ph
        rpt.metadata["lock4_matched"]            = matched
        rpt.metadata["lock4_unmatched"]          = unmatched
        rpt.metadata["lock4_unmatched_pct"]      = round(pct, 4)

        if pct < 1.0:
            case = "A"; status = PASS_S
        else:
            case = "B"; status = WARN_S
        rpt.record("lock4_deleted_post_visibility",
                   status, f"{unmatched:,} unmatched ({pct:.4f}%)  Case {case}",
                   "Case A (<1%): deleted posts invisible, irreducible limitation. "
                   "Case B: some history survives, check type breakdown.")

        if case == "B":
            creation_in_unmatched = q1(cj, f"""
                SELECT COUNT(*) FROM ph
                WHERE PostId NOT IN (SELECT Id FROM pst)
                  AND PostHistoryTypeId IN {CREATION_TYPES}
            """)
            rpt.metadata["lock4_creation_type_rows_in_unmatched"] = creation_in_unmatched
            rpt.record("lock4_creation_type_rows_recoverable",
                       PASS_S if creation_in_unmatched > 0 else WARN_S,
                       f"{creation_in_unmatched:,}",
                       "creation-type rows (1-3) in unmatched = partial recovery possible")

        # Temporal spike detection near enforcement dates
        enforcement_rows = q1(cj, """
            SELECT COUNT(*) FROM ph
            WHERE CreationDate >= '2022-12-01' AND CreationDate <= '2022-12-31'
              AND PostId NOT IN (SELECT Id FROM pst)
        """)
        rpt.metadata["lock4_enforcement_spike_dec2022"] = enforcement_rows
        rpt.record("lock4_enforcement_spike_dec2022",
                   WARN_S if enforcement_rows > 10000 else PASS_S,
                   f"{enforcement_rows:,} unmatched rows in 2022-12",
                   "high value = ban enforcement signal, relevant for bundled-treatment interpretation")

        cj.close()
    else:
        rpt.record("lock4_cross_file_check", WARN_S, "skipped",
                   "posts.parquet not found; run validate_posts first")

    # Null checks
    for col in ["PostId","PostHistoryTypeId","CreationDate"]:
        nulls = q1(c, f"SELECT COUNT(*) FROM data WHERE {col} IS NULL")
        rpt.record(f"nulls_{col}", WARN_S if nulls > 0 else PASS_S, nulls)

    # Sample
    sample = qdf(c, "SELECT Id, PostHistoryTypeId, PostId, CreationDate FROM data LIMIT 3")
    rpt.record("sample_rows_readable", PASS_S if len(sample) > 0 else FAIL_S, len(sample))
    print(f"    Sample: {sample}")

    rpt.save(out_dir)
    print(f"\n  OVERALL: {rpt.overall()}")
    return rpt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path",       default="data/interim/posthistory.parquet")
    ap.add_argument("--posts-path", default="data/interim/posts.parquet")
    ap.add_argument("--outdir",     default="logs")
    a = ap.parse_args()
    run(a.path, a.posts_path, out_dir=a.outdir)
