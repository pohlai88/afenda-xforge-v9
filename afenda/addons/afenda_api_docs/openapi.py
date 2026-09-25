"""Generate an OpenAPI 3.1 document by walking the live registry.

Every prose string passes through `alias_prose` at the point it is inserted;
wire values (model, field, method and parameter names, selection keys) are
inserted verbatim. See `aliasing.py` for why the split is structural.
"""
import inspect

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method

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


# Annotation name -> JSON Schema type. Annotations arrive as *strings*: the ORM
# (odoo/orm/models.py:22) and most addons use `from __future__ import
# annotations`, so `search`'s `limit` reads as "int | None", never as the
# `int` type. A map keyed on type objects would therefore match nothing.
# Anything not listed here - a model class, `Self`, a TypeVar - leaves the
# whole parameter untyped rather than guessed at.
_ANNOTATION_TYPES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "None": "null",
    "list": "array",
    "tuple": "array",
    "set": "array",
    "frozenset": "array",
    "Sequence": "array",
    "Iterable": "array",
    "Collection": "array",
    # odoo/orm/types.py: a domain is a list of terms, a values dict an object.
    "DomainType": "array",
    "dict": "object",
    "Mapping": "object",
    "ValuesType": "object",
}


def _split_union(text):
    """Split "a | b[c | d]" at top-level pipes only."""
    parts, depth, start = [], 0, 0
    for i, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "|" and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [part.strip() for part in parts]


def _annotation_schema(annotation):
    if annotation is inspect.Parameter.empty:
        return {}
    if not isinstance(annotation, str):
        annotation = inspect.formatannotation(annotation)
    types = []
    for part in _split_union(annotation):
        name = part.split("[", 1)[0].rsplit(".", 1)[-1]
        json_type = _ANNOTATION_TYPES.get(name)
        if json_type is None:
            return {}
        if json_type not in types:
            types.append(json_type)
    return {"type": types[0] if len(types) == 1 else types}


def model_operations(model):
    """Every method on `model` the /json/2 dispatcher would accept.

    Delegates the rule to `get_public_method`, the same function the
    dispatcher calls (addons/rpc/controllers/json2.py), so this cannot drift
    into documenting a 404.
    """
    operations = {}
    for name in sorted(dir(type(model))):
        try:
            operations[name] = get_public_method(model, name)
        except (AttributeError, AccessError):
            continue
    return operations


def path_item(model_name, method_name, func):
    """The OpenAPI path item for POST /json/2/<model>/<method>.

    Mirrors how the dispatcher binds the body: `ids` browses the recordset
    passed as the method's first argument, `context` is applied with
    `with_context`, and every remaining key is bound by name through
    `inspect.signature(func).bind(records, **kwargs)`.
    """
    properties = {}
    # @api.model and @api.model_create_multi set `_api_model`; the dispatcher
    # answers 422 to a call that sends `ids` to one of those.
    if not getattr(func, "_api_model", False):
        properties["ids"] = {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Record ids the method is called on.",
        }
    properties["context"] = {
        "type": "object",
        "description": "Context for the call, such as lang, tz and allowed_company_ids.",
    }
    required = []
    parameters = list(inspect.signature(func).parameters.values())
    for param in parameters[1:]:  # [0] is the recordset the dispatcher binds
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD, param.POSITIONAL_ONLY):
            continue
        # The dispatcher's own signature consumes these two keys, so a method
        # parameter of the same name can never be reached through the body.
        if param.name in ("ids", "context"):
            continue
        properties[param.name] = _annotation_schema(param.annotation)
        if param.default is param.empty:
            required.append(param.name)

    body = {"type": "object", "properties": properties}
    if required:
        body["required"] = required
    return {
        "post": {
            "operationId": f"{model_name}.{method_name}",
            # A wire value, inserted verbatim: the summary is the method name
            # the caller puts in the URL, so it is never passed to alias_prose.
            "summary": method_name,
            "description": alias_prose(inspect.getdoc(func) or ""),
            "tags": [model_name],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": body}},
            },
            "responses": {
                "200": {"description": "Success."},
                "404": {"description": "The model or method does not exist."},
                "422": {"description": "The arguments do not match the method signature."},
            },
            "security": [{"bearerAuth": []}],
        }
    }
