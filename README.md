# Newcomer-to-Contributor Conversion on Stack Overflow, Before and After Generative AI

Research repository for a computational social science study of whether the rate at
which newcomers reach recognised contribution on Stack Overflow changed around the
public release of generative AI in late 2022. 

**Research question.** Did the rate at which newcomer cohorts reach a first accepted
answer within twelve months of joining change after generative AI became widely
available; does any change appear at the December 2022 boundary or continue a
pre-existing trend; and does it operate through participation or through recognition?

The manuscript is in `docs/`.

## 1. Repository structure


config/config.yaml          contains design parameters.
data/raw/                   Source archive (gitignored, not redistributed)
data/interim/               Parquet from streaming extraction (gitignored)
data/processed/             analysis_panel.parquet -- the analysis dataset
src/data_processing/        extract_stream.py, build_panel.py
src/analysis/               descriptives.py, survival.py, ph_check.py
scripts/                    Validation and verification tools
docs/                       Manuscript, data provenance, Windows run notes
logs/                       Run logs and verification reports
results/tables/             Tables and model output
results/figures/            Kaplan-Meier figures (PDF and PNG)
results/descriptives/       Descriptive report




## 2. Environment

bash
conda env create -f environment.yml
conda activate css_env


Pipeline dependencies: `lxml` (streaming XML), `pyarrow` (Parquet), `duckdb`
(panel construction and aggregation), `pandas`, `lifelines` (survival models),
`matplotlib`. Extraction additionally requires **7-Zip** installed locally.

The pipeline uses neither Spark nor object storage. All processing is single-machine.

**All commands below are run from the repository root.**



## 3. Raw data

**Source.** Stack Exchange public data dump, release **2025-03-31**, Stack Overflow
site only, obtained from the Internet Archive under CC BY-SA. Full provenance,
including the access URL and file checksum, is recorded in `docs/data_source.md`.

**Placement.** Place the archive at the path given in `config/config.yaml`:


data/raw/stackoverflow.com.7z


The archive is roughly 63 GB compressed. It is **not** redistributed with this
repository and is excluded from version control.

**Only the Stack Overflow archive is required.** If you obtained the full network
dump, the remaining site archives are unused.



## 4. Extraction

Uncompressed, the three required XML members exceed 300 GB, which will not fit on a
typical workstation. The XML is therefore **never written to disk**. 7-Zip decompresses
one member to standard output; Python parses that byte stream incrementally, retains
only the fields the analysis needs, and writes compact Parquet. 

### Windows

Binary piping must run in **`cmd.exe`, not PowerShell**. PowerShell applies text
encoding to pipeline data and will corrupt the stream. Set a session alias for 7-Zip:

bat
set SZ="C:\Program Files\7-Zip\7z.exe"


Confirm the archive's internal member names before the long runs:

bat
%SZ% l data\raw\stackoverflow.com.7z


Expect `Posts.xml`, `Votes.xml`, `PostHistory.xml`.

Run a short smoke test before committing to a multi-hour extraction:

bat
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml | python -m src.data_processing.extract_stream --which posts --limit 1000


Then delete the truncated test output and run the three full extractions:

bat
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml       | python -m src.data_processing.extract_stream --which posts
%SZ% x -so data\raw\stackoverflow.com.7z Votes.xml       | python -m src.data_processing.extract_stream --which votes
%SZ% x -so data\raw\stackoverflow.com.7z PostHistory.xml | python -m src.data_processing.extract_stream --which posthistory


**Outputs:** `data/interim/{posts,votes,posthistory}.parquet`
**Logs:** `logs/extract_{posts,votes,posthistory}.log`

`PostHistory` is required only for the deleted-post visibility check. The primary and
secondary outcomes need `posts` and `votes` alone.

Detailed Windows notes, including disk-space guidance, are in `docs/RUN_windows.md`.



## 5. Validation

Run before building the panel. Validation applies freeze gates: a failure means the
extraction is not fit to analyse.

