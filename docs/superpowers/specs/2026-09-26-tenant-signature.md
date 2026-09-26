# The tenant signature, and seasons around it

Status: owner ruling, 2026-09-26: "restore it and build on top; avoid future overriding, since
this is the tenant's signature design."

## The ruling

- **The crystal bear is the tenant's signature.** It is the auth-page design of 68b0b9913: the
  tenant-green crystal bear, drawn in the app icons' Crystal Duotone material, on light paper.
  - Version 19.0.1.0.9 restores it exactly as it stood at c5545d38f.
  - The four-season stage, which recoloured the bear, is removed. Its spec is kept as history.
- **It is protected by three layers:**
  - `afenda/tools/tests/test_tenant_signature.py` pins `crystal_bear.svg` and `auth_bear.xml`
    byte for byte.
  - `.claude/settings.json` denies agent edits to both.
  - CLAUDE.md and the superdesign skill state the rule.
- **Re-pinning a digest is the owner's decision**, never the fix for a red test.

## The season layer: built on top, never in

A separate layer adds the seasons around the signature. It never touches the bear, the card,
the logo, the buttons or the text.

- **Markup:** `.o_afenda_seasons` is its own `aria-hidden` element in `webclient_templates.xml`'s
  `login_layout`, fixed to the viewport. It holds four season sheets: spring, summer, autumn,
  winter.
- **Each sheet** tints the paper very lightly and carries its own weather, drawn in CSS:
  - spring: falling petals;
  - summer: twinkling glints;
  - autumn: falling leaves;
  - winter: snow, in pale blue-grey so it reads on light paper.
- **Stacking:** the paper tint lies under everything. The weather crosses the page and the bear,
  but stays under the form column, so it never covers a field or a word.
- **Motion:**
  - A 32 s loop: each season holds for 6 s, then cross-fades over 2 s.
  - The loop starts on today's season, taken from the server's UTC date in northern
    meteorological order, which is a brand cycle, not a climate.
  - Only `opacity` and `transform` animate, so the compositor draws it and the bear never
    repaints.
- **Reduced motion:** only today's sheet shows, and it is still.
- **Styles** live in `static/src/css/auth_seasons.css`, every selector under `.o_afenda_login`.

## Acceptance

- The signature test passes. `crystal_bear.svg` and `auth_bear.xml` are unchanged from
  c5545d38f.
- Every auth page shows the layer. The bear is pixel-identical to the pre-season render with
  the layer hidden.
- 0 layouts per frame at rest; frame p95 ≤ 20 ms.
- The owner sees stills and a loop video before the merge.
