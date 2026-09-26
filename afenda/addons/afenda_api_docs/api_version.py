# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""The AFENDA JSON API's own version, independent of Odoo's.

``openapi.py`` reads ``API_VERSION`` for ``info.version``: the document
versions the AFENDA-owned contract (this file, the ``Error`` schema, the
``Problem`` response), not the Odoo release the server happens to run, and
not a commit id or a build timestamp (AFD-ARCH-CORR-0004) - either of those
would make every committed asset differ from the last regeneration for no
contract reason. Bump this by hand when the contract changes.
"""

API_VERSION = "1.0.0"
