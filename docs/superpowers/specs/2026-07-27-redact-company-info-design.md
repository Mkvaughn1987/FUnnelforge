# Redact company names on generated résumé PDFs (MPC + Arena 5×3)

## Problem

Redacted résumé PDFs (MPC's "Redacted Résumé" section, and the résumé PDFs
Arena 4×4/5×5/5×3 campaigns generate) strip candidate name and contact info,
but currently expose real employer names (e.g. "UCLA", "USC", "City of
Hope") in the experience section. Some users want those names hidden —
replaced with a generic descriptor of the organization ("Major Academic
Medical Center") — while keeping city/state, dates, titles, and achievement
bullets untouched.

Through brainstorming, the request evolved twice from its original form:

1. **Scope** grew from MPC-only to "MPC + Arena 4×4/5×3" — until the
   investigation below found the 4×4/5×5 path structurally can't carry an
   employer name in the first place (see **Correction** below), narrowing
   the real scope to **MPC + Arena 5×3**.
2. **Default** flipped: the original ask was "default OFF (current
   behavior unchanged), with a button to turn redaction on." The user
   later reversed this explicitly — **redaction is now the default for
   all new résumés**, with a toggle to reveal real company names. This is
   a deliberate behavior change affecting every user and every new
   campaign, confirmed by the user as "the new baseline."

## Correction from the brainstormed scope: Arena 4×4/5×5 has nothing to redact

The original design discussion assumed `_build_redacted_resumes_from_cards`
(flowdrip_app.py:32636), which backs Arena 4×4/5×5/5×3, has one AI
redaction prompt symmetrical to MPC's `_gen_redacted`, and that adding a
"keep it generic" rule to that prompt would cover all three campaign types
uniformly. That's wrong. The function branches by campaign type:

- **5×3** (`camp_type == "fivebythree"`): builds a structured résumé via
  `_ai_structure_resume(client, rec)` (flowdrip_app.py:32355) from the
  candidate's real `resume_text`, or falls back to
  `_representative_resume_from_card(card)` (flowdrip_app.py:32335) when
  there's no pool record. `_ai_structure_resume`'s prompt *already*
  unconditionally instructs the AI to "Replace every employer NAME with an
  anonymized descriptor of the firm" — real employer names are discarded
  today, not merely hidden by a toggle. There is currently no way to
  recover the real name.
- **Every other type, including 4×4/5×5** (the `else` branch): calls
  `_aicb_card_to_resume_text(card)` (flowdrip_app.py:32609), which formats
  a `{label, role, bullets}` "card" straight to text. These cards never
  carry an employer field at all — the bullets come from
  `_aicb_pool_candidate_bullets` (flowdrip_app.py:33874, pool-sourced:
  location/target role/one summary sentence/salary) or from the
  auto-generate AI prompt, which produces the same shape. Real employer
  names never enter this path to begin with.

So: **4×4/5×5 résumé cards already never contain a company name — there's
nothing for a toggle to redact or reveal.** Building a toggle for that path
would be a no-op wired to state that's never read. This spec drops 4×4/5×5
from scope. If a future request wants employer context to actually appear
in 4×4/5×5 cards, that's a separate, larger change (teaching the card
builder to pull real employer data at all) and not part of this feature.

The `_representative_resume_from_card` fallback (used by 5×3 when a card
has no linked pool record) is also unaffected either way: it already
outputs a fixed placeholder employer ("Anonymized representative profile")
because there's no real résumé behind it — no real name exists to reveal.

## Scope

- **MPC** (`p_candidate_campaign`, flowdrip_app.py:39719): the
  `_gen_redacted` AI redaction step, ~flowdrip_app.py:39970.
- **Arena 5×3** (`camp_type == "fivebythree"`): `_ai_structure_resume`
  (flowdrip_app.py:32355) and its caller
  `_build_redacted_resumes_from_cards` (flowdrip_app.py:32636).
- Both default to **redacted** (generic descriptor, no real employer
  name). A toggle reveals real employer names. This is a new default for
  every user, not just an opt-in.
- Out of scope: Arena 4×4/5×5 (nothing to redact, see Correction above);
  any change to `_representative_resume_from_card`'s placeholder text;
  name/contact redaction (already handled, unchanged).

