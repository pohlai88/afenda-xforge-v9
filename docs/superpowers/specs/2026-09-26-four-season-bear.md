# The four-season crystal bear

Status: approved by the owner on 2026-09-26 (four decisions below, given in the session that
produced this spec). Plan: `docs/superpowers/plans/2026-09-26-four-season-bear.md`.

## Owner decisions (binding)

1. **Continuous loop.** The auth-page bear cycles spring → summer → autumn → winter by itself,
   8 s per season (6 s hold + 2 s cross-fade), a 32 s loop, each season with its effect:
   spring petals, summer sun glints, autumn falling leaves, winter snow. The motion is living and
   continuous, not a still picture.
2. **Deep solid panel.** An opaque deep-forest ink panel behind the bear only; the crystal bear
   becomes luminous, its colours shifting with the season, in strong contrast to the panel. The
   sign-in form stays on the light paper.
3. **Reduced motion.** With `prefers-reduced-motion: reduce`, nothing moves and the bear shows
   today's real-world season, fully coloured.
4. **No on-page pause control.** WCAG 2.2.2 (Pause, Stop, Hide, Level A) asks for one for
   auto-playing motion longer than 5 s beside other content; the owner declined it. The
   reduced-motion setting is the only way to stop the loop.

## Rulings this supersedes (named, deliberate)

- **"No plate under the art"** (the poster rule in `login.scss` and
  `test_the_auth_page_is_art_left_and_card_right`): the art column paints `--bear-ink`, flat
  (no gradient, radius, shadow or border), only when the bear renders. A named deviation from
  visual-QA row H4's spirit; its letter (no shadow, radius, gradient, glass) still holds.
- **"Motion is state reactions only; nothing animates at rest"** (`auth_bear.css` header,
  `test_the_bear_stylesheet_is_scoped_and_invents_no_colour`): one exception, the four-season
  loop, confined to `.o_afenda_auth_stage` and to the generated `auth_bear_seasons.css`. The
  hand-written stylesheet keeps the old contract. The superdesign skill's "no decorative
  motion" rule names this single exception.

## Design constraints found while planning

- **Contrast window.** The cream face mask sits on facet f1, so "lighter facets" everywhere
  would erase the face. Face-side roles (base, f1, s1, s2, headlight) sit at scale step 600
  (headlight 500, drawn at 0.34 opacity); lit-side roles (f2, f3, sheen, rim, haze) at steps
  50–400. Target ≥ 3:1: every body role and particle against `--bear-ink`, face-side roles
  against the cream mark. The bear is `aria-hidden` decoration, so WCAG 1.4.11 does not formally
  apply; 3:1 is a design target, enforced by the generator's tests.
- **Particles live in a sibling SVG** over the bear: animating inside the bear SVG would repaint
  its 16 px Gaussian blur every frame. The bear repaints only during the four 2 s cross-fades.
- **The body no longer shows `#1C573E`** in any season; the tenant green survives in the
  branches on the cream bush and in the standalone `crystal_bear.svg`, which is unchanged.
- **Today's season is the server's UTC date**, northern-hemisphere meteorological seasons
  (Dec–Feb winter, Mar–May spring, Jun–Aug summer, Sep–Nov autumn), computed in QWeb
  (`datetime` is a default rendering value, `odoo/addons/base/models/ir_qweb.py:1317`). No
  JavaScript, no hemisphere or timezone setting. At a season boundary it can be hours off.
- **Per-page skins** (dawn, tide, night, moss) shrink to the form-side mood aura; the seasons own
  the bear's palette. The eight form-state reactions keep working.

## Owner design guidance adopted (2026-09-26, second pass)

- **One bear, four moods.** Silhouette, face and geometry never change; only facet colour,
  highlights, rim, haze and particles do. Personalities: spring rose, soft pink and fresh green;
  summer emerald and warm gold; autumn rust, amber and copper; winter blue-grey, silver and icy
  white. The season table in the plan follows these, inside the contrast window.
- **Particles support the bear** (roughly: bear 100 %, season colour 60 %, rim and glow 35 %,
  particles 20 %): spring 9 petals, summer 6 glints, autumn 8 leaves, winter 16 flakes (raised after the first
  render; see the rulings below). Glints and
  the gleam never sit over the face; nothing ever enters the form column.
