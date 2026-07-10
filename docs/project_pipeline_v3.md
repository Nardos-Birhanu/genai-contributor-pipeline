# Playbook — What Does Generative AI Substitute in the Expertise Pipeline?
### MSc CSS final paper · ~3–4 weeks · the *defensible* substitution project
**Substitution framing, verified-distinct gap. Deliberately lean — not bigger.**

> **Why this framing.** Eight targeted searches across two review rounds established that every *pure*-substitution angle is published (see the map). The only way to give a substitution question a defensible gap for a 3–4 week paper is to ask what AI substitutes **in the newcomer→answerer pipeline** — a substitution question routed through the one gap in this space that survives skeptical review. This document fixes the three critical weaknesses the review found: no defensible gap → a verified-distinct gap; unobservable individual AI use → scoped claims; vague "substitution" → one measurable, unconditional outcome.

---

## Map of occupied ground (do not re-enter)
del Rio-Chanona (decline); Burtch et al. (decline, topic/user heterogeneity, Stack Overflow-vs-Reddit social fabric, complexity); Xue et al. (40 communities, DiD); Helic et al. (question difficulty, 2 yrs); Marketing Letters (verification/moderation cost); Padilla et al. + household-browsing paper (demand side); Wikipedia (engagement, content prevalence, governance); OSS; freelance; creative communities (perceptions, AI-comment disruption); **CHI 2026 — role reversals + recognition inequality among existing users.** Anything phrased as "how much / what content / which users / which community type / existing-user roles" is a dead end.

## The gap (required 4-part form)
- **What existing papers know:** how much participation declines, in which topics, for which users, in which community types, across the Stack Exchange network, and how *existing* users swap asking/answering roles (CHI 2026). All measure activity, content, or the behavior of users already present.
- **What remains unknown:** whether the community still *converts its newcomer intake into answerers* — the **cohort conversion rate** — after AI substitutes the routine questions newcomers historically used as entry practice.
- **Why it matters theoretically:** legitimate peripheral participation (Lave & Wenger) — expertise is reproduced by novices moving from periphery to centre through routine participation. If AI substitutes the routine rung, the *reproduction mechanism* of the commons, not merely its volume, is at risk. This is a claim about the **sustainability** of peer-produced knowledge.
- **Why different from existing AI-substitution research:** inflow shrinking (Burtch) ≠ the conversion function degrading; existing-user role reversal (CHI 2026) ≠ new-cohort entry. None of the incumbents measure the conversion rate of the *intake*. This is distinct-in-kind, not incremental.

## What exactly is being substituted (measurability — the review's core demand)
- **The substitution claim (the most defensible interpretation):** AI substitutes the **routine informational exchange** that historically served as newcomers' entry practice — not social bonding, not expert deliberation.
- **What CAN be measured:** the share of a join-cohort reaching its first accepted answer within a fixed window; how that share changes around ChatGPT's release; whether the change concentrates in AI-substitutable topics.
- **What CANNOT be measured:** whether any individual used AI (unobservable in the data); actual learning; intent; off-platform maturation.
- **Claims allowed:** an *association* between ChatGPT's release and a change in cohort conversion, **consistent with** substitution of the entry rung, strengthened by the topic-substitutability differential. **Not allowed:** "AI caused newcomers to stop learning."

## Research design (full)
- **RQ:** After ChatGPT's release, has the share of Stack Overflow newcomer cohorts that enter the answerer pipeline within their first year declined — and is the decline concentrated in topics where AI is a stronger substitute?
- **Hypotheses:** H1 — cohort conversion rate falls for post-ChatGPT join-cohorts, net of the pre-existing trend. H2 — the fall is larger in high-substitutability topics (the DiD differential).
- **Unit of analysis:** the **tag** (for the DiD); conversion computed from user join-cohorts. *(Unit and treatment-assignment locked together — the error purged from earlier drafts.)*
- **Dataset:** Stack Exchange data dumps (open, Internet Archive) + Stack Exchange Data Explorer for prototyping; **record the exact snapshot date.**
- **Variables:** join-cohort = account-creation quarter; **primary outcome = share of the join-cohort reaching first accepted answer within a fixed window (UNCONDITIONAL on persistence** — no collider); tag substitutability = contemporaneous behavioral proxy (post-ChatGPT question-volume drop per tag + public training-data volume), validated in Phase 6.
- **Method:** event-study difference-in-differences, high vs low substitutability tags; **parallel-trends diagnostic run first**.
- **Limitations:** individual AI use unobservable; entry-composition shift across cohorts; right-censoring of recent cohorts; secular pre-trend; platform shocks (the 2023 GenAI ban, the moderator strike); external validity (one platform).
- **Alternative explanations & how handled:** secular decline (detrend with pre-cohorts), GenAI ban / moderator strike (acknowledge; topic-DiD differences out platform-wide shocks), migration (the differential is the identifying lever, not the level).

