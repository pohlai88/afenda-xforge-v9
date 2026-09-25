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


def load_company_records(env, module, model_name, records):
    """Create or update company-scoped records, each owned by ``module``.

    Every XMLID is stored ``noupdate=True``, and that is not a choice left to
    the caller. A seeded record is never reloaded on ``-u``: the hook that made
    it runs only at install (odoo/modules/loading.py:239-243), so its XMLID is
    never in ``registry.loaded_xmlids``, and at the end of every update
    ``_process_end`` deletes each of the module's *non*-noupdate XMLIDs missing
    from that set, record included (odoo/addons/base/models/ir_model.py:2655-2662).
    ``noupdate=False`` would therefore have the next upgrade delete the tenant's
    POS counter and reordering rules.

    The flag does not protect *this* call, though: ``_load_records`` is invoked
    with its default ``update=False``, so ``not (update and d_noupdate)`` is
    true (odoo/orm/models.py:5178) and a second call rewrites the record.
    Harmless on the intended path, a ``post_init_hook``, which fires once.

    :param env: environment; records are created against ``env.company``
    :param str module: the pack's technical name, e.g. ``afenda_industry_bakery``
    :param str model_name: the model to seed, e.g. ``pos.config``
    :param records: list of ``(suffix, values)``; the XMLID is ``module.suffix``
    :return: the records, in the order given
    """
    # No .sudo() here, deliberately. Both intended callers already run as
    # superuser -- a post_init_hook's env, and TransactionCase.env -- so sudo()
    # would buy nothing, while leaving any future caller (a controller, a wizard)
    # able to write arbitrary `values` with record rules bypassed.
    # .claude/odoo-agent-rules.md:37-40 requires a stated reason for sudo(), and
    # "it was superuser anyway" is a reason to drop it, not to keep it. XMLID
    # assignment is unaffected: _load_records sudoes its own ir.model.data access
    # (odoo/orm/models.py:5132).
    model = env[model_name]
    # Not every seeded model is company-scoped (`pos.category` is not), so only
    # pin the company where the field actually exists.
    pin_company = "company_id" in model._fields
    data_list = [
        {
            "xml_id": f"{module}.{suffix}",
            "noupdate": True,
            "values": dict(values, company_id=env.company.id) if pin_company else dict(values),
        }
        for suffix, values in records
    ]
    return model._load_records(data_list)
