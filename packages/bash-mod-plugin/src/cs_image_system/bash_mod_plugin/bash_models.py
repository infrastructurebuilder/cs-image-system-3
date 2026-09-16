# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from pathlib import Path
from typing import Any, Type

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.mod_builder import ModBuilderModel
from cs_image_system.base.models.moditem_type import ModItemModel
BASH_EXECUTABLE: str = "bash"

BASH_BUILDER: str = "bash-remote"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class BashModItemModel(ModItemModel):
    """A shell-script modification (DESIGN §3M2).

    Attributes:
        script: inline command lines, run in order inside one
            ``provisioner "shell"`` (``inline = [...]``).
        scripts: script FILES (config-root-relative), copied beside the
            packer root and run as ``scripts = [...]``.
        ensure: a declarative, IDEMPOTENT form (EXPLORE "Generation of
            Idempotent Script-based Modifications") the plugin turns into
            guarded shell: ``packages: [..]``, ``files: [{path, content,
            mode}]``, ``services: [..]`` (enabled + started), ``commands:
            [{run, unless}]`` (run only when ``unless`` fails).
    At least one of the three must be given. Free-form ``script``/``scripts``
    are recorded as ``idempotent: unknown``; ``ensure``-only items as
    ``idempotent: declared``.
    """
    type = BASH_BUILDER
    script: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    ensure: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def csis_name(cls) -> str:
        return BASH_BUILDER

    def __post_init__(self) -> None:
        super().__post_init__()
        self.script = [str(s) for s in (self.script or []) if str(s).strip()]
        self.scripts = [str(s) for s in (self.scripts or []) if str(s).strip()]
        self.ensure = dict(self.ensure or {})
        unknown = set(self.ensure) - {"packages", "files", "services", "commands"}
        if unknown:
            raise ValueError(f"Bash modification '{self.get_display_name()}': unknown ensure keys {sorted(unknown)}")
        if not self.script and not self.scripts and not self.ensure:
            raise ValueError(
                f"Bash modification '{self.get_display_name()}' must supply 'script' (inline lines), "
                "'scripts' (script files) and/or 'ensure' (declarative, idempotent)")

    @property
    def idempotent(self) -> str:
        return "declared" if self.ensure and not self.script and not self.scripts else "unknown"

    def ensure_lines(self) -> list[str]:
        """Guarded shell for the declarative form: every step checks before it
        changes, so re-running is a no-op."""
        out: list[str] = []
        pkgs = [str(p) for p in self.ensure.get("packages", []) or []]
        if pkgs:
            joined = " ".join(pkgs)
            out.append(f"for p in {joined}; do rpm -q \"$p\" >/dev/null 2>&1 || dpkg -s \"$p\" >/dev/null 2>&1 || "
                       "{ command -v dnf >/dev/null 2>&1 && sudo dnf -y install \"$p\" || command -v yum >/dev/null 2>&1 && sudo yum -y install \"$p\" || sudo apt-get install -y \"$p\"; }; done")
        for f in self.ensure.get("files", []) or []:
            path = str(f["path"]); content = str(f.get("content", "")); mode = str(f.get("mode", "0644"))
            b64 = __import__("base64").b64encode(content.encode()).decode()
            out.append(f"printf '%s' '{b64}' | base64 -d > /tmp/.csis-ensure && "
                       f"( sudo cmp -s /tmp/.csis-ensure '{path}' || sudo install -m {mode} /tmp/.csis-ensure '{path}' ) && rm -f /tmp/.csis-ensure")
        for svc in self.ensure.get("services", []) or []:
            out.append(f"sudo systemctl is-enabled '{svc}' >/dev/null 2>&1 || sudo systemctl enable '{svc}'")
            out.append(f"sudo systemctl is-active '{svc}' >/dev/null 2>&1 || sudo systemctl start '{svc}'")
        for c in self.ensure.get("commands", []) or []:
            run = str(c["run"]); unless = c.get("unless")
            out.append(f"( {unless} ) >/dev/null 2>&1 || {{ {run}; }}" if unless else run)
        return out

    def remap_self_with_copied_assets(self, copied_assets: dict[str, Path]) -> None:
        """Point script files at their copies beside the packer root."""
        self.scripts = [str(copied_assets.get(s, s)) for s in self.scripts]


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class BashBuilderModel(ModBuilderModel):
    """Dataclass representing a Bash script modification.
    """
    type = BASH_BUILDER
    configuration_user: str | None = None  # Username to use for provisioning (if none use OSBuilder)
    extra_arguments: list[str] = field(default_factory=list) # Extra arguments to pass to bash
    # Optional packer shell-provisioner settings applied to every item.
    execute_command: str | None = None
    environment_vars: list[str] = field(default_factory=list)
    expect_disconnect: bool = False


    # TODO Add min version / max version for early validation (for weird playbooks/OS versions...)

    def get_target_deferred_type_by_VCT(self, vct: VCT) -> Type[BashModItemModel] | None:
        if vct == VCT.MOD_BUILDER_ITEM_MODEL:
            return BashModItemModel
        return None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class BashModBuilderModel(BashBuilderModel):

  @classmethod
  def csis_name(cls) -> str:
    return BASH_BUILDER
