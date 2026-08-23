"""
ph_check.py -- proportional-hazards checks for the Cox models.

Checks both reported models and keeps durations unchanged to match survival.py.

USAGE
    python -m src.analysis.ph_check --outcome primary
    python -m src.analysis.ph_check --outcome secondary
    python -m src.analysis.ph_check --outcome both --sample 500000
"""
from __future__ import annotations

import argparse
import datetime
import os

import numpy as np
import pandas as pd
import yaml
from lifelines import CoxPHFitter
from lifelines.statistics import proportional_hazard_test

SPLIT_DAYS = 30  # early/late follow-up boundary

MODELS = {
    "M1": ["post", "cohort_idx"],   # primary
    "M2": ["post"],                 # trend sensitivity
}
MODEL_LABEL = {
    "M1": "M1  hazard ~ post + cohort_idx   [primary]",
    "M2": "M2  hazard ~ post                [trend sensitivity]",
}


def load_cfg(path: str = "config/config.yaml") -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def prepare(df: pd.DataFrame, outcome: str) -> tuple[pd.DataFrame, str, str]:
    if outcome == "primary":
        t_col, e_col = "time_primary_days", "event_primary"
    else:
        t_col, e_col = "time_secondary_days", "event_secondary"

    d = df[df[t_col] >= 0].copy()
    d["post"] = (d["cohort_period"] == "post").astype(int)
    # Keep cohort index consistent with survival.py.
    d["cohort_idx"] = (
        pd.to_datetime(d["cohort_month"] + "-01").rank(method="dense").astype(int) - 1
    )
    # NOTE: # Keep observed durations unchanged.
    return d, t_col, e_col


def fit(d: pd.DataFrame, t_col: str, e_col: str, covs: list[str]) -> CoxPHFitter:
    cph = CoxPHFitter()
    cph.fit(
        d[[t_col, e_col] + covs].rename(columns={t_col: "T", e_col: "E"}),
        duration_col="T",
        event_col="E",
    )
    return cph


def verdict(rho: float) -> str:
    a = abs(rho)
    if a < 0.05:
        return "NEGLIGIBLE -- hazard ratio is a reasonable summary"
    if a < 0.15:
        return "MILD -- report the hazard ratio with a caveat"
    return "SUBSTANTIAL -- emphasize Kaplan-Meier; HR is an average effect"


def check_model(d, d_test, t_col, e_col, covs, key, say) -> float:
    """Fit one specification, run the Schoenfeld test, report rho."""
    say("")
    say("=" * 68)
    say(MODEL_LABEL[key])
    say("=" * 68)

    cph = fit(d, t_col, e_col, covs)
    hr = cph.summary.loc["post", "exp(coef)"]
    lo = cph.summary.loc["post", "exp(coef) lower 95%"]
    hi = cph.summary.loc["post", "exp(coef) upper 95%"]
    say(f"  reported HR(post) = {hr:.4f}  [{lo:.4f}, {hi:.4f}]")

    cph_t = fit(d_test, t_col, e_col, covs)
    frame = d_test[[t_col, e_col] + covs].rename(columns={t_col: "T", e_col: "E"})
    results = proportional_hazard_test(cph_t, frame, time_transform="rank")

    say("")
    say(f"  {'covariate':<14s} {'test stat':>12s} {'p':>13s}")
    for cov in results.summary.index:
        say(f"  {str(cov):<14s} "
            f"{results.summary.loc[cov, 'test_statistic']:>12.3f} "
            f"{results.summary.loc[cov, 'p']:>13.3e}")

    resid = cph_t.compute_residuals(frame, kind="scaled_schoenfeld")
    rho = float(np.corrcoef(resid.index.to_series().rank(), resid["post"])[0, 1])
    say("")
    say(f"  Schoenfeld correlation with time, 'post': rho = {rho:+.4f}")
    say(f"  Magnitude verdict: {verdict(rho)}")
    return rho