---

## Phases (each with Assumption / Early test / Failure condition / Fallback)

**P0 Rubric (½d).** Aim at Originality (6) + Lit (4) + Design (4) = 61%; avoid hallucinated refs / LLM artefacts. *Assume:* you know the target. *Test:* recall weights + tripwires. *Fail:* optimising for a model. *Fallback:* n/a.

**P1 Literature matrix (2d) [E].** Fill the matrix (template below) on the map papers, full text. *Assume:* you command the incumbents. *Test:* one-sentence "what each did NOT do." *Fail:* can't distinguish your seam from theirs. *Fallback:* revert to the prior v3 (identical core).

**P2 Gap validation (1d) [E] · GATE 1.** Confirm the conversion-function seam survives targeted search and is distinct from Burtch AND CHI 2026. *Assume:* seam unpublished. *Test:* adversarial search on "cohort conversion rate newcomer answerer ChatGPT." *Fail:* a 2025–26 paper did it. *Fallback:* revert. **Proceed only if distinct-in-kind.**

**P3 RQ + evaluation (1d) [E].** Score candidate RQs (framework below); keep 1. *Assume:* one RQ is novel + answerable. *Test:* framework scores. *Fail:* novel ones infeasible. *Fallback:* the descriptive MVP.

**P4 Lock the causal core (1d) [C].** Lock the **unconditional estimand**, primary outcome, **unit = tag**, treatment-assignment, window, cohort cut. *Assume:* definitions computable. *Test:* can a stranger compute your outcome? *Fail:* ambiguity. *Fallback:* simplify outcome.

**P5 Feasibility + POWER (2–3d) [E] · GATE 2 (kill).** On a sample: computability, joins, censoring, **and a hard count of post-cohort N × base conversion rate**. No real pre/post peeking; seal a confirm set. *Assume:* measurable + powered. *Test:* the N-count + a placebo-split notebook. *Fail:* powered cell is tiny, or data gated. *Fallback:* descriptive MVP; or revert. **This gate decides DiD vs MVP.**

**P6 Validate the substitutability proxy (2d) [E→C] · GATE T.** Build + confound-check the proxy (vs tag age/popularity/difficulty), using a contemporaneous signal. *Assume:* proxy tracks realized substitutability. *Test:* does the on-platform volume-drop align with training-data volume across tags? *Fail:* confounded. *Fallback:* drop DiD → cohort comparison.

**P7 Instructor meeting (½d) [CP].** Bring the one-pager (below). *Assume:* direction defensible. *Test:* can you rebut "this is Burtch/CHI again" in 3 sentences? *Fail:* you can't. *Fallback:* reframe with instructor.

**P8 Freeze + pre-analysis plan (1–2d) [C].** Lock estimator (event-study), clustering (tag), composition control (entry-activity threshold), primary outcome; **timestamped PAP to git before confirmatory run.** *Assume:* design stable. *Test:* is the analysis now mechanical? *Fail:* still deciding. *Fallback:* n/a — do not proceed unfrozen.

**P9 Pipeline (3–4d) [C].** Raw → cohort panel; scripted, seeded; **snapshot + pinned env.** *Assume:* dumps process in time. *Test:* a sample runs end-to-end day 1. *Fail:* wrangling overruns. *Fallback:* smaller site / tag-subset (pre-chosen).

**P10 Exploratory on develop set (2d) [E].** Descriptives, secular trend, gradient — confirm set sealed. *Assume:* signal survives at scale. *Test:* the descriptive curves. *Fail:* phenomenon gone. *Fallback:* MVP.

**P11 Parallel-trends FIRST + confirmatory on confirm set (3–4d) [C] · GATE D.** Diagnostic must pass; then frozen spec + robustness. *Assume:* trends parallel. *Test:* the event-study pre-period. *Fail:* not parallel. *Fallback:* descriptive MVP (a complete paper).

**P12 Interpret (2d) [C].** Link to LPP + Burtch/CHI-2026; statistical-vs-substantive; "consistent with, not proof of."

