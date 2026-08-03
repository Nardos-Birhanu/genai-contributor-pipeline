"""
descriptives.py — Descriptive statistics over analysis_panel.parquet.

All aggregation runs in DuckDB over Parquet; the full panel is never loaded into
pandas. Only small aggregate result sets are pulled into Python for formatting.

Produces (no interpretation):
  results/tables/table1_sample_characteristics.{csv,tex}
  results/tables/table2_conversion_outcomes.{csv,tex}
  results/tables/cohort_monthly.csv
  results/tables/time_to_event.csv
  results/descriptives/descriptive_report.txt

USAGE:
    python -m src.analysis.descriptives
    python -m src.analysis.descriptives --panel data/processed/analysis_panel.parquet
"""
from __future__ import annotations
import argparse, os, datetime
import duckdb

# ---- columns known to exist in the frozen panel schema ----
CORE_COLS = [
    "user_id", "cohort_month", "cohort_period", "first_post_date",
    "first_answer_date", "faa_created", "faa_accept", "window_end",
    "event_primary", "time_primary_days",
    "event_secondary", "time_secondary_days",
    "time_primary_acceptdate_days",
]
# optional columns we'll use IF present (script degrades gracefully if absent)
OPTIONAL_COLS = [
    "initial_post_type", "first_post_type", "post_type",
    "initial_score", "first_post_score", "score",
    "n_questions", "n_answers", "num_questions", "num_answers",
    "initial_tags", "tags",
]

def fmt_int(x):  return f"{int(x):,}" if x is not None else "NA"
def fmt_flt(x, d=4): return f"{x:.{d}f}" if x is not None else "NA"

