from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_api_docs.openapi import model_schema


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
