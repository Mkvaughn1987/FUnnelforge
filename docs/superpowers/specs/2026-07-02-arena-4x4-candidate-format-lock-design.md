# Arena 4×4 — Candidate-Format Lock — Design

**Date:** 2026-07-02
**Status:** Awaiting user review
**Approach:** A (prompt + locked candidate format) — user chose over A+validator.

## Problem

Mike wants every Arena 4×4 email to follow his reference template "to a tee."
Investigation shows the 4×4 **sequence structure and subjects already match** the
reference (`AICB_CAMPAIGN_TYPES["fourbyfour"]` touch_sequence, flowdrip_app.py):

- Step 1 — Introducing Available Talent (intro + candidate slate + CTA)
- Step 2 — **Top Talent Insights** (market facts + candidate highlights)
- Step 3 — Follow-up **Call**, `delay_days:0` (same day as Step 2) ✓ already there
- Step 4 — Proven Results, subject **"Thoughts on this?"** (80–90% fill, 2–3 wk,
  contingency, replacement guarantee, $25k cost, competitive advantage) + candidates
- Step 5 — **"Market Trends and Hiring Solutions for <Role>"** (market updates,
  soft close, newsletter mention), no candidates

The one real gap is the **candidate block format**. `_4x4_candidate_block()` passes
the candidate data to Haiku with "write 4–6 concise bullets," so the layout drifts
per issue — the "doesn't look like a resume" complaint.

## Locked decisions (with user)

- **Candidates:** each campaign's real slate, rendered in the exact bullet format.
- **Rigid:** 4-email sequence, subjects, section order, candidate bullet format.
- **AI-adapted per company/industry:** prose wording and market stats ("strong guide").
- **Same-day call** after Email 2: keep as-is.
- **Approach A:** lock via prompt + deterministic renderer; no validator (for now).

## Design

### 1. Deterministic candidate renderer (the core change)

Rewrite `_4x4_candidate_block(client, label, cand)` so the FORMAT is code, not AI:

**Target output (HTML), matching the reference:**
```
<p><strong><u>Candidate A: Senior CNC Machinist</u></strong></p>
<p>- <strong>Experience:</strong> 25+ years in CNC machining …</p>
<p>- <strong>Skills:</strong> …</p>
<p>- <strong>Proficiencies:</strong> …</p>
<p>- <strong>Certifications:</strong> …</p>
<p>- <strong>Tools:</strong> …</p>
<p>- <strong>Preferred Location:</strong> …</p>
<p><strong>Target Salary:</strong> $…</p>
```

**Logic:**
- Header = `f"{label}: {role}"`, bold + underlined. Resolve `role` from
  `cand` aliases: `role` / `target_role`.
- **If `cand["bullets"]` exists** (agent-provided, already "Label: value" form):
  render each bullet as `- <strong>Label:</strong> value` (split on first ":";
  plain dash line if no colon). **No AI call** — format guaranteed.
- **Else if only free-text** (`redacted_resume`/`summary`/`resume_text`):
  one Haiku call to EXTRACT into the labeled fields (Experience, Skills,
  Proficiencies, Certifications, Tools, Preferred Location) returned as a JSON
  list of `"Label: value"` strings, then rendered by the SAME deterministic
  path. AI fills content, code fixes format.
- Salary line from `cand` aliases: `salary` / `target_salary`, rendered as a
  bold-label `Target Salary:` line (appended if not already among bullets).
- Reuse the `**bold**`/escape helper approach from `_jway_render` for safety.
- Preserve existing fallback when data is minimal.

**Implementation note (reconcile field shapes):** confirm what `cand` dict is
passed at call sites (API `candidates[]` uses `{label, role, bullets[], years?,
location?, target_salary?}`; the current renderer reads `target_role`/`salary`/
`redacted_resume`). The renderer must read all aliases so both shapes work.

### 2. Sequence prompt polish (small)

In the `fourbyfour` touch_sequence string:
- Step 1: tighten the opener to Mike's line — "I noticed you're actively seeking
  a **{Role}** at **{Location}**; I'm currently working with a pool of qualified
  candidates in **{area}**…" (AI writes the real values, no brackets shipped).
- Step 5: nudge market updates toward Mike's categories — salary trends, fuel /
  commute costs, local wage pressure, housing costs.
- Keep the standing rule: insert the candidate blocks **verbatim**.

### 3. Unchanged

Same-day call, scheduler, J's-Way handoff, market snapshot, and the rest of the
generation pipeline are untouched.

## Testing

Unit-test the deterministic renderer (pure, no AI):
- bullets `["Experience: 25 yrs", "Tools: Mazak"]` → dash + bold-label lines.
- header bold+underlined; role from `role` and from `target_role`.
- salary from `salary` and from `target_salary` → bold `Target Salary:` line.
- no-bullets + no-resume → minimal fallback (no crash).
- split on first colon only; plain dash line when a bullet has no colon.

(The AI-extraction branch is integration-tested manually via a preview send.)

## Out of scope

- Structural validator / auto-repair (Approach A+ — deferred).
- Any change to email subjects or the 4-step cadence (already correct).
