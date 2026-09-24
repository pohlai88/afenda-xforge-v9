# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
# post_init_hook is defined in hooks.py rather than inline here, so that the
# seeding tables and the source citations behind them sit next to the code they
# justify instead of in the package's entry point. Odoo resolves the name
# against this package (odoo/modules/loading.py:239-243), so it has to be
# re-exported here.
from .hooks import post_init_hook
