# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Declarative OS update policy for base images (EXPLORE "More Targeted
Updates?").

``dnf -y update`` everything is heavy-handed and breaks things. A base
image now declares WHAT to update:

.. code-block:: yaml

    os_builders:
      - name: basic-rhel-8
        update:
          policy: security            # none | security | packages | full
          packages: [openssl, curl]   # policy=packages: exactly these; else: also these
          exclude: ["kernel*"]        # never touched by any policy
          pin: {glibc: "2.28-236.el8"} # explicit versions, installed and locked

The OS plugin translates the policy into family-specific commands; the
build's lineage record carries the policy and the bake writes a package
manifest (``/var/lib/csis/packages.txt``) so the package set of every
build is known. ``auto_update: true`` remains an alias for
``policy: full``. Updates apply to BASE images only (instance images bake
"the same base, refreshed modifications" -- N17).
"""
from __future__ import annotations

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

POLICY_NONE = "none"
POLICY_SECURITY = "security"
POLICY_PACKAGES = "packages"
POLICY_FULL = "full"
POLICIES = (POLICY_NONE, POLICY_SECURITY, POLICY_PACKAGES, POLICY_FULL)

PACKAGE_MANIFEST_PATH = "/var/lib/csis/packages.txt"


@dataclass(frozen=True, config=CSIS_MODEL_CONFIG)
class UpdatePolicy:
    policy: str = POLICY_NONE
    packages: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    pin: tuple[tuple[str, str], ...] = ()   # (package, version) pairs, sorted
    # Convergent bakes (stage 9): re-bake when the series head is at least this
    # old -- the only way package updates (invisible to the input fingerprint)
    # reach a new build without a config change. None = never by age.
    refresh_days: int | None = None

    @classmethod
    def from_config(cls, cfg: Any, auto_update: bool = False) -> "UpdatePolicy":
        if cfg is None:
            return cls(policy=POLICY_FULL if auto_update else POLICY_NONE)
        # a bare policy name (`update: none`) is refused when the structure
        # loads (the field is a mapping); stage 63 removed the branch that
        # pretended to accept one here
        if not isinstance(cfg, dict):
            raise ValueError(f"update: must be a mapping (`update: {{policy: <name>}}`), got {type(cfg).__name__}")
        policy = str(cfg.get("policy", POLICY_FULL if auto_update else POLICY_NONE)).strip().lower()
        pins = cfg.get("pin") or {}
        return cls(
            policy=policy,
            packages=tuple(str(p) for p in (cfg.get("packages") or [])),
            exclude=tuple(str(p) for p in (cfg.get("exclude") or [])),
            pin=tuple(sorted((str(k), str(v)) for k, v in dict(pins).items())),
            refresh_days=int(cfg["refresh_days"]) if cfg.get("refresh_days") is not None else None,
        )

    def validate(self, where: str) -> list[str]:
        errors: list[str] = []
        if self.policy not in POLICIES:
            errors.append(f"{where}: update.policy {self.policy!r} is not one of {POLICIES}")
        if self.policy == POLICY_PACKAGES and not self.packages and not self.pin:
            errors.append(f"{where}: update.policy 'packages' needs update.packages and/or update.pin")
        for p, v in self.pin:
            if not v or " " in v:
                errors.append(f"{where}: update.pin[{p}] must be a version string")
        bad = set(self.packages) & set(self.exclude)
        if bad:
            errors.append(f"{where}: packages both updated and excluded: {sorted(bad)}")
        if self.refresh_days is not None and self.refresh_days <= 0:
            errors.append(f"{where}: update.refresh_days must be a positive number of days")
        return errors

    @property
    def is_noop(self) -> bool:
        return self.policy == POLICY_NONE and not self.pin

    def as_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "packages": list(self.packages), "exclude": list(self.exclude),
                "pin": {k: v for k, v in self.pin},
                **({"refresh_days": self.refresh_days} if self.refresh_days is not None else {})}


def manifest_commands() -> list[str]:
    """Record the package set of the build (rpm or dpkg) for lineage/debugging."""
    return [
        "sudo mkdir -p /var/lib/csis",
        "( rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\\n' 2>/dev/null || dpkg-query -W -f='${Package}=${Version}\\n' ) "
        f"| sort | sudo tee {PACKAGE_MANIFEST_PATH} >/dev/null",
    ]
