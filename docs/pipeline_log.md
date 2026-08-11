# Pipeline Log

Dated record of every data decision, verification, and deviation for the study of
newcomer-to-contributor conversion on Stack Overflow before and after generative AI.

This document exists so that any claim in the manuscript about how the data were
obtained, processed, or checked can be traced to a specific decision and its evidence.

Repository conventions: all commands are run from the repository root. Verification
outputs are written to `logs/`. Design parameters live in `config/config.yaml`.



## 1. Data source

| Dataset | Stack Exchange public data dump, Stack Overflow site only |
| Release | 2025-03-31 |
| Source | Internet Archive community release |
| Licence | CC BY-SA |
| Download tool | aria2c (resumable) |
| Download date | 2026-07-27 |
| SHA256 | E98C3850FE4249486E022A26F16AF5B76A29F36C63A0872191AC1B6B8C46812B |

**Why this release.** It is the most recent release confirmed to precede changes in
Stack Exchange's dump-generation process affecting later releases, and its coverage
reaches March 2025, giving the final cohort (November 2023) a complete twelve-month
observation window with roughly four months to spare.

**Archive integrity, verified before use:**

7z t data/raw/stackoverflow.com.7z   ->  Everything is Ok
Files: 10
Compressed:   68,346,625,738 bytes
Uncompressed: 357,120,308,489 bytes


Uncompressed member sizes:

| Member | Bytes |
| Posts.xml | 105,661,126,290 |
| Votes.xml | 23,869,760,941 |
| PostHistory.xml | 184,794,992,826 |

**Rejected alternatives.** Later dump releases (integrity concerns in the
dump-generation process); Stack Exchange Data Explorer as the primary source (live,
weekly-refreshed, no immutable snapshot); third-party pre-processed corpora (stale or
already transformed).




## 2. Schema verification

Confirmed against the archive before extraction:

- Fields are XML **attributes** on `<row>` elements, not positional columns.
- `Posts.xml` carries `Id`, `PostTypeId`, `OwnerUserId`, `CreationDate`, `ParentId`,
  `AcceptedAnswerId`, `Tags`.
- `Votes.xml` carries `Id`, `PostId`, `VoteTypeId`, `CreationDate`.
- `VoteTypeId = 1` is AcceptedByOriginator.
- `PostTypeId` 1 = Question, 2 = Answer.
- `OwnerUserId` is nullable (deleted or anonymous accounts).

**Consequence for correctness.** Extraction reads `elem.get("FieldName")`, retrieving
attributes by name. There is no positional parsing anywhere between XML and Parquet, so
column misalignment cannot occur: either a name matches and the correct value is
returned, or it does not and the column is uniformly null — a loud failure, detected by
the null-profile checks in §6.

Evidence: `logs/validate_posts.txt`, `logs/validate_votes.txt`



## 3. Acceptance-event reconstruction


`Posts.AcceptedAnswerId` stores only which answer is **currently** accepted. It carries
no timestamp and does not preserve acceptance that was later changed. Acceptance events
are therefore recovered from `Votes` where `VoteTypeId = 1`, each of which is a separate
timestamped event.

An answer authored by a newcomer counts as accepted if its identifier appears among
those events. The primary event time is the **creation date of that answer**, not the
date of the acceptance vote. 


## 4. Deleted-post visibility

`PostHistory.xml` was extracted to assess whether records survive for posts deleted out
of `Posts.xml`.


| Unmatched PostHistory rows | 14 |
| Percentage | 0.00% |
| Conclusion | **14 unmatched records were found, consistent with deleted posts being invisible in `Posts.xml`; deleted-post visibility is therefore an irreducible dataset limitation, but the observed share is negligible and does not materially affect the analysis.** |




## 5. Newcomer entry definition

Entry is dated by a user's **first observed post**, restricted to `PostTypeId` 1 and 2.
Comments are excluded.

**Rationale.** Participation, not registration, is what the theory concerns and what the
data record reliably; many accounts are created and never used. Restricting to questions
and answers keeps the definition aligned with the contribution pathway and avoids a
second, noisier data source. Commenting is additionally reputation-gated on Stack
Overflow, so including it would introduce a privilege dependence the design otherwise
avoids.

