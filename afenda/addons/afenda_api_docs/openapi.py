"""Generate an OpenAPI 3.1 document by walking the live registry.

Every prose string passes through `alias_prose` at the point it is inserted;
wire values (model, field, method and parameter names, selection keys) are
inserted verbatim. See `aliasing.py` for why the split is structural.
"""
import inspect
import json

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method

from odoo.addons.afenda_brand.brand import BRAND
from odoo.addons.afenda_runtime.problems import PROBLEM_CODES

from .aliasing import alias_prose
from .api_version import API_VERSION

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
    # Model names carry digits (l10n_*), hence 0-9 in the model part.
    "reference": {"type": "string", "pattern": r"^[a-z0-9_.]+,\d+$"},
    # A jsonb list of property definitions (odoo/orm/fields_properties.py).
    "properties_definition": {"type": "array", "items": {"type": "object"}},
}
# Only reached by a field type added after this map was written. A new type
# documented as a string is a wrong contract, not a missing one, so
# `test_every_odoo_field_type_is_mapped` fails loudly instead of letting it
# through quietly.
_FALLBACK = {"type": "string"}

# AFD-ARCH-CORR-0011, amended (commit e344ed3c8): a selection also counts as
# environment-derived when it is a *static* list built at import time from
# something that varies by server (installed pytz, the host's OS locale
# data...), so baking it into a committed asset would freeze one server's
# snapshot. `res.partner.tz` is exactly this: `fields.Selection(_tzs, ...)`
# (odoo/addons/base/models/res_partner.py:223) passes the module-level list
# `_tzs` (line 40: `_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, ...)]`)
# directly, never through the `_tz_get` method one line below it - so its
# field object's `selection` is a plain list, not a callable or method name,
# and the general rule below would otherwise miss it. A grep of this tree
# confirms `_tzs` is the only such import-time-computed selection list
# reachable from a model field. Entries are (model, field name) pairs on the
# field that actually *owns* the selection - i.e. after following any
# related chain (see `_resolve_selection_owner`), never on a field that
# merely relates to it.
ENVIRONMENT_DERIVED_SELECTIONS = frozenset({
    ("res.partner", "tz"),
})


def _resolve_selection_owner(field):
    """The field that actually defines `selection`, following `related`.

    A related selection field's own `selection` attribute is *always* a
    wrapper lambda that delegates to the target
    (`Selection.setup_related`, odoo/orm/fields_selection.py:77-82: `self.
    selection = lambda model: field._description_selection(model.env)`), so
    checking `field.selection` directly would call every related selection
    field dynamic regardless of what its target actually is. Odoo resolves
    a related field's ultimate target at setup time onto `related_field`
    (`odoo/orm/fields.py:290` declares `related`, `:302` declares
    `related_field`, `:604-626` is `setup_related`, which walks the whole
    dotted chain and assigns `self.related_field = field` to the *last*
    field in it - itself possibly still related, e.g.
    `res.users.tz` -(_inherits, model_classes.py:503)-> related to
    `partner_id.tz`, i.e. `res.partner.tz` directly). Walking `related_field`
    until it stops being set reaches the true owner in one or more hops.
    """
    seen = set()
    while field.related and field.related_field is not None and id(field) not in seen:
        seen.add(id(field))
        field = field.related_field
    return field