**P13 Write (5–6d, mostly consolidation) [C].** Intro/Discussion/Limits/Abstract; **Week-4 literature re-scan** before Discussion.

**P14 Audit + submit (2–3d) [C].** Verify every reference; clean-run reproduction; LLM-artefact self-audit; word count; **confirm registration**; zip code+data+README.

---

## Continuous tracks
**R** references (Zotero; open every citation) · **C** reproducibility (git, seeds, snapshot, pinned env) · **W** write as you go (contribution statement + skeleton + rough Intro in Week 1) · **D** decision & assumption log.

## Literature matrix template (one row/paper)
`Zotero key | Setting/data | RQ | Design | Finding | Substitution construct measured | What it did NOT do | Relation to mine (differs-in-kind / competes) | quote-free note`

## Decision log (one row/decision)
`Date | Phase | Decision | Options | Rationale | Assumption | Test & when | Reversible? | Status`

## RQ evaluation framework (1–5; kill if <4 on Novelty or Data)
Novelty (distinct-in-kind) · CSS relevance (reveals a social truth, not a metric) · Theory (extends a named theory) · Data availability (open, now) · Feasibility (one student, 3–4 wk) · Analysis strength (clean identification or rich description).

## Weekly timeline
| Wk | Focus | Milestone | Gate |
|---|---|---|---|
| 1 | P1 matrix → P2 gap → P3 RQ → P4 lock core → **P5 feasibility+power** → P6 begin proxy → P7 meeting | Distinct-in-kind gap; **power verdict**; instructor go | 1, 2, C |
| 2 | Finish P6 → **P8 freeze + PAP** → P9 pipeline | Validated proxy; PAP committed; clean panel; async check | T |
| 3 | P10 (develop) → **P11 parallel-trends → confirmatory** | Identification verdict (+ MVP if failed); results | D |
| 4 | P12 → **lit re-scan** → P13 write → P14 audit → submit | Full draft → verified refs → repro zip → submit | — |
| Buffer | ~2 floating days (Wks 2–4) | absorbs pipeline overrun | — |

## Instructor one-pager
RQ · contribution claim · gap (4-part) · **why different from Burtch, del Rio-Chanona, Xue, AND CHI-2026 role-reversal** (name them; 3-sentence seam) · methodology diagram · feasibility count · questions: (1) distinct enough? (2) identification + causal-language line? (3) right outcome/construct? (4) one site enough? (5) is the MVP acceptable if trends fail?

## Minimum viable paper
Unconditional cohort-conversion **descriptive** study, pre vs post, as a specialised analysis of non-trivial data — a complete, rubric-accepted paper without the DiD. Pre-choose the smaller-scope site now.

---

## Final supervisor review — "if executed perfectly, why might it STILL fail?" (fixes baked in above)

**Most likely failure, even done flawlessly: the result is correct but reads as a *corollary* of published work, scoring low on Originality despite clean method.** In a saturated field, "conversion rate declined, concentrated in AI-substitutable topics" can be dismissed by a skeptic as an obvious consequence of "newcomers post/answer less" (Burtch) and "role/recognition inequality widened" (CHI 2026). Method cannot rescue this — only three things can, and they are now required, not optional:

1. **Framing must do heavy lifting (baked into P2/P7/P13):** a mandatory positioning paragraph that names the four incumbents and states, in three sentences, why *conversion rate of the intake* is a distinct construct from activity, roles, and recognition. If a reader finishes the intro thinking "Burtch again," the paper fails regardless of the analysis.
2. **An empirical payload the incumbents could not produce (added to design):** exploit the **now-available 2+ year horizon** to test whether the conversion decline is *transient or persistent* — incumbents' windows ended in 2023 and structurally could not answer this. Persistence vs recovery is a genuinely new empirical finding, and it is your insurance against "corollary."
3. **Theory must carry weight (P12):** argue *why* a commons that still functions but no longer reproduces its contributors is a distinct and more consequential form of decline (LPP + sustainability), so the number *means* something the incumbents' numbers do not.

Secondary failures, already gated: underpowered post-cohorts (P5 power kill-gate → MVP); collider (unconditional estimand, P4); parallel-trends failure (P11 → MVP); causal overreach (scoped claims throughout). The one that is not method-fixable is #1–#3 above — so treat framing, the horizon payload, and the theoretical argument as the *primary* deliverables, and the estimation as secondary. That inversion is what lets a defensible-but-adjacent question clear the Originality bar in a crowded field.
