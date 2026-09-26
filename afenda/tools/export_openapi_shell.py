# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Write the committed OpenAPI asset areas, run through `odoo-bin shell`.

Not a module of its own: `odoo-bin shell -c ... -d ... < this file` execs it
with `env` already bound (odoo/cli/shell.py, `Shell.shell` -> `self.console`
-> `exec(sys.stdin.read(), local_vars)`), superuser, on that database. It
switches to the exact caller identity the asset contract requires
(AFD-ARCH-CORR-0006) before building anything, since the shell's own `env`
is always `su=True` (uid == SUPERUSER_ID forces it, odoo/orm/environments.py).

Reads `OUT_DIR` and `ADDONS_ROOT` from the environment; prints exactly
`afenda-openapi: wrote <N> documents` on success, one line, nothing else, so
a caller (a Make target, a CI step) can match it verbatim.
"""
import os

from odoo.addons.afenda_api_docs.assets import write_assets

out_dir = os.environ["OUT_DIR"]
addons_root = os.environ["ADDONS_ROOT"]

admin = env.ref("base.user_admin")  # noqa: F821 - `env` is bound by `odoo-bin shell`
build_env = env(user=admin.id, su=False, context={"lang": "en_US"})  # noqa: F821

written = write_assets(build_env, out_dir, addons_root)
print(f"afenda-openapi: wrote {written} documents")
