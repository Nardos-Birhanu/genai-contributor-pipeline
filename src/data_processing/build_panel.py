"""
build_panel.py  --  cohort construction, acceptance reconstruction, panel assembly.

CORRECTED VERSION. The previous build omitted two exclusions specified in the
frozen design; both are applied here and both are logged so the panel's
provenance is auditable.

  EXCLUSION 1 -- COHORT WINDOW.
      Restrict to the frozen symmetric windows:
          pre  : 2021-12 .. 2022-11
          post : 2022-12 .. 2023-11
      Without this the "pre" group spans the platform's entire history and the
      comparison is not the one the design specifies.

  EXCLUSION 2 -- WINDOW COMPLETENESS.
      Every cohort member needs a full 12-month observation window inside the
      data. Cohorts entering later than (dump_end - 12 months) cannot have one:
      they are recorded as non-converters because observation stopped, not
      because they failed to convert. Those cohorts fall entirely in the post
      period, so including them biases the post rate downward.

      With the 2025-03-31 dump and a Nov-2023 latest cohort this exclusion is
      already satisfied by EXCLUSION 1 (Nov 2023 + 12 months = Nov 2024, well
      inside coverage). It is enforced explicitly anyway so the panel remains
      correct if the cohort window is ever changed.

Everything runs in DuckDB over the interim Parquet; nothing large is loaded
into Python memory.

USAGE
    python -m src.data_processing.build_panel
    python -m src.data_processing.build_panel --no-window-restriction   # diagnostic only
"""
from __future__ import annotations

import argparse
import datetime
import os

import duckdb
import yaml


