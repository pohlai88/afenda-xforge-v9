# The AFENDA xForge mark

The mark is an X built from four tapered wedges meeting at a diamond void —
two halves closing on each other, not four separate strokes. It replaces the
identity v2.1 mark (an A over a double total rule) as of 2026-09-23, on
these grounds:

- The A-over-rule mark's double rule — the detail carrying its whole idea —
  merges into an unreadable smear by 32px and is a plain solid triangle by
  16px, the size a favicon and most menu icons actually render at.
- The X remains legible at every size tested, including 16px, because it has
  no fine horizontal detail to lose.
- A 2026-09-22 benchmark had rejected an X for reading as a close/dismiss
  button at 16–32px. Re-tested against the real rendering pipeline
  (supersampled and downscaled exactly as it ships) rather than judged in the
  abstract: both risks were real, and the A's illegibility was the more
  severe defect of the two.

**Source of truth:** `afenda/tools/brand_images.py` — `MARK_SVG_INNER` (the
path data) and `_mark()` (the same shape, redrawn as PIL polygons for PNG
output; the two must be kept in sync by hand, since nothing currently
generates one from the other). Every icon, favicon, and lockup in this repo
is produced by that module's render pipeline — never hand-edit a generated
file; change the source and re-render.

The 108 per-module app icons (the ones with a FontAwesome glyph) are a
separate system in `afenda/tools/app_icons.py`. This mark is what appears
there only as the fallback for modules with no glyph mapping.

## Geometry

Four wedges, each a 45°-symmetric shape: a flat outer terminal (one cut,
matching how the wordmark's own lowercase *x* terminates on its baseline and
x-height, rather than a two-sided corner), tapering 3.3:1 to a chamfered
inner tip, leaving a symmetric diamond void at centre. Ink box is square.
Mirror-symmetric about both centre axes — the symmetry a letterform X
actually has, not rotational symmetry.

Master coordinates: 240-unit frame, ink box `30..210` square, terminal
length 56, chamfer 5, tip at 112.5. Every rendered size is a reprojection of
this one shape; nothing is redrawn per size.

## Colourways

| Variant | Fill | Ground | Where |
|---|---|---|---|
| Tile | White `#FFFFFF` | Ledger Blue `#1E3A8A`, radius 12/64 | App icon, favicon, PWA icons |
| Bare, coloured | Ledger Blue | transparent, no tile | `odoobot_transparent.png`, `odoo_o.png` |
| Bare, white | White | transparent, no tile | Dark-surface lockups (`lockup_white_png`) |
| Faint watermark | Standard lockup at 12% alpha | transparent | Report background (`demo_logo_report.png`) |

The mark's single-fill pipeline (`MARK_SVG_INNER.format(fg=...)`, `_mark()`)
takes exactly one foreground colour — there is no multi-tone variant in this
codebase. A duotone or four-fill treatment (silver/blue halves at different
weights) exists only in exploratory design work outside this repo and is not
wired into any generator here.

## With typography vs. without

**Icon alone** (`tile_svg`, `tile_png`, `mark_png`): app icon, browser tab,
favicon, taskbar, PWA home-screen icon, anywhere the product is represented
as a single glyph with no room to read a wordmark. Never place text near the
bare icon at these sizes — there is no room for it to be legible.

**Full lockup** (`lockup_svg`, `lockup_png`, `lockup_dark_svg`,
`lockup_white_png`): login screen, email header, printed report letterhead,
marketing surfaces, anywhere the product is named rather than just
represented. The lockup is mark + "AFENDA" (Source Serif 4, 600) +
"xForge" (Source Sans 3, 500) — never the mark alone with no wordmark, and
never the wordmark alone with no mark, once there is room for both.

The lockup's type is Source Serif 4 / Source Sans 3 — the product's own
identity fonts, not the Geist typeface used in any external exploratory
design board. Nothing in this repo's identity uses Geist.

## Light and dark

Two lockup renderers, not one recoloured:

- `lockup_svg("#0F172A", "#1E3A8A")` / `lockup_png(...)` — ink text, blue
  "xForge", on a light or transparent ground. Default.
- `lockup_svg("#F7F7F5", "#A5B4FC")` / `lockup_white_png(...)` — paper text,
  lifted-blue link colour, bare white mark with no tile, for a dark ground.

Do not composite the light lockup onto a dark background or vice versa —
each was built with a fill set validated for its own ground; swapping the
background under the wrong set fails contrast.

## Clear space and minimum size

- Clear space: at least 25% of the mark's own ink-box width on every side,
  measured from the ink box edge (not the outer frame). A tiled icon already
  carries a little more than this from the tile's own corner radius; a bare
  mark placed in a layout needs the full 25% added explicitly.
- Minimum size: 16px for the tiled icon (the centre void closes below this
  and the mark reads as a plain solid X — the intended fallback, not a
  defect). 24px for the bare mark with no tile. 120px wide for the full
  lockup, below which the wordmark stops being legible before the mark does.

## Don't

- Don't recolour the mark outside the four fills above. It is not a
  multi-tone system in this codebase; introducing new colourways here
  without updating both `MARK_SVG_INNER` and `_mark()` produces two
  inconsistent representations of the same shape.
- Don't distort the mark's proportions. The ink box is deliberately square
  and the wedges are deliberately tapered 3.3:1 — stretching either changes
  the shape's identity, not just its size.
- Don't add a drop shadow, bevel, gradient, or outer glow. Every consumer of
  this mark is an icon container that clips to its own shape (OS app grids,
  browser tabs, PWA manifests); an effect that extends past the ink box gets
  silently cropped by the platform, not rendered.
- Don't hand-edit a generated file (any path in `brand_images.TARGETS`).
  Change `MARK_SVG_INNER` / `_mark()` and re-render; a hand-edited output
  diverges from its own source the next time anyone regenerates it.
