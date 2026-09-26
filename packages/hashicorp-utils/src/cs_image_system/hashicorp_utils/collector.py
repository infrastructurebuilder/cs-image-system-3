# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Run-scoped collectors for terraform and packer configuration.

Plugins declare what they need ("provider Y at version X configured with
A/B/C"); the collectors dedupe per workspace (= builder name / HCL root dir),
merge version constraints, abort on unresolvable conflicts (per-workspace AND
run-wide), and generate in-memory HCL line lists. Nothing here writes files —
builders wrap the generated lines in Asset/AssetSet objects.

Both collectors are @singleton with Registry-style ``_init_state()`` /
``reset()`` so registrations persist for the duration of a run and can be
consumed across plugins (e.g. tf-ebs-instance referencing tf-s3-state's
backend registrations).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Mapping, Protocol

import hcl2
from hcl2 import Builder

from cs_image_system.base.constants import DEFAULT, OOPS_DEFAULTS
from cs_image_system.base.singleton import singleton
from cs_image_system.base.utils import super_safe_name as ssn

from .blocks import BlockSpec, DataSpec, Raw, render_blocks
from .blocks import hcl_value as _hcl_value
from .hashicorp import FO, QString, packer_variable
from .versions import HclConfigConflictError, assert_satisfiable

log = logging.getLogger(__name__)

# stage 34: a value the emission must not carry in plaintext is emitted as the
# SAME ENC[age:...] ciphertext the configuration carries, and terraform decrypts
# it at plan time through one `data "external"` per root whose program is the
# system's own decrypt command, with the identity from CSIS_CONFIG_IDENTITY in
# the runner's environment. The committed emission is readable by anyone and
# decryptable only by a recipient; plans and state hold the plaintext, which is
# why they are never committed.
SENSITIVE_LABEL = "sensitive"
SENSITIVE_PROGRAM = ("cs-image-system", "decrypt", "--json")
EXTERNAL_PROVIDER = "external"


# --------------------------------------------------------------------------
# Declaration dataclasses
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderRequirement:
    """One workspace's requirement on a terraform provider."""
    name: str
    source: str | None = None
    version: str | None = None
    requested_by: str | None = None


@dataclass
class ConfiguredTerraformProvider:
    """A provider requirement together with its provider-block configuration."""
    name: str
    source: str
    version: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Arguments for a ``provider "<name>" {}`` block."""
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    alias: str | None = None


@dataclass
class TerraformVariable:
    name: str
    type: str = "string"
    default: Any | None = None
    description: str | None = None
    sensitive: bool = False


@dataclass(frozen=True)
class StateLocation:
    """Where one workspace keeps its state (stage 46): the tuple (backend type,
    container, key), normalised so that two spellings of one place compare
    equal -- repeated slashes collapsed, leading and trailing ones stripped,
    case kept (object keys are case-sensitive), ``.`` and ``..`` segments
    refused. The container is what the type addresses (an S3 or GCS bucket, a
    local directory) and the key the state object within it; the type decides
    both (stage 47), which is why ``BUCKET1//xyz`` and ``BUCKET1/xyz`` are one
    location and the emitted key is the normalised one."""
    type: str
    container: str
    key: str

    @staticmethod
    def normalise_key(key: str | None) -> str:
        segments = [s for s in (key or "").split("/") if s]
        for s in segments:
            if s in (".", ".."):
                raise ValueError(f"state key {key!r} carries a {s!r} segment")
        return "/".join(segments)

    @classmethod
    def of(cls, type: str, container: str, prefix: str | None, workspace: str) -> "StateLocation":
        """The object-store convention: ``<prefix>/<workspace>.tfstate``, the
        workspace name made safe, the prefix normalised."""
        return cls(type=type, container=container, key=cls.normalise_key(f"{prefix or ''}/{ssn(workspace)}.tfstate"))

    @property
    def bucket(self) -> str:
        """The container, under the name the object-store types give it."""
        return self.container

    def __str__(self) -> str:
        return f"{self.type}://{self.container}/{self.key}"


def render_backend_value(v: Any) -> str:
    """One backend-file value in HCL: bools lower-case, numbers bare,
    lists and maps (the s3 backend's ``assume_role``/``endpoints`` are
    object attributes) recursively, strings quoted and escaped. A
    decrypted setting is written as the ciphertext it was read from
    (stage 63; it was written in clear, and only the plaintext guard
    caught it); ``materialize`` restores it in the private copy."""
    from cs_image_system.base.encryption import emit
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(render_backend_value(x) for x in v) + "]"
    if isinstance(v, dict):
        inner = ", ".join(f"{k} = {render_backend_value(x)}" for k, x in v.items())
        return "{ " + inner + " }"
    text = str(emit(v)).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


class BackendKind(Protocol):
    """What a state backend TYPE knows (stage 47.1): where a workspace's state
    lives, the settings its partial configuration file needs, and the
    settings a consumer's remote-state data source needs -- which differ (a
    data source has no ``encrypt`` or ``use_lockfile``). A state plugin
    supplies one per type it declares; the collector renders whatever the
    kind returns and names no field of its own."""
    type: str

    def location(self, settings: Mapping[str, Any], workspace: str) -> StateLocation: ...

    def backend_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]: ...

    def remote_state_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BackendRegistration:
    """A state backend made available for the run (registered by a state
    plugin): what every backend has -- a name, a type, whether it is the
    default -- plus the type's own settings as an opaque mapping, and the kind
    that renders them (stage 47.1). Equality is the declaration (name, type,
    settings, default); the kind is behaviour."""
    name: str
    type: str
    settings: dict[str, Any] = field(default_factory=dict, hash=False)
    kind: Any = field(default=None, compare=False, repr=False, hash=False)
    is_default: bool = False
    # stage 63: the names the backend answers to beside its own; a root's
    # `state_configuration` may name any of them
    aliases: tuple[str, ...] = field(default=(), compare=False, hash=False)

    def _kind(self) -> BackendKind:
        if self.kind is None:
            raise HclConfigConflictError(
                f"State backend '{self.name}' (type '{self.type}') was registered without a kind: "
                "the plugin that declares the type must supply its renderings")
        return self.kind

    def state_location(self, workspace: str) -> StateLocation:
        return self._kind().location(self.settings, workspace)

    def state_file_path(self, workspace: str) -> str:
        """The state object's key within the container, normalised."""
        return self.state_location(workspace).key

    def backend_settings(self, workspace: str) -> dict[str, Any]:
        """The ``key = value`` settings the workspace's backend file carries."""
        return self._kind().backend_settings(self.settings, workspace)

    def remote_state_settings(self, workspace: str) -> dict[str, Any]:
        """The ``config`` a consumer's remote-state data source carries."""
        return self._kind().remote_state_settings(self.settings, workspace)


