# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA Documentation",
    "summary": "Generated API reference and guides served at /docs",
    # 19.0.1.0.1: the OpenAPI document's Error schema and every operation's
    # 4XX/5XX responses now describe afenda_runtime's Problem Details
    # contract (components.responses.Problem); info.version reads
    # api_version.API_VERSION instead of a bare "2"; /docs/api/errors lists
    # every code. No migration: the document is regenerated, not stored.
    "version": "19.0.1.0.1",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # `rpc` owns the /json/2 route this documents; `afenda_brand` owns BRAND;
    # `afenda_runtime` owns the Problem Details vocabulary (problems.py) this
    # module's Error schema and /docs/api/errors read.
    "depends": ["web", "rpc", "afenda_brand", "afenda_runtime"],
    "data": ["views/landing.xml", "views/guides.xml", "views/api.xml", "views/errors.xml"],
}
