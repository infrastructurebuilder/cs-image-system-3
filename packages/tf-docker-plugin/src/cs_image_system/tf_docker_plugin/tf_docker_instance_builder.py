# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The container instance builder (stage 103 branch 2).

One ``module`` call per instance against tfmodules/docker_container, on
OpenTofu's ``kreuzwerker/docker`` provider. The image is the instance's
pinned build (an image id), else the resolved provider-specific image, else
the per-instance variable finalization fills from the packer manifest with
the series' floating tag as the fallback (the daemon has no "newest image
matching a pattern" query, so the tag the bake moves IS that query). Each
container gets the canonical hostname ``<name>-NNN``, labels for the
configuration id, the instance and the generation (the module adds the
build), its network by name, the limits of its machine type, its volumes at
their mount points and the restart policy ``unless-stopped``; it is declared
so the next apply leaves a stopped container alone (``must_run = false``).

Launching without user data: the same launch script the clouds feed through
user data is rendered by ``templatefile`` and UPLOADED into the container at
creation; the launch-delivery hook runs it through ``docker exec`` after the
apply (the runtime's ``launch_delivery`` is ``session``). The daemon mounts
each volume, so the script only makes the group's subtree; the hostname
comes from the container.

The daemon's address never enters the root: every tofu process the root
runs carries the runtime's ``DOCKER_HOST`` or ``DOCKER_CONTEXT`` in its
environment (an ENC host stays a marker in the runner script and opens
where the line runs), and the provider block is empty.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, TypeVar, cast

from cs_image_system.base import utils
from cs_image_system.base.launch_params import ENROLLMENT_TOKEN_VARIABLE, compute_launch_params, user_data_template
from cs_image_system.base.models.executable import ExecutableModel
from cs_image_system.base.models.instance import Instance
from cs_image_system.contract.assets import AssetSet
from cs_image_system.contract.hcl import HclRaw, hcl_expr, render_module_call
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.hashicorp_utils.collector import TerraformCollector, TerraformVariable
from cs_image_system.tf_ebs_instance_plugin.tf_instance_builder import TofuInstanceBuilder

from .tf_docker_models import TOFU_DOCKER, TofuDockerInstanceBuilderModel

log = logging.getLogger(__name__)

Q = TypeVar("Q", bound=TofuDockerInstanceBuilderModel)

DOCKER_PROVIDER_SOURCE = "kreuzwerker/docker"
_MEMORY = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgGtT]?)[bB]?\s*$")
_UNIT_MB = {"": 1, "k": 1 / 1024, "m": 1, "g": 1024, "t": 1024 * 1024}


def memory_mb(value: Any) -> int:
    """A machine type's memory in the provider's unit (MB) from docker's own
    spelling (``512m``, ``4g``, ``2048``; a bare number is MB). 0 = none."""
    if value is None or str(value).strip() == "":
        return 0
    m = _MEMORY.match(str(value))
    if not m:
        raise ValueError(f"memory {value!r} is not a size docker understands (512m, 4g, 2048)")
    number, unit = m.group(1), m.group(2).lower()
    mb = float(number) * _UNIT_MB[unit]
    return int(round(mb))


def cpus_as_read_back(value: Any) -> str:
    """The provider reads ``cpus`` back with a decimal point (``1`` becomes
    ``1.0`` and would plan a replacement forever; found while proving the
    module): render every value with one. Empty when none."""
    if value is None or str(value).strip() == "":
        return ""
    try:
        text = format(Decimal(str(value)).normalize(), "f")
    except InvalidOperation as e:
        raise ValueError(f"cpus {value!r} is not a number") from e
    return text if "." in text else text + ".0"


def generation_of(hostname: str, name: str) -> str:
    """The generation a canonical hostname carries (``coops-model-003`` is
    3); a machine grandfathered without a suffix is the record's first."""
    tail = hostname[len(name) + 1:] if hostname.startswith(name + "-") else ""
    return str(int(tail)) if tail.isdigit() else "1"


