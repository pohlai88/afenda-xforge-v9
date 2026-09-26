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

## Acceptance

- Every auth page (`/web/login`, `/web/signup?token`, `/web/reset_password` in all its states,
  `/web/login/totp`, `/request-access`) shows the stage: panel, luminous bear, season layer.
- The loop starts on today's season; under reduced motion only today's season shows, still.
- Layout: the hero's box matches `main` within 0.5 px at 1440, 1366, 1280, 1024, 390, 360 px.
- At rest: no layout per frame, no running CSS transition; frame p95 ≤ 20 ms.
- Seen rendered at a wide and a narrow viewport, all four seasons, before merge; the owner sees
  the stills and a full-loop video.
