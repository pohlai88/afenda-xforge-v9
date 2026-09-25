# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA Documentation",
    "summary": "Generated API reference and guides served at /docs",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # `rpc` owns the /json/2 route this documents; `afenda_brand` owns BRAND.
    "depends": ["web", "rpc", "afenda_brand"],
    "data": ["views/landing.xml", "views/guides.xml", "views/api.xml"],
}
