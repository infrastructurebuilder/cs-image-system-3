# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The type a model declares a secret field with.

Any configuration value may be an ``ENC[age:...]`` marker: a ciphertext
encrypted to the recipients the configuration lists. A field declared
:data:`EncryptedStr` decrypts such a value at load; an unmarked value
passes through untouched. The type composes: ``list[EncryptedStr]`` and
``dict[str, EncryptedStr]`` decrypt each element on its own. The decrypted
value is a :class:`Decrypted` -- a ``str`` in every use, but its ``repr``
hides the text so a model dump in a log or an error never shows it, and it
carries the marker it was read from so an emission can refer to the
ciphertext instead of the text.

The decryption itself (the identity from the environment, the age
primitives) is the core's: it registers its decoder with
:func:`register_secret_decoder` when it loads, and a marked value met with
no decoder is refused, never passed through in clear.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Callable

from pydantic import PlainValidator

MARKER_PREFIX = "ENC[age:"
MARKER_RE = re.compile(r"^ENC\[age:([A-Za-z0-9+/=]+)\]$")


def is_marker(value: Any) -> bool:
    """Whether the value is a whole ``ENC[age:...]`` marker."""
    return isinstance(value, str) and MARKER_RE.match(value.strip()) is not None


class Decrypted(str):
    """A decrypted configuration value: a ``str`` everywhere it is used, with
    a ``repr`` that never shows the text, carrying the ``marker`` it was read
    from. A ``str`` subclass cannot declare slots, hence the attribute."""

    marker: str

    def __new__(cls, plaintext: str, marker: str = "") -> "Decrypted":
        obj = super().__new__(cls, plaintext)
        obj.marker = marker
        return obj

    def __repr__(self) -> str:
        return "Decrypted('***')"


#: The decoder: a marker in, its plaintext out (or a ``ValueError`` naming
#: why it could not be opened). Installed by the core.
SecretDecoder = Callable[[str], str]
_decoder: SecretDecoder | None = None


def register_secret_decoder(decoder: SecretDecoder | None) -> None:
    """Install the decoder an :data:`EncryptedStr` field decrypts with (the
    core's, at import); ``None`` uninstalls it."""
    global _decoder
    _decoder = decoder


def open_marker(marker: str) -> str:
    """The plaintext of one ``ENC[age:...]`` marker, through the installed
    decoder (stage 125): what a plugin calls where it holds a marker outside a
    model field -- a daemon address read from raw settings, say -- and no run
    context. Refused, never passed through in clear, when no decoder is
    installed."""
    if _decoder is None:
        raise ValueError("an encrypted value was met with no decoder installed: the core's encryption "
                         "module registers one when it loads")
    return _decoder(marker)


def _validate_encrypted_str(value: Any) -> str:
    """The whole validation of an ``EncryptedStr``: a plain validator, because
    pydantic's own ``str`` step would flatten the ``Decrypted`` subclass back to
    ``str`` and lose the hidden repr. Numbers are coerced to text the way
    the model configuration does for every other string field."""
    if isinstance(value, bool) or value is None:
        raise ValueError("a string is required")
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError(f"a string is required, not {type(value).__name__}")
    if is_marker(value):
        return Decrypted(open_marker(value), marker=value)
    return value


#: The field type. Composes: list[EncryptedStr] / set[EncryptedStr] /
#: dict[str, EncryptedStr] decrypt each element on its own.
EncryptedStr = Annotated[str, PlainValidator(_validate_encrypted_str, json_schema_input_type=str)]