**Bias direction.** If a user commented before posting, their entry is dated later than
their true first activity, shortening measured duration and biasing conversion upward —
against, not toward, the hypothesised decline. The exclusion is therefore conservative.



## 6. Extraction

**Method.** The XML is never written to disk. 7-Zip decompresses one member to standard
output; `lxml.iterparse` consumes the byte stream incrementally, retains only the
required attributes, clears each element, and writes Parquet in batches. Uncompressed,
the three members exceed 300 GB, which the available workstation could not hold.

bat
set SZ="C:\Program Files\7-Zip\7z.exe"
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml       | python -m src.data_processing.extract_stream --which posts
%SZ% x -so data\raw\stackoverflow.com.7z Votes.xml       | python -m src.data_processing.extract_stream --which votes
%SZ% x -so data\raw\stackoverflow.com.7z PostHistory.xml | python -m src.data_processing.extract_stream --which posthistory


**Known limitation of the streaming approach.** The extractor reads until standard input
closes. A broken pipe is indistinguishable from a completed one, and on Windows the exit
code of `A | B` reflects only `B`, so a 7-Zip failure would not surface in the return
code. This is addressed by the completeness and integrity checks below rather than by
the extractor itself.



## 7. Validation

bash
python scripts/validate_all.py

Applies freeze gates covering field presence and typing, null profiles on universal
fields, structural invariants (acceptance pointers only on questions; parent identifiers
only on answers), value domains, date coverage spanning the study window, and
acceptance-event presence with timestamps.


Evidence: `logs/validate_{posts,votes,posthistory}.{txt,json}`,
`logs/validation_summary.json`

All 15/15 freeze gates passed, and the validated datasets are FROZEN.



## 8. Panel construction

bash
python -m src.data_processing.build_panel


Assigns each user to a cohort by the month of first post; applies the cohort-window and
observation-completeness exclusions; reconstructs acceptance from the vote record;
derives event indicators and durations. Executed as DuckDB queries over the interim
Parquet.

**Output:** `data/processed/analysis_panel.parquet` — one row per newcomer
**Log:** `logs/build_panel.txt`


| Panel rows | 750,373 |
| Pre-boundary cohorts (2021-12 to 2022-11) | 444,490 |
| Post-boundary cohorts (2022-12 to 2023-11) | 305,883 |
| Distinct cohort months | 24 |

Columns: `user_id`, `cohort_month`, `cohort_period`, `first_post_date`,
`first_answer_date`, `faa_created`, `faa_accept`, `window_end`, `event_primary`,
`time_primary_days`, `event_secondary`, `time_secondary_days`,
`time_primary_acceptdate_days`.



## 9. Data anomaly investigated: acceptance-vote timestamps

**Observation.** The design-alignment audit flagged 29,214 panel rows where
`faa_accept` precedes `faa_created`, which is logically impossible for true event times.

**Investigation.** A direct query against the interim Parquet found 6,523,326 source
records in which an acceptance vote's timestamp precedes its answer's creation
timestamp. A follow-up query established the cause:


total acceptance votes: 12,570,342
of which timestamped 00:00:00: 12,570,342   (100%)


**Cause.** Stack Exchange releases `Votes.CreationDate` **truncated to date-level**,
with the time component set to midnight, to protect voter anonymity. A same-day
acceptance therefore appears to precede its own answer when compared against the
full-precision `Posts.CreationDate`. The universality of the midnight timestamp
confirms a deliberate platform policy rather than corruption or a join error.

**Scope of effect.** The truncation touches `faa_accept` and the derived
`time_primary_acceptdate_days` only. Neither is reported in the manuscript. All
reported outcomes — `event_primary`, `time_primary_days`, `event_secondary`,
`time_secondary_days`, and the day-zero percentages — derive from `Posts.CreationDate`
and are unaffected. All 29,214 flagged rows have `event_primary = 0` and enter the
analysis only as censored observations.

