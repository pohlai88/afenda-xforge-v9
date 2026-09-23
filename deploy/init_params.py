# Fed on stdin to `odoo-bin shell -c $RC` by afenda-init. The shell exec()s
# stdin with `env` bound to a superuser environment and rolls back when the
# script returns (odoo/cli/shell.py, Shell.shell), so the commit at the end
# is what makes these writes stick.
import os

required = os.environ.get("AFENDA_REQUIRED_MODULES", "").split()
modules = env["ir.module.module"].search([("name", "in", required)])  # noqa: F821
states = {m.name: m.state for m in modules}
missing = [name for name in required if states.get(name) != "installed"]
if missing:
    # `module install` drops names it cannot find on the addons path without
    # an error, so a missing module is only visible here.
    raise SystemExit(f"afenda-init: modules not installed: {', '.join(missing)} ({states})")

public_url = (os.environ.get("PUBLIC_URL") or "http://localhost:8080").rstrip("/")
if not public_url.startswith(("http://", "https://")):
    raise SystemExit(f"afenda-init: PUBLIC_URL must start with http:// or https://, got {public_url!r}")

params = env["ir.config_parameter"].sudo()  # noqa: F821
params.set_param("web.base.url", public_url)
params.set_param("web.base.url.freeze", "True")
# wkhtmltopdf fetches report assets from the server itself, inside the
# container, never through the public URL.
params.set_param("report.url", "http://127.0.0.1:8069")
env.cr.commit()  # noqa: F821
print(f"afenda-init: web.base.url={public_url} (frozen), report.url=http://127.0.0.1:8069")
