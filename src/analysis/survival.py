"""KM + Cox on data/processed/analysis_panel.parquet. Frozen analysis."""
import argparse, os, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test
import yaml
def cfg(p="config/config.yaml"):
    with open(p) as f: return yaml.safe_load(f)
def run(c, outcome):
    figs=os.path.join(c["paths"]["results_dir"],"figures"); tabs=os.path.join(c["paths"]["results_dir"],"tables")
    os.makedirs(figs,exist_ok=True); os.makedirs(tabs,exist_ok=True)
    df=pd.read_parquet(os.path.join(c["paths"]["processed_dir"],"analysis_panel.parquet"))
    T,E=("time_primary_days","event_primary") if outcome=="primary" else ("time_secondary_days","event_secondary")
    df=df[df[T]>=0].copy()
    kmf=KaplanMeierFitter(); fig,ax=plt.subplots(figsize=(8,5))
    for per,g in df.groupby("cohort_period"):
        kmf.fit(g[T],g[E],label=f"{per} (n={len(g):,})"); kmf.plot_survival_function(ax=ax)
    ax.set_xlabel("days since first post"); ax.set_ylabel("P(not yet converted)")
    ax.set_title(f"Time to first {'accepted answer' if outcome=='primary' else 'answer'}, pre vs post")
    fig.tight_layout(); fig.savefig(os.path.join(figs,f"km_{outcome}.png"),dpi=150); plt.close(fig)
    pre,post=df[df.cohort_period=="pre"],df[df.cohort_period=="post"]
    lr=logrank_test(pre[T],post[T],pre[E],post[E])
    d=df.copy(); d["post"]=(d.cohort_period=="post").astype(int)
    d["cohort_idx"]=pd.to_datetime(d.cohort_month+"-01").rank(method="dense").astype(int)-1
    cph=CoxPHFitter(); cph.fit(d[[T,E,"post","cohort_idx"]].rename(columns={T:"T",E:"E"}),"T","E")
    with open(os.path.join(tabs,f"survival_{outcome}.txt"),"w") as f:
        f.write(f"OUTCOME {outcome}\nN={len(df):,}\n")
        f.write(f"pre n={len(pre):,} conv={pre[E].mean():.4f}\npost n={len(post):,} conv={post[E].mean():.4f}\n")
        f.write(f"log-rank chi2={lr.test_statistic:.3f} p={lr.p_value:.3e}\n\n{cph.summary.to_string()}\n")
    print(f"[{outcome}] pre={pre[E].mean():.4f} post={post[E].mean():.4f} logrank_p={lr.p_value:.3e} HR(post)={cph.summary.loc['post','exp(coef)']:.4f}")
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--outcome",default="primary",choices=["primary","secondary"]); a=ap.parse_args()
    run(cfg(),a.outcome)
