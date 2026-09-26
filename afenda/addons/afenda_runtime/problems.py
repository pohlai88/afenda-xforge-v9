# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""RFC 9457 Problem Details vocabulary for JSON-2 errors.

``models.ir_http.IrHttp._handle_error`` rewrites every JSON-2
(``/json/2/<model>/<method>``) error body into an RFC 9457
(https://www.rfc-editor.org/rfc/rfc9457) Problem Details object, never
echoing Odoo internals (the exception's class name, its raw arguments,
``context``, or the server traceback) to the client. This module holds the
stable vocabulary that override renders. Task 2's OpenAPI exporter reads
``PROBLEM_CODES`` to document the shared ``Problem`` response, so its name
and tuple shape are a contract with that task, not just this one.
"""

from odoo.exceptions import (
    AccessDenied,
    AccessError,
    LockError,
    MissingError,
    UserError,
    ValidationError,
)

# (code, status, one-line description), documentation order. Every status is
# the integer the client actually receives, except "invalid_request": the
# runtime (`problem_code` below) returns it for any 4xx status not covered by
# another row, so its documented status is the literal string "4xx" rather
# than a single integer that would misrepresent every other 4xx it also
# covers (fix round 2, finding 1, PR #5 review - a malformed JSON body is 400,
# an argument the method does not accept is 422, and nothing here enumerates
# every case in between). The response body itself always carries the real
# integer status (afenda_api_docs/openapi.py's `Error` schema keeps
# `status: {"type": "integer"}`); only this table's documentation column, the
# shared Problem response description
# (afenda_api_docs/openapi.py's `_PROBLEM_STATUSES`) and the /docs/api/errors
# page (`views/errors.xml`) render the string.
PROBLEM_CODES = (
    ("unauthenticated", 401, "No, or no valid, credentials were presented."),
    ("access_denied", 403, "The credentials are valid but do not allow this operation."),
    ("not_found", 404, "The model, method or record does not exist."),
    ("conflict", 409, "The record could not be locked for the operation; retry later."),
    ("validation_error", 422, "A field or record constraint was violated."),
    ("user_error", 422, "The operation makes no sense given the current state."),
    (
        "invalid_request",
        "4xx",
        (
            "Any other 4xx: the request itself is malformed - 400 for a "
            "body that is not valid JSON, 422 for arguments the method "
            "does not accept."
        ),
    ),
    ("internal_error", 500, "An unexpected server error occurred."),
)

# Checked in this order: subclasses before their parents, so e.g. a
# LockError (itself a UserError) gives "conflict", not "user_error".
_CODES_BY_EXCEPTION = (
    (AccessDenied, "access_denied"),
    (AccessError, "access_denied"),
    (MissingError, "not_found"),
    (LockError, "conflict"),
    (ValidationError, "validation_error"),
    (UserError, "user_error"),
)

_CODES_BY_STATUS = {
    401: "unauthenticated",
    403: "access_denied",
    404: "not_found",
    409: "conflict",
}


def problem_code(exception: BaseException, status: int) -> str:
    """Return the stable AFENDA error code for ``exception``/``status``.

    500 and above is always ``"internal_error"``. Below that, a known Odoo
    exception class wins over the status; otherwise the status decides, and
    any other 4xx status is ``"invalid_request"``.
    """
    if status >= 500:
        return "internal_error"
    for exc_class, code in _CODES_BY_EXCEPTION:
        if isinstance(exception, exc_class):
            return code
    return _CODES_BY_STATUS.get(status, "invalid_request")
