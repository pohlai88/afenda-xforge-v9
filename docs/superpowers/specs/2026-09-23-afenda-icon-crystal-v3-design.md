# AFENDA xForge icon system — Crystal Duotone v3

Design for upgrading `afenda/tools/app_icons.py` to the Crystal Duotone v3
look, from the specimen sheet at
`AFENDA_xForge_Crystal_Duotone_V3/afenda_icons_v3/`.

## Objective

The specimen states five design principles and one construction rule:

> Clear silhouette · Controlled translucency · Distinct xForge geometry ·
> Scales 16–128px · Consistent across modules
>
> core semantic shape + xForge angular shard = final icon (max 3 planes)

The current generator already satisfies four of the six:

| Principle | Where it already lives |
|---|---|
| Clear silhouette | `GLYPH_SCALE = 0.84`, `CENTRE_PENALTY = 2.4` |
| Controlled translucency | `controlled_overlap_colour`, `MIN_OVERLAP_LUMINANCE` |
| Max 3 planes | the premultiplied decomposition in `icon_png` — exactly three |
| Consistent across modules | `accent_score` / `choose_accent_shape` |

So this is not a rewrite. Two principles are unmet — **distinct xForge
geometry** and **scales 16–128px** — and the specimen's visual depth comes from
gradients the current renderer does not draw. Three changes close all of it.

## Decisions taken

1. **Palette: v3 colours, icons only.** The vivid v3 values become renderer
   inputs in `app_icons.py`. `brand.py`'s `tags` list and `$o-colors` in
   `primary_variables.scss` are not touched. This follows the existing rule in
   `.claude/odoo-agent-rules.md`: shades that exist only inside a drawn mark are
   renderer inputs, not tokens. The six colours currently shared between
   `app_icons.py` and the tag palette are the reason this must be explicit —
   they read as an icon palette and are not one.
2. **Coverage: keep the scorer.** New geometry enters the candidate pool;
   `accent_score` keeps choosing for all ~60 modules. No hand-authored specs.
3. **Versioning: digest only.** `spec_digest()` as a function. No `schema.sql`,
   no `ui_icon_version`, no object storage, no manifest file.

## Change 1 — gradients per plane

`icon_png` keeps its three masks unchanged. Only the fill changes:

| Plane | Now | After |
|---|---|---|
| `glyph ∖ accent` | flat colour A | ramp A → A_hi |
| `accent ∖ glyph` | flat colour B | ramp B → B_hi |
| `glyph ∩ accent` | `controlled_overlap_colour(A, B)` | ramp of the same pair |

The premultiplied decomposition is preserved exactly. Its docstring invariant —
*the three masks sum to the union's coverage at every alpha, so the seam has no
halo* — is the reason v3's own compositing is **not** ported: v3 paints the
accent at 80% alpha over the base, which is layering rather than partition and
reintroduces the halo at the small sizes these icons actually ship at.

**Implementation.** Build one L-mode diagonal ramp per side and use
`Image.composite(hi_image, lo_image, ramp)`, which is the per-pixel lerp.
v3's `linear_gradient` uses a nested Python loop — about 1M iterations per plane
per icon at the supersampled size — and is not worth porting.

## Change 2 — one new shape

Add to `ACCENT_SHAPES`:

```python
"band-diag": ("polygon", ((-10, 78), (78, -10), (106, 18), (18, 106))),
```

The existing 13 shapes are discs, dots, wedges, bars and corner shards; none is
a diagonal band. The band is the X-derived geometry the specimen calls the
"xForge angular shard", so it is the one shape that is actually missing. The
100-unit coordinate space and `("polygon", …)` form already match, so
`accent_mask` needs no change.

`fold-tr` and `fold-br` from the v3 script are deliberately not adopted: they
are near-duplicates of the existing `shard-tr` / `shard-br`.

## Change 3 — one size threshold

Gradients below 32px cost sharpness and show nothing. One threshold, not v3's
three tiers:

- `min(width, height) < 32` — flat fill, as today.
- otherwise — gradients.

This is what makes "scales 16–128px" true rather than asserted.

## Palette

v3 names five families. The repo uses thirteen. Named values are adopted
verbatim; the rest derive their `_hi` stop from a single documented lightening
rule rather than eight hand-tuned constants nobody can predict.

Adopted from v3: `LEDGER #1E3A8A` (unchanged, still primary),
`SIGNAL_BLUE #2563EB`, `TEAL #10B981` with `TEAL_DARK #0F766E`,
`PLUM #7C3A8A`, `MULBERRY #BE2F7F`, `OCHRE #C97917`, `MUSTARD #D49A23`.

Derived: `MOSS`, `BRICK`, `CLAY`, `VIOLET`, `GREY`, `INDIGO`, `SLATE`.

The derivation rule, in HLS via the stdlib `colorsys`, chosen because it moves in
the same direction as every pair v3 hand-picked (lighter and slightly more
saturated, not washed toward white):

```python
def lighten(base):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb(base)))
    return colorsys.hls_to_rgb(h, min(1.0, l + 0.14), min(1.0, s * 1.15))
```

A family whose `_hi` would clip at white keeps its hand-picked value instead;
`GREY` is the expected case, and the test below is what catches any other.

## Explicitly not built

- **Drop shadow.** Not among the five principles, and wrong here: these render
  on unknown backgrounds in the apps menu, and a baked shadow is incorrect
  against the dark scheme this product ships.
- **Edge highlight.** Not among the five principles. v3's own code disables it
  below 48px, so it would appear at two of the five target sizes.
- **`fold-tr` / `fold-br`.** Near-duplicates of shapes that exist.
- **Manifest file, PostgreSQL schema, lineage, approval states.** Nothing reads
  them. If tenant theming becomes real, it gets its own spec.
- **`brand.py`, `primary_variables.scss`, the tag palette.** Out of scope by
  decision 1.

## Testing

Extending `afenda/tools/tests/test_app_icons.py`:

- The no-halo invariant becomes an executed regression test rather than a
  docstring claim: for each plane decomposition, the three masks sum to the
  union's coverage at every alpha.
- Icon palette and tag palette are disjoint, so a later edit cannot silently
  re-couple them.
- Below the threshold the render is flat; at and above it, it is not.
- Every colour family has an `_hi` stop distinguishable from its base.
- `band-diag` is reachable by `choose_accent_shape` for at least one module.
- `spec_digest` is stable for an unchanged design and changes when the renderer
  version does.

Sequence per the repo's rules: `corpus diff` to review every distinct rewrite,
then `corpus golden`, then one apply, then `scan_identity`.

## Risks

- **The scorer may not pick `band-diag` anywhere.** Its penalties were tuned
  against the existing vocabulary. If the band scores badly everywhere, the
  specimen's signature geometry never appears and the shape needs either a
  tuning pass or explicit assignment on a few modules. The test above is what
  surfaces this rather than letting it pass silently.
- **Gradients change every rendered byte.** The corpus diff will be large. That
  is expected and is why it is reviewed on the corpus and applied once.