## Design

### MPC

Add `cpc_redact_companies: bool = True` to `AppState` (alongside the
existing `cpc_candidates` slate state).

In the "Redacted Résumé" UI block (flowdrip_app.py:39963-40010, just above
the `for _ridx, _rcand in enumerate(...)` loop), add one campaign-level
checkbox — "Redact company names" — bound to `s.cpc_redact_companies`,
checked by default. It sits once above the loop (not per-candidate),
matching the user's explicit ask: one toggle applies to every résumé in
the slate.

`_gen_redacted`'s prompt (inside the loop, currently rules 1-7 with
employer names left as-is) gets an 8th rule, included only when
`s.cpc_redact_companies` is true:

> Replace every employer name in the experience section with a generic
> descriptor of the type of organization (sector, rough size/prestige
> tier) — e.g. "Major Academic Medical Center" instead of "UCLA Medical
> Center." Do not use the real organization name anywhere. Keep city/state,
> dates, titles, and bullets exactly as extracted.

When the toggle is off, the prompt is unchanged from today (rules 1-7
only, real names kept) — this is how the pre-existing "unredacted"
behavior is preserved for anyone who flips it off.

Toggling the checkbox re-runs `_gen_redacted` for every candidate in the
slate (reuses the existing per-candidate "regenerate" plumbing/`ui.timer`
pattern already in the loop) since this is a prompt-level change requiring
a fresh AI call, not a client-side text transform.

### Arena 5×3

Add `aicb_redact_companies: bool = True` to `AppState`.

`_ai_structure_resume`'s JSON schema (flowdrip_app.py:32376-32386) changes
to return **both** the real employer name and a generic descriptor per
experience entry, instead of only the anonymized one:

```
"experience": [{"title": "...", "employer": "real organization name",
                 "employer_type": "generic descriptor of the org",
                 "dates": "...", "bullets": [...]}]
```

The prompt rule changes from "Replace every employer NAME with an
anonymized descriptor" to "Extract the real employer name AND a generic
descriptor of it (sector, rough size/prestige tier) for every entry."

Immediately after parsing the AI response (flowdrip_app.py:32406-32414,
where `exp` is built), `_ai_structure_resume` picks which value lands in
the `employer` key consumed by `_build_polished_resume_pdf`'s `entry()`
renderer (flowdrip_app.py:32237) based on `s.aicb_redact_companies`:
redacted → `employer_type`; revealed → the real `employer`. Both raw
values still pass through `_redact_resume_pii` before this selection, same
as today.

`s.aicb_redact_companies` needs to reach `_ai_structure_resume`, which
today takes only `(client, candidate)`. Thread it through as a third
argument from `_build_redacted_resumes_from_cards` (flowdrip_app.py:32636,
which already has `s` available via its caller
`_aicb_build_redacted_resumes(s, client=None)` at flowdrip_app.py:32673) —
add `redact_companies=True` as a keyword argument on both functions,
sourced from `s.aicb_redact_companies` at the `_aicb_build_redacted_resumes`
call site.

UI: one checkbox — "Redact company names," checked by default — in the
AICB wizard's candidate-cards review step (the screen rendering
`s.aicb_cand_cards`, flowdrip_app.py:~33650-33900), shown only when
`s.aicb_camp_type == "fivebythree"`, since that's the only AICB path this
affects. No regenerate step is needed here: the toggle is read at build
time (flowdrip_app.py:36703, `_aicb_build_redacted_resumes(s, client)`),
which runs once per campaign generation, after the user has finished
setting up the wizard — there's no standing PDF to regenerate in place the
way MPC's slate view has.

### Existing campaigns / already-generated PDFs

Both defaults only affect résumés generated after this ships. Already-built
PDFs (attached to campaigns already sent or in flight) are untouched —
this feature has no backfill/migration step.

## Out of scope / not done here

- Arena 4×4/5×5 (see Correction above — no employer name exists in that
  path to redact or reveal).
- Any change to name/contact/PII redaction (already handled, unrelated to
  this feature).
- Per-candidate toggles (explicitly rejected — one toggle per campaign).
- Backfilling or regenerating résumés for already-sent campaigns.
