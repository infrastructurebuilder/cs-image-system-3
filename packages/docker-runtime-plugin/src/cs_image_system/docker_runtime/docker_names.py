# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The spellings a container daemon accepts (stage 103), mapped ONCE here.

* a **repository** name is lowercase: ``[a-z0-9]`` with single ``.``, ``_``,
  ``__`` or ``-`` separators, path components joined by ``/``;
* a **tag** is ``[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}``: at most 128
  characters, and a build's final name (``<prefix>-<timestamp>``) is written
  as one, so a name that would be cut is refused rather than cut (the cut
  would fall where the timestamp is);
* a **label** key is a string without whitespace or ``=``; the OCI convention
  is lowercase reverse-DNS, but the system's ``csis_*`` keys and a tree's
  own are accepted as written.

A build is identified by its IMAGE ID (``sha256:<64 hex>``), which tags
move around; the lineage build id on this runtime is that id.
"""
from __future__ import annotations

import re

TAG_MAX = 128
_TAG_BAD = re.compile(r"[^A-Za-z0-9_.-]+")
_REPO_BAD = re.compile(r"[^a-z0-9._/-]+")
_IMAGE_ID = re.compile(r"^(sha256:)?[0-9a-f]{64}$")
_DIGEST_REF = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


def tag_name(value: str) -> str:
    """A valid docker tag derived deterministically from ``value``: what it
    cannot keep becomes ``-``, a separator may not lead. Not shortened."""
    v = _TAG_BAD.sub("-", str(value)).strip(".-")
    if not v:
        return "i"
    if not (v[0].isalnum() or v[0] == "_"):
        v = f"i{v}"
    return v


def tag_problem(name: str) -> str | None:
    """Why ``name``, once made a tag, cannot be one: only its length."""
    made = tag_name(name)
    if len(made) > TAG_MAX:
        return (f"a docker tag is at most {TAG_MAX} characters; {name!r} becomes {made!r} ({len(made)}) "
                f"and would be cut where the timestamp is")
    return None


def repository_name(value: str) -> str:
    """A valid repository name derived from ``value``: lowercase, what it
    cannot keep becomes ``-``, separators never doubled or leading."""
    v = _REPO_BAD.sub("-", str(value).lower())
    v = re.sub(r"[._-]{2,}", "-", v).strip("._-/")
    return v or "csis"


def label_key_problem(key: str) -> str | None:
    """Why ``key`` cannot be a docker label key, or None."""
    k = str(key)
    if not k.strip():
        return "a docker label key cannot be empty"
    if any(c.isspace() for c in k):
        return f"a docker label key carries no whitespace; {key!r} does"
    if "=" in k:
        return f"a docker label key carries no '='; {key!r} does"
    return None


def is_image_id(value: str) -> bool:
    return bool(_IMAGE_ID.match(str(value).strip()))


def is_digest_reference(value: str) -> bool:
    """``<repository>@sha256:<digest>``: the form ``image_id`` pins."""
    return bool(_DIGEST_REF.match(str(value).strip()))


def short_id(image_id: str) -> str:
    """The twelve hex characters the CLI shows for an image id."""
    v = str(image_id).strip()
    v = v.split(":", 1)[1] if v.startswith("sha256:") else v
    return v[:12]


def full_id(image_id: str) -> str:
    """The ``sha256:``-prefixed form of an image id the CLI printed."""
    v = str(image_id).strip()
    return v if v.startswith("sha256:") else f"sha256:{v}"


# tags that carry what a label cannot change after the build (stage 103,
# decision 4: labels are fixed when an image is built, so release and
# relabel MOVE TAGS): `<repository>:<short id>--<key>--<value as tag>`
MOVABLE_SEP = "--"


def movable_tag(image_id: str, key: str, value: str) -> str:
    return f"{short_id(image_id)}{MOVABLE_SEP}{tag_name(key)}{MOVABLE_SEP}{tag_name(value)}"


_ID_AS_TAG = re.compile(r"^sha256-([0-9a-f]{64})$")


def movable_value_decoded(value: str) -> str:
    """A movable tag's value as it was given: an image id written as a tag
    lost its colon (``sha256-<hex>``), and gets it back; anything else is
    returned as it stands (found live: the state query compared the
    lineage's ``sha256:...`` parent with the tag's ``sha256-...``)."""
    m = _ID_AS_TAG.match(str(value))
    return f"sha256:{m.group(1)}" if m else str(value)


def parse_movable_tag(tag: str) -> tuple[str, str, str] | None:
    """``(short id, key, value)`` of a movable tag, or None for any other;
    the value is decoded (``movable_value_decoded``)."""
    parts = str(tag).split(MOVABLE_SEP, 2)
    if len(parts) != 3 or not re.fullmatch(r"[0-9a-f]{12}", parts[0]) or not parts[1] or not parts[2]:
        return None
    return parts[0], parts[1], movable_value_decoded(parts[2])