bash
python scripts/validate_all.py


This calls `validate_posts.py`, `validate_votes.py`, and `validate_posthistory.py`.
Individual files can also be validated separately.

**Outputs:** `logs/validate_*.{txt,json}`, `logs/validation_summary.json`

Two further verification tools confirm that the extraction faithfully reflects the
archive:

bash
python scripts/check_stream_completeness.py      # detects a truncated stream
python scripts/verify_extraction_integrity.py    # schema, nulls, cross-file integrity


**Outputs:** `logs/stream_completeness.txt`, `logs/extraction_integrity.txt`



## 6. Panel construction

bash
python -m src.data_processing.build_panel


Assigns each user to a cohort by the month of their first post, applies the cohort-window
and observation-completeness exclusions, reconstructs acceptance events from the vote
record, and derives the survival variables. Runs as DuckDB queries over the interim
Parquet; nothing large is loaded into memory.

**Input:** `data/interim/{posts,votes}.parquet`
**Output:** `data/processed/analysis_panel.parquet` (one row per newcomer)
**Log:** `logs/build_panel.txt`




## 7. Analysis

All three read only `data/processed/analysis_panel.parquet`. A reader who obtains that
file can reproduce every reported figure without touching the archive.

bash
python -m src.analysis.descriptives
python -m src.analysis.survival --outcome primary
python -m src.analysis.survival --outcome secondary
python -m src.analysis.ph_check


| Command | Produces |
| `descriptives` | `results/descriptives/descriptive_report.txt`; `results/tables/{table1_sample_characteristics,table2_conversion_outcomes}.{csv,tex}`, `cohort_monthly.csv`, `time_to_event.csv` |
| `survival` | `results/tables/survival_{primary,secondary}.txt`; `results/figures/km_{primary,secondary}.{pdf,png}` |
| `ph_check` | `results/tables/ph_check_{primary,secondary}.txt` |

`survival.py` fits the pre-specified model (post indicator plus cohort-month trend) and
a sensitivity specification omitting the trend, and reports the collinearity between the
two time controls. `ph_check.py` assesses proportional hazards using scaled Schoenfeld
residuals and by re-fitting over early and late follow-up.



## 8. Design parameters

Frozen in `config/config.yaml`. Changing any of these changes the study.

| Parameter | Value |
| Dump release | 2025-03-31 |
| Treatment boundary | 2022-12-01 (period split; ChatGPT released 30 Nov 2022) |
| Pre-boundary cohorts | 2021-12 to 2022-11 |
| Post-boundary cohorts | 2022-12 to 2023-11 |
| Conversion window | 12 months |
| Newcomer entry | First post, `PostTypeId` 1 or 2 (comments excluded) |
| Accepted answer | `VoteTypeId` 1 (AcceptedByOriginator), from the vote record |
| Primary event timing | Answer creation, **not** the acceptance vote |



## 9. Data notes

**Acceptance-vote timestamps are date-level only.** Stack Exchange releases
`Votes.CreationDate` truncated to the date, with the time set to `00:00:00`, for voter
anonymity. All 12,570,342 acceptance votes in this dump carry a midnight timestamp. A
same-day acceptance therefore appears to precede its own answer when compared against
the full-precision `Posts.CreationDate`. This affects only `faa_accept` and the derived
`time_primary_acceptdate_days`, neither of which is reported. Every reported outcome is
timed from `Posts.CreationDate`. This is one reason the primary event is dated at answer
creation rather than at acceptance.

**Deleted content is absent.** Posts removed from the platform, including under the
AI-generated-content policy, do not appear in the public dump.

Verification records are in `docs/pipeline_log.md`; source provenance in
`docs/data_source.md`.



## 10. Reproducing without the archive

`data/processed/analysis_panel.parquet` is small and is the sole input to every analysis
step. Sections 7 onward reproduce all reported tables and figures from it alone.
Sections 3 to 6 are needed only to rebuild the panel from source.