@dataclass(frozen=True)
class RemoteStateReference:
    """Consumer workspace's reference to a producer workspace's state."""
    producer_workspace: str
    backend_name: str | None = None   # None => the producer's backend / default
    label: str | None = None          # datasource label; default = producer name

    def datasource_label(self) -> str:
        return ssn(self.label or self.producer_workspace)


@dataclass(frozen=True)
class PackerPluginRequirement:
    name: str
    source: str | None = None
    version: str | None = None
    requested_by: str | None = None


@dataclass
class PackerVariableDecl:
    name: str
    type: str = "string"
    default: Any | None = None
    description: str | None = None
    env_var: str | None = None
    sensitive: bool = False


# Quoting policy is blocks.hcl_value (imported above as _hcl_value): one rule
# for resource specs and collector generators alike -- Raw passthrough,
# raw var./data./local./module./each./count. prefixes, list/dict recursion.

# --------------------------------------------------------------------------
# Terraform collector
# --------------------------------------------------------------------------

@singleton
class TerraformCollector:
    """Run-scoped collector of terraform requirements, keyed by workspace."""

    def __init__(self) -> None:
        self._init_state()

    def _init_state(self) -> None:
        self._providers: dict[str, list[ProviderRequirement]] = {}
        self._provider_configs: dict[str, list[ProviderConfig]] = {}
        self._variables: dict[str, dict[str, TerraformVariable]] = {}
        self._backends: dict[str, BackendRegistration] = {}
        self._workspace_backend: dict[str, str] = {}
        self._remote_refs: dict[str, list[RemoteStateReference]] = {}
        self._sensitive: dict[str, dict[str, str]] = {}   # workspace -> {key: ENC[age:...]}

    def reset(self) -> None:
        """Clear all registrations (fresh run / test isolation)."""
        self._init_state()

    # --- registration -----------------------------------------------------
    def require_provider(self, workspace: str, name: str,
                         source: str | None = None,
                         version: str | None = None,
                         requested_by: str | None = None) -> None:
        req = ProviderRequirement(name=name, source=source, version=version,
                                  requested_by=requested_by or workspace)
        reqs = self._providers.setdefault(workspace, [])
        if req not in reqs:
            reqs.append(req)

    def configure_provider(self, workspace: str, name: str,
                           config: dict[str, Any],
                           alias: str | None = None) -> None:
        """Record a provider block for the workspace.

        The alias defaults to the (sanitized) workspace name so that provider
        blocks from different builders never collide when aggregated into a
        single configuration. Module calls must therefore bind explicitly via
        ``providers = { <name> = <name>.<alias> }`` (see provider_bindings) --
        aggregation-readiness assumes all resources live in modules.
        """
        if alias is None:
            alias = ssn(workspace)
        cfgs = self._provider_configs.setdefault(workspace, [])
        for existing in cfgs:
            if existing.name == name and existing.alias == alias:
                if existing.config != config:
                    raise HclConfigConflictError(
                        f"Provider '{name}' (alias={alias}) configured twice with "
                        f"different arguments in workspace '{workspace}'"
                    )
                return
        cfgs.append(ProviderConfig(name=name, config=dict(config), alias=alias))

    def provider_bindings(self, workspace: str) -> dict[str, str]:
        """Module ``providers`` meta-argument bindings for the workspace:
        {provider name: "<name>.<alias>"} for each configured provider."""
        return {
            pc.name: f"{pc.name}.{pc.alias}"
            for pc in self._provider_configs.get(workspace, [])
            if pc.alias
        }

    def sensitive_ref(self, workspace: str, key: str, value: Any) -> Any:
        """The emission-side form of a value (stage 34): a decrypted value (one
        carrying the ``marker`` it was read from) is registered under ``key``
        and referenced as ``local.sensitive["<key>"]``; any other value is
        returned as it is. Registering also requires the external provider the
        decrypting data source needs, so call it before the terraform block."""
        marker = getattr(value, "marker", "")
        if not marker:
            return value
        values = self._sensitive.setdefault(workspace, {})
        existing = values.get(key)
        if existing is not None and existing != marker:
            raise HclConfigConflictError(
                f"Sensitive value '{key}' registered twice with different ciphertexts "
                f"in workspace '{workspace}'")
        values[key] = marker
        self.require_provider(workspace, EXTERNAL_PROVIDER, source="hashicorp/external")
        return Raw(f'local.{SENSITIVE_LABEL}["{key}"]')

    def sensitive_values(self, workspace: str) -> dict[str, str]:
        """{key: ciphertext} registered for the workspace (insertion order)."""
        return dict(self._sensitive.get(workspace, {}))

    def declare_variable(self, workspace: str, variable: TerraformVariable) -> None:
        vars_ = self._variables.setdefault(workspace, {})
        existing = vars_.get(variable.name)
        if existing is not None:
            if existing != variable:
                raise HclConfigConflictError(
                    f"Variable '{variable.name}' redefined with different attributes "
                    f"in workspace '{workspace}'"
                )
            return
        vars_[variable.name] = variable

    def register_backend(self, registration: BackendRegistration) -> None:
        existing = self._backends.get(registration.name)
        if existing is not None:
            if existing != registration:
                raise HclConfigConflictError(
                    f"State backend '{registration.name}' registered twice with "
                    "different configurations"
                )
            return
        self._backends[registration.name] = registration

    def set_backend(self, workspace: str, backend_name: str = DEFAULT) -> None:
        """Bind a workspace to a backend. A workspace keeps its state in exactly
        one location (stage 46): a second binding to a DIFFERENT backend is
        refused, naming the workspace and both backends; rebinding to the same
        one is a no-op (a builder may bind per phase)."""
        current = self._workspace_backend.get(workspace)
        if current is not None and current != backend_name:
            raise HclConfigConflictError(
                f"Workspace '{workspace}' is bound to state backend '{current}' and cannot be "
                f"rebound to '{backend_name}': a workspace keeps its state in exactly one location"
            )
        self._workspace_backend[workspace] = backend_name

    @staticmethod
    def effective_backend_name(*candidates: str | None) -> str:
        """The chain a workspace's backend resolves through (stage 46.2): the first
        candidate outside the loader's absent sentinels (``default``, ``self``,
        empty, unset) -- the builder's own ``state_configuration``, then its
        runtime's -- else ``default``, the single backend marked ``is_default``."""
        for candidate in candidates:
            if candidate not in OOPS_DEFAULTS:
                return str(candidate)
        return DEFAULT

    def bind_workspace(self, workspace: str, *candidates: str | None) -> str:
        """``set_backend`` through the chain; returns the name bound."""
        name = self.effective_backend_name(*candidates)
        self.set_backend(workspace, name)
        return name

    def reference_remote_state(self, consumer_workspace: str,
                               producer_workspace: str,
                               backend_name: str | None = None,
                               label: str | None = None) -> None:
        ref = RemoteStateReference(producer_workspace=producer_workspace,
                                   backend_name=backend_name, label=label)
        refs = self._remote_refs.setdefault(consumer_workspace, [])
        if ref not in refs:
            refs.append(ref)

    # --- lookup / validation ----------------------------------------------
    def backends_enabled(self) -> bool:
        """Backend/remote-state emission is gated by the global config flag."""
        from cs_image_system.base.global_context import GlobalTypeContext
        try:
            return bool(GlobalTypeContext().config.get("use_state_backends", False))
        except Exception:
            return False

    def resolve_backend(self, name_or_default: str | None) -> BackendRegistration | None:
        if name_or_default in (None, DEFAULT, ""):
            defaults = [b for b in self._backends.values() if b.is_default]
            if len(defaults) > 1:
                raise HclConfigConflictError(
                    f"Multiple default state backends registered: "
                    f"{sorted(b.name for b in defaults)}"
                )
            return defaults[0] if defaults else None
        found = self._backends.get(name_or_default)
        if found is None:
            # stage 63: an alias binds too (it was registered and never read)
            found = next((b for b in self._backends.values() if name_or_default in b.aliases), None)
        return found

    def _workspace_backend_registration(self, workspace: str) -> BackendRegistration | None:
        if workspace not in self._workspace_backend:
            return None
        return self.resolve_backend(self._workspace_backend[workspace])

    def workspace_backend(self, workspace: str) -> BackendRegistration | None:
        """The backend a workspace is bound to (None when unbound or when
        backends are disabled) -- the state-isolation evidence consumers use."""
        if not self.backends_enabled():
            return None
        return self._workspace_backend_registration(workspace)

    def bound_workspaces(self) -> list[str]:
        return sorted(self._workspace_backend)

    def state_locations(self) -> dict[str, StateLocation]:
        """Every bound workspace's resolved location (unbound and unresolvable
        ones absent), whether or not backends are enabled: the collision rule
        is about the declaration, not the emission."""
        out: dict[str, StateLocation] = {}
        for workspace in self.bound_workspaces():
            reg = self._workspace_backend_registration(workspace)
            if reg is not None:
                out[workspace] = reg.state_location(workspace)
        return out

    @staticmethod
    def state_collisions(locations: dict[str, StateLocation]) -> list[str]:
        """One message per location that two or more workspaces would share
        (stage 46.3): the same bucket and normalised prefix under two backend
        names, two workspace names that collapse under super_safe_name, or a
        doubled slash against a single one."""
        by_location: dict[StateLocation, list[str]] = {}
        for workspace, location in locations.items():
            by_location.setdefault(location, []).append(workspace)
        return [f"workspaces {', '.join(sorted(names))} would share the state object {location}"
                for location, names in sorted(by_location.items(), key=lambda kv: str(kv[0]))
                if len(names) > 1]

    def validate_state_locations(self) -> None:
        """Refuse the run when two bound workspaces resolve to one state object."""
        collisions = self.state_collisions(self.state_locations())
        if collisions:
            raise HclConfigConflictError("state location collision: " + "; ".join(collisions))

    def merged_providers(self, workspace: str) -> list[ConfiguredTerraformProvider]:
        """Per-workspace merge: one entry per provider name with intersected
        version constraint; abort on conflict or source disagreement."""
        merged: list[ConfiguredTerraformProvider] = []
        by_name: dict[str, list[ProviderRequirement]] = {}
        for req in self._providers.get(workspace, []):
            by_name.setdefault(req.name, []).append(req)
        for name, reqs in by_name.items():
            source = self._agree_source(name, reqs)
            version = assert_satisfiable(
                name, [(r.version, r.requested_by) for r in reqs])
            merged.append(ConfiguredTerraformProvider(
                name=name, source=source or "", version=version))
        return merged

    @staticmethod
    def _agree_source(name: str, reqs: list[ProviderRequirement]) -> str | None:
        sources = {r.source.lower(): r.source for r in reqs if r.source}
        if len(sources) > 1:
            raise HclConfigConflictError(
                f"Provider '{name}' requested with different sources: "
                f"{sorted(sources.values())} "
                f"(requested by {sorted({r.requested_by or '?' for r in reqs})})"
            )
        return next(iter(sources.values()), None)

    def validate_all(self) -> None:
        """Run-wide check: combined constraints for each provider name across
        ALL workspaces must be satisfiable (catches config drift early)."""
        by_name: dict[str, list[ProviderRequirement]] = {}
        for reqs in self._providers.values():
            for req in reqs:
                by_name.setdefault(req.name, []).append(req)
        for name, reqs in by_name.items():
            self._agree_source(name, reqs)
            assert_satisfiable(name, [(r.version, r.requested_by) for r in reqs])
        self.validate_state_locations()

    # --- generation (in-memory only) ----------------------------------------
    def generate_terraform_block(self, workspace: str) -> list[str]:
        """``terraform { required_providers {...} [backend "..." {...}] }``"""
        self.validate_all()
        doc = Builder()
        tf = doc.block("terraform")
        provs = self.merged_providers(workspace)
        if provs:
            pblock = tf.block("required_providers")
            for p in provs:
                args: dict[str, Any] = {}
                if p.source:
                    args["source"] = QString(p.source, quoted=True)
                if p.version:
                    args["version"] = QString(p.version, quoted=True)
                pblock.block(p.name, labels=["="], **args)
        reg = self._workspace_backend_registration(workspace)
        if reg is not None and self.backends_enabled():
            # Partial configuration: the block is empty here; the settings live
            # in the workspace's .tfbackend.hcl file (generate_backend_config)
            # and are supplied via ``init -backend-config=<file>``.
            tf.block("backend", labels=[f'"{reg.type}"'])
        return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()

    def generate_backend_config(self, workspace: str) -> list[str]:
        """Contents of the workspace's ``.tfbackend.hcl`` partial-config file:
        top-level ``key = value`` backend settings for
        ``init -backend-config=<file>``. Empty unless the workspace has a
        backend bound and backends are enabled."""
        reg = self._workspace_backend_registration(workspace)
        if reg is None or not self.backends_enabled():
            return []
        return self.render_backend_config(
            reg.backend_settings(workspace),
            f"# Backend '{reg.name}' ({reg.type}) partial configuration for workspace {workspace}")

    @staticmethod
    def render_backend_config(settings: dict[str, Any], comment: str) -> list[str]:
        lines = [comment]
        for k, v in settings.items():
            lines.append(f"{k} = {render_backend_value(v)}")
        return lines

    def backend_record(self, workspace: str) -> dict[str, Any] | None:
        """The record meta-state keeps of where a workspace's state lives
        (stage 46.4): the backend's name and type over its file settings, enough
        to write that file again for a migration's previous location."""
        reg = self._workspace_backend_registration(workspace)
        if reg is None:
            return None
        return {"backend": reg.name, "type": reg.type, "location": str(reg.state_location(workspace)),
                **reg.backend_settings(workspace)}

    def generate_provider_blocks(self, workspace: str) -> list[str]:
        self.validate_all()
        lines: list[str] = []
        for pc in self._provider_configs.get(workspace, []):
            doc = Builder()
            args = {k: _hcl_value(v) for k, v in pc.config.items()}
            if pc.alias:
                args["alias"] = QString(pc.alias, quoted=True)
            doc.block("provider", labels=[f'"{ssn(pc.name)}"'], **args)
            lines.extend(hcl2.dumps(doc.build(), formatter_options=FO).splitlines())
        return lines

    def generate_variable_blocks(self, workspace: str) -> list[str]:
        self.validate_all()
        variables = self._variables.get(workspace, {})
        if not variables:
            return []
        doc = Builder()
        for v in variables.values():
            args: dict[str, Any] = {"type": v.type}
            if v.default is not None:
                args["default"] = (str(v.default).lower() if isinstance(v.default, bool)
                                   else _hcl_value(v.default))
            if v.description:
                args["description"] = QString(v.description, quoted=True)
            if v.sensitive:
                args["sensitive"] = True
            doc.block("variable", labels=[f'"{v.name}"'], **args)
        return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()

    def generate_sensitive_blocks(self, workspace: str) -> list[str]:
        """``data "external" "sensitive" {...}`` and ``locals { sensitive = ... }``
        for the workspace's registered ciphertexts (stage 34); empty when none.
        Bound to the workspace's configured external provider when it has one
        (the group root aliases it for the gid shim), the default otherwise."""
        values = self._sensitive.get(workspace)
        if not values:
            return []
        args: dict[str, Any] = {}
        binding = self.provider_bindings(workspace).get(EXTERNAL_PROVIDER)
        if binding:
            args["provider"] = Raw(binding)
        args["program"] = list(SENSITIVE_PROGRAM)
        args["query"] = {k: values[k] for k in sorted(values)}
        spec = DataSpec(
            EXTERNAL_PROVIDER, SENSITIVE_LABEL, args,
            comment=("Sensitive values (stage 34): the same ENC[age:...] ciphertext the "
                     "configuration carries, decrypted at plan time by the identity in "
                     "CSIS_CONFIG_IDENTITY; never committed in clear"))
        loc = BlockSpec(type="locals", label="", kind="locals", labels=[],
                        args={SENSITIVE_LABEL: Raw(f"sensitive(data.{EXTERNAL_PROVIDER}.{SENSITIVE_LABEL}.result)")})
        return render_blocks([spec, loc], separator="")

    def generate_remote_state_datasources(self, workspace: str) -> list[str]:
        """``data "terraform_remote_state" "<label>" { backend, config {...} }``
        per registered reference; empty unless backends are enabled."""
        self.validate_all()
        if not self.backends_enabled():
            return []
        lines: list[str] = []
        for ref in self._remote_refs.get(workspace, []):
            reg = (self.resolve_backend(ref.backend_name)
                   if ref.backend_name
                   else self._workspace_backend_registration(ref.producer_workspace)
                   or self.resolve_backend(None))
            if reg is None:
                raise HclConfigConflictError(
                    f"Workspace '{workspace}' references remote state of "
                    f"'{ref.producer_workspace}' but no backend is registered for it"
                )
            doc = Builder()
            ds = doc.block("data",
                           labels=['"terraform_remote_state"',
                                   f'"{ref.datasource_label()}"'],
                           backend=QString(reg.type, quoted=True))
            # whatever the producer's TYPE says a data source needs (stage 47.1)
            cargs: dict[str, Any] = {
                k: (QString(v, quoted=True) if isinstance(v, str) else v)
                for k, v in reg.remote_state_settings(ref.producer_workspace).items()
            }
            ds.block("config", labels=["="], **cargs)
            lines.extend(hcl2.dumps(doc.build(), formatter_options=FO).splitlines())
        return lines


