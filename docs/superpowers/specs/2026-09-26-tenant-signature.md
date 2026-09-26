# The tenant signature

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

## No season layer

A season layer drawn in CSS around the bear (petals, sun and butterflies, maple leaves,
snowflakes) was built and shown on 2026-09-26; the owner rejected it the same day ("reset to
original without your added CSS"). The auth page is the design of c5545d38f, nothing added.

## Acceptance

- The signature test passes. `crystal_bear.svg` and `auth_bear.xml` are unchanged from
  c5545d38f.
- The auth page's view, stylesheets and manifest assets equal c5545d38f; only the module version
  differs (19.0.1.0.9, so a redeploy reloads them over 19.0.1.0.8).
