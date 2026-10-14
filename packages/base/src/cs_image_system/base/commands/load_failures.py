# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One line for a failure that stops the configuration from loading
(hygiene XII; the walk's findings F10, F30, F41 and F42).

Every command loads the configuration first, and four things the walk met
there came out as tracebacks under a good one-line message: a missing OPA
key pair (F10), AWS keys that had lapsed (F30, ``RequestExpired``), a
shell with no age identity (F41, ``MissingIdentityError``) and a reserved
word used as a name (F42, ``ReservedNameError``). The first three are the
ENVIRONMENT's, and end like preflight's absent session (exit 2); the last
is the CONFIGURATION's, and ends as every other rule does, under
``Validation failed with 1 error(s).`` (exit 1). Anything else keeps its
traceback: an unknown failure is not dressed up as a known one.

The classification walks the exception's cause chain, because a cloud's
error arrives wrapped (``AMIQueryError`` around ``ClientError``), and
names botocore's classes by name so that this package needs no boto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from ..encryption import MissingIdentityError
from ..reserved_names import ReservedNameError

#: AWS error codes that mean the credentials in hand have lapsed or are not
#: credentials any more: temporary keys (``RequestExpired``,
#: ``ExpiredToken``) and an SSO token the CLI could not renew.
AWS_LAPSED_CODES: tuple[str, ...] = ("RequestExpired", "ExpiredToken", "ExpiredTokenException",
                                     "InvalidClientTokenId", "UnrecognizedClientException")
#: botocore's own classes for a session that cannot even be built.
AWS_SESSION_CLASSES: tuple[str, ...] = ("TokenRetrievalError", "SSOTokenLoadError", "UnauthorizedSSOTokenError",
                                        "NoCredentialsError", "CredentialRetrievalError", "ProfileNotFound")
#: What a load says when the OPA key pair is not in the environment.
OPA_CREDENTIAL_MARKS: tuple[str, ...] = ("not found in the environment", "is missing a key value",
                                         "is missing a secret value")

AWS_REMEDY = ("an SSO profile: `aws sso login --profile <profile>`; keys pasted into the shell or a credentials "
              "file: FRESH keys (`aws sso login` does nothing for them). `preflight` cannot see a key's lapse "
              "coming: it reads no expiry for keys, and says so")
OPA_REMEDY = ("the `TF_VAR_<team>_key` / `TF_VAR_<team>_secret` pair is needed by `validate` and every dry run, "
              "not only at apply: `source .envrc`; in CI, the secrets the workflow names")
IDENTITY_REMEDY = ("the shell never loaded `.envrc` (a new terminal, a directory direnv has not entered or "
                   "allowed): `source .envrc`, or `direnv allow`")


@dataclass
class LoadFailure:
    kind: str                       # "configuration" | "environment"
    lines: list[str] = field(default_factory=list)
    code: int = 2


def _chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        yield e
        e = e.__cause__ or e.__context__


def _aws_code(e: BaseException) -> str:
    response = getattr(e, "response", None)
    if isinstance(response, dict):
        return str((response.get("Error") or {}).get("Code") or "")
    return ""


def classify_load_failure(exc: BaseException) -> LoadFailure | None:
    """The one-line form of a known load-time failure, or None for one
    that keeps its traceback."""
    for e in _chain(exc):
        if isinstance(e, ReservedNameError):
            return LoadFailure("configuration", [f" - {e}", "Validation failed with 1 error(s)."], code=1)
        if isinstance(e, MissingIdentityError):
            return LoadFailure("environment", [f"the configuration cannot load: {e}", f"({IDENTITY_REMEDY})"])
        name = type(e).__name__
        code = _aws_code(e)
        if name == "ClientError" and code in AWS_LAPSED_CODES:
            return LoadFailure("environment", [f"the configuration cannot load: AWS refused the credentials ({code}): "
                                               f"{_message(e)}", f"({AWS_REMEDY})"])
        if name in AWS_SESSION_CLASSES:
            return LoadFailure("environment", [f"the configuration cannot load: the AWS session could not be built "
                                               f"({name}): {e}", f"({AWS_REMEDY})"])
        if isinstance(e, ValueError) and "TF_VAR_" in str(e) and any(m in str(e) for m in OPA_CREDENTIAL_MARKS):
            return LoadFailure("environment", [f"the configuration cannot load: {e}", f"({OPA_REMEDY})"])
    return None


def _message(e: BaseException) -> str:
    response = getattr(e, "response", None)
    if isinstance(response, dict):
        msg = str((response.get("Error") or {}).get("Message") or "")
        if msg:
            return msg
    return str(e)
