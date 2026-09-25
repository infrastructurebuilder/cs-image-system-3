# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import re
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


ENSURE_KINDS: dict[str, str] = {
    "packages": "a list of package names",
    "files": "a list of {path, content, mode} mappings",
    "services": "a list of systemd unit names",
    "commands": "a list of {run, unless} mappings",
}
_FILE_KEYS = {"path", "content", "mode"}
_COMMAND_KEYS = {"run", "unless"}
_MODE_TEXT = re.compile(r"^[0-7]{3,4}$")


def _mode_text(mode: Any) -> str:
    """A file mode as the four-digit octal text ``install -m`` takes.

    YAML reads an unquoted ``0644`` as the integer 420, so an integer is
    rendered back in octal (stage 63 item 16, decided 2026-09-25); a
    string must already be three or four octal digits."""
    if isinstance(mode, bool):
        raise ValueError(f"mode {mode!r} is not a file mode")
    if isinstance(mode, int):
        return f"{mode:04o}"
    return str(mode)


def _names(label: str, kind: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label}: ensure.{kind} must be {ENSURE_KINDS[kind]}, "
                         f"not {type(value).__name__} {value!r} (write `{kind}: [{value}]` for one)")
    out: list[str] = []
    for i, v in enumerate(value):
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{label}: ensure.{kind}[{i}] must be a non-empty name, not {v!r}")
        out.append(v)
    return out


def _entries(label: str, kind: str, value: Any, allowed: set[str], required: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label}: ensure.{kind} must be {ENSURE_KINDS[kind]}, not {type(value).__name__}")
    for i, entry in enumerate(value):
        where = f"{label}: ensure.{kind}[{i}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where} must be a mapping ({ENSURE_KINDS[kind]}), not {entry!r}")
        unknown = set(entry) - allowed
        if unknown:
            raise ValueError(f"{where}: unknown keys {sorted(unknown)} (allowed: {sorted(allowed)})")
        req = entry.get(required)
        if not isinstance(req, str) or not req.strip():
            raise ValueError(f"{where}: `{required}` is required and must be non-empty text")
        for k, v in entry.items():
            if k in (required, "mode"):
                continue
            if v is not None and not isinstance(v, str):
                raise ValueError(f"{where}: `{k}` must be text, not {type(v).__name__} {v!r}")
    return value


def validate_ensure(label: str, ensure: Any) -> dict[str, Any]:
    """Every ``ensure`` entry checked at load, one rule per kind (stage 63
    item 16). A valid mapping comes back UNCHANGED except that an integer
    file mode becomes its octal text: the lineage fingerprint hashes this
    mapping, so a tree that was already valid keeps every fingerprint.

    Refused: an unknown kind; a kind that is not a list (``packages: git``
    iterated the letters); an entry of the wrong shape or with unknown keys
    (a missing ``path`` or ``run`` was a ``KeyError`` at generation); a mode
    that is not three or four octal digits; an integer mode above 0777 (an
    unquoted ``644`` is the decimal number, not the mode); and an
    ``ensure`` whose kinds are all empty (it loaded as ``idempotent:
    declared`` and emitted nothing)."""
    label = f"Bash modification '{label}'"
    if ensure is None:
        return {}
    if not isinstance(ensure, dict):
        raise ValueError(f"{label}: ensure must be a mapping of {sorted(ENSURE_KINDS)}, not {ensure!r}")
    ensure = dict(ensure)
    if not ensure:
        return {}
    unknown = set(ensure) - set(ENSURE_KINDS)
    if unknown:
        raise ValueError(f"{label}: unknown ensure keys {sorted(unknown)} (allowed: {sorted(ENSURE_KINDS)})")
    for kind in ("packages", "services"):
        if ensure.get(kind) is not None:
            _names(label, kind, ensure[kind])
    if ensure.get("files") is not None:
        files = _entries(label, "files", ensure["files"], _FILE_KEYS, "path")
        fixed: list[dict[str, Any]] = []
        for i, f in enumerate(files):
            if "mode" in f and f["mode"] is not None:
                mode = f["mode"]
                if isinstance(mode, int) and not isinstance(mode, bool) and not 0 <= mode <= 0o777:
                    raise ValueError(f"{label}: ensure.files[{i}].mode {mode} is not a mode YAML could have "
                                     f"read from octal (an unquoted `644` is the decimal number); quote it: \"0644\"")
                text = _mode_text(mode)
                if not _MODE_TEXT.match(text):
                    raise ValueError(f"{label}: ensure.files[{i}].mode {mode!r} must be three or four octal digits")
                f = {**f, "mode": text} if isinstance(mode, int) else f
            fixed.append(f)
        ensure["files"] = fixed
    if ensure.get("commands") is not None:
        _entries(label, "commands", ensure["commands"], _COMMAND_KEYS, "run")
    if not any(ensure.get(k) for k in ENSURE_KINDS):
        raise ValueError(f"{label}: ensure declares {sorted(ensure)} but every one is empty, so it would "
                         f"emit nothing; remove `ensure` or give it an entry")
    return ensure


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
        self.ensure = validate_ensure(self.get_display_name(), self.ensure)
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
            # stage 63 item 16: the FIRST package manager that exists installs,
            # and its failure is the failure (the old chain fell through dnf,
            # yum and apt-get, so an EL host showed `apt-get: command not found`)
            out.append(f"for p in {joined}; do rpm -q \"$p\" >/dev/null 2>&1 || dpkg -s \"$p\" >/dev/null 2>&1 || "
                       "if command -v dnf >/dev/null 2>&1; then sudo dnf -y install \"$p\"; "
                       "elif command -v yum >/dev/null 2>&1; then sudo yum -y install \"$p\"; "
                       "elif command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y \"$p\"; "
                       "else echo \"csis ensure: no dnf, yum or apt-get to install $p\" >&2; false; fi || exit 1; done")
        for f in self.ensure.get("files", []) or []:
            path = str(f["path"]); content = str(f.get("content", "")); mode = _mode_text(f.get("mode", "0644"))
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
