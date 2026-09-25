import json

from odoo import api, models, tools

from ..openapi import build_document


class AfendaApiDocs(models.AbstractModel):
    """Holds the per-caller cache of the generated OpenAPI document.

    An AbstractModel only because `tools.ormcache` stores its entries in the
    registry of the model it decorates (odoo/tools/cache.py, `model.pool`);
    it has no table and no records, hence no access rule.
    """
    _name = "afenda.api.docs"
    _description = "API documentation generator"

    @api.model
    def _openapi_json(self, app=None):
        """The serialised document for the current user, built at most once per key.

        The key is everything the document depends on:

        * `app` and `env.lang` (labels, help and selection labels are
          translated by fields_get);
        * `env.su`, which bypasses field groups and ACLs;
        * the caller's groups, sorted (`all_group_ids`, res_users.py:258).
          The document reads access only through `has_access("read")` on an
          empty recordset - ACL only, since record rules apply only
          `if any(self._ids)` (odoo/orm/models.py:4157) - and through
          `fields_get`, i.e. `_has_field_access`. Every override of the
          latter in this tree reduces to groups or su for an empty model:
          addons/hr/models/hr_employee.py:376 (su or hr.group_hr_user),
          addons/project/models/project_task.py:1061 (su or portal, a
          group), odoo/addons/base/models/res_users.py:571 (adds
          `self._origin == self.env.user`, never true for an empty
          recordset);
        * the current company, and the allowed companies: `fields_get` can
          depend on records the caller's record rules select, and those
          rules read `company_ids` - account.analytic.line renames its plan
          columns after the plans the caller can search
          (addons/analytic/models/analytic_line.py:108-118, rule in
          addons/analytic/security/analytic_security.xml:9).

        The registry version needs no key: every Registry starts with fresh
        caches (odoo/orm/registry.py:243) and load()/setup_models() clear them
        on each module install, upgrade or model setup (registry.py:390,
        :427); ir.model.fields creation and ACL changes clear the 'stable'
        cache, which cascades to 'default' (odoo/addons/base/models/
        ir_model.py:1038, :2200; registry.py:68). A string is cached, not the
        dict, so no caller can mutate a shared entry.
        """
        return self._openapi_json_cached(
            app or None,
            self.env.lang,
            self.env.su,
            tuple(sorted(self.env.user.all_group_ids.ids)),
            self.env.company.id,
            tuple(sorted(self.env.companies.ids)),
        )

    @tools.ormcache("app", "lang", "su", "group_ids", "company_id", "company_ids")
    def _openapi_json_cached(self, app, lang, su, group_ids, company_id, company_ids):
        return json.dumps(build_document(self.env, app=app))