def run(cfg: dict, outcome: str, sample: int | None, out_dir: str) -> None:
    panel = os.path.join(cfg["paths"]["processed_dir"], "analysis_panel.parquet")
    os.makedirs(out_dir, exist_ok=True)
    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text)
        lines.append(text)

    say("=" * 68)
    say(f"PROPORTIONAL-HAZARDS DIAGNOSTIC -- {outcome} outcome")
    say(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    say("=" * 68)

    df = pd.read_parquet(
        panel,
        columns=["cohort_month", "cohort_period",
                 "time_primary_days", "event_primary",
                 "time_secondary_days", "event_secondary"],
    )
    d, t_col, e_col = prepare(df, outcome)
    say(f"  panel rows: {len(d):,}   events: {int(d[e_col].sum()):,}")
    say(f"  cohort months: {d.cohort_month.min()} .. {d.cohort_month.max()} "
        f"({d.cohort_month.nunique()} distinct)")
    say(f"  zero-duration rows: {int((d[t_col] == 0).sum()):,} "
        f"(kept as observed; rank-based estimators are unaffected)")

    if sample and len(d) > sample:
        d_test = d.sample(n=sample, random_state=42)
        say(f"  Schoenfeld test on a random subsample of {sample:,} rows")
        say("  (rho is stable at this sample size; the full-sample p-value is")
        say("   highly sensitive to small departures from proportional hazards)")
    else:
        d_test = d
        say(f"  Schoenfeld test on all {len(d):,} rows")

    rhos = {}
    for key, covs in MODELS.items():
        rhos[key] = check_model(d, d_test, t_col, e_col, covs, key, say)

    # ---- early vs late follow-up
    say("")
    say("-" * 68)
    say(f"EARLY vs LATE FOLLOW-UP (M1, split at {SPLIT_DAYS} days)")
    say("-" * 68)
    say("  Similar hazard ratios suggest limited variation in the effect")
    say("  across follow-up.")

    covs = MODELS["M1"]
    hr_full = fit(d, t_col, e_col, covs).summary.loc["post", "exp(coef)"]

    early = d.copy()
    early[e_col] = np.where(early[t_col] <= SPLIT_DAYS, early[e_col], 0)
    early[t_col] = early[t_col].clip(upper=SPLIT_DAYS)
    hr_early = fit(early, t_col, e_col, covs).summary.loc["post", "exp(coef)"]

    late = d[d[t_col] > SPLIT_DAYS].copy()
    hr_late = np.nan
    if len(late) > 1000 and late[e_col].sum() > 50:
        hr_late = fit(late, t_col, e_col, covs).summary.loc["post", "exp(coef)"]

    say("")
    say(f"    HR(post), full follow-up   : {hr_full:.4f}")
    say(f"    HR(post), first {SPLIT_DAYS:>3d} days   : {hr_early:.4f}")
    if not np.isnan(hr_late):
        say(f"    HR(post), beyond {SPLIT_DAYS:>3d} days  : {hr_late:.4f}")
        spread = abs(hr_early - hr_late)
        say("")
        if spread < 0.10:
            say(f"    Spread {spread:.4f} -- effect is stable across follow-up.")
        elif spread < 0.30:
            say(f"    Spread {spread:.4f} -- moderate variation; note it in Results.")
        else:
            say(f"    Spread {spread:.4f} -- the effect changes materially over")
            say("    follow-up. A single hazard ratio averages over that change")
            say("    and should be described as an average, not a constant.")
    else:
        say("    (too few late events to fit a separate late-period model)")


    say("")
    say("-" * 68)
    say("REPORTING")
    say("-" * 68)
    rho = rhos["M1"]
    a = abs(rho)
    split_ok = (not np.isnan(hr_late)) and abs(hr_early - hr_late) < 0.30
    split_known = not np.isnan(hr_late)

    if a < 0.05 and split_ok:
        say("  The proportional-hazards assumption was assessed using scaled")
        say("  Schoenfeld residuals. The correlation between residuals and")
        say(f"  ranked follow-up time was negligible (rho = {rho:+.3f}), and hazard")
        say("  ratios estimated over early and late follow-up were similar, so")
        say("  the reported hazard ratio is a fair summary of the difference")
        say("  between cohorts.")
    elif a < 0.05 and split_known:
        say("  The proportional-hazards assumption was assessed using scaled")
        say("  Schoenfeld residuals. The correlation between residuals and")
        say(f"  ranked follow-up time was small (rho = {rho:+.3f}); however, hazard")
        say("  ratios estimated separately over early and late follow-up differed")
        say(f"  ({hr_early:.3f} within {SPLIT_DAYS} days versus {hr_late:.3f} beyond),")
        say("  indicating the difference between cohorts is not constant over the")
        say("  observation window. The reported hazard ratio is therefore")
        say("  interpreted as an average effect across follow-up, and the")
        say("  Kaplan-Meier curves are presented alongside it.")
    elif a < 0.05:
        say("  The proportional-hazards assumption was assessed using scaled")
        say("  Schoenfeld residuals; the correlation with ranked follow-up time")
        say(f"  was negligible (rho = {rho:+.3f}). Too few late events were available")
        say("  to estimate a separate late-period model, so the reported hazard")
        say("  ratio is interpreted as an average effect over the window.")
    elif a < 0.15:
        say("  The proportional-hazards assumption was assessed using scaled")
        say("  Schoenfeld residuals. A mild departure was detected")
        say(f"  (rho = {rho:+.3f}). Given the sample size, formal tests reject on")
        say("  substantively small departures; the hazard ratio is therefore")
        say("  reported as an average effect over the observation window rather")
        say("  than as a constant multiplier, and the Kaplan-Meier curves are")
        say("  presented alongside it.")
        if split_known and not split_ok:
            say(f"  (Early/late refit corroborates this: {hr_early:.3f} within "
                f"{SPLIT_DAYS} days versus {hr_late:.3f} beyond.)")
    else:
        say("  The proportional-hazards assumption was assessed using scaled")
        say("  Schoenfeld residuals and is not satisfied for this outcome")
        say(f"  (rho = {rho:+.3f}); the estimated difference between cohorts varies")
        say("  over follow-up. The Kaplan-Meier survival functions are therefore")
        say("  the primary basis for interpretation, and the Cox estimate is")
        say("  reported only as an average effect over the window.")
        if split_known:
            say(f"  (Early/late refit: {hr_early:.3f} within {SPLIT_DAYS} days "
                f"versus {hr_late:.3f} beyond.)")

    if abs(rhos["M1"] - rhos["M2"]) > 0.05:
        say("")
        say("  NOTE: the departure differs between specifications "
            f"(M1 rho = {rhos['M1']:+.3f}, M2 rho = {rhos['M2']:+.3f}). The linear")
        say("  cohort trend is absorbing time-varying structure; mention this")
        say("  alongside the trend-sensitivity comparison in survival.py.")

    path = os.path.join(out_dir, f"ph_check_{outcome}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n  Report written -> {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--outcome", default="both",
                    choices=["primary", "secondary", "both"])
    ap.add_argument("--sample", type=int, default=500_000,
                    help="subsample size for the Schoenfeld test (0 = full)")
    ap.add_argument("--outdir", default="results/tables")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    sample = args.sample if args.sample > 0 else None
    outcomes = ["primary", "secondary"] if args.outcome == "both" else [args.outcome]
    for oc in outcomes:
        run(cfg, oc, sample, args.outdir)
        print()


if __name__ == "__main__":
    main()