class TofuDockerInstanceBuilder(TofuInstanceBuilder[Q]):
    @classmethod
    def csis_name(cls) -> str:
        return TOFU_DOCKER

    @staticmethod
    def _image_var(label: str) -> str:
        return f"{label}_image"

    @staticmethod
    def _ami_var(label: str) -> str:
        """The variable the inherited ``pre_finalize_phase`` writes into
        ``instances.auto.tfvars`` for a build this run baked (the GCE
        builder's lesson, stage 63 item 7)."""
        return TofuDockerInstanceBuilder._image_var(label)

    def get_executable_copy(self) -> ExecutableModel:
        """Every tofu process of this root reaches the runtime's daemon: the
        runtime's tool environment rides on the executable (the runner
        script carries it as an assignment prefix)."""
        e = super().get_executable_copy()
        rtb = self._runtime_builder()
        env_of = getattr(rtb, "tool_environment", None)
        if callable(env_of):
            extra = cast(dict[str, str], env_of())
            e.environment = {**dict(e.environment or {}), **extra}
        return e

    @staticmethod
    def _launch_script_template_name(label: str) -> str:
        return f"launch-{label}.sh.tftpl"

    def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        items = AssetSet()
        if phase != ExecutionLifecyclePhase.INSTANCE_GENERATION or not self._root_has_work():
            return items
        rpath = self.get_path_for_phase(phase, suffix=".tf")
        items = items.with_default_path(rpath)
        items.add(f"# Terraform configuration for containers generated by "
                  f"{self.__class__.__name__} ({self.name})")
        items.add("# The daemon's address is not here: every tofu process of this root carries the")
        items.add("# runtime's DOCKER_HOST or DOCKER_CONTEXT in its environment (stage 103 branch 2).")
        col = TerraformCollector()
        ws = self.name
        self._declare_ephemeral_variable(col, ws)
        if self.model.required_plugins:
            for plugin in self.model.required_plugins:
                col.require_provider(ws, plugin.name, source=getattr(plugin, "source", None),
                                     version=getattr(plugin, "version", None))
        else:
            col.require_provider(ws, "docker", source=DOCKER_PROVIDER_SOURCE)
        col.configure_provider(ws, "docker", {})      # the address rides in the environment
        for instance in self._instances:
            label = utils.super_safe_name(instance.get_name())
            col.declare_variable(ws, TerraformVariable(name=self._image_var(label), type="string", default=""))
        col.declare_variable(ws, TerraformVariable(
            name=ENROLLMENT_TOKEN_VARIABLE, type="string", default="", sensitive=True,
            description="Identity enrollment token handed to instances at launch (TF_VAR_...); empty = no enrollment"))
        col.bind_workspace(ws, self.model.state_configuration, self.runtime_state_configuration())   # stage 46: own, runtime's, default
        ctx = self._get_context()
        for sb_name, sb in ctx.storage_builders.items():
            if getattr(sb.model, "_storages", None):
                col.reference_remote_state(ws, producer_workspace=sb_name)
        identity_ws: set[str] = set()
        for instance in self._instances:
            image = ctx.images_map.get(str(instance.image)) if instance.image else None
            iws = self._identity_workspace_for(getattr(image, "group", None))
            if iws:
                identity_ws.add(iws)
        for iws in sorted(identity_ws):
            col.reference_remote_state(ws, producer_workspace=iws)
        items.add_list(col.generate_terraform_block(ws))
        items.add_list(col.generate_provider_blocks(ws))
        variable_lines = col.generate_variable_blocks(ws)
        if variable_lines:
            items.add_list(variable_lines)
        remote_lines = col.generate_remote_state_datasources(ws)
        if remote_lines:
            items.add_list(remote_lines)
        backend_lines = col.generate_backend_config(ws)
        if backend_lines:
            items.add_list(self._backend_config_path(phase), backend_lines)
        return items

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        items = AssetSet()
        if phase != ExecutionLifecyclePhase.INSTANCE_GENERATION or not self._root_has_work():
            return items                                    # ledger 70: outside --only-runtime, nothing
        ctx = self._get_context()
        rtb = self._runtime_builder()
        src = utils.module_source("docker_container", self.get_path_for_phase(phase, suffix=".tf").parent)
        bindings = TerraformCollector().provider_bindings(self.name)
        for instance in self._instances:
            label = utils.super_safe_name(instance.get_name())
            rpath = self.get_path_for_phase(phase, f"instance-{label}", suffix=".tf")
            params = compute_launch_params(ctx, instance)
            items.add(rpath, f"# Terraform module call for container {instance.get_name()} "
                             f"generated by {self.__class__.__name__} ({self.name})")
            if params.get("group"):
                items.add(rpath, f"# owning group: {params['group']} (via image {instance.image}); "
                                 f"launch parameters recorded in meta-state/launch-params.yaml (N26)")
            items.add_list(rpath, render_module_call(
                f"instance_{label}", src, self._with_ephemeral_count(instance, self._module_args(ctx, rtb, instance, params)),
                providers=bindings))
            # the launch script beside the root: uploaded into the container at
            # creation, run through the session after the apply
            tpath = rpath.parent / self._launch_script_template_name(label)
            items.add(tpath, user_data_template(params))
        return items

    def _module_args(self, ctx, rtb, instance: Instance, params: dict[str, Any] | None = None) -> dict[str, Any]:
        from cs_image_system.base.lineage import config_tags, pinned_instance_build
        label = utils.super_safe_name(instance.get_name())
        name = str(instance.get_name())
        hostname = str((params or {}).get("hostname") or name)
        args: dict[str, Any] = {"name": name, "hostname": hostname}
        pinned = pinned_instance_build(ctx, instance) if hasattr(ctx, "meta_state") else None
        psi = (ctx.get_provider_specific_image(instance.image, rtb.get_name()) if rtb and instance.image else None)
        if pinned:
            args["image"] = pinned
        elif psi is not None and psi.is_resolved():
            args["image"] = psi.identifier
        elif psi is not None:
            # built later: the per-instance variable (filled by finalization
            # from the packer manifest); the series' floating tag is the fallback
            args["image"] = f"var.{self._image_var(label)}"
            floating = getattr(psi, "floating_tag", None)
            tag = floating() if callable(floating) else None
            if tag:
                args["image_tag"] = tag
        else:
            log.warning(f"No provider-specific image for image {instance.image!r} of instance "
                        f"{instance.get_name()}; the module call will not resolve an image")
        if rtb:
            mt_name = str(getattr(instance, "machine_type", "") or "") or str(rtb.get_default_machine_type() or "")
            get_types = getattr(rtb.model, "get_machine_types", None)
            types: dict[str, Any] = cast(dict[str, Any], get_types()) if callable(get_types) else {}
            mt = types.get(mt_name) if mt_name else None
            if mt_name and types and mt is None:
                raise ValueError(f"instance {name}: machine_type {mt_name!r} is not one of runtime "
                                 f"{rtb.get_name()}'s machine_types ({', '.join(sorted(types))})")
            if mt is not None:
                cpus = cpus_as_read_back(mt.get_cpus())
                if cpus:
                    args["cpus"] = cpus
                memory = memory_mb(mt.get_memory())
                if memory:
                    args["memory"] = memory
            networking = getattr(rtb.model, "networking", None)
            network = getattr(networking, "network", None) if networking else None
            if network:
                args["network"] = str(network)
        labels = {str(k): str(v) for k, v in {**(instance.get_tags() or {}), **config_tags(ctx)}.items()}   # stage 93
        labels["csis_instance"] = name
        labels["csis_generation"] = generation_of(hostname, name)
        args["labels"] = labels
        if params is not None:
            args.update(self._launch_args(ctx, label, params))
        return args

    def _launch_args(self, ctx, label: str, params: dict[str, Any]) -> dict[str, Any]:
        """The launch script (templatefile over the recorded launch parameters,
        the gid by the group builder's expression) and the volume mounts, each
        by remote-state reference to the storage root's outputs."""
        out: dict[str, Any] = {}
        group = params.get("group")
        gid = self._gid_expression_for(group)          # stage 75 step 3: the group builder writes it
        template_vars: dict[str, Any] = {}
        if gid is not None:
            template_vars["group_gid"] = HclRaw(gid)
        volumes: dict[str, Any] = {}
        for m in params.get("mounts", []):
            sb = m.get("builder") or self._storage_builder_name(m["storage"])
            if not sb:
                continue
            ref = (f"data.terraform_remote_state.{utils.super_safe_name(sb)}"
                   f".outputs.storage_{utils.super_safe_name(m['storage'])}")
            if m.get("platform_mounted"):
                volumes[m["storage"]] = {"volume_name": HclRaw(f"{ref}.volume_name"),
                                         "container_path": str(m["mount_point"])}
        template_vars["efs"] = {}
        template_vars["filestore"] = {}
        template_vars["ebs"] = {}
        # an OPA group on a container runtime is refused at validation (decision
        # 3), so no enrollment reaches here; the variable keeps the template whole
        template_vars[ENROLLMENT_TOKEN_VARIABLE] = ""
        tpl = self._launch_script_template_name(label)
        out["launch_script"] = HclRaw(f'templatefile("${{path.module}}/{tpl}", {hcl_expr(template_vars, 2)})')
        if volumes:
            out["volumes"] = volumes
        return out

    def _attachment_address(self, instance_name: str, storage: str) -> str | None:
        return None   # a volume mount is an attribute of docker_container; changing it re-creates

    def _module_address(self, instance_name: str) -> str:
        return f"module.instance_{utils.super_safe_name(instance_name)}"

    def _replacements(self) -> list[str]:
        ctx = self._get_context()
        from cs_image_system.base.lineage import pending_instance_replacements
        names = pending_instance_replacements(ctx, self._instances)   # upgrades + follow (stage 9)
        return [f"{self._module_address(n)}.docker_container.this" for n in sorted(names)]

    def _own_resources_to_let_go(self) -> list[str]:
        return []      # the root makes nothing of its own beside the containers
