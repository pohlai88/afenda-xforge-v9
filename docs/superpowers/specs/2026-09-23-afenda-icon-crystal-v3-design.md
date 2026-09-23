# AFENDA xForge icon system — Crystal Duotone v3

Design for reaching the icon quality in the specimen sheet at
`AFENDA_xForge_Crystal_Duotone_V3/afenda_icons_v3/`.

## What the specimen actually is, and what we have

The sheet states a construction rule — *core semantic shape + xForge angular
shard = final icon (max 3 planes)* — and five principles: clear silhouette,
controlled translucency, distinct xForge geometry, scales 16–128px, consistent
across modules.

An earlier draft of this design proposed five material changes and got the
diagnosis wrong. Rendering it and looking at the result against the sheet showed
two errors worth recording, because both would have shipped:

**The accent is never clipped.** `icon_png` draws three planes, and the first is
`_mask_only(accent, glyph)` — the part of the accent lying *outside* the glyph.
The rendered silhouette is therefore `glyph ∪ polygon`: a bar hanging in empty
space past the edge of the icon. Every icon on the sheet has exactly one clean
silhouette. Clipping the shard into the shape is a one-line change and is the
single largest step toward the specimen.

**A FontAwesome glyph cannot carry the rest.** Even clipped, four properties of
the sheet are properties of drawn artwork, not of render settings:

- the forms are **solid**; `money` and `cube` are outline glyphs with no body to facet
- they carry **interior detail** (the document's three white bars); a monochrome
  glyph's counters are holes, not white shapes
- the facets **follow the object** — the cube's colour breaks land on the cube's
  own edges, not on an arbitrary diagonal
- one consistent **light direction** across the set

So the geometry has to be authored. The material work is real but secondary.

## Architecture: one pipeline, two geometry sources

The renderer stops being "recolour a glyph" and becomes "composite named planes".
Both geometry sources feed the same compositor, which is what keeps this from
becoming two systems:

| Source | `body` | `shard` | `detail` |
|---|---|---|---|
| **Authored** (`icon_art/<module>.svg`) | the drawn silhouette | a drawn plane following the form | optional drawn elements |
| **Fallback** (any module not yet drawn) | the FontAwesome glyph | the scored accent polygon, **clipped to body** | none |

`body` alone defines the silhouette. `shard` and `detail` are always clipped to
it, so the fallback path inherits the clipping fix for free and the ~55
undrawn modules improve the day this lands.

### Authored format

`afenda/tools/icon_art/<module>.svg`, `viewBox="0 0 100 100"` — the same
100-unit space `ACCENT_SHAPES` already uses. Paths carry a role in `id`:

```xml
<svg viewBox="0 0 100 100">
  <path id="body"   d="M20 8 H62 L80 26 V92 Q80 96 76 96 H24 Q20 96 20 92 Z"/>
  <path id="shard"  d="M62 8 L80 26 H62 Z"/>
  <path id="detail" d="M30 44 H62 M30 56 H70 M30 68 H54"/>
</svg>
```

Geometry only — no colour. Colour comes from the module's palette entry, so one
drawing serves light and dark and any future palette revision. A designer can
open these in any vector tool.

### Rasterising without a new dependency

`fontTools.svgLib.path.parse_path` turns a `d` attribute into pen commands, and
`fontTools` is already pinned in `afenda/tools/requirements.txt`. A small pen
flattens curves to line segments and hands polygons to `ImageDraw.polygon`,
matching how `accent_mask` already works. No `cairosvg`, no native Cairo on
Windows, no new pin.

## Material

Applied identically to both sources.

**Crossing colour is a composite, not a multiply.** `controlled_overlap_colour`
is a multiply, so the crossing can only ever be darker than both planes. On the
sheet the Accounting band is *lighter* than the document it crosses and the
Inventory cube carries one light face and one dark. Use the blend the sheet's
"controlled translucency" actually describes:

```python
crossing = lerp(body_colour, shard_colour, ACCENT_ALPHA)   # 0.80
```

The existing `MIN_OVERLAP_LUMINANCE` floor stays — it stops a dark pair
collapsing into mud and is orthogonal to which direction the blend moves.

This is a change of **colour**, not of compositing. Planes still partition the
silhouette exactly, so the invariant in `icon_png`'s docstring — *the masks sum
to the union's coverage at every alpha, so the seam has no halo* — still holds.
v3's own renderer reaches the same colour by painting an 80%-alpha shard **over**
the body, which is layering rather than partition: on a body edge at α 0.5 inside
the shard it yields 0.90 where true coverage is 1.00, a transparent seam along
every internal edge, worst at 16–24px. Take v3's colour model, not its
compositing.

**Gradients per plane.** Each plane fills with a ramp from its base to its `_hi`
stop rather than a flat colour. Build one L-mode diagonal ramp per side and use
`Image.composite(hi, lo, ramp)`, which is the per-pixel lerp. v3's
`linear_gradient` is a nested Python loop — roughly 1M iterations per plane per
icon at the supersampled size — and is not worth porting.

**Edge highlight and ambient shadow**, both gated at `min(width, height) >= 48`.
The highlight is what makes two planes read as one faceted solid at the sizes
these are actually seen; erode the shard mask by a pixel
(`ImageFilter.MinFilter(3)`), subtract, paint white at low alpha, clipped to the
body. The shadow is a Gaussian blur of the body mask, offset down, in ink at low
alpha. One PNG serves both colour schemes, so the shadow stays tight and
low-alpha: grounding on paper, invisible on ink.

**One size threshold.** Below 32px, flat fill and no highlight or shadow — they
cost sharpness and show nothing. This is what makes "scales 16–128px" true.

## Palette

Renderer inputs in `app_icons.py`, never `brand.py`. The six colours currently
shared with `brand.py`'s `tags` list are exactly why this must be explicit: they
read as an icon palette and are not one. `brand.py` and `$o-colors` are
untouched.

Adopted from v3: `LEDGER #1E3A8A` (unchanged, still primary),
`SIGNAL_BLUE #2563EB`, `TEAL #10B981` with `TEAL_DARK #0F766E`,
`PLUM #7C3A8A`, `MULBERRY #BE2F7F`, `OCHRE #C97917`, `MUSTARD #D49A23`.

Families v3 does not name — `MOSS`, `BRICK`, `CLAY`, `VIOLET`, `GREY`, `INDIGO`,
`SLATE` — derive their `_hi` stop from one rule, rather than eight hand-tuned
constants nobody can predict:

```python
def lighten(base):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb(base)))
    return colorsys.hls_to_rgb(h, min(1.0, l + 0.14), min(1.0, s * 1.15))
```

It moves in the same direction as every pair v3 hand-picked — lighter and
slightly more saturated, not washed toward white. A family whose `_hi` would clip
keeps a hand-picked value; `GREY` is the expected case.

## Scope

Five authored icons first, the ones on the sheet: `account`, `hr`, `stock`,
`mrp`, `crm`. Every other module keeps working through the fallback path and
gains the clipping fix and the material. Drawing the long tail is incremental
and needs no further code.

The `account` and `crm` glyphs are also semantically wrong for the sheet —
FontAwesome gives a banknote and a suitcase where the sheet shows a document and
a play mark. Authoring replaces both, so no `APP_GLYPHS` remap is needed.

`choose_accent_shape` and its penalties now serve the fallback path only.
`band-diag` joins `ACCENT_SHAPES` as the diagonal the vocabulary lacks:

```python
"band-diag": ("polygon", ((-10, 78), (78, -10), (106, 18), (18, 106))),
```

## Explicitly not built

- **PostgreSQL schema, lineage, approval states, object storage.** A separate
  subsystem for tenant theming. `spec_digest()` stays as a function; a manifest
  file waits until something reads it.
- **`fold-tr` / `fold-br`** from the v3 script — near-duplicates of the existing
  `shard-tr` / `shard-br`.
- **`brand.py`, `primary_variables.scss`, the tag palette.**
- **Authored art for all ~60 modules** in this change.

## Testing

In `afenda/tools/tests/test_app_icons.py`:

- **The silhouette equals `body`.** No rendered pixel falls outside it. This is
  the regression test for the bug that motivated the rewrite, and it holds for
  both geometry sources.
- The plane masks sum to the body's coverage at every alpha — the no-halo
  invariant, executed rather than asserted in a docstring.
- The crossing lands *between* the two source colours: for a pair whose shard is
  lighter than its body, the crossing is lighter than the body. This fails if
  anyone reverts to the multiply.
- Every authored SVG parses, carries a `body`, and every non-`body` path lies
  within it.
- Highlight and shadow absent below 48px, present at and above.
- The shadow stays legible over both `brand.PALETTE["paper"]` and the dark
  scheme's background, within a stated alpha band.
- Every colour family has an `_hi` distinguishable from its base.
- A module with no authored art still renders through the fallback.
- `spec_digest` is stable for unchanged input and moves with the renderer version.

Then `corpus diff` to review every distinct rewrite, `corpus golden`, one apply,
`scan_identity`.

## Risks

- **Authoring quality is the deliverable now.** The renderer can only composite
  what is drawn. Five icons that do not hold together as a set will look worse
  than the current uniform duotone, because inconsistency reads as broken where
  uniformity reads as plain. The five ship together or not at all.
- **Mixed set during the transition.** Authored icons sit beside fallback ones in
  the apps menu. Shared palette and material keep them related, but they will not
  be siblings. Accept it, or hold the release until more are drawn.
- **Every rendered byte changes.** The corpus diff will be large; that is why it
  is reviewed on the corpus and applied once.
- **The crossing change affects the ~60 fallback modules**, which were
  art-directed by eye against a multiply. `overlap_report()` already exists; run
  it before and after and inspect the pairs that move most.
