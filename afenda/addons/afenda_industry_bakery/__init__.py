# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
# post_init_hook lives in its own module rather than here so that importing the
# package (which Odoo does at server start, for every installed and uninstalled
# addon alike) stays free of pack-seeding code.
from .hooks import post_init_hook
