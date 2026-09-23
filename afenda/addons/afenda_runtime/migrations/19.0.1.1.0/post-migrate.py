from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Close self-signup on a database that installed this module before 19.0.1.1.0.

    Fresh installs get `b2b` from data/ir_config_parameter.xml. That `<function>`
    sits in a noupdate block, so it never runs on update
    (odoo/tools/convert.py:272-274); an existing database gets the value here,
    once, on the upgrade that crosses this version
    (odoo/modules/migration.py:209). A tenant who reopens signup afterwards
    keeps that choice.

    Through the ORM rather than a raw UPDATE: `_get_param` is ormcached
    (odoo/addons/base/models/ir_config_parameter.py:72-73) and only `create` /
    `write` clear that cache (:107, :115), so raw SQL could leave this process
    serving the old scope. `set_param` also creates the key if it is missing.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.config_parameter"].set_param("auth_signup.invitation_scope", "b2b")
