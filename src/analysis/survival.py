"""
survival.py --> Kaplan-Meier and Cox proportional-hazards analysis.

Fits two Cox models:
    M1: post + cohort_idx   (primary)
    M2: post only           (sensitivity)

Zero-day events are kept as observed to match the analysis design.

Figures are saved as PDF and PNG.

USAGE
    python -m src.analysis.survival --outcome primary
    python -m src.analysis.survival --outcome secondary
"""
from __future__ import annotations

import argparse
import datetime
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.statistics import logrank_test


def load_cfg(path: str = "config/config.yaml") -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def fit_cox(d: pd.DataFrame, t_col: str, e_col: str,
            covariates: list[str]) -> CoxPHFitter:
    cols = [t_col, e_col] + covariates
    cph = CoxPHFitter()
    cph.fit(
        d[cols].rename(columns={t_col: "T", e_col: "E"}),
        duration_col="T",
        event_col="E",
    )
    return cph


def run(cfg: dict, outcome: str) -> None:
    figs = os.path.join(cfg["paths"]["results_dir"], "figures")
    tabs = os.path.join(cfg["paths"]["results_dir"], "tables")
    os.makedirs(figs, exist_ok=True)
    os.makedirs(tabs, exist_ok=True)

    panel = os.path.join(cfg["paths"]["processed_dir"], "analysis_panel.parquet")
    df = pd.read_parquet(panel)

    if outcome == "primary":
        t_col, e_col = "time_primary_days", "event_primary"
        pretty = "accepted answer"
    else:
        t_col, e_col = "time_secondary_days", "event_secondary"
        pretty = "answer"

    df = df[df[t_col] >= 0].copy()

    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text)
        lines.append(text)

    say(f"OUTCOME {outcome}")
    say(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    say(f"Panel: {panel}")
    say(f"N={len(df):,}")

    # cohort window actually present -- guards against an unrestricted panel
    say(f"cohort months: {df.cohort_month.min()} .. {df.cohort_month.max()} "
        f"({df.cohort_month.nunique()} distinct)")

    pre = df[df.cohort_period == "pre"]
    post = df[df.cohort_period == "post"]
    say(f"pre  n={len(pre):,}  events={int(pre[e_col].sum()):,}  "
        f"conv={pre[e_col].mean():.4f}")
    say(f"post n={len(post):,}  events={int(post[e_col].sum()):,}  "
        f"conv={post[e_col].mean():.4f}")

    # ---- Kaplan-Meier ----------------------------------------------------
    kmf = KaplanMeierFitter()
    fig, ax = plt.subplots(figsize=(8, 5))
    for period in ("pre", "post"):
        g = df[df.cohort_period == period]
        if len(g) == 0:
            continue
        kmf.fit(g[t_col], g[e_col], label=f"{period} (n={len(g):,})")
        kmf.plot_survival_function(ax=ax, ci_show=True)
    ax.set_xlabel("Days since first post")
    ax.set_ylabel("P(not yet converted)")
    ax.set_title(f"Time to first {pretty}, pre- versus post-2022 cohorts")
    fig.tight_layout()
    fig.savefig(os.path.join(figs, f"km_{outcome}.pdf"))      # vector, for the paper
    fig.savefig(os.path.join(figs, f"km_{outcome}.png"), dpi=150)
    plt.close(fig)

    # ---- log-rank --------------------------------------------------------
    lr = logrank_test(pre[t_col], post[t_col], pre[e_col], post[e_col])
    say(f"\nlog-rank chi2={lr.test_statistic:.3f} p={lr.p_value:.3e}")

    # ---- covariates ------------------------------------------------------
    d = df.copy()
    d["post"] = (d.cohort_period == "post").astype(int)
    d["cohort_idx"] = (
        pd.to_datetime(d.cohort_month + "-01").rank(method="dense").astype(int) - 1
    )

    # collinearity between the two time controls
    r = float(np.corrcoef(d["cohort_idx"], d["post"])[0, 1])
    vif = 1.0 / (1.0 - r ** 2) if abs(r) < 1 else float("inf")
    say(f"\ncollinearity: corr(post, cohort_idx) = {r:.4f}   VIF = {vif:.2f}")
    if vif >= 5:
        say("  WARNING: high collinearity between the post indicator and the")
        say("  linear cohort trend. The two models below should be compared")
        say("  carefully before interpreting the post coefficient as a step.")
    elif vif >= 2.5:
        say("  NOTE: moderate collinearity. Compare M1 and M2 below; a stable")
        say("  HR(post) across the two indicates the finding does not depend")
        say("  on how the secular trend is modelled.")

    # ---- M1: pre-specified model (post + trend) -------------------------
    m1 = fit_cox(d, t_col, e_col, ["post", "cohort_idx"])
    hr1 = m1.summary.loc["post", "exp(coef)"]
    lo1 = m1.summary.loc["post", "exp(coef) lower 95%"]
    hi1 = m1.summary.loc["post", "exp(coef) upper 95%"]

    say("\n" + "=" * 62)
    say("M1 (PRE-SPECIFIED, REPORTED): hazard ~ post + cohort_idx")
    say("=" * 62)
    say(m1.summary.to_string())

    # ---- M2: sensitivity (post only) ------------------------------------
    m2 = fit_cox(d, t_col, e_col, ["post"])
    hr2 = m2.summary.loc["post", "exp(coef)"]
    lo2 = m2.summary.loc["post", "exp(coef) lower 95%"]
    hi2 = m2.summary.loc["post", "exp(coef) upper 95%"]

    say("\n" + "=" * 62)
    say("M2 (SENSITIVITY): hazard ~ post   [no secular-trend control]")
    say("=" * 62)
    say(m2.summary.to_string())

    # ---- comparison ------------------------------------------------------
    say("\n" + "-" * 62)
    say("TREND-SPECIFICATION SENSITIVITY")
    say("-" * 62)
    say(f"  M1  HR(post) = {hr1:.4f}  [{lo1:.4f}, {hi1:.4f}]   (with trend)")
    say(f"  M2  HR(post) = {hr2:.4f}  [{lo2:.4f}, {hi2:.4f}]   (no trend)")
    diff = abs(hr1 - hr2)
    rel = diff / hr1 if hr1 else float("inf")
    say(f"  absolute difference = {diff:.4f}  ({rel*100:.1f}% of M1)")
    say("")
    if rel < 0.10:
        say("  STABLE. HR(post) changes little across trend specifications, so")
        say("  the estimate does not depend on how the secular decline is")
        say("  modelled. Report M1; note M2 as a sensitivity check.")
    elif rel < 0.25:
        say("  MODERATE SENSITIVITY. Report both estimates in the paper and")
        say("  state that the magnitude depends in part on the trend control.")
    else:
        say("  SENSITIVE. HR(post) shifts materially without the trend control.")
        say("  With a 24-month window the step and the linear trend are hard to")
        say("  separate. Report both, and describe the post estimate as an")
        say("  association conditional on the trend specification rather than")
        say("  as a clean discontinuity.")

    say("\nNOTE: hazard ratio < 1 indicates lower/slower conversion post-2022.")
    say("Proportional-hazards assumption is assessed separately "
        "(src/analysis/ph_check.py).")

    out_path = os.path.join(tabs, f"survival_{outcome}.txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n  Written -> {out_path}")
    print(f"  Figures -> {figs}/km_{outcome}.pdf (+ .png)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--outcome", default="primary",
                    choices=["primary", "secondary", "both"])
    args = ap.parse_args()
    cfg = load_cfg(args.config)
    outcomes = ["primary", "secondary"] if args.outcome == "both" else [args.outcome]
    for oc in outcomes:
        run(cfg, oc)
        print()


if __name__ == "__main__":
    main()