**Consequence for the design.** This supplies a second, independent justification for
dating the primary event at answer creation rather than at the acceptance vote: the
dump does not support sub-day precision on acceptance timestamps, so an
acceptance-dated duration could not be measured reliably in any case.

**Audit-check correction.** The design-alignment check asserted
`faa_accept >= faa_created` as a logical invariant. That premise is wrong for
date-truncated timestamps. The check should compare at day granularity. The FAIL
reflects a flaw in the test, not in the pipeline.



## 10. Verification audits

| Audit | Command | Evidence |
| Stream completeness | `python scripts/check_stream_completeness.py`  | `logs/stream_completeness.txt` |
All three extracted files reach the March 2025 dump boundary. The tail-taper warnings coincide with the expected release cutoff and are not evidence of premature stream termination.

| Extraction integrity | `python scripts/verify_extraction_integrity.py` | `logs/extraction_integrity.txt` |
Schema, null profiles, ID coverage, date coverage, cross-file relationships, panel structure, and independent recomputation all passed.

| Design alignment | `python scripts/verify_design_alignment.py`  | `logs/design_alignment.txt` |
The single exception concerns the acceptance-vote timestamp artefact documented in §9; it is a source-data limitation and does not affect the reported outcome.

| Numerical trace | `python final_numerical_audit.py` | — |
All 51 reported numerical claims trace to output files or verified recomputations; no discrepancies were found.



## 11. Deviations from the frozen design

**Deviation 1 — treatment date.**
Pre-analysis plan: `2022-11-30`. Implemented: `2022-12-01`.

*Rationale.* ChatGPT was released on 30 November 2022. Using that date as the period
split would place users whose first post fell on 30 November in the post period while
their cohort month (`2022-11`) sits in the pre-period range, producing an internal
inconsistency. Moving the split to the month boundary aligns period assignment with
cohort assignment. Verified: 0 rows where the month and the period label disagree.
2,762 rows fall in the 48 hours before the boundary, so the check had data to exercise.

**Deviation 2 — cohort-window exclusions applied after an initial build.**
The first panel build omitted the cohort-window and observation-completeness exclusions
specified in the pre-analysis plan, producing a panel spanning 2008-07 to 2025-03 (201
cohort months). This was detected before any results were written up, `build_panel.py`
was corrected to apply both exclusions, and the panel was rebuilt. All reported results
derive from the corrected panel (24 cohort months, 2021-12 to 2023-11).

No other deviations.


## 12. Analysis record

bash
python -m src.analysis.descriptives
python -m src.analysis.survival --outcome primary
python -m src.analysis.survival --outcome secondary
python -m src.analysis.ph_check


**Conversion outcomes (unconditional over the entry cohort):**

| | Pre | Post |
| First accepted answer | 0.0931 (41,381 events) | 0.0761 (23,291 events) |
| First answer, any | 0.4019 (178,623 events) | 0.4105 (125,554 events) |

**Primary outcome:** log-rank χ² = 645.029, p = 2.693e-142.
M1 (post + cohort trend): HR(post) = 0.9744 [0.9455, 1.0042], p = 0.092;
cohort-month HR = 0.9842, z = −13.878, p = 8.58e-44.
M2 (post only): HR = 0.8133 [0.8003, 0.8264].
Collinearity: corr(post, cohort_idx) = 0.8512, VIF = 3.63.

**Secondary outcome:** log-rank χ² = 79.366, p = 5.161e-19.
M1: HR(post) = 1.0134 [0.9995, 1.0274], p = 0.058; cohort-month HR = 1.0025.
M2: HR = 1.0428 [1.0353, 1.0504].

**Proportional hazards:** primary ρ = +0.0099, early/late HR 0.9815 vs 0.9378
(spread 0.044); secondary ρ = +0.0049, early/late 1.0209 vs 0.9123 (spread 0.109).

**Zero-duration events:** primary 28,346 of 64,672 (43.8%); secondary 239,330 of
304,177 (78.7%).

Outputs: `results/tables/`, `results/figures/`, `results/descriptives/`




