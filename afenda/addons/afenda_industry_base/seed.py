# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Company-scoped seeding for AFENDA industry packs.

A pack's company-less content (categories, products, bills of material) belongs
in `data/` XML. Its company-scoped content does not: `pos.config.company_id` is
`required=True, default=lambda self: self.env.company`
(addons/point_of_sale/models/pos_config.py:143) and `picking_type_id` is required
with a domain on `warehouse_id.company_id` (:76-82), so an XML record silently
resolves against whichever company happens to load the file. Correct for a
single-company demo, wrong for a multi-tenant product.

Those records are therefore created here, at install, against `env.company` --
and always through `_load_records` (odoo/orm/models.py:5121), which assigns an
XMLID. That is not decoration: uninstall deletes the records *referenced by
ir.model.data entries* (odoo/addons/base/models/ir_model.py:2464-2471), so a
hook that calls `create()` directly leaves orphan POS configs and reordering
rules in the tenant's database forever.

`_load_records` also makes this idempotent by construction: an XMLID that
already exists is routed to the update set rather than created again
(models.py:5121-5165), so no separate "already seeded" guard is needed.
"""


def load_company_records(env, module, model_name, records, noupdate=True):
    """Create or update company-scoped records, each owned by ``module``.

    :param env: environment; records are created against ``env.company``
    :param str module: the pack's technical name, e.g. ``afenda_industry_bakery``
    :param str model_name: the model to seed, e.g. ``pos.config``
    :param records: list of ``(suffix, values)``; the XMLID is ``module.suffix``
    :param bool noupdate: flag stored on the XMLID; ``True`` means a module
        upgrade will not overwrite what the tenant has since edited
    :return: the records, in the order given
    """
    model = env[model_name].sudo()
    # Not every seeded model is company-scoped (`pos.category` is not), so only
    # pin the company where the field actually exists.
    pin_company = "company_id" in model._fields
    data_list = [
        {
            "xml_id": f"{module}.{suffix}",
            "noupdate": noupdate,
            "values": dict(values, company_id=env.company.id) if pin_company else dict(values),
        }
        for suffix, values in records
    ]
    return model._load_records(data_list)
