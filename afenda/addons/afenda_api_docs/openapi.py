"""Generate an OpenAPI 3.1 document by walking the live registry.

Every prose string passes through `alias_prose` at the point it is inserted;
wire values (model, field, method and parameter names, selection keys) are
inserted verbatim. See `aliasing.py` for why the split is structural.
"""
from .aliasing import alias_prose

# Odoo field type -> JSON Schema fragment. Relational fields are documented as
# the ids the /json/2 route actually accepts and returns, not as nested
# objects, because that is what the dispatcher passes to the ORM.
_TYPE_MAP = {
    "char": {"type": "string"},
    "text": {"type": "string"},
    "html": {"type": "string"},
    "selection": {"type": "string"},
    "integer": {"type": "integer"},
    "float": {"type": "number"},
    "monetary": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "datetime": {"type": "string", "format": "date-time"},
    "binary": {"type": "string", "format": "byte"},
    "json": {"type": "object"},
    "properties": {"type": "object"},
    "many2one": {"type": "integer"},
    "one2many": {"type": "array", "items": {"type": "integer"}},
    "many2many": {"type": "array", "items": {"type": "integer"}},
    # The three below are easy to miss and two of them are NOT strings.
    # many2one_reference stores an integer id, with the model name in a
    # companion Char named by its `model_field` (odoo/orm/fields_reference.py).
    # Falling through to the string fallback would tell an integrator to send
    # "5" where the ORM wants 5.
    "many2one_reference": {"type": "integer"},
    # Reference really is a string, but a structured one: "res_model,res_id".
    "reference": {"type": "string", "pattern": r"^[a-z_.]+,\d+$"},
    # A jsonb list of property definitions (odoo/orm/fields_properties.py).
    "properties_definition": {"type": "array", "items": {"type": "object"}},
}
# Only reached by a field type added after this map was written. A new type
# documented as a string is a wrong contract, not a missing one, so
# `test_every_odoo_field_type_is_mapped` fails loudly instead of letting it
# through quietly.
_FALLBACK = {"type": "string"}


def model_schema(model):
    """JSON Schema for one model, from what the calling user may read.

    `fields_get` already drops fields whose `groups` the caller lacks
    (odoo/orm/models.py:3364), so the schema is per user by construction.
    """
    properties = {}
    required = []
    for name, meta in model.fields_get().items():
        prop = dict(_TYPE_MAP.get(meta["type"], _FALLBACK))
        # Prose.
        prop["title"] = alias_prose(meta.get("string") or name)
        if meta.get("help"):
            prop["description"] = alias_prose(meta["help"])
        # Wire values: enum keys are sent back verbatim, labels are read.
        if meta.get("selection"):
            prop["enum"] = [key for key, _label in meta["selection"]]
            prop["x-enum-labels"] = [alias_prose(label) for _key, label in meta["selection"]]
        if meta.get("relation"):
            prop["x-relation"] = meta["relation"]
        if meta.get("readonly"):
            prop["readOnly"] = True
        if meta.get("required"):
            required.append(name)
        properties[name] = prop

    schema = {
        "type": "object",
        "title": alias_prose(model._description or model._name),
        "properties": properties,
    }
    if required:
        schema["required"] = sorted(required)
    return schema
