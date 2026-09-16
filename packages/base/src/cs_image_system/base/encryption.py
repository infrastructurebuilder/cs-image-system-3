# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Encrypted configuration values (stage 33).

A value anywhere in the configuration may be the element-level marker

    ENC[age:<base64 of a standard age-encryption.org/v1 file>]

encrypted to every recipient listed in ``cfg/_config.yml`` under
``encryption.recipients`` (age X25519 public keys, ``age1…``). A field
declared :data:`EncryptedStr` decrypts such a value at load with the
identity the environment supplies in :data:`IDENTITY_ENV` -- the
``AGE-SECRET-KEY-1…`` string itself, the path of an identity file in the
age-keygen layout, or a directory of ``*.age-identity`` files, each tried
until one opens the value. An unmarked value passes through untouched; a
marked value with no identity is a load-time refusal naming the variable,
never a silent plaintext. The type composes: ``list[EncryptedStr]`` and
``set[EncryptedStr]`` decrypt each element on its own, so a roster is
encrypted entry by entry and a diff shows which entry changed.

The decrypted value is a :class:`Decrypted` -- a ``str`` in every use, but
its ``repr`` hides the text so a model dump in a log or an error never
shows it. The same marker is what ``bin/crypt_age.sh``, ``bin/rotate_age.sh``
and the ``age`` CLI produce, so any of them interoperate with the loader.
"""
from __future__ import annotations

import base64
import io
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Iterable

from pydantic import PlainValidator

IDENTITY_ENV = "CSIS_CONFIG_IDENTITY"
MARKER_PREFIX = "ENC[age:"
MARKER_RE = re.compile(r"^ENC\[age:([A-Za-z0-9+/=]+)\]$")
INLINE_MARKER_RE = re.compile(r"ENC\[age:([A-Za-z0-9+/=]+)\]")


class Decrypted(str):
    """A decrypted configuration value: a ``str`` everywhere it is used, with
    a ``repr`` that never shows the text, carrying the ``marker`` it was read
    from so an emission can refer to the ciphertext instead of the text
    (stage 34). A ``str`` subclass cannot declare slots, hence the attribute."""

    marker: str

    def __new__(cls, plaintext: str, marker: str = "") -> "Decrypted":
        obj = super().__new__(cls, plaintext)
        obj.marker = marker
        return obj

    def __repr__(self) -> str:
        return "Decrypted('***')"


class MissingIdentityError(ValueError):
    pass


def _represent_decrypted(dumper, value):
    """PyYAML refuses a ``str`` subclass; a decrypted value is written as the
    plain text it is wherever a model is dumped (the read-models' rosters).
    ``assert_public_safe`` on every meta-state write remains the backstop."""
    return dumper.represent_str(str(value))


try:
    import yaml as _yaml
    for _dumper in (_yaml.SafeDumper, _yaml.Dumper):
        _dumper.add_representer(Decrypted, _represent_decrypted)
except ImportError:                                  # pragma: no cover
    pass


def is_marker(value: Any) -> bool:
    return isinstance(value, str) and MARKER_RE.match(value.strip()) is not None


# ---------------------------------------------------------------- identities

def _parse_identity_text(text: str, source: str):
    from age.keys.agekey import AgePrivateKey
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("AGE-SECRET-KEY-1"):
            return AgePrivateKey.from_private_string(line)
    raise MissingIdentityError(f"{source}: no AGE-SECRET-KEY-1 line")


@lru_cache(maxsize=8)
def _identities_for(value: str) -> tuple:
    """The identities the environment value names -- the key itself, an
    identity file, or a directory of them. Cached per value: a load
    decrypts many values with the same keys."""
    value = value.strip()
    if value.startswith("AGE-SECRET-KEY-1"):
        return (_parse_identity_text(value, IDENTITY_ENV),)
    path = Path(os.path.expanduser(value))
    if path.is_dir():
        files = sorted(path.glob("*.age-identity"))
        if not files:
            raise MissingIdentityError(f"{IDENTITY_ENV}={value}: no *.age-identity files in that directory")
        return tuple(_parse_identity_text(f.read_text(), str(f)) for f in files)
    if path.is_file():
        return (_parse_identity_text(path.read_text(), str(path)),)
    raise MissingIdentityError(f"{IDENTITY_ENV}={value!r}: not an AGE-SECRET-KEY-1 string, an identity file or a directory")


def identities_from_env(env: dict[str, str] | None = None) -> tuple:
    lookup = os.environ if env is None else env
    value = lookup.get(IDENTITY_ENV)
    if not value:
        raise MissingIdentityError(
            f"an encrypted value is present but {IDENTITY_ENV} is not set -- export the age identity "
            f"(the AGE-SECRET-KEY-1 string, an identity file, or a directory of *.age-identity files)")
    return _identities_for(value)


# ---------------------------------------------------------------- values

def decrypt_marker(marker: str, identities: Iterable | None = None) -> str:
    from age.file import Decryptor
    m = MARKER_RE.match(marker.strip())
    if not m:
        raise ValueError("not an ENC[age:...] marker")
    ids = tuple(identities) if identities is not None else identities_from_env()
    raw = base64.b64decode(m.group(1))
    last: Exception | None = None
    for ident in ids:
        try:
            with Decryptor([ident], io.BytesIO(raw)) as d:
                return d.read().decode("utf-8")
        except Exception as exc:                 # not a recipient of this value
            last = exc
    raise ValueError(f"no identity in {IDENTITY_ENV} can decrypt this value "
                     f"({len(ids)} tried; it was encrypted to other recipients)") from last


def encrypt_value(plaintext: str, recipients: Iterable[str]) -> str:
    from age.file import Encryptor
    from age.keys.agekey import AgePublicKey
    keys = [AgePublicKey.from_public_string(r) for r in recipients]
    if not keys:
        raise ValueError("no recipients: declare encryption.recipients in cfg/_config.yml")
    buf = io.BytesIO()
    with Encryptor(keys, buf) as e:
        e.write(plaintext.encode("utf-8"))
    return MARKER_PREFIX + base64.b64encode(buf.getvalue()).decode("ascii") + "]"


def _validate_encrypted_str(value: Any) -> str:
    """The whole validation of an ``EncryptedStr``: a plain validator, because
    pydantic's own ``str`` step would flatten the ``Decrypted`` subclass back to
    ``str`` and lose the hidden repr. Numbers are coerced to text the way
    ``CSIS_MODEL_CONFIG`` does for every other string field."""
    if isinstance(value, bool) or value is None:
        raise ValueError("a string is required")
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError(f"a string is required, not {type(value).__name__}")
    if is_marker(value):
        return Decrypted(decrypt_marker(value), marker=value)
    return value


# The field type. Composes: list[EncryptedStr] / set[EncryptedStr] /
# dict[str, EncryptedStr] decrypt each element on its own.
EncryptedStr = Annotated[str, PlainValidator(_validate_encrypted_str, json_schema_input_type=str)]


# ---------------------------------------------------------------- the tree

def recipients_from_config(root: Path) -> list[str]:
    """``encryption.recipients`` from the raw ``cfg/_config.yml`` -- read as
    text, not through the loader, so encrypting needs no identity."""
    import yaml
    cfg = root / "cfg" / "_config.yml"
    data = yaml.safe_load(cfg.read_text()) or {}
    recipients = ((data.get("encryption") or {}).get("recipients")) or []
    if not recipients:
        raise ValueError(f"{cfg}: no encryption.recipients declared")
    return [str(r) for r in recipients]


_SCALAR_RE = r"^(?P<indent>\s*(?:- )?)(?P<key>{key}):\s*(?P<value>\S.*?)\s*(?P<comment>#.*)?$"   # `key:` or `- key:`
_LIST_HEAD_RE = r"^(?P<indent>\s*)(?P<key>{key}):\s*(?P<comment>#.*)?$"
_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+(?P<value>\S.*?)\s*(?P<comment>#.*)?$")


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def encrypt_fields_in_text(text: str, field_names: Iterable[str], recipients: Iterable[str]) -> tuple[str, int]:
    """Encrypt, textually and in place, every scalar value of a mapping key
    named in ``field_names`` and every element of a block list under such a
    key. Comments, ordering and every other byte are preserved; a value that
    is already a marker, a template (``{{``), empty, or a nested block is left
    alone. Returns the new text and the count encrypted."""
    recipients = list(recipients)
    names = "|".join(re.escape(n) for n in field_names)
    scalar_re = re.compile(_SCALAR_RE.format(key=names))
    head_re = re.compile(_LIST_HEAD_RE.format(key=names))
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    count = 0
    in_list_indent: int | None = None
    for line in lines:
        body = line.rstrip("\n")
        if body.lstrip().startswith("#") or not body.strip():
            out.append(line)
            continue
        if in_list_indent is not None:
            m = _ITEM_RE.match(body)
            if m and len(m.group("indent")) > in_list_indent:
                v = _unquote(m.group("value"))
                if not is_marker(v) and "{{" not in v and not v.startswith(("[", "{")):
                    body = f"{m.group('indent')}- {encrypt_value(v, recipients)}" + (f"  {m.group('comment')}" if m.group("comment") else "")
                    count += 1
                out.append(body + ("\n" if line.endswith("\n") else ""))
                continue
            in_list_indent = None
        m = scalar_re.match(body)
        if m:
            v = _unquote(m.group("value"))
            if not is_marker(v) and "{{" not in v and not v.startswith(("[", "{", "|", ">", "&", "*")):
                body = f"{m.group('indent')}{m.group('key')}: {encrypt_value(v, recipients)}" + (f"  {m.group('comment')}" if m.group("comment") else "")
                count += 1
            out.append(body + ("\n" if line.endswith("\n") else ""))
            continue
        m = head_re.match(body)
        if m:
            in_list_indent = len(m.group("indent"))
        out.append(line)
    return "".join(out), count


def rotate_text(text: str, identities: Iterable, recipients: Iterable[str]) -> tuple[str, int]:
    """Re-encrypt every marker in ``text`` to ``recipients``; raises on the
    first marker the identities cannot open (nothing is returned partially)."""
    ids = tuple(identities)
    rec = list(recipients)
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        plain = decrypt_marker(m.group(0), ids)
        count += 1
        return encrypt_value(plain, rec)

    return INLINE_MARKER_RE.sub(_sub, text), count
