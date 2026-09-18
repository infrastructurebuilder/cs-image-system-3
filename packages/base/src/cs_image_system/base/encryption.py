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


class EncryptedKeyError(ValueError):
    """A marker used as a MAPPING KEY. Keys select, dedupe and name things --
    list entries are deduped by ``name``, concrete classes dispatch on
    ``type``, generated directories are named from both -- so a key must be
    readable without an identity."""


class InlineMarkerError(ValueError):
    """A marker EMBEDDED in a longer string. Only a whole value decrypts: a
    composite carries no single ciphertext, so the emission could not refer to
    one and would write the secret in clear."""


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


# ------------------------------------------------------- the tree (stage 49)

#: Keys whose values are read by the RAW readers -- the ones that run before
#: the loader, or without it, and several of which must work with no identity
#: at all. A marker at one of these is refused by name rather than silently
#: becoming a bogus profile name or an unreadable allow list.
#:
#: Each entry is a dotted path from a configuration document's root; a ``[]``
#: segment matches every element of a list.
EXEMPT_PATHS: tuple[str, ...] = (
    "encryption.recipients[]",          # recipients_from_config: encrypting must need no identity
    "public_safe.allow[]",              # allow_from_config: the gate must not depend on a load
    "runtime_builders[].name",          # preflight.raw_session_infos: sessions are checked before the load
    "runtime_builders[].type",
    "runtime_builders[].profile",
    "runtime_builders[].credentials.profile_name",
    "config.preflight.expected_run_minutes",
    "config.apply_instances",           # cli apply-check reads cfg/_config.yml raw
    "config.apply_storage",
    "config.apply_identity",
)

#: Every list of declarations in a ``cfg/`` document is deduped by ``name``
#: and dispatched by ``type``; both must be readable without an identity.
EXEMPT_ENTRY_KEYS: frozenset[str] = frozenset({"name", "type"})


#: Every marker this process has opened, and what it opened to. The system
#: knows this by construction -- it did the decrypting -- so the emission guard
#: can search the committed output for those exact plaintexts instead of
#: guessing at shapes, CI can mask exactly them, and :func:`substitute_markers`
#: can materialise an emission without decrypting a second time. Run-scoped;
#: never written anywhere.
_OPENED: dict[str, str] = {}

#: plaintext -> the configuration keys it was read under. A value is exempt
#: from the emission guard only when EVERY key it ever appeared under is
#: public by decision, so a name that is also declared as an email is not.
_OPENED_KEYS: dict[str, set[str]] = {}

#: Public by decision since stage 34: "no declared-encrypted value other than a
#: USERNAME in clear". A username is emitted as a quoted literal in the okta
#: group module call and stands in the identity read-model, because it is the
#: join key between a roster and an access grant. Every other decrypted value
#: is refused in the emission.
PUBLIC_BY_DECISION_KEYS: frozenset[str] = frozenset({"name", "members", "admins"})


def decrypted_plaintexts(include_public_by_decision: bool = False) -> set[str]:
    """The run's plaintext set -- what must not appear in a committed file.

    Values read ONLY under :data:`PUBLIC_BY_DECISION_KEYS` are left out: a
    username is emitted in clear by the stage-34 decision. Pass
    ``include_public_by_decision`` for the masking pass, where hiding a
    username from a log costs nothing."""
    if include_public_by_decision:
        return set(_OPENED.values())
    return {plain for plain in _OPENED.values()
            if not (_OPENED_KEYS.get(plain, set()) <= PUBLIC_BY_DECISION_KEYS)}


def opened_markers() -> dict[str, str]:
    """Marker -> plaintext, for everything opened so far."""
    return dict(_OPENED)


def reset_decrypted_plaintexts() -> None:
    _OPENED.clear()
    _OPENED_KEYS.clear()


def substitute_markers(text: str, identities: Iterable | None = None) -> str:
    """``text`` with every embedded marker replaced by its plaintext.

    This is what turns a committed emission into the private copy the tools
    run from, and what the lineage fingerprint hashes so a rotation -- which
    mints new ciphertext for the same plaintext -- does not move it. Markers
    already opened come from the map; any other is decrypted here."""
    def _sub(m: re.Match) -> str:
        marker = m.group(0)
        plain = _OPENED.get(marker)
        if plain is None:
            plain = decrypt_marker(marker, identities)
            _OPENED[marker] = plain
        return plain

    return INLINE_MARKER_RE.sub(_sub, text)


def like(original: Any, text: str) -> Any:
    """``text``, carrying ``original``'s ciphertext if it had one.

    For the places that reshape a value -- a strip, a case fold -- and would
    otherwise hand back a plain ``str`` and lose the marker."""
    marker = getattr(original, "marker", None)
    return Decrypted(text, marker=marker) if marker else text


def emit(value: Any) -> Any:
    """What an EMISSION writes for ``value``: the ciphertext it was read from
    when it carries one, else the value itself (stage 49).

    The committed artifact therefore says ``ENC[age:...]`` wherever the
    configuration did, and :func:`materialize` substitutes the plaintext into
    the private mirror the tools actually run from. Age is randomised, so the
    SOURCE marker is reused rather than re-encrypted: re-encrypting would move
    every emitted byte on every run."""
    return getattr(value, "marker", None) or value


