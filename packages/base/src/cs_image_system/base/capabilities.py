# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Capability plumbing (DESIGN §3F1-F3, Q1, N4, N9-N12, N24).

* A base image declares ``identity_types`` and ``storage_types``; for each
  declared type the owning plugin contributes prerequisites baked at build
  time (installed, dormant).
* An instance image names only its owning group (Q4); the group's builder
  fixes the identity type. Attached storages resolve to the storage plugin's
  capability type.
* Effective capabilities resolve through PINS to the root base build's
  stamped capabilities (N11), inherited verbatim through the chain (N24);
  the YAML declaration is the truth only for a build that has not happened
  yet.
* The mandatory admin user carries operator-supplied PUBLIC keys; the
  schema hard-fails on anything resembling private-key material (N9).
"""
from __future__ import annotations

import re
from dataclasses import field
from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import TYPE_CHECKING, Any

from .basic.builder_base_group import GroupBuilderBase
from .basic.builder_base_storage import StorageBuilderBase
from .encryption import like
from .constants import SELF

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext
    from .models.base_image import BaseImage
    from .models.image import Image

ADMIN_KEYS_CONFIG_KEY = "admin_public_keys"

_PUBLIC_KEY = re.compile(
    r"^(ssh-(rsa|dss|ed25519)|ecdsa-sha2-nistp(256|384|521)|sk-(ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)"
    r"\s+[A-Za-z0-9+/=]+(\s+\S.*)?$")
_PRIVATE_MARKER = re.compile(r"PRIVATE KEY", re.IGNORECASE)


def validate_public_key(key: str) -> str | None:
    """None when ``key`` is a well-formed SSH public key, else the reason."""
    text = str(key or "").strip()
    if not text:
        return "empty key"
    if _PRIVATE_MARKER.search(text) or text.startswith("-----BEGIN"):
        return "PRIVATE key material (never allowed; the config repo is public)"
    if "\n" in text:
        return "multi-line value is not a public key"
    if not _PUBLIC_KEY.match(text):
        return "not an OpenSSH public key line (ssh-ed25519/ssh-rsa/ecdsa-sha2-* AAAA...)"
    return None


@dataclass(config=CSIS_MODEL_CONFIG)
class EffectiveCapabilities:
    identity_types: list[str]
    storage_types: list[str]
    root_base: str
    source: str            # "pin:<build id>" or "declaration"
    chain: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"identity_types": list(self.identity_types), "storage_types": list(self.storage_types),
                "root_base": self.root_base, "source": self.source, "chain": list(self.chain)}


# ------------------------------------------------------------- lookups

def group_builders_by_identity_type(ctx: "GlobalTypeContext") -> dict[str, list[GroupBuilderBase]]:
    """``{identity type: [group builders]}``. Callers bake and verify with
    the FIRST builder of a type, so a builder that manages its groups comes
    before a lookup-only one, then by name (stage 63 item 18: by name alone,
    a read-only builder called ``okta-groups-ro`` sorted before the managed
    ``oktagroups`` and its name went into every base image's bake)."""
    out: dict[str, list[GroupBuilderBase]] = {}
    for name in sorted(ctx.group_builders):
        b = ctx.group_builders[name]
        if isinstance(b, GroupBuilderBase):
            out.setdefault(b.identity_type(), []).append(b)
    for builders in out.values():
        builders.sort(key=lambda b: not b.manages_groups())     # stable: name order within each kind
    return out


def storage_builders_by_type(ctx: "GlobalTypeContext") -> dict[str, list[StorageBuilderBase]]:
    out: dict[str, list[StorageBuilderBase]] = {}
    for name in sorted(ctx.storage_builders):
        b = ctx.storage_builders[name]
        if isinstance(b, StorageBuilderBase):
            out.setdefault(b.capability_type(), []).append(b)
    return out


def group_builder_of(ctx: "GlobalTypeContext", group: str) -> GroupBuilderBase | None:
    for name in sorted(ctx.group_builders):
        b = ctx.group_builders[name]
        if isinstance(b, GroupBuilderBase) and any(g.get_name() == group for g in b.get_groups_for_builder()):
            return b
    return None


def identity_type_of_group(ctx: "GlobalTypeContext", group: str) -> str | None:
    b = group_builder_of(ctx, group)
    return b.identity_type() if b is not None else None


def storage_type_of(ctx: "GlobalTypeContext", storage_name: str) -> str | None:
    for s in ctx.storages:
        if s.get_name() == storage_name:
            b = ctx.storage_builders.get(s.type_)
            return b.capability_type() if isinstance(b, StorageBuilderBase) else None
    return None


# ---------------------------------------------------------------- chains

def image_chain(ctx: "GlobalTypeContext", image: "Image") -> tuple[list[str], str | None]:
    """Follow ``source_image`` links: ``([image, parent, ...], root base name)``.
    The root is the first name that is an OS builder (a base image)."""
    chain: list[str] = []
    name: str | None = image.get_name()
    images = ctx.images_map
    seen: set[str] = set()
    while name and name not in seen:
        seen.add(name)
        if name in ctx.os_builders:
            return chain, name
        chain.append(name)
        img = images.get(name)
        if img is None:
            return chain, None
        src = img.source_image
        name = None if not src or src == SELF else str(src)
    return chain, None


def declared_capabilities(ctx: "GlobalTypeContext", base_name: str) -> dict[str, list[str]]:
    osb = ctx.os_builders.get(base_name)
    if osb is None:
        return {"identity_types": [], "storage_types": []}
    return {"identity_types": sorted(osb.model.get_identity_types()),
            "storage_types": sorted(osb.model.get_storage_types())}


def effective_capabilities(ctx: "GlobalTypeContext", image: "Image",
                           runtime: str | None = None) -> EffectiveCapabilities | None:
    """N11/N24: resolve through the pin chain to the root base build's stamp;
    without a pinned, recorded build the current declaration governs (it
    describes the build that is about to happen)."""
    chain, root = image_chain(ctx, image)
    if root is None:
        return None
    ms = ctx.meta_state
    # Walk the chain's pins from the image toward the root: the first image
    # whose pin resolves to a recorded build supplies the stamp.
    for name in chain:
        pin = ms.image_pin(name, runtime)
        if not pin:
            continue
        record = ms.build(pin)
        if record and record.get("capabilities"):
            caps = record["capabilities"]
            return EffectiveCapabilities(
                identity_types=sorted(caps.get("identity_types", [])),
                storage_types=sorted(caps.get("storage_types", [])),
                root_base=root, source=f"pin:{pin}", chain=chain)
    decl = declared_capabilities(ctx, root)
    return EffectiveCapabilities(identity_types=decl["identity_types"],
                                 storage_types=decl["storage_types"],
                                 root_base=root, source="declaration", chain=chain)


# ------------------------------------------------------------- admin keys

def admin_public_keys(ctx: "GlobalTypeContext", base: "BaseImage | None" = None,
                      os_builder_name: str | None = None) -> list[str]:
    """Per-base-image override, else the global list (N12)."""
    override: list[str] | None = None
    if base is not None:
        override = base.admin_public_keys
    elif os_builder_name and os_builder_name in ctx.os_builders:
        override = ctx.os_builders[os_builder_name].model.get_admin_public_keys()
    # `like` keeps a decrypted value's ciphertext across the strip (stage 49):
    # str()/strip() on a str subclass returns a plain str, and the marker is
    # what tells the emission to write the ciphertext rather than the key.
    if override is not None:
        return [like(k, str(k).strip()) for k in override if str(k).strip()]
    keys = ctx.config.get(ADMIN_KEYS_CONFIG_KEY) or []
    if isinstance(keys, str):
        keys = [keys]
    return [like(k, str(k).strip()) for k in keys if str(k).strip()]


def admin_user(ctx: "GlobalTypeContext", os_builder_name: str) -> str:
    osb = ctx.os_builders.get(os_builder_name)
    return osb.model.get_admin_user() if osb is not None else "csisadmin"
