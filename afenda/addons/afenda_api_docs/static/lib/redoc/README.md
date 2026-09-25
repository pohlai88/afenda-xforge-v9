# Redoc (vendored)

The API reference page `/docs/api` renders with Redoc's standalone bundle,
served from this directory so the page works offline and same-origin. No
template may reference a CDN copy.

- Package: `redoc` on npm, version **2.5.4** (MIT, Copyright Rebilly, Inc.)
- Source: https://registry.npmjs.org/redoc/-/redoc-2.5.4.tgz
- Tarball integrity (npm `dist.integrity`, verified on download):
  `sha512-M6jWhG1qoBnH6TFmzJnstyCZ87HmOY/UzDm78mHiYihEdlV/YcS9ogOo1NlElnJMeLsyxHFe2yFc4sNjHTrABQ==`
- Files, copied unmodified from the tarball:
  - `package/bundles/redoc.standalone.js` -> `redoc.standalone.js`
  - `package/bundles/redoc.standalone.js.LICENSE.txt` -> `redoc.standalone.js.LICENSE.txt`
    (licenses of the libraries bundled inside it; the bundle's first line points here)
  - `package/LICENSE` -> `LICENSE`

sha256: dcaf76612bc4a3fbcc923a8966dee2f6146a5f32e5ce1b6f02dd60cbbf89500b  redoc.standalone.js

`tests/test_api_routes.py` checks the served file against the sha256 line
above, so a changed bundle fails until this record is updated with it.

The bundle unconditionally renders an "API docs by Redocly" link whose logo
is fetched from cdn.redoc.ly. The file is not patched for that; instead
`controllers/api.py` sends `Content-Security-Policy: img-src 'self' data:`
on `/docs/api`, so the browser refuses the fetch, and `views/api.xml` hides
the link.

To upgrade: download the new tarball, check its integrity against
`npm view redoc@<version> dist.integrity`, copy the three files, and update
the version, integrity and sha256 lines here.
