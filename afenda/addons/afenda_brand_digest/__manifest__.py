# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA xForge Branding: Digest",
    "summary": "AFENDA colors in the periodic digest email",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://afenda.app",
    "license": "LGPL-3",
    "application": False,
    # `digest` is optional, so the digest layout cannot be touched from
    # afenda_brand itself; this bridge installs itself the moment both sides
    # are present.
    "auto_install": True,
    "depends": ["afenda_brand", "digest"],
    "data": [
        "views/digest_templates.xml",
    ],
}
