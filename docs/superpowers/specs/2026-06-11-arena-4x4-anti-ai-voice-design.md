# Arena 4×4: Anti-AI Voice + Redacted Resumes on Email 2 & 4

Date: 2026-06-11
Status: Approved (design)

## Goal
Make the Arena 4×4 outreach read like a recruiter wrote it, not an AI, and
attach redacted resume PDFs to Email 2 and Email 4 of the four-email cadence.
Cadence timing is unchanged (the existing "4 steps, 2 weeks" spacing stays).

## Background
The 4×4 is the `fourbyfour` preset in `AICB_CAMPAIGN_TYPES`
(`flowdrip_app.py` ~L3948). It generates four emails (Introducing Available
Talent, Top Talent Insights, Thoughts on this?, Market Trends) anchored to a
real advertised role.

Two problems today:
1. The 4×4 generation prompt carries no "write like a human" guard. The
   newsletter and reply flows have strong anti-AI style blocks (~L8137,
   ~L8186) but the campaign-build path does not. The universal scrubber
   `_strip_dashes` (~L6739) only swaps an em dash for a spaced hyphen
   `" - "`, which is itself an AI/typography tell.
2. Redacted resume PDFs are attached to email index 0 and 2 (Email 1 and 3)
   when they exist (~L33696). The desired placement for the 4×4 is Email 2
   and Email 4.

## Scope

### Piece 1: Anti-AI copy engine
Three layers, because the prompt alone leaks and the scrubber alone is blunt.

**Layer A. Voice guard (prompt-side).**
A reusable rules constant injected into the 4×4 (and AICB campaign) build
prompt so the model writes human from the first token:
- No em dashes, en dashes, or a spaced hyphen used as a sentence dash. Use
  periods and commas.
- Contractions on. Vary sentence length, including short sentences.
- One idea per sentence. No three-part parallel lists.
- Banned openers: "I hope this email finds you well", "I hope all is well",
  "I wanted to reach out", "Hope you're having a great week".
- Banned corporate-AI words: streamline, leverage, elevate, delve, robust,
  seamless, unlock, spearhead, "in today's market", fast-paced, "it's worth
  noting", moreover, furthermore.
- Write like a recruiter typing a quick note, not a brochure. No padded,
  symmetric bullets.

**Layer B. Humanizer (post-generation safety net).**
A new `_humanize_email_text(text)` applied to generated 4×4 email subjects
and bodies before save. Conservative:
- Deletes a known cliché opener line if it slipped through (whole-sentence
  match only, e.g. "I hope this email finds you well.").
- Converts em/en dashes inside body copy to a period or comma based on
  context (independent clause on both sides becomes a period and the next
  word is capitalized, otherwise a comma), so output never shows the spaced
  hyphen tell.
- Does NOT rewrite mid-sentence wording, to avoid breaking grammar. The
  prompt (Layer A) does the heavy lifting; this is the safety net.

**Layer C. Leave the global scrubber alone.**
`_strip_dashes` keeps guarding UI labels and legitimate uses
("Candidate A - Foreman"). The smarter dash handling lives in
`_humanize_email_text` and runs only on generated email bodies/subjects.

### Piece 2: Redacted resumes on Email 2 & 4
For the 4×4, attach redacted resume PDFs to email index 1 (Email 2) and
index 3 (Email 4), and only when real redacted resume PDFs exist. If no
resumes were uploaded, nothing attaches and the emails still send clean.
Non-4×4 campaigns keep their current attachment behavior.

## Components / boundaries
- `HUMAN_VOICE_RULES` (new module constant): the Layer A text. Pure data.
- `_humanize_email_text(text) -> str` (new pure function): Layer B. No I/O,
  unit-testable in isolation.
- 4×4 prompt assembly: inject `HUMAN_VOICE_RULES` into the build prompt.
- AICB build path: call `_humanize_email_text` on each generated 4×4
  subject/body before save; route resume PDFs to index 1 and 3 when mode is
  4×4.

## Testing
- `_humanize_email_text`: em dash between clauses becomes a period with the
  next word capitalized; em dash mid-phrase becomes a comma; a cliché opener
  line is removed; ordinary text is unchanged; no spaced-hyphen-as-dash
  remains.
- 4×4 attachment routing: given 2+ redacted PDFs and 4 emails in 4×4 mode,
  PDFs land on emails index 1 and 3, not 0 and 2; with 0 PDFs nothing
  attaches; non-4×4 mode keeps index 0/2 behavior.

## Out of scope
- Cadence/timing changes.
- Live market-stat fetching (BLS/Indeed Hiring Lab integration).
- Newsletter auto-enrollment handoff after Email 4.
- Weekly Tuesday rhythm and Wed/Thu call+LinkedIn touches.
