from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_api_docs.openapi import model_operations, model_schema, path_item


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
        self.assertEqual(body["properties"]["ids"]["type"], "array")
        self.assertIn("context", body["properties"])
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
