import json

from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_api_docs.openapi import (
    build_document,
    model_operations,
    model_schema,
    models_for_app,
    path_item,
)

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

    def test_private_methods_are_not_documented(self):
        ops = model_operations(self.env["res.partner"])
        for hidden in ("_read", "_write", "browse"):
            self.assertNotIn(hidden, ops)

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
        ops = model_operations(self.env["res.partner"])
        for specific in ("address_get", "find_or_create"):
            self.assertIn(specific, ops)

    def test_every_documented_method_is_actually_callable(self):
        # The one invariant that matters: the docs must not describe an
        # operation the dispatcher would 404.
        model = self.env["res.partner"]
        for name in model_operations(model):
            get_public_method(model, name)

    def test_path_item_shape(self):
        model = self.env["res.partner"]
        func = model_operations(model)["read"]
        item = path_item("res.partner", "read", func)
        body = _body(item)
        # Shared shapes are referenced, not inlined; build_document supplies
        # the components (TestDocument.test_every_ref_resolves).
        self.assertEqual(body["properties"]["ids"], {"$ref": "#/components/schemas/Ids"})
        self.assertEqual(body["properties"]["context"], {"$ref": "#/components/schemas/Context"})
        self.assertIn("404", item["post"]["responses"])
        self.assertIn("422", item["post"]["responses"])

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

    def test_error_responses_use_the_dispatcher_error_shape(self):
        # odoo/http.py serialize_exception: what Json2Dispatcher.handle_error
        # sends back for a 404 or a 422.
        doc = build_document(self.env)
        error = doc["components"]["schemas"]["Error"]
        self.assertEqual(
            set(error["properties"]), {"name", "message", "arguments", "context", "debug"}
        )
        item = doc["paths"]["/json/2/res.partner/read"]["post"]
        for status in ("404", "422"):
            name = item["responses"][status]["$ref"].rsplit("/", 1)[1]
            response = doc["components"]["responses"][name]
            schema = response["content"]["application/json"]["schema"]
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