def _path_str(path: tuple[Any, ...]) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "<root>"


def _exempt_pattern(path: tuple[Any, ...]) -> str:
    """``path`` as an EXEMPT_PATHS pattern: list indices collapse to ``[]``."""
    out = ""
    for part in path:
        if isinstance(part, int):
            out += "[]"
        else:
            out += f".{part}" if out else str(part)
    return out


def refuse_markers_at(doc: Any, source: str) -> None:
    """Refuse a marker where one may never stand (stage 49). Needs NO identity:
    it is a structural check, so it still runs when nothing can be decrypted.

    Refused: any key in :data:`EXEMPT_PATHS`; the ``name`` or ``type`` of a
    declaration in any top-level list; a marker used as a mapping key.
    """
    def walk(node: Any, path: tuple[Any, ...], entry_depth: int | None) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if is_marker(key):
                    raise EncryptedKeyError(
                        f"{source}: {_path_str(path)}: a mapping KEY may not be encrypted")
                here = path + (str(key),)
                if is_marker(value):
                    if _exempt_pattern(here) in EXEMPT_PATHS:
                        raise ValueError(
                            f"{source}: {_path_str(here)}: this value may not be encrypted -- it is read "
                            f"before the configuration loads, with no identity available")
                    if entry_depth is not None and len(here) == entry_depth and str(key) in EXEMPT_ENTRY_KEYS:
                        raise ValueError(
                            f"{source}: {_path_str(here)}: a declaration's '{key}' may not be encrypted -- "
                            f"it names and dispatches the entry")
                walk(value, here, entry_depth)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                here = path + (idx,)
                if is_marker(item) and _exempt_pattern(here) in EXEMPT_PATHS:
                    raise ValueError(
                        f"{source}: {_path_str(here)}: this value may not be encrypted -- it is read "
                        f"before the configuration loads, with no identity available")
                # a top-level list is a list of DECLARATIONS: its entries' name/type are keys
                depth = len(here) + 1 if len(path) == 1 else entry_depth
                walk(item, here, depth)

    walk(doc, (), None)


def decrypt_tree(data: Any, source: str = "<configuration>",
                 identities: Iterable | None = None,
                 collect: set[str] | None = None) -> Any:
    """``data`` with every whole-value marker replaced by its
    :class:`Decrypted` (stage 49).

    Any value anywhere may be a marker -- not only the fields typed
    :data:`EncryptedStr` -- and the ``Decrypted`` remembers the ciphertext it
    came from, so the emission can write that back (:func:`emit`). Identities
    are resolved LAZILY, on the first marker seen, so a tree with no markers
    still loads with no :data:`IDENTITY_ENV` set. A marker as a mapping key or
    embedded inside a longer string is refused, naming its path; a refusal to
    decrypt names the path too, which a pydantic field name could not.

    ``collect``, when given, receives every plaintext produced -- the run's
    plaintext set, which the emission guard searches the committed output for.
    """
    ids: list = list(identities) if identities is not None else []
    resolved = identities is not None

    def opener() -> Iterable:
        nonlocal ids, resolved
        if not resolved:
            ids = list(identities_from_env())
            resolved = True
        return ids

    def walk(node: Any, path: tuple[Any, ...]) -> Any:
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if is_marker(key):
                    raise EncryptedKeyError(
                        f"{source}: {_path_str(path)}: a mapping KEY may not be encrypted")
                out[key] = walk(value, path + (str(key),))
            return out
        if isinstance(node, list):
            return [walk(v, path + (i,)) for i, v in enumerate(node)]
        if isinstance(node, tuple):
            return tuple(walk(v, path + (i,)) for i, v in enumerate(node))
        if isinstance(node, set):
            return {walk(v, path) for v in node}
        if isinstance(node, Decrypted):          # already opened: idempotent
            return node
        if isinstance(node, str):
            text = node.strip()
            if is_marker(text):
                try:
                    plain = decrypt_marker(text, opener())
                except MissingIdentityError as exc:
                    raise MissingIdentityError(f"{source}: {_path_str(path)}: {exc}") from exc
                except ValueError as exc:
                    raise ValueError(f"{source}: {_path_str(path)}: {exc}") from exc
                _OPENED[text] = plain
                key = next((p for p in reversed(path) if isinstance(p, str)), "")
                _OPENED_KEYS.setdefault(plain, set()).add(key)
                if collect is not None:
                    collect.add(plain)
                return Decrypted(plain, marker=text)
            if INLINE_MARKER_RE.search(node):
                raise InlineMarkerError(
                    f"{source}: {_path_str(path)}: an encrypted value is embedded in a longer string; "
                    f"make the marker the ENTIRE value (a composite carries no ciphertext, so the "
                    f"emission would write the secret in clear)")
        return node

    return walk(data, ())
