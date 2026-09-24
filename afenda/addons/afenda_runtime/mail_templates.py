"""Remove Odoo's own marketing from the auth_signup invitation mails.

The internal-user invitation (addons/auth_signup/data/mail_template_data.xml:53-56)
carries two paragraphs this product cannot stand behind: a "12+ million users"
claim that is Odoo's, and a link to a tour page that returns 404. Every
translation carries them too (e.g. addons/auth_signup/i18n/fr.po:632-640). Only
that template has them; the other auth_signup templates are listed so a database
whose copies drifted is covered by the same pass.

The records are noupdate (mail_template_data.xml:3), so a data override is
skipped on upgrade. One function serves every path: `post_init_hook` for a fresh
install, migrations/19.0.1.2.0/post-migrate.py for a database that crosses that
version, and the `_load_module_terms` override in models/ir_module.py for a
language whose translations load later.
"""
import json
import re

from odoo.tools import SQL

TEMPLATES = (
    "auth_signup.set_password_email",
    "auth_signup.portal_set_password_email",
    "auth_signup.mail_template_user_signup_account_created",
    "auth_signup.mail_template_data_unregistered_users",
)

_BREAK = r"<br\s*/?>\s*<br\s*/?>"
# Matched by structure, not wording, so it holds in every language, and never
# by the colour attribute, which a noupdate record keeps from its install.
# Upstream the layout is, in every translation:
#   ...sign-in line</b><br/><br/>  CLAIM  <br/><br/>  ...<a href=".../page/tour...">...</a>...  <br/><br/>  sign-off
# The tour paragraph is the one whose link goes to /page/tour; the claim is the
# single text run between the two breaks right before it. Every `[^<]*` is one
# text run, so the match can only consume those two paragraphs, their breaks
# and the tour link: it cannot reach the invitation button, the sign-off or
# the footer, which all sit behind other tags. The claim is optional so a body
# already missing it still loses the dead link. The break that closes the
# sign-in line is kept, so the sign-off follows it exactly as the tour did.
_MARKETING = re.compile(
    rf"(?P<kept>{_BREAK})"
    rf"(?:[^<]*{_BREAK})?"
    rf"[^<]*<a\b[^>]*/page/tour[^>]*>[^<]*</a>[^<]*{_BREAK}"
)


def remove_marketing(html):
    return _MARKETING.sub(r"\g<kept>", html)


def strip_invitation_marketing(env):
    """Remove the two paragraphs from every stored language of each template.

    Returns the templates it changed; running it again changes nothing.

    The write is SQL on the jsonb column rather than an ORM write per
    `with_context(lang=...)`: the ORM only reaches active languages
    (odoo/orm/environments.py:300-302), while the column can also hold values
    for languages since deactivated, and an ORM write re-sanitizes the whole body
    (odoo/orm/fields_textual.py:631-695). The SQL merges only the language values
    that changed, and the cache is invalidated after it.
    """
    changed = env["mail.template"]
    for xmlid in TEMPLATES:
        template = env.ref(xmlid, raise_if_not_found=False)
        if not template:
            continue
        template.flush_recordset(["body_html"])
        env.cr.execute(SQL(
            "SELECT body_html FROM mail_template WHERE id = %s", template.id,
        ))
        stored = env.cr.fetchone()[0] or {}
        updates = {
            lang: new
            for lang, old in stored.items()
            if old and (new := remove_marketing(old)) != old
        }
        if not updates:
            continue
        env.cr.execute(SQL(
            "UPDATE mail_template SET body_html = body_html || %s::jsonb WHERE id = %s",
            json.dumps(updates), template.id,
        ))
        template.invalidate_recordset(["body_html"])
        changed |= template
    return changed
