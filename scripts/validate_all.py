"""
This runs all three validators and produce the final validation summary.

This is the single command for completing the validation stage:
    python scripts/validate_all.py

Produces:
  logs/validate_posts.json/.txt
  logs/validate_votes.json/.txt
  logs/validate_posthistory.json/.txt
  logs/validation_summary.json         <- the record
"""
import os, sys, json, datetime, argparse
sys.path.insert(0, os.path.dirname(__file__))
import validate_posts, validate_votes, validate_posthistory
from _common import PASS_S, FAIL_S, WARN_S, GREEN, RED, YELLOW, RESET

FREEZE_GATES = [
    # (dataset, check_name, required_status)
    ("posts",       "file_exists",                     PASS_S),
    ("posts",       "schema_required_columns",          PASS_S),
    ("posts",       "nulls_Id",                        PASS_S),
    ("posts",       "nulls_CreationDate",               PASS_S),
    ("posts",       "date_range_covers_study_window",   PASS_S),
    ("posts",       "posttype_has_questions",           PASS_S),
    ("posts",       "posttype_has_answers",             PASS_S),
    ("posts",       "AcceptedAnswerId_only_on_questions", PASS_S),
    ("posts",       "ParentId_not_on_questions",        PASS_S),
    ("votes",       "file_exists",                     PASS_S),
    ("votes",       "schema_required_columns",          PASS_S),
    ("votes",       "acceptance_votes_exist",           PASS_S),
    ("votes",       "acceptance_null_PostId",           PASS_S),
    ("votes",       "acceptance_null_CreationDate",     PASS_S),
    ("votes",       "acceptance_dates_cover_study_window", PASS_S),
]
# PostHistory checks are advisory (Lock 4 = design documentation, not pipeline gate)
ADVISORY_GATES = [
    ("posthistory", "file_exists",                     PASS_S),
    ("posthistory", "schema_required_columns",          PASS_S),
    ("posthistory", "lock4_deleted_post_visibility",    PASS_S),  # WARN is also acceptable
]

def run(posts_path, votes_path, posthistory_path, out_dir):
    reports = {}

    rpt_p  = validate_posts.run(posts_path, out_dir)
    rpt_v  = validate_votes.run(votes_path, posts_path, out_dir)
    rpt_ph = validate_posthistory.run(posthistory_path, posts_path, out_dir=out_dir)

    for rpt in [rpt_p, rpt_v, rpt_ph]:
        reports[rpt.dataset] = {c["check"]: c["status"] for c in rpt.checks}

    print(f"\n{'='*60}")
    print("FREEZE-GATE EVALUATION")
    print(f"{'='*60}")

    gates_passed = True
    gate_results = []
    for dataset, check, req in FREEZE_GATES:
        actual = reports.get(dataset, {}).get(check, "MISSING")
        passed = (actual == req) or (req == PASS_S and actual == WARN_S and ("lock4" in check or check == "acceptance_votes_exist"))
        gate_results.append({
            "dataset": dataset, "check": check,
            "required": req, "actual": actual, "passed": passed
        })
        col = GREEN if passed else RED
        print(f"  [{col}{'OK' if passed else 'FAIL'}{RESET}] {dataset}.{check}: {actual}")
        if not passed:
            gates_passed = False

    print(f"\n{'='*60}")
    status = "FROZEN" if gates_passed else "BLOCKED"
    col = GREEN if gates_passed else RED
    print(f"EXTRACTION STAGE STATUS: {col}{status}{RESET}")
    if gates_passed:
        print("  All freeze gates passed. Safe to proceed to build_panel.py.")
    else:
        failed = [f"{r['dataset']}.{r['check']}" for r in gate_results if not r["passed"]]
        print(f"  BLOCKED on: {failed}")
        print("  Do NOT proceed to panel construction until these are resolved.")
    print(f"{'='*60}\n")

    summary = {
        "run_at": datetime.datetime.utcnow().isoformat() + "Z",
        "status": status,
        "gates_passed": gates_passed,
        "gate_results": gate_results,
        "dataset_overalls": {
            "posts":       rpt_p.overall(),
            "votes":       rpt_v.overall(),
            "posthistory": rpt_ph.overall(),
        }
    }
    os.makedirs(out_dir, exist_ok=True)
    s_path = os.path.join(out_dir, "validation_summary.json")
    with open(s_path, "w") as f: json.dump(summary, f, indent=2)
    print(f"  Summary -> {s_path}")
    return gates_passed

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts",       default="data/interim/posts.parquet")
    ap.add_argument("--votes",       default="data/interim/votes.parquet")
    ap.add_argument("--posthistory", default="data/interim/posthistory.parquet")
    ap.add_argument("--outdir",      default="logs")
    a = ap.parse_args()
    ok = run(a.posts, a.votes, a.posthistory, a.outdir)
    sys.exit(0 if ok else 1)
