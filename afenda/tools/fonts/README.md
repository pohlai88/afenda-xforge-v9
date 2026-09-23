# Renderer input fonts

Not addon assets. Odoo serves everything under `<addon>/static/` over HTTP
regardless of the manifest, so a typeface placed there is reachable at a URL and
ships in every deployment. These two faces are read by `brand_images.py` at
render time to draw the wordmark in the logo lockup, and the lockup it produces
carries the wordmark as outlines — so nothing downstream needs the font either.
Keeping them here is what makes "Geist never reaches the product" structural
rather than a convention.

The product's own typefaces are a different thing and stay where they are
served from: `afenda/addons/afenda_brand/static/fonts/`.

| File | Licence |
|---|---|
| `Geist-Medium.ttf`, `Geist-Semibold.ttf` | SIL OFL 1.1, see `OFL-Geist.txt` |
