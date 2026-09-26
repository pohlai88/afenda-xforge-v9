import json
import re
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_api_docs.api_version import API_VERSION
from odoo.addons.afenda_api_docs.openapi import (
    build_document,
    model_operations,
    model_schema,
    models_for_app,
    path_item,
)
from odoo.addons.afenda_runtime.problems import PROBLEM_CODES

CORE = ("res.partner", "res.users", "product.template",
        "sale.order", "account.move", "stock.picking")


@tagged("post_install", "-at_install")
class TestModelSchema(TransactionCase):
    def test_scalar_field_types_map_to_json_schema(self):
        schema = model_schema(self.env["res.partner"])
        self.assertEqual(schema["properties"]["name"]["type"], "string")
        self.assertEqual(schema["properties"]["active"]["type"], "boolean")

    def test_many2one_is_an_integer_id(self):
        schema = model_schema(self.env["res.partner"])
        self.assertEqual(schema["properties"]["country_id"]["type"], "integer")

    def test_x2many_is_an_array_of_ids(self):
        schema = model_schema(self.env["res.partner"])
        child = schema["properties"]["child_ids"]
        self.assertEqual(child["type"], "array")
        self.assertEqual(child["items"]["type"], "integer")

    def test_selection_keys_are_wire_values_and_are_not_aliased(self):
        schema = model_schema(self.env["res.users"])
        state = schema["properties"]["odoobot_state"]
        # The field name and every enum key must survive verbatim.
        self.assertIn("odoobot_state", schema["properties"])
        self.assertTrue(state["enum"])
        for key in state["enum"]:
            self.assertNotIn("AFENDA", key)

    def test_selection_labels_are_prose_and_are_aliased(self):
        schema = model_schema(self.env["res.users"])
        labels = " ".join(schema["properties"]["odoobot_state"]["x-enum-labels"])
        self.assertNotIn("Odoo", labels)

    def test_every_odoo_field_type_is_mapped(self):
        # The fallback silently documents an unknown type as a string, which is
        # a wrong contract rather than a missing one. If Odoo gains a field type,
        # fail here rather than mis-document it. Every model in the registry,
        # not one: res.partner alone never declares reference, json or
        # properties_definition fields.
        from odoo.addons.afenda_api_docs.openapi import _TYPE_MAP
        declared = {
            field.type
            for name in self.env.registry
            for field in self.env[name]._fields.values()
        }
        self.assertTrue(declared)
        self.assertEqual(declared - set(_TYPE_MAP), set())

    def test_reference_pattern_accepts_model_names_with_digits(self):
        # Model names carry digits (l10n_*), and a reference is "model,id".
        from odoo.addons.afenda_api_docs.openapi import _TYPE_MAP
        pattern = re.compile(_TYPE_MAP["reference"]["pattern"])
        for value in ("res.partner,5", "l10n_in.gst.report,12", "l10n_be_hr.x2,1"):
            self.assertTrue(pattern.match(value), value)
        for value in ("res.partner", "res.partner,", ",5"):
            self.assertFalse(pattern.match(value), value)

    def test_group_restricted_fields_follow_the_caller(self):
        # activity_ids is restricted to base.group_user (mail.activity.mixin);
        # a portal user must not see it documented, an administrator must.
        field = self.env["res.partner"]._fields["activity_ids"]
        self.assertEqual(field.groups, "base.group_user")
        portal = self.env["res.users"].create({
            "name": "Docs field portal",
            "login": "docs_field_portal",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        admin = self.env.ref("base.user_admin")
        self.assertIn(
            "activity_ids",
            model_schema(self.env["res.partner"].with_user(admin))["properties"],
        )
        self.assertNotIn(
            "activity_ids",
            model_schema(self.env["res.partner"].with_user(portal))["properties"],
        )

    def test_help_text_is_aliased(self):
        schema = model_schema(self.env["res.partner"])
        for prop in schema["properties"].values():
            self.assertNotIn("Odoo", prop.get("description", ""))
            self.assertNotIn("Odoo", prop["title"])


def _body(item):
    return item["post"]["requestBody"]["content"]["application/json"]["schema"]


@tagged("post_install", "-at_install")
class TestOperations(TransactionCase):
    def test_public_orm_methods_are_documented(self):
        ops = model_operations(self.env["res.partner"])
        for expected in ("search", "read", "create", "write", "unlink"):
            self.assertIn(expected, ops)

    def test_methods_the_dispatcher_refuses_are_not_documented(self):
        # Both are defined for res.partner itself, not on `base`, so the
        # generic-name filter cannot be what drops them: they reach
        # get_public_method, which must refuse them - an underscore method
        # (odoo/addons/base/models/res_partner.py:378) and an @api.private
        # one (addons/auth_signup/models/res_partner.py:90-91).
        model = self.env["res.partner"]
        generic = set(dir(type(self.env["base"])))
        ops = model_operations(model)
        for name in ("_get_complete_name", "signup_get_auth_param"):
            self.assertTrue(callable(getattr(type(model), name, None)), name)
            self.assertNotIn(name, generic, name)
            with self.assertRaises(AccessError):
                get_public_method(model, name)
            self.assertNotIn(name, ops)

    def test_web_client_plumbing_is_not_documented(self):
        # Every model inherits ~54 public methods from `base`; most are the
        # web client's own RPCs. Repeating them on every model made the
        # `base` document 8 MiB, so only the ORM core is kept from that set.
        ops = model_operations(self.env["res.partner"])
        for plumbing in ("web_search_read", "web_save", "onchange", "get_views",
                         "read_group", "search_panel_select_range"):
            self.assertNotIn(plumbing, ops)

    def test_model_specific_methods_are_documented(self):
        # Methods a model adds itself are its real API surface.
        # Known public methods, named independently of the generator: two
        # of res.partner's own, one from its mail.thread mixin.
        ops = model_operations(self.env["res.partner"])
        for specific in ("address_get", "find_or_create", "create_company", "message_post"):
            self.assertIn(specific, ops)

    def test_path_item_shape(self):
        model = self.env["res.partner"]
        func = model_operations(model)["read"]
        item = path_item("res.partner", "read", func)
        body = _body(item)
        # Shared shapes are referenced, not inlined; build_document supplies
        # the components (TestDocument.test_every_ref_resolves).
        self.assertEqual(body["properties"]["ids"], {"$ref": "#/components/schemas/Ids"})
        self.assertEqual(body["properties"]["context"], {"$ref": "#/components/schemas/Context"})
        self.assertEqual(set(item["post"]["responses"]), {"200", "4XX", "5XX"})

    def test_method_docstring_is_aliased(self):
        model = self.env["res.partner"]
        for name, func in model_operations(model).items():
            item = path_item("res.partner", name, func)
            self.assertNotIn("Odoo", item["post"].get("description", ""))

    def test_string_annotations_are_typed(self):
        # odoo/orm/models.py uses `from __future__ import annotations`, so
        # every annotation reaches inspect.signature as a string such as
        # "int | None". A map keyed on the `int` type object never matches
        # one of those and would leave every ORM parameter untyped.
        func = model_operations(self.env["res.partner"])["search"]
        props = _body(path_item("res.partner", "search", func))["properties"]
        self.assertEqual(props["offset"], {"type": "integer"})
        self.assertEqual(props["limit"], {"type": ["integer", "null"]})
        self.assertEqual(props["order"], {"type": ["string", "null"]})

    def test_model_methods_take_no_ids(self):
        # The dispatcher answers 422 to `ids` on an @api.model method
        # (addons/rpc/controllers/json2.py), so documenting the key there
        # would describe a request the server rejects.
        ops = model_operations(self.env["res.partner"])
        for name in ("search", "create"):
            self.assertNotIn("ids", _body(path_item("res.partner", name, ops[name]))["properties"])
        self.assertIn("ids", _body(path_item("res.partner", "write", ops["write"]))["properties"])

    def test_parameters_without_a_default_are_required(self):
        func = model_operations(self.env["res.partner"])["write"]
        body = _body(path_item("res.partner", "write", func))
        self.assertEqual(body["required"], ["vals"])


@tagged("post_install", "-at_install")
class TestDocument(TransactionCase):
    def test_default_document_is_the_core_set_intersected_with_the_registry(self):
        doc = build_document(self.env)
        tags = {t["name"] for t in doc["tags"]}
        self.assertTrue(tags)
        for name in tags:
            self.assertIn(name, CORE)
            self.assertIn(name, self.env)

    def test_app_scoping_uses_ir_model_data(self):
        # ir.model.modules is computed and non-stored, so it cannot be searched.
        names = models_for_app(self.env, "base")
        self.assertIn("res.partner", names)
        self.assertNotIn("sale.order", names)
        self.assertNotIn("mail.message", names)
        self.assertIn("mail.message", models_for_app(self.env, "mail"))

    def test_app_scoping_is_models_the_app_defines_not_extends(self):
        # ir.model.data holds an xmlid such as `mail.model_res_partner` for
        # every model a module *extends*, so the ir.model.data search alone
        # would put res.partner in mail's document. Abstract models (no
        # table, nothing to call) are left out too.
        names = models_for_app(self.env, "mail")
        for extended in ("res.partner", "res.users", "ir.cron"):
            self.assertNotIn(extended, names)
        for abstract in ("mail.thread", "ir.http", "base"):
            self.assertNotIn(abstract, names)

    def test_app_scoped_document_covers_only_that_app(self):
        doc = build_document(self.env, app="mail")
        tags = {t["name"] for t in doc["tags"]}
        self.assertIn("mail.message", tags)
        self.assertNotIn("res.partner", tags)

    def test_document_is_openapi_31_and_structurally_complete(self):
        doc = build_document(self.env)
        self.assertEqual(doc["openapi"], "3.1.0")
        self.assertIn("info", doc)
        self.assertTrue(doc["paths"])
        for path, item in doc["paths"].items():
            self.assertTrue(path.startswith("/json/2/"))
            self.assertIn("post", item)

    def test_every_ref_resolves(self):
        doc = build_document(self.env)
        refs = []

        def walk(node):
            if isinstance(node, dict):
                ref = node.get("$ref")
                if ref:
                    refs.append(ref)
                    prefix, kind, name = ref.rsplit("/", 2)
                    self.assertEqual(prefix, "#/components")
                    self.assertIn(name, doc["components"][kind])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(doc)
        # Vacuous otherwise: a document with no $ref at all passes the loop.
        self.assertTrue(refs)

    def test_asset_description_differs_from_the_live_document(self):
        # The live document really is built per request for env.user
        # (models/api_docs.py); the committed asset is built once, as
        # base.user_admin, on a fresh installation with no demo data
        # (export_openapi_shell.py, AFD-ARCH-CORR-0006) - so info.description
        # must say so instead of claiming to be the signed-in caller's own
        # view (fix round 1, finding 6).
        live = build_document(self.env, names=["res.partner"], asset=False)
        asset = build_document(self.env, names=["res.partner"], asset=True)
        self.assertIn("signed-in user", live["info"]["description"])
        self.assertNotIn("signed-in user", asset["info"]["description"])
        self.assertIn("fresh installation as the administrator", asset["info"]["description"])
        self.assertIn("fields behind optional feature groups are not listed",
                       asset["info"]["description"])
        self.assertNotEqual(live["info"]["description"], asset["info"]["description"])

    def test_info_version_is_the_api_version(self):
        # info.version documents the AFENDA contract (api_version.py), not
        # the Odoo release the server happens to run.
        doc = build_document(self.env)
        self.assertEqual(doc["info"]["version"], API_VERSION)

    def test_error_schema_is_problem_details(self):
        doc = build_document(self.env)
        error = doc["components"]["schemas"]["Error"]
        self.assertEqual(error["required"], ["type", "title", "status", "code", "detail"])
        self.assertEqual(
            error["properties"]["code"]["enum"],
            [code for code, _status, _description in PROBLEM_CODES],
        )

    def test_every_operation_answers_4xx_and_5xx_with_problem(self):
        doc = build_document(self.env)
        self.assertTrue(doc["paths"])
        for item in doc["paths"].values():
            responses = item["post"]["responses"]
            self.assertEqual(set(responses), {"200", "4XX", "5XX"})
            self.assertEqual(responses["4XX"], {"$ref": "#/components/responses/Problem"})
            self.assertEqual(responses["5XX"], {"$ref": "#/components/responses/Problem"})
        problem = doc["components"]["responses"]["Problem"]
        schema = problem["content"]["application/problem+json"]["schema"]
        self.assertEqual(schema, {"$ref": "#/components/schemas/Error"})

    def test_a_body_shared_by_many_models_is_written_once(self):
        # A method no model overrides has one signature, hence one body, on
        # every model; it must be written once in components and referenced.
        # A body used once stays inline (res.users overrides fields_get with
        # its own signature, odoo/addons/base/models/res_users.py, so the
        # two-model default document legitimately inlines it).
        doc = build_document(self.env, app="mail")
        uses = {}
        for item in doc["paths"].values():
            body = item["post"]["requestBody"]
            if "$ref" in body:
                uses[body["$ref"]] = uses.get(body["$ref"], 0) + 1
        self.assertTrue(uses)
        self.assertTrue(all(count >= 2 for count in uses.values()), uses)
        self.assertEqual(set(doc["components"]["requestBodies"]),
                         {ref.rsplit("/", 1)[1] for ref in uses})
        self.assertGreaterEqual(max(uses.values()), 10)

    def test_every_app_document_stays_renderable(self):
        # A reference UI does not render a multi-megabyte document; the plan's
        # budget is 1 MiB per app. `base` is the largest app installed here.
        for app in (None, "base", "mail"):
            size = len(json.dumps(build_document(self.env, app=app)))
            self.assertLess(size, 1024 * 1024, "document for app=%r is %d bytes" % (app, size))

    def test_no_odoo_identity_in_prose_but_wire_values_survive(self):
        doc = build_document(self.env)
        self.assertNotIn("Odoo", doc["info"]["title"] + doc["info"]["description"])
        for tag in doc["tags"]:
            self.assertNotIn("Odoo", tag.get("description", ""))
        self.assertIn("res.partner", doc["components"]["schemas"])
        self.assertIn("odoobot_state", doc["components"]["schemas"]["res.users"]["properties"])

    def test_models_the_user_cannot_read_are_left_out(self):
        # The document is per user. ir.cron is readable by group_system only
        # (odoo/addons/base/security/ir.model.access.csv:5), so a portal
        # user's document for `base` must carry neither its schema nor its
        # paths - nor those of any other base model the user cannot read.
        portal = self.env["res.users"].create({
            "name": "Docs portal",
            "login": "docs_portal",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        portal_env = self.env(user=portal)
        doc = build_document(portal_env, app="base")
        hidden = [
            name for name in models_for_app(self.env, "base")
            if not portal_env[name].has_access("read")
        ]
        self.assertIn("ir.cron", hidden)
        for name in hidden:
            self.assertNotIn(name, doc["components"]["schemas"])
            self.assertFalse([p for p in doc["paths"] if p.startswith(f"/json/2/{name}/")])
        self.assertIn("res.partner", doc["components"]["schemas"])


@tagged("post_install", "-at_install")
class TestDocumentCache(TransactionCase):
    def setUp(self):
        super().setUp()
        # Another test in the same registry may have filled the entry.
        self.env.registry.clear_cache()
        from odoo.addons.afenda_api_docs.models import api_docs
        self.build = self.startPatcher(
            patch.object(api_docs, "build_document", wraps=api_docs.build_document)
        )
        self.admin = self.env.ref("base.user_admin")
        self.portal = self.env["res.users"].create({
            "name": "Docs cache portal",
            "login": "docs_cache_portal",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })

    def test_second_call_is_served_from_the_cache(self):
        Docs = self.env["afenda.api.docs"].with_user(self.admin)
        first = Docs._openapi_json("base")
        second = Docs._openapi_json("base")
        self.assertEqual(self.build.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["openapi"], "3.1.0")

    def test_different_groups_get_different_documents(self):
        admin_doc = json.loads(self.env["afenda.api.docs"].with_user(self.admin)._openapi_json("base"))
        portal_doc = json.loads(self.env["afenda.api.docs"].with_user(self.portal)._openapi_json("base"))
        self.assertEqual(self.build.call_count, 2)
        # ir.cron is readable by group_system only.
        self.assertIn("ir.cron", admin_doc["components"]["schemas"])
        self.assertNotIn("ir.cron", portal_doc["components"]["schemas"])

    def test_superuser_does_not_share_an_entry_with_its_groups(self):
        # env.su bypasses field groups and ACLs (models.py has_access,
        # _has_field_access), so it must be part of the key.
        Docs = self.env["afenda.api.docs"].with_user(self.admin)
        Docs._openapi_json("base")
        Docs.sudo()._openapi_json("base")
        self.assertEqual(self.build.call_count, 2)

    def test_allowed_companies_do_not_share_an_entry(self):
        # fields_get can depend on records the caller's company-scoped record
        # rules select (account.analytic.line renames its plan columns after
        # the plans it can search), so the allowed companies are in the key,
        # not only the current one.
        other = self.env["res.company"].create({"name": "Docs cache second company"})
        self.admin.company_ids |= other
        main = self.admin.company_id
        Docs = self.env["afenda.api.docs"].with_user(self.admin)
        Docs.with_context(allowed_company_ids=[main.id])._openapi_json("base")
        Docs.with_context(allowed_company_ids=[main.id, other.id])._openapi_json("base")
        self.assertEqual(self.build.call_count, 2)