- **The gleam** is a slow, very low-opacity diagonal reflection, once per season.
- **Form states stay subtle and keep the season**: focus changes sheen, rim and facet brightness
  by about 5–8 %; an error adds a warm rim and one settle, never recolouring the bear; success is
  a short soft glow.
- **This is a brand season cycle, not a climate.** The tenant is in Malaysia, where four
  meteorological seasons do not occur; the northern-hemisphere months only order the cycle and
  pick the reduced-motion still. A hemisphere- or locale-aware choice is a possible later
  change, not part of this work.
- **Pause-ready.** The loop lives on one element (`.o_afenda_auth_stage`), so a later on-page
  pause control is one `:has(...)` rule that sets `animation-play-state: paused` there. No
  redesign is needed if the WCAG 2.2.2 decision is revisited.
- **Targets:** 60 fps on desktop, 30+ fps on a low-power phone; nothing animates `filter`,
  `box-shadow` or a blur per frame.
- **Not adopted:** "animating CSS custom properties is cheap". Registered custom properties
  animate on the main thread and repaint what they colour, which is why the colour loop is
  confined to the stage and the bear repaints only during the four cross-fades.
- **Composition re-framed (owner, 2026-09-26).** Desktop ≥ 1200 px: the ink column is 40–45 % of
  the width; tablet 768–1199 px: 35–40 %; phone: a 180–250 px dark banner above the form. Inside
  the column the bear is about 70–80 % of its width and 75–85 % of its height, with an 8–10 %
  top safe zone, a left offset of −4 % to +2 % and a bottom offset of −3 % to 0; the face is
  always fully visible. This replaces the earlier "hero box unchanged" acceptance.
  The bear's aspect makes the width and height targets exclusive in a landscape column; the
  rulings below settle it height-led.

## Rulings after the first render (2026-09-26)

The first render, reviewed at six viewports, and Codex's review on PR #8 found the bear too
small (58 % of the column's height at 1440×900, 44 % at 1024×768, with 44 % of the panel empty
above it), the particles too small to read, a muddy spring (rose beside moss on the face side)
and a violet cast in autumn and winter (the dusk hue). The rulings:

- **Height-led bear.** An art column narrower than the bear's 800:887 aspect, which is every
  landscape viewport (1440×900 at 45 % is 0.72, 1024×768 at 40 % is 0.53), cannot hold the bear
  at 70–80 % of its width and 75–85 % of its height at once. The bear takes 76 % of the column's
  height, capped at 92 % of its width; the face stays fully visible under the −1 % bleed.
  The columns take the top of the owner's ranges: 45 % on desktop, 40 % on tablet.
- **The season layer fills the panel.** It extends one bear height above the bear and 30 % to its
  right (viewBox `0 -887 1040 1774`), so whatever panel the bear leaves is weather, not empty ink.
  The art column's `overflow: hidden` is the only clip; nothing reaches the form.
- **Particles** are about twice the first size, and 1.5× as many for the larger area: spring 14
  petals, summer 6 glints (still inside the bear), autumn 12 leaves, winter 24 flakes. The on-screen
  fall speed is unchanged.
- **Palette.** Spring's face side is all rose; green only on the lit side. Autumn is rust, amber
  and copper, no dusk. Winter uses a new low-chroma blue-grey `frost` hue (230°, peak chroma
  0.06), no dusk. The contrast window and its tests are unchanged.

## Acceptance

- Every auth page (`/web/login`, `/web/signup?token`, `/web/reset_password` in all its states,
  `/web/login/totp`, `/request-access`) shows the stage: panel, luminous bear, season layer.
- The loop starts on today's season; under reduced motion only today's season shows, still.
- Layout: the re-framed proportions, as settled by the rulings after the first render, hold at 1440×900, 1366×768, 1280×633, 1024×768,
  390×844 and 360×640; the face is fully visible at each; no horizontal scroll at 360 px; no
  particle enters the form column.
- At rest: no layout per frame, no running CSS transition; frame p95 ≤ 20 ms.
- Seen rendered at a wide and a narrow viewport, all four seasons, before merge; the owner sees
  the stills and a full-loop video.
