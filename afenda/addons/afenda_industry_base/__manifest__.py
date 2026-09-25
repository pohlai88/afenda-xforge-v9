# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA Industry Packs",
    "summary": "The contract every AFENDA industry preset pack follows",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # No security/ directory on purpose: this module declares no models, and a
    # module that adds no models adds no ir.model.access.csv lines. The absence
    # is deliberate, not forgotten.
    "depends": ["base"],
}
