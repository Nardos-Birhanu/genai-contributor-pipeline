# Stack Overflow Newcomer Study

**Did generative AI change how newcomers become contributors on Stack Overflow?**

This repository contains the full data pipeline, analysis code, and manuscript for a
computational social science study of newcomer-to-contributor conversion before and
after the December 2022 ChatGPT boundary.

The study asks three questions:

- Did newcomer conversion rates change after late 2022?
- Does any change sit at the December boundary, or does it continue an earlier trend?
- Does any change operate through participation, or through recognition?

The manuscript is in `docs/`.

---

## What is in this repository

```
config/config.yaml        All frozen study parameters — the single source of truth
data/raw/                 The Stack Overflow archive (not tracked; too large)
data/interim/             Parquet files from extraction (not tracked; regenerable)
data/processed/           analysis_panel.parquet — the analysis-ready dataset
src/data_processing/      extract_stream.py, build_panel.py
src/analysis/             descriptives.py, survival.py, ph_check.py
scripts/                  Validation and verification scripts
docs/                     Manuscript, data provenance, Windows run guide
logs/                     Run logs and verification reports
results/tables/           Model output and summary tables
results/figures/          Kaplan–Meier figures (PDF and PNG)
results/descriptives/     Descriptive statistics report
```

---

## Quick start

If you have `data/processed/analysis_panel.parquet`, jump straight to
[Step 6 — Analysis](#6-analysis). 

---

## Step 1 — Set up the environment

```bash
conda env create -f environment.yml
conda activate css_env
```

**What you need installed:**
`lxml` · `pyarrow` · `duckdb` · `pandas` · `lifelines` · `matplotlib` · **7-Zip** (for extraction only)

> All commands below are run from the repository root.

---

## Step 2 — Get the raw data

Download the **Stack Overflow** data dump, release `2025-03-31`, from the Internet
Archive. Full download details, the access URL, and the SHA-256 checksum are in
`docs/data_source.md`.

Place the archive here:

```
data/raw/stackoverflow.com.7z    (~63 GB compressed)
```

> If you downloaded the full network dump, only the Stack Overflow archive is used.
> All other site archives can be ignored.

---

## Step 3 — Extract the data

The uncompressed XML files total more than 300 GB — too large to write to disk on a
typical machine. Instead, 7-Zip streams each file directly into Python, which reads
only the fields it needs and saves compact Parquet files. **No XML is ever saved.**

> **Windows users: use `cmd.exe`, not PowerShell.**
> PowerShell re-encodes binary data and will corrupt the stream.

Set up 7-Zip and check the archive contents:

```bat
set SZ="C:\Program Files\7-Zip\7z.exe"
%SZ% l data\raw\stackoverflow.com.7z
```

You should see `Posts.xml`, `Votes.xml`, and `PostHistory.xml`.

**Run a quick smoke test first** (processes 1,000 rows, takes seconds):

```bat
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml | python -m src.data_processing.extract_stream --which posts --limit 1000
```

If that works, delete the test output and run the three full extractions:

```bat
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml       | python -m src.data_processing.extract_stream --which posts
%SZ% x -so data\raw\stackoverflow.com.7z Votes.xml       | python -m src.data_processing.extract_stream --which votes
%SZ% x -so data\raw\stackoverflow.com.7z PostHistory.xml | python -m src.data_processing.extract_stream --which posthistory
```

| Output | Location |
|---|---|
| Posts | `data/interim/posts.parquet` |
| Votes | `data/interim/votes.parquet` |
| Post history | `data/interim/posthistory.parquet` |
| Logs | `logs/extract_{posts,votes,posthistory}.log` |

> `PostHistory` is only needed for the deleted-post check. Posts and votes are enough
> for the main analysis. See `docs/RUN_windows.md` for disk-space guidance.

---

## Step 4 — Validate the extracted data

Run validation before building the panel. If any freeze gate fails, the extraction
should not be used for analysis.

```bash
python scripts/validate_all.py
```

**Outputs:** `logs/validate_*.txt`, `logs/validate_*.json`, `logs/validation_summary.json`

---

## Step 5 — Build the analysis panel

```bash
python -m src.data_processing.build_panel
```

This assigns each user to a cohort by their first post month, applies the study's
cohort-window and observation-window rules, reconstructs acceptance events from the
vote record, and calculates the survival variables. Everything runs as database queries
over the Parquet files — nothing large is loaded into memory.

| | |
|---|---|
| Input | `data/interim/posts.parquet`, `data/interim/votes.parquet` |
| Output | `data/processed/analysis_panel.parquet` (one row per newcomer) |
| Log | `logs/build_panel.txt` |


---

## Step 6 — Analysis

All analysis commands read only `data/processed/analysis_panel.parquet`.

```bash
python -m src.analysis.descriptives

python -m src.analysis.survival --outcome primary
python -m src.analysis.survival --outcome secondary

python -m src.analysis.ph_check --outcome both --sample 500000
```

| Command | What it produces |
|---|---|
| `descriptives` | `results/descriptives/descriptive_report.txt` · `results/tables/table1_*.{csv,tex}` · `table2_*.{csv,tex}` · `cohort_monthly.csv` · `time_to_event.csv` |
| `survival` | `results/tables/survival_{primary,secondary}.txt` · `results/figures/km_{primary,secondary}.{pdf,png}` |
| `ph_check` | `results/tables/ph_check_{primary,secondary}.txt` |

`survival.py` fits both the pre-specified model (post indicator plus cohort-month trend)
and a sensitivity model without the trend term, and reports the collinearity between
them. `ph_check.py` tests the proportional-hazards assumption using Schoenfeld residuals
and by re-estimating the model separately over early and late follow-up.

---

## Study parameters

These are frozen in `config/config.yaml`. Changing any of them changes the study.

| Parameter | Value |
|---|---|
| Dump release | 2025-03-31 |
| Treatment boundary | 2022-12-01 *(ChatGPT released 30 Nov 2022)* |
| Pre-boundary cohorts | December 2021 – November 2022 |
| Post-boundary cohorts | December 2022 – November 2023 |
| Observation window | 12 months per newcomer |
| Newcomer entry | First post of type Question (1) or Answer (2); comments excluded |
| Accepted answer | `VoteTypeId = 1` from the vote record |
| Primary event timing | Answer creation date, **not** the acceptance vote date |

---

## Two data notes worth knowing

**Acceptance timestamps are date-level only.**
Stack Exchange releases vote dates truncated to midnight (`00:00:00`) to protect voter
anonymity. All 12,570,342 acceptance votes in this dump carry a midnight timestamp.
This means a same-day acceptance can appear to pre-date its own answer when compared
against the full-precision post timestamp. The effect is confined to `faa_accept` and
`time_primary_acceptdate_days`, neither of which is reported. Every reported result uses
`Posts.CreationDate`. This is also why the primary outcome is timed at answer creation
rather than acceptance.

**Deleted posts are not in the dump.**
Content removed from the platform — including posts taken down under the AI-content
policy — does not appear in the public data export.

---

## Verification records

Full pipeline documentation is in `docs/pipeline_log.md`. Data source details and the
archive checksum are in `docs/data_source.md`.