def load_cfg(path: str = "config/config.yaml") -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def build(cfg: dict, restrict: bool = True) -> None:
    interim = cfg["paths"]["interim_dir"]
    processed = cfg["paths"]["processed_dir"]
    logs_dir = cfg["paths"].get("logs_dir", "logs")
    os.makedirs(processed, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    posts = os.path.join(interim, "posts.parquet")
    votes = os.path.join(interim, "votes.parquet")
    out = os.path.join(processed, "analysis_panel.parquet")

    design = cfg["design"]
    tdate = design["treatment_date"]
    window = design["conversion_window_months"]
    acc_vt = design["accepted_vote_type"]
    pre_start, pre_end = design["pre_cohorts"]
    post_start, post_end = design["post_cohorts"]

    log: list[str] = []

    def say(text: str = "") -> None:
        print(text)
        log.append(text)

    say("=" * 66)
    say("PANEL CONSTRUCTION")
    say(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    say("=" * 66)
    say(f"  posts:  {posts}")
    say(f"  votes:  {votes}")
    say(f"  treatment date:   {tdate}")
    say(f"  window (months):  {window}")
    say(f"  frozen cohorts:   pre {pre_start}..{pre_end} | "
        f"post {post_start}..{post_end}")
    say(f"  window restriction applied: {restrict}")

    con = duckdb.connect()
    con.execute("PRAGMA threads=4;")

    # ---- typed views over the interim Parquet ----------------------------
    con.execute(f"""
        CREATE VIEW posts AS
        SELECT TRY_CAST(Id AS BIGINT)               AS post_id,
               TRY_CAST(PostTypeId AS INT)          AS post_type,
               TRY_CAST(OwnerUserId AS BIGINT)      AS user_id,
               TRY_CAST(CreationDate AS TIMESTAMP)  AS created
        FROM read_parquet('{posts}')
        WHERE OwnerUserId IS NOT NULL
    """)
    con.execute(f"""
        CREATE VIEW acc_votes AS
        SELECT TRY_CAST(PostId AS BIGINT)           AS post_id,
               TRY_CAST(CreationDate AS TIMESTAMP)  AS accept_date
        FROM read_parquet('{votes}')
        WHERE TRY_CAST(VoteTypeId AS INT) = {acc_vt}
    """)

    # dump coverage end -- needed for the window-completeness exclusion
    dump_end = con.execute("SELECT MAX(created) FROM posts").fetchone()[0]
    say(f"  dump coverage end: {dump_end}")

    # ---- entry: first question-or-answer per user ------------------------
    con.execute("""
        CREATE VIEW entry AS
        SELECT user_id, MIN(created) AS first_post_date
        FROM posts
        WHERE post_type IN (1, 2)
        GROUP BY user_id
    """)
    n_all = con.execute("SELECT COUNT(*) FROM entry").fetchone()[0]
    say(f"\n  newcomers before exclusions: {n_all:,}")

    # ---- events ----------------------------------------------------------
    con.execute("""
        CREATE VIEW first_acc AS
        SELECT p.user_id,
               MIN(p.created)     AS faa_created,
               MIN(v.accept_date) AS faa_accept
        FROM posts p
        JOIN acc_votes v ON p.post_id = v.post_id
        WHERE p.post_type = 2
        GROUP BY p.user_id
    """)
    con.execute("""
        CREATE VIEW first_ans AS
        SELECT user_id, MIN(created) AS first_answer_date
        FROM posts WHERE post_type = 2 GROUP BY user_id
    """)

    # ---- assemble, then apply exclusions ---------------------------------
    con.execute(f"""
        CREATE VIEW base AS
        SELECT e.user_id,
               e.first_post_date,
               strftime(e.first_post_date, '%Y-%m') AS cohort_month,
               CASE WHEN e.first_post_date < TIMESTAMP '{tdate}'
                    THEN 'pre' ELSE 'post' END      AS cohort_period,
               e.first_post_date + INTERVAL {window} MONTH AS window_end,
               fa.first_answer_date,
               fc.faa_created,
               fc.faa_accept
        FROM entry e
        LEFT JOIN first_ans fa ON e.user_id = fa.user_id
        LEFT JOIN first_acc fc ON e.user_id = fc.user_id
    """)

    # EXCLUSION 2 -- window completeness (always enforced)
    con.execute(f"""
        CREATE VIEW complete_window AS
        SELECT * FROM base
        WHERE window_end <= TIMESTAMP '{dump_end}'
    """)
    n_cw = con.execute("SELECT COUNT(*) FROM complete_window").fetchone()[0]
    say(f"  after window-completeness exclusion: {n_cw:,} "
        f"(dropped {n_all - n_cw:,})")

    # EXCLUSION 1 -- frozen cohort window
    if restrict:
        con.execute(f"""
            CREATE VIEW kept AS
            SELECT * FROM complete_window
            WHERE cohort_month >= '{pre_start}' AND cohort_month <= '{post_end}'
        """)
    else:
        con.execute("CREATE VIEW kept AS SELECT * FROM complete_window")

    n_kept = con.execute("SELECT COUNT(*) FROM kept").fetchone()[0]
    say(f"  after cohort-window exclusion:       {n_kept:,} "
        f"(dropped {n_cw - n_kept:,})")

    # ---- survival variables ---------------------------------------------
    con.execute("""
        CREATE VIEW final AS
        SELECT
            user_id,
            cohort_month,
            cohort_period,
            first_post_date,
            first_answer_date,
            faa_created,
            faa_accept,
            window_end,

            CASE WHEN faa_created IS NOT NULL AND faa_created <= window_end
                 THEN 1 ELSE 0 END AS event_primary,
            CASE WHEN faa_created IS NOT NULL AND faa_created <= window_end
                 THEN date_diff('day', first_post_date, faa_created)
                 ELSE date_diff('day', first_post_date, window_end)
            END AS time_primary_days,

            CASE WHEN first_answer_date IS NOT NULL
                  AND first_answer_date <= window_end
                 THEN 1 ELSE 0 END AS event_secondary,
            CASE WHEN first_answer_date IS NOT NULL
                  AND first_answer_date <= window_end
                 THEN date_diff('day', first_post_date, first_answer_date)
                 ELSE date_diff('day', first_post_date, window_end)
            END AS time_secondary_days,

            CASE WHEN faa_accept IS NOT NULL AND faa_accept <= window_end
                 THEN date_diff('day', first_post_date, faa_accept)
                 ELSE date_diff('day', first_post_date, window_end)
            END AS time_primary_acceptdate_days
        FROM kept
    """)

    # ---- integrity guards ------------------------------------------------
    neg = con.execute(
        "SELECT COUNT(*) FROM final "
        "WHERE time_primary_days < 0 OR time_secondary_days < 0"
    ).fetchone()[0]
    if neg:
        raise SystemExit(f"ABORT: {neg:,} rows have negative durations")

    con.execute(f"COPY final TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    # ---- summary ---------------------------------------------------------
    say("\n  PANEL SUMMARY")
    for period, n, cp, cs, mn, mx in con.execute(
        "SELECT cohort_period, COUNT(*), AVG(event_primary), AVG(event_secondary), "
        "MIN(cohort_month), MAX(cohort_month) "
        "FROM final GROUP BY cohort_period ORDER BY cohort_period"
    ).fetchall():
        say(f"    [{period:4s}] n={n:>10,}  months {mn}..{mx}")
        say(f"           primary={cp:.4f}  secondary={cs:.4f}")

    total = con.execute("SELECT COUNT(*) FROM final").fetchone()[0]
    say(f"\n  total rows: {total:,}")
    say(f"  written -> {out}")

    log_path = os.path.join(logs_dir, "build_panel.txt")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    print(f"  log -> {log_path}")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--no-window-restriction", action="store_true",
                    help="skip the frozen cohort window (diagnostic only; "
                         "do not use for reported results)")
    args = ap.parse_args()
    build(load_cfg(args.config), restrict=not args.no_window_restriction)


if __name__ == "__main__":
    main()
