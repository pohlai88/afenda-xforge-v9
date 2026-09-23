from urllib.parse import quote

from odoo import http
from odoo.http import request
from odoo.tools import email_normalize, single_email_re

SUBJECT = quote("Access request — AFENDA xForge")


def _mailto_address(raw):
    """The company email as one bare address safe to put in a mailto: URL, or None.

    `email_normalize` alone is not a validity check here
    (odoo/tools/mail.py:812-845): it pulls 'x@y.z' out of
    "not an email\r\nBcc: x@y.z" (the "Bcc:" parses as an RFC 5322 group),
    returns '@x.y' for "a@b.c?cc=evil@x.y", and returns "a?bcc=evil@x.y"
    unchanged, which in a mailto: URL would add a Bcc header. So a value with a
    control character is refused outright, and the normalized address must match
    `single_email_re` (odoo/tools/mail.py:722), whose local part admits no `?`,
    `&` or `=`.
    """
    if not raw or not raw.isprintable():
        return None
    email = email_normalize(raw)
    return email if email and single_email_re.match(email) else None


class RequestAccess(http.Controller):
    @http.route("/request-access", type="http", auth="public", methods=["GET"], sitemap=False)
    def request_access(self):
        email = _mailto_address(request.env.company.sudo().email)
        if email:
            # `local=False` keeps the mailto: scheme: with `local=True` the
            # scheme and host are stripped (odoo/http.py:2104-2106). The
            # redirect then goes through werkzeug.utils.redirect
            # (odoo/addons/base/models/ir_http.py:378-379), which does not
            # restrict the scheme. `quote` also turns a `%` or `+` from the
            # local part into an escape, so nothing in the address can read
            # as a mailto: header.
            return request.redirect(f"mailto:{quote(email, safe='@')}?subject={SUBJECT}", code=303, local=False)
        return request.render("afenda_runtime.request_access_by_invitation")