# --------------------------------------------------------------------------
# Packer collector
# --------------------------------------------------------------------------

@singleton
class PackerCollector:
    """Run-scoped collector of packer plugin requirements, keyed by workspace."""

    def __init__(self) -> None:
        self._init_state()

    def _init_state(self) -> None:
        self._plugins: dict[str, list[PackerPluginRequirement]] = {}
        self._variables: dict[str, dict[str, PackerVariableDecl]] = {}

    def reset(self) -> None:
        self._init_state()

    def require_plugin(self, workspace: str, name: str,
                       source: str | None = None,
                       version: str | None = None,
                       requested_by: str | None = None) -> None:
        req = PackerPluginRequirement(name=name, source=source, version=version,
                                      requested_by=requested_by or workspace)
        reqs = self._plugins.setdefault(workspace, [])
        if req not in reqs:
            reqs.append(req)

    def declare_variable(self, workspace: str, variable: PackerVariableDecl) -> None:
        vars_ = self._variables.setdefault(workspace, {})
        existing = vars_.get(variable.name)
        if existing is not None:
            if existing != variable:
                raise HclConfigConflictError(
                    f"Packer variable '{variable.name}' redefined with different "
                    f"attributes in workspace '{workspace}'"
                )
            return
        vars_[variable.name] = variable

    def merged_plugins(self, workspace: str) -> list[PackerPluginRequirement]:
        merged: list[PackerPluginRequirement] = []
        by_name: dict[str, list[PackerPluginRequirement]] = {}
        for req in self._plugins.get(workspace, []):
            by_name.setdefault(req.name, []).append(req)
        for name, reqs in by_name.items():
            sources = {r.source.lower(): r.source for r in reqs if r.source}
            if len(sources) > 1:
                raise HclConfigConflictError(
                    f"Packer plugin '{name}' requested with different sources: "
                    f"{sorted(sources.values())}"
                )
            version = assert_satisfiable(
                name, [(r.version, r.requested_by) for r in reqs])
            merged.append(PackerPluginRequirement(
                name=name, source=next(iter(sources.values()), None),
                version=version, requested_by=workspace))
        return merged

    def validate_all(self) -> None:
        by_name: dict[str, list[PackerPluginRequirement]] = {}
        for reqs in self._plugins.values():
            for req in reqs:
                by_name.setdefault(req.name, []).append(req)
        for name, reqs in by_name.items():
            assert_satisfiable(name, [(r.version, r.requested_by) for r in reqs])

    def generate_packer_block(self, workspace: str) -> list[str]:
        """``packer { required_plugins { <name> { version, source } } }``"""
        self.validate_all()
        doc = Builder()
        packer = doc.block("packer")
        plugins = self.merged_plugins(workspace)
        if plugins:
            rp = packer.block("required_plugins")
            for p in plugins:
                args: dict[str, Any] = {}
                if p.version:
                    args["version"] = QString(p.version, quoted=True)
                if p.source:
                    args["source"] = QString(p.source, quoted=True)
                rp.block(p.name, labels=["="], **args)
        return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()

    def generate_variable_blocks(self, workspace: str) -> list[str]:
        self.validate_all()
        variables = self._variables.get(workspace, {})
        if not variables:
            return []
        doc = Builder()
        for v in variables.values():
            packer_variable(doc, v.name, v.type, default=v.default,
                            description=v.description, env_var=v.env_var,
                            sensitive=v.sensitive)
        return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()