def present_columns(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info('panel')").fetchall()]
    return set(cols)

def latex_table(caption, label, header, rows, note=None):
    ncol = len(header)
    colspec = "l" + "r" * (ncol - 1)
    out = []
    out.append(r"\begin{table}[htbp]")
    out.append(r"  \centering")
    out.append(f"  \\caption{{{caption}}}")
    out.append(f"  \\label{{{label}}}")
    out.append(f"  \\begin{{tabular}}{{{colspec}}}")
    out.append(r"    \toprule")
    out.append("    " + " & ".join(header) + r" \\")
    out.append(r"    \midrule")
    for r in rows:
        out.append("    " + " & ".join(str(c) for c in r) + r" \\")
    out.append(r"    \bottomrule")
    out.append(r"  \end{tabular}")
    if note:
        out.append(rf"  \\[0.4em]\parbox{{0.9\textwidth}}{{\footnotesize \textit{{Note.}} {note}}}")
    out.append(r"\end{table}")
    return "\n".join(out)

def write_csv(path, header, rows):
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows: w.writerow(r)

def run(panel_path: str, tables_dir: str, desc_dir: str):
    os.makedirs(tables_dir, exist_ok=True)
    os.makedirs(desc_dir, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"CREATE VIEW panel AS SELECT * FROM read_parquet('{panel_path}')")
    cols = present_columns(con)
    report = []
    def line(s=""): report.append(s); print(s)

    line("="*64)
    line("DESCRIPTIVE STATISTICS REPORT")
    line(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}Z")
    line(f"Panel:     {panel_path}")
    line("="*64)

    # ---------------- SAMPLE COMPOSITION ----------------
    line("\n## SAMPLE COMPOSITION")
    n_total = con.execute("SELECT COUNT(*) FROM panel").fetchone()[0]
    line(f"Total newcomers: {fmt_int(n_total)}")

    period_counts = con.execute("""
        SELECT cohort_period, COUNT(*) AS n
        FROM panel GROUP BY cohort_period ORDER BY cohort_period
    """).fetchall()
    for period, n in period_counts:
        line(f"  {period}: {fmt_int(n)}")

    # cohort month range + per-month counts
    month_range = con.execute("""
        SELECT MIN(cohort_month), MAX(cohort_month), COUNT(DISTINCT cohort_month)
        FROM panel
    """).fetchone()
    line(f"Cohort month range: {month_range[0]} to {month_range[1]} "
         f"({month_range[2]} distinct months)")

    monthly = con.execute("""
        SELECT cohort_month, cohort_period, COUNT(*) AS n_newcomers,
               AVG(event_primary)   AS conv_primary,
               AVG(event_secondary) AS conv_secondary
        FROM panel
        GROUP BY cohort_month, cohort_period
        ORDER BY cohort_month
    """).fetchall()
    write_csv(os.path.join(tables_dir, "cohort_monthly.csv"),
              ["cohort_month","cohort_period","n_newcomers","conv_primary","conv_secondary"],
              [[m, p, n, fmt_flt(cp), fmt_flt(cs)] for m,p,n,cp,cs in monthly])
    line(f"Per-cohort-month table written: cohort_monthly.csv ({len(monthly)} rows)")

    # ---------------- CONVERSION OUTCOMES ----------------
    line("\n## CONVERSION OUTCOMES")
    conv = con.execute("""
        SELECT cohort_period,
               COUNT(*) AS n,
               AVG(event_primary)   AS conv_primary,
               SUM(event_primary)   AS n_primary,
               AVG(event_secondary) AS conv_secondary,
               SUM(event_secondary) AS n_secondary
        FROM panel GROUP BY cohort_period ORDER BY cohort_period
    """).fetchall()
    for period, n, cp, np_, cs, ns in conv:
        line(f"  [{period}] n={fmt_int(n)}")
        line(f"      primary   (first accepted answer): rate={fmt_flt(cp)}  events={fmt_int(np_)}")
        line(f"      secondary (first answer):          rate={fmt_flt(cs)}  events={fmt_int(ns)}")

    # overall
    overall = con.execute("""
        SELECT AVG(event_primary), AVG(event_secondary) FROM panel
    """).fetchone()
    line(f"  [overall] primary={fmt_flt(overall[0])}  secondary={fmt_flt(overall[1])}")

    # ---------------- TIME-TO-EVENT ----------------
    line("\n## TIME-TO-EVENT (among converters only)")
    tte_rows = []
    for period in ["pre", "post"]:
        # primary: restrict to event_primary=1
        row = con.execute(f"""
            SELECT
                MEDIAN(time_primary_days)       AS med,
                AVG(time_primary_days)          AS mean,
                QUANTILE_CONT(time_primary_days, 0.25) AS p25,
                QUANTILE_CONT(time_primary_days, 0.75) AS p75,
                QUANTILE_CONT(time_primary_days, 0.90) AS p90,
                MIN(time_primary_days) AS mn, MAX(time_primary_days) AS mx
            FROM panel WHERE cohort_period='{period}' AND event_primary=1
        """).fetchone()
        line(f"  [{period}] primary (days to first accepted answer, converters):")
        line(f"      median={fmt_flt(row[0],1)} mean={fmt_flt(row[1],1)} "
             f"p25={fmt_flt(row[2],1)} p75={fmt_flt(row[3],1)} p90={fmt_flt(row[4],1)}")
        tte_rows.append([period, "primary", fmt_flt(row[0],1), fmt_flt(row[1],1),
                         fmt_flt(row[2],1), fmt_flt(row[3],1), fmt_flt(row[4],1)])
        # secondary
        row2 = con.execute(f"""
            SELECT MEDIAN(time_secondary_days), AVG(time_secondary_days),
                   QUANTILE_CONT(time_secondary_days,0.25), QUANTILE_CONT(time_secondary_days,0.75),
                   QUANTILE_CONT(time_secondary_days,0.90)
            FROM panel WHERE cohort_period='{period}' AND event_secondary=1
        """).fetchone()
        line(f"  [{period}] secondary (days to first answer, converters):")
        line(f"      median={fmt_flt(row2[0],1)} mean={fmt_flt(row2[1],1)} "
             f"p25={fmt_flt(row2[2],1)} p75={fmt_flt(row2[3],1)} p90={fmt_flt(row2[4],1)}")
        tte_rows.append([period, "secondary", fmt_flt(row2[0],1), fmt_flt(row2[1],1),
                         fmt_flt(row2[2],1), fmt_flt(row2[3],1), fmt_flt(row2[4],1)])
    write_csv(os.path.join(tables_dir, "time_to_event.csv"),
              ["cohort_period","outcome","median_days","mean_days","p25","p75","p90"],
              tte_rows)
    line("  Time-to-event table written: time_to_event.csv")

    # ---------------- OPTIONAL NEWCOMER CHARACTERISTICS ----------------
    line("\n## NEWCOMER CHARACTERISTICS (optional columns)")
    opt_found = [c for c in OPTIONAL_COLS if c in cols]
    if not opt_found:
        line("  No optional characteristic columns present in panel "
             "(initial_post_type, initial_score, n_questions, etc.).")
        line("  Panel columns available: " + ", ".join(sorted(cols)))
    else:
        for c in opt_found:
            # numeric vs categorical handling
            try:
                stats = con.execute(f"""
                    SELECT cohort_period, AVG(TRY_CAST({c} AS DOUBLE)) AS mean_val,
                           MEDIAN(TRY_CAST({c} AS DOUBLE)) AS med_val, COUNT({c}) AS n_nonnull
                    FROM panel GROUP BY cohort_period ORDER BY cohort_period
                """).fetchall()
                line(f"  {c}:")
                for period, mv, mdv, nn in stats:
                    line(f"      [{period}] mean={fmt_flt(mv,3) if mv is not None else 'NA'} "
                         f"median={fmt_flt(mdv,3) if mdv is not None else 'NA'} n={fmt_int(nn)}")
            except Exception as e:
                line(f"  {c}: (could not summarize: {e})")

    # ---------------- TABLE 1: SAMPLE CHARACTERISTICS ----------------
    # pre vs post columns
    t1_header = ["Characteristic", "Pre-ChatGPT", "Post-ChatGPT"]
    pre = {r[0]: r for r in conv if r[0]=="pre"}
    post = {r[0]: r for r in conv if r[0]=="post"}
    prr = pre.get("pre"); por = post.get("post")
    def g(row, idx): return row[idx] if row else None
    n_pre  = g(prr,1); n_post = g(por,1)
    # month ranges per period
    pre_range = con.execute("SELECT MIN(cohort_month),MAX(cohort_month) FROM panel WHERE cohort_period='pre'").fetchone()
    post_range= con.execute("SELECT MIN(cohort_month),MAX(cohort_month) FROM panel WHERE cohort_period='post'").fetchone()
    t1_rows = [
        ["Newcomers (n)", fmt_int(n_pre), fmt_int(n_post)],
        ["Cohort months", f"{pre_range[0]}–{pre_range[1]}", f"{post_range[0]}–{post_range[1]}"],
        ["Distinct cohort months",
         con.execute("SELECT COUNT(DISTINCT cohort_month) FROM panel WHERE cohort_period='pre'").fetchone()[0],
         con.execute("SELECT COUNT(DISTINCT cohort_month) FROM panel WHERE cohort_period='post'").fetchone()[0]],
    ]
    # add mean days-to-first-answer among converters as a characteristic
    for period, store in [("pre", "pre"), ("post","post")]:
        pass
    write_csv(os.path.join(tables_dir, "table1_sample_characteristics.csv"),
              t1_header, t1_rows)
    with open(os.path.join(tables_dir, "table1_sample_characteristics.tex"), "w") as f:
        f.write(latex_table(
            "Sample characteristics, pre- versus post-ChatGPT newcomer cohorts.",
            "tab:sample_characteristics", t1_header, t1_rows,
            note="Newcomers defined by first observed post (question or answer) in the cohort month."))
    line("\nTable 1 written: table1_sample_characteristics.{csv,tex}")

    # ---------------- TABLE 2: CONVERSION OUTCOMES ----------------
    t2_header = ["Outcome", "Pre-ChatGPT", "Post-ChatGPT"]
    t2_rows = [
        ["Primary: first accepted answer (rate)", fmt_flt(g(prr,2)), fmt_flt(g(por,2))],
        ["Primary: events (n)",                   fmt_int(g(prr,3)), fmt_int(g(por,3))],
        ["Secondary: first answer (rate)",        fmt_flt(g(prr,4)), fmt_flt(g(por,4))],
        ["Secondary: events (n)",                 fmt_int(g(prr,5)), fmt_int(g(por,5))],
        ["Total newcomers (n)",                   fmt_int(g(prr,1)), fmt_int(g(por,1))],
    ]
    write_csv(os.path.join(tables_dir, "table2_conversion_outcomes.csv"),
              t2_header, t2_rows)
    with open(os.path.join(tables_dir, "table2_conversion_outcomes.tex"), "w") as f:
        f.write(latex_table(
            "Conversion outcomes, pre- versus post-ChatGPT newcomer cohorts.",
            "tab:conversion_outcomes", t2_header, t2_rows,
            note="Conversion measured within a 12-month window from entry. Rates are "
                 "means of binary event indicators over all newcomers in the cohort "
                 "(unconditional)."))
    line("Table 2 written: table2_conversion_outcomes.{csv,tex}")

    # ---------------- SAVE REPORT ----------------
    rpt_path = os.path.join(desc_dir, "descriptive_report.txt")
    with open(rpt_path, "w") as f:
        f.write("\n".join(report) + "\n")
    line(f"\nReport saved: {rpt_path}")
    con.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default="data/processed/analysis_panel.parquet")
    ap.add_argument("--tables-dir", default="results/tables")
    ap.add_argument("--desc-dir", default="results/descriptives")
    a = ap.parse_args()
    run(a.panel, a.tables_dir, a.desc_dir)

if __name__ == "__main__":
    main()
