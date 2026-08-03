"""
This is to validate extracted Posts Parquet data.

Checks schema, required fields, data coverage, and structural consistency
before using the dataset for analysis.

Usage:
  python scripts/validate_posts.py
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _common import con, q1, qdf, ValidationReport, PASS_S, FAIL_S, WARN_S

REQUIRED_COLS = ["Id","PostTypeId","OwnerUserId","CreationDate",
                 "ParentId","AcceptedAnswerId","Tags"]
STUDY_START = "2021-12-01"
STUDY_END   = "2024-11-30"   # latest observation date (Nov 2023 cohort + 12 months)
MIN_ROWS    = 50_000_000     # SO has >200M posts; anything below signals truncation

def run(path: str, out_dir: str = "logs"):
    print(f"\n{'='*60}")
    print(f"VALIDATING: posts")
    print(f"PATH:       {path}")
    print(f"{'='*60}")

    rpt = ValidationReport("posts", path)

    # 1. File existence
    exists = os.path.isfile(path)
    rpt.record("file_exists", PASS_S if exists else FAIL_S, exists)
    if not exists:
        print("  Cannot continue — file missing."); rpt.save(out_dir); return rpt

    # 2. File size
    size_bytes = os.path.getsize(path)
    size_gb = size_bytes / 1e9
    rpt.metadata["file_size_bytes"] = size_bytes
    rpt.metadata["file_size_gb"]    = round(size_gb, 3)
    rpt.record("file_size", PASS_S if size_bytes > 1e6 else FAIL_S, f"{size_gb:.3f} GB",
               "expect >0.5 GB for full SO posts")

    c = con(path)

    # 3. Schema — column names and types
    schema = qdf(c, "DESCRIBE data")
    actual_cols = [r[0] for r in schema]
    rpt.metadata["schema"] = {r[0]: r[1] for r in schema}
    missing = [col for col in REQUIRED_COLS if col not in actual_cols]
    rpt.record("schema_required_columns",
               FAIL_S if missing else PASS_S,
               f"missing={missing if missing else 'none'}",
               "all required columns must be present for pipeline")
    # all should be VARCHAR (stored as strings from streaming extraction)
    non_varchar = [r[0] for r in schema if r[0] in REQUIRED_COLS and "VARCHAR" not in r[1].upper()]
    rpt.record("schema_types_all_varchar",
               WARN_S if non_varchar else PASS_S,
               f"non-varchar required cols: {non_varchar if non_varchar else 'none'}",
               "build_panel.py uses TRY_CAST; unexpected types may cause silent nulls")

    # 4. Row count
    n = q1(c, "SELECT COUNT(*) FROM data")
    rpt.metadata["row_count"] = n
    rpt.record("row_count", PASS_S if n >= MIN_ROWS else WARN_S, f"{n:,}",
               f"expect >{MIN_ROWS:,} for complete SO dump")

    # 5. Null counts on critical columns
    for col in ["Id","PostTypeId","CreationDate"]:
        nulls = q1(c, f"SELECT COUNT(*) FROM data WHERE {col} IS NULL")
        rpt.record(f"nulls_{col}", FAIL_S if nulls > 0 else PASS_S, nulls,
                   "must be zero — these are primary keys/timestamps")

    owner_nulls = q1(c, "SELECT COUNT(*) FROM data WHERE OwnerUserId IS NULL")
    pct = owner_nulls / n * 100 if n else 0
    rpt.metadata["null_owner_count"] = owner_nulls
    rpt.metadata["null_owner_pct"]   = round(pct, 4)
    rpt.record("nulls_OwnerUserId", PASS_S if owner_nulls < n * 0.05 else WARN_S,
               f"{owner_nulls:,} ({pct:.2f}%)",
               "expected (deleted accounts); >5% is unusual and worth logging")

    # 6. PostTypeId distribution — must contain types 1 (Q) and 2 (A)
    pt_dist = qdf(c, "SELECT PostTypeId, COUNT(*) AS n FROM data GROUP BY PostTypeId ORDER BY CAST(PostTypeId AS INT) NULLS LAST")
    rpt.metadata["posttype_distribution"] = {r[0]: r[1] for r in pt_dist}
    pt_ids = [r[0] for r in pt_dist]
    rpt.record("posttype_has_questions", PASS_S if "1" in pt_ids else FAIL_S,
               "PostTypeId=1 present",
               "missing questions would break newcomer definition")
    rpt.record("posttype_has_answers", PASS_S if "2" in pt_ids else FAIL_S,
               "PostTypeId=2 present",
               "missing answers means no conversion events")
    print(f"    PostType distribution: { {r[0]: r[1] for r in pt_dist} }")

    # 7. Structural invariants (schema semantics)
    aa_on_nonq = q1(c, "SELECT COUNT(*) FROM data WHERE AcceptedAnswerId IS NOT NULL AND PostTypeId != '1'")
    rpt.record("AcceptedAnswerId_only_on_questions",
               FAIL_S if aa_on_nonq > 0 else PASS_S, aa_on_nonq,
               "AcceptedAnswerId must only appear on questions (PostTypeId=1)")

    pid_on_q = q1(c, "SELECT COUNT(*) FROM data WHERE ParentId IS NOT NULL AND PostTypeId = '1'")
    rpt.record("ParentId_not_on_questions",
               FAIL_S if pid_on_q > 0 else PASS_S, pid_on_q,
               "ParentId must only appear on answers (PostTypeId=2)")

    # 8. Date range
    min_date = q1(c, "SELECT MIN(CreationDate) FROM data WHERE CreationDate IS NOT NULL")
    max_date = q1(c, "SELECT MAX(CreationDate) FROM data WHERE CreationDate IS NOT NULL")
    rpt.metadata["date_min"] = str(min_date)
    rpt.metadata["date_max"] = str(max_date)
    rpt.record("date_range_min", PASS_S if min_date and str(min_date) < "2010-01-01" else WARN_S,
               str(min_date), "SO launched 2008; expect records from ~2008")
    rpt.record("date_range_covers_study_window",
               PASS_S if max_date and str(max_date) >= STUDY_END else FAIL_S,
               f"max={max_date}  need>={STUDY_END}",
               "dump must cover the full observation window")

    # 9. Study-window row count
    sw = q1(c, f"SELECT COUNT(*) FROM data WHERE CreationDate >= '{STUDY_START}' AND CreationDate <= '{STUDY_END}'")
    rpt.metadata["study_window_row_count"] = sw
    rpt.record("study_window_rows", PASS_S if sw > 1_000_000 else WARN_S, f"{sw:,}",
               f"rows in {STUDY_START}–{STUDY_END}; expect millions for SO")

    # 10. Sample rows
    sample = qdf(c, "SELECT Id, PostTypeId, OwnerUserId, CreationDate, AcceptedAnswerId FROM data LIMIT 5")
    rpt.metadata["sample_rows"] = sample
    rpt.record("sample_rows_readable", PASS_S if len(sample) == 5 else FAIL_S,
               f"{len(sample)} rows returned")
    print(f"    Sample: {sample[:2]}")

    # 11. Null-owner attrition by year (enforcement signal)
    attrition = qdf(c, """
        SELECT strftime(TRY_CAST(CreationDate AS TIMESTAMP), '%Y') AS yr,
               COUNT(*) AS total,
               SUM(CASE WHEN OwnerUserId IS NULL THEN 1 ELSE 0 END) AS null_owner
        FROM data
        WHERE CreationDate IS NOT NULL
        GROUP BY yr ORDER BY yr
    """)
    rpt.metadata["null_owner_by_year"] = [(r[0], int(r[2])) for r in attrition if r[0]]
    rpt.record("null_owner_attrition_computed", PASS_S, "see metadata.null_owner_by_year",
               "spike in 2022-2023 near ban date signals enforcement attrition")

    rpt.save(out_dir)
    print(f"\n  OVERALL: {rpt.overall()}")
    return rpt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="data/interim/posts.parquet")
    ap.add_argument("--outdir", default="logs")
    a = ap.parse_args()
    run(a.path, a.outdir)
