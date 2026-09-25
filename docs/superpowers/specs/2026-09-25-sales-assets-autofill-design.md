# Sales Assets: Autofill with AI

Date: 2026-09-25. Instance: inboxslide (sales mode). Arena is unchanged.

## Ask

Give the Sales Assets form the same Autofill the New Campaign Target
details step got: enter a company name or website, click Autofill, and
the AI fills the industry and looks up the positions the company is
hiring for right now that fit offshore work. Applies to every PDF type,
because every type shares this one form.

## Design

- One **Autofill with AI** button under the Company / Location row, shown
  only when `_SALES_MODE` is true. It reads the Company Website field
  first, then Company or Market.
- The company lookup is the exact call the campaign Autofill uses. It
  moved out of `_aicb_ai_extract` into `_aicb_lookup_company`, with
  `_aicb_parse_extracted` and `_aicb_domain_of` beside it, so both
  buttons share one prompt.
- On ThriveModal a second call, `_tm_research_offshore_roles`, returns
  the remote-capable open postings (chips) and the best offshore picks.
- **Fill rule:** only blank fields are filled. Anything already typed
  stays. The one exception: a company typed as a domain becomes the
  official name. Location follows `_default_locations`, so ThriveModal
  gets Nationwide and Arena would get the city. Target Role gets the
  picks joined by commas when it is blank.
- **Chips** under Target Role list every posting found. Clicking one adds
  the title to the Target Role box; clicking again removes it. When no
  postings exist the picks are shown instead, with a hint saying so.
- Typed values are copied into state before Autofill or a chip click, so
  the re-render never loses them. Clear / New PDF also clears the chips.
- Errors show under the button and never clear the form.

## Not in scope

- Starting from an uploaded contact list. The Sales Assets form has no
  contact input; that path lives in the New Campaign wizard.
- Overwriting typed fields.

## Tests

`tests/test_tm_sales_assets_autofill.py`: fill rule, chip toggle text,
the background runner with a mocked model (website first, name fallback,
Arena skips roles, unmatched company, empty input), state init, and a
source grep that the page offers the button and shares the lookup.