def model_schema(model, asset=False):
    """JSON Schema for one model, from what the calling user may read.

    `fields_get` already drops fields whose `groups` the caller lacks
    (odoo/orm/models.py:3364), so the schema is per user by construction.

    `asset=True` applies the dynamic-selection rule (AFD-ARCH-CORR-0011): a
    selection field whose *owning* field (see `_resolve_selection_owner`)
    has a `selection` attribute (on the field object, not `fields_get`'s
    already-resolved list - see odoo/orm/fields_selection.py) that is a
    callable or a method name, or whose owning `(model, field)` is listed in
    `ENVIRONMENT_DERIVED_SELECTIONS`, would otherwise bake one server's
    runtime values (installed languages, timezones...) into a committed
    asset. Such a field gets no `enum`/`x-enum-labels`, and
    `x-afenda-dynamic-enum: true` instead. The live document (asset=False)
    is unaffected.
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
            field = model._fields.get(name)
            dynamic = False
            if asset and field is not None:
                owner = _resolve_selection_owner(field)
                dynamic = (
                    callable(owner.selection)
                    or isinstance(owner.selection, str)
                    or (owner.model_name, owner.name) in ENVIRONMENT_DERIVED_SELECTIONS
                )
            if dynamic:
                prop["x-afenda-dynamic-enum"] = True
            else:
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


# The methods every model inherits from `base` that belong in an integrator's
# reference: CRUD, the search family, field introspection, name lookup and
# `formatted_read_group` (the public grouping API in 19.0; `read_group` is
# deprecated). The rest of what `base` exposes (~54 public methods in all:
# web_search_read, web_save, onchange, get_views, search_panel_*, and
# conveniences such as copy, default_get, name_create, action_archive) is
# left out - still callable, just not advertised. Measured on the `base` app
# (89 models): every inherited method made its document 8 MiB and 1.2 s to
# build; this set, with the shared components below, brings it under 1 MiB.
_ORM_CORE = frozenset({
    "create",
    "fields_get",
    "formatted_read_group",
    "name_search",
    "read",
    "search",
    "search_count",
    "search_read",
    "unlink",
    "write",
})


def model_operations(model):
    """The documented methods of `model`, each one the /json/2 dispatcher accepts.

    Acceptance is delegated to `get_public_method`, the same function the
    dispatcher calls (addons/rpc/controllers/json2.py), so this cannot drift
    into documenting a 404. Of the methods every model inherits from `base`
    only `_ORM_CORE` is kept; every method a model or its mixins add is kept.
    """
    generic = set(dir(type(model.env["base"]))) - _ORM_CORE
    operations = {}
    for name in sorted(dir(type(model))):
        if name in generic:
            continue
        try:
            operations[name] = get_public_method(model, name)
        except (AttributeError, AccessError):
            continue
    return operations


# Shared components. Every path item references these rather than inlining
# them: repeated on each of the ~1,700 operations of the `base` app they cost
# ~600 bytes apiece, which is most of what pushed that document past budget.
_COMPONENT_SCHEMAS = {
    # An RFC 9457 (https://www.rfc-editor.org/rfc/rfc9457) Problem Details
    # object: what `afenda_runtime`'s `ir.http._handle_error` override sends
    # for every JSON-2 4xx or 5xx (never upstream's exception name, raw
    # arguments, context or traceback - see that module's docstring).
    "Error": {
        "type": "object",
        "title": "Error",
        "properties": {
            "type": {
                "type": "string",
                "format": "uri-reference",
                "description": "A reference to the error code's entry on /docs/api/errors.",
            },
            "title": {"type": "string", "description": "The HTTP reason phrase."},
            "status": {"type": "integer"},
            "code": {
                "type": "string",
                "enum": [code for code, _status, _description in PROBLEM_CODES],
            },
            "detail": {"type": "string"},
            "message": {"type": "string", "description": "Repeats detail."},
            "instance": {
                "type": "string",
                "description": "An opaque id for this occurrence; present on 5xx only.",
            },
        },
        "required": ["type", "title", "status", "code", "detail"],
    },
    "Ids": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "Record ids the method is called on.",
    },
    "Context": {
        "type": "object",
        "description": "Context for the call, such as lang, tz and allowed_company_ids.",
    },
}
# One line per PROBLEM_CODES entry, in its documentation order: "401
# unauthenticated", "403 access_denied", and so on.
_PROBLEM_STATUSES = "; ".join(
    f"{status} {code}" for code, status, _description in PROBLEM_CODES
)
_COMPONENT_RESPONSES = {
    # Shared by every operation's 4XX and 5XX: `afenda_runtime`'s
    # `ir.http._handle_error` override answers every JSON-2 error this shape,
    # never upstream's per-exception body.
    "Problem": {
        "description": (
            "An RFC 9457 Problem Details object. code is one of: "
            + _PROBLEM_STATUSES + ". See /docs/api/errors for what each means."
        ),
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/Error"}},
        },
    },
}


def _summary_paragraph(func):
    """The first prose paragraph of a method's docstring.

    Only the first paragraph: Redoc renders descriptions as Markdown, so the
    reST field lists that follow (`:param x:`, `:raise:`) show as literal
    text, and the parameters are already described by the request schema. A
    leading paragraph that merely restates the call signature, as in
    `search(domain[, offset=0]...)`, is skipped.
    """
    doc = inspect.getdoc(func) or ""
    for paragraph in doc.split("\n\n"):
        text = " ".join(paragraph.split())
        if not text or text.startswith(":") or text.startswith(f"{func.__name__}("):
            continue
        return text
    return ""


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
        properties["ids"] = {"$ref": "#/components/schemas/Ids"}
    properties["context"] = {"$ref": "#/components/schemas/Context"}
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
    post = {
        "operationId": f"{model_name}.{method_name}",
        # A wire value, inserted verbatim: the summary is the method name
        # the caller puts in the URL, so it is never passed to alias_prose.
        "summary": method_name,
        "tags": [model_name],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": body}},
        },
        "responses": {
            "200": {"description": "Success."},
            "4XX": {"$ref": "#/components/responses/Problem"},
            "5XX": {"$ref": "#/components/responses/Problem"},
        },
    }
    description = alias_prose(_summary_paragraph(func))
    if description:
        post["description"] = description
    return {"post": post}


# Emitted when no ?app= is given, so the default URL is useful rather than
# empty. Intersected with the registry: a model whose module is not installed
# does not exist.
_CORE_MODELS = (
    "res.partner",
    "res.users",
    "product.template",
    "sale.order",
    "account.move",
    "stock.picking",
)


def models_for_app(env, app):
    """Names of the concrete models one module defines.

    Candidates come from ir.model.data rather than ir.model.modules: the
    latter reads as the obvious choice and is a non-stored computed field
    (odoo/addons/base/models/ir_model.py, `compute='_in_modules'`), so it
    cannot appear in a search domain. But ir.model.data also holds an xmlid
    such as `mail.model_res_partner` for every model a module merely
    *extends*, so the candidates are narrowed to the models whose class was
    first defined by `app` (`_original_module`, set once at definition in
    odoo/orm/model_classes.py:183). Abstract models have no table and
    nothing to call on them, so they are left out.

    sudo() because ir.model.data is not readable by every user; only model
    *names* leave this function, and build_document filters those by the
    caller's own read access.
    """
    data = env["ir.model.data"].sudo().search(
        [("module", "=", app), ("model", "=", "ir.model")]
    )
    models = env["ir.model"].sudo().browse(data.mapped("res_id"))
    return sorted(
        m.model for m in models
        if m.model in env
        and env[m.model]._original_module == app
        and not env[m.model]._abstract
    )


def _share_request_bodies(paths):
    """Move every request body used by two or more operations into components.

    A method no model overrides - `search`, `read`, `write`... - has the
    same signature, hence the same body, on every model in the document.
    Inlined, that body is repeated once per model; shared, it is written
    once and referenced. Rewrites `paths` in place and returns the
    `components.requestBodies` mapping, named after the first method that
    uses each body (suffixed when two different bodies share a method name).
    """
    def key(item):
        return json.dumps(item["post"]["requestBody"], sort_keys=True)

    counts = {}
    for item in paths.values():
        counts[key(item)] = counts.get(key(item), 0) + 1

    shared, names = {}, {}
    for path, item in paths.items():
        body_key = key(item)
        if counts[body_key] < 2:
            continue
        if body_key not in names:
            method_name = path.rsplit("/", 1)[1]
            name, n = method_name, 1
            while name in shared:
                n += 1
                name = f"{method_name}_{n}"
            names[body_key] = name
            shared[name] = item["post"]["requestBody"]
        item["post"]["requestBody"] = {"$ref": f"#/components/requestBodies/{names[body_key]}"}
    return shared


def build_document(env, app=None, names=None, asset=False):
    """An OpenAPI 3.1 document for one app, the core set, or an explicit model list.

    Generated for `env.user`: models it cannot read are left out entirely,
    and `fields_get` drops fields outside its groups.

    `names`, when given, is used verbatim in place of `models_for_app(env,
    app)` - the asset exporter groups models into areas that cut across a
    single app's own models (assets.py), so it must supply its own list
    rather than have this function derive one from `app`. `asset=True`
    applies the dynamic-selection rule to every model's schema (see
    `model_schema`).
    """
    if names is None:
        names = models_for_app(env, app) if app else [m for m in _CORE_MODELS if m in env]

    paths = {}
    schemas = dict(_COMPONENT_SCHEMAS)
    tags = []
    for name in names:
        model = env[name]
        if not model.has_access("read"):
            continue
        schemas[name] = model_schema(model, asset=asset)
        tags.append({"name": name, "description": alias_prose(model._description or name)})
        for method_name, func in model_operations(model).items():
            paths[f"/json/2/{name}/{method_name}"] = path_item(name, method_name, func)
    request_bodies = _share_request_bodies(paths)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": alias_prose(f"{BRAND['product']} JSON API"),
            "version": API_VERSION,
            "description": alias_prose(
                "Every model and method reachable over POST /json/2/<model>/<method>. "
                "Generated from the running system for the signed-in user, so it "
                "shows only what that user may read."
            ),
        },
        "servers": [{"url": "/"}],
        "tags": tags,
        "paths": paths,
        # Document-wide: every operation is /json/2, and /json/2 is
        # auth='bearer' (an API key in the Authorization header).
        "security": [{"bearerAuth": []}],
        "components": {
            "schemas": schemas,
            "responses": _COMPONENT_RESPONSES,
            "requestBodies": request_bodies,
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            },
        },
    }
