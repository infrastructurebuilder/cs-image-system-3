# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The AWS instance root: the provider-neutral root of hashicorp-utils with
the ``aws`` provider, one ``module`` call per instance against
tfmodules/aws_instance, and the instances' own security group.

The AMI comes from the instance's image's ProviderSpecificImage: a concrete
id when resolved, a most-recent name-pattern query when deferred (the image
is built by a prior phase). Each instance's launch parameters -- storage
mounts and the enrollment trigger -- are generated as a ``templatefile``
user-data script whose runtime values (gids, filesystem ids, the token)
enter by terraform reference only; EBS volumes attach through the module;
the session instance profile is wired when the runtime offers one.
"""
import logging
from typing import Any, TypeVar

from cs_image_system.base import utils
from cs_image_system.base.capabilities import group_builder_of
from cs_image_system.base.launch_params import ENROLLMENT_TOKEN_VARIABLE
from cs_image_system.base.models.instance import Instance
from cs_image_system.contract.constants import OOPS_DEFAULTS
from cs_image_system.contract.hcl import HclRaw, hcl_expr
from cs_image_system.hashicorp_utils.collector import TerraformCollector
from cs_image_system.tofu_roots.tofu_instance_builder import TofuInstanceBuilderBase, TofuVersionChecker

from .tf_instance_models import TOFU, TofuInstanceBuilderModel

__all__ = ["TofuInstanceBuilder", "TofuVersionChecker"]

log = logging.getLogger(__name__)


def _group_tags_line(ctx: Any) -> str:
    """The security group's tags: its name, and the configuration it belongs
    to (``csis_config``), so that in a shared account the state is not the
    only thing that says whose it is."""
    from cs_image_system.base.lineage import CONFIG_TAG, configuration_tag
    tag = configuration_tag(ctx)
    if tag:
        return f'  tags = {{ Name = "csis-instances", {CONFIG_TAG} = "{tag}" }}'
    return '  tags = { Name = "csis-instances" }'


def _instances_vpc(rtb: Any) -> str | None:
    """The runtime's VPC id, when concretely configured."""
    networking = getattr(getattr(rtb, "model", None), "networking", None)
    vpc = getattr(networking, "network", None) if networking else None
    return vpc if vpc and vpc not in OOPS_DEFAULTS else None


Q = TypeVar("Q", bound=TofuInstanceBuilderModel)


class TofuInstanceBuilder(TofuInstanceBuilderBase[Q]):
    """The AWS instance root (``type: tofu``); see the module docstring."""

    @classmethod
    def csis_name(cls) -> str:
        return TOFU

    # ------------------------------------------------------------ the hooks
    def _provider_name(self) -> str:
        return "aws"

    def _provider_source(self) -> str:
        return "hashicorp/aws"

    def _provider_config(self, rtb: Any) -> dict[str, Any] | None:
        """The region and, when the runtime names one, the profile; no
        provider block without a region."""
        get_region = getattr(rtb.model, "get_region", None) if rtb else None
        region = get_region() if callable(get_region) else None
        if not region:
            return None
        config: dict[str, Any] = {"region": region}
        creds = rtb.model.get_credentials() if rtb else None
        profile = (creds or {}).get("profile_name")
        if profile:
            config["profile"] = profile
        return config

    def _module_dirname(self) -> str:
        return "aws_instance"

    def _module_resource(self) -> str:
        return "aws_instance"

    @staticmethod
    def _image_var(label: str) -> str:
        return f"{label}_ami_id"

    def _declare_variables(self, col: TerraformCollector, ws: str) -> None:
        """The AWS root's order: one AMI variable per instance, the ephemeral
        toggle, the enrollment trigger."""
        self._declare_image_variables(col, ws)
        self._declare_ephemeral_variable(col, ws)
        self._declare_enrollment_variable(col, ws)

    def _attachment_address(self, instance_name: str, storage: str) -> str | None:
        """On AWS a volume attachment is a resource of its own, so its destroy
        IS the detach."""
        return f"{self._module_address(instance_name)}.aws_volume_attachment.this"

    def _own_resources_to_let_go(self) -> list[str]:
        """With no instance declared, the security group the root made for
        them may go."""
        return [] if self._instances else ["aws_security_group.csis_instances"]

    def _root_extra_blocks(self, rtb: Any) -> list[str]:
        """The VPC lookup and the instances' own security group. Instances
        wear their own group because the VPC default group blocks the Okta
        gateway's inbound SSH relay, so sft ssh to the advertised private
        address hangs. SSH ingress references only the configured source
        groups (the gateway) -- never the shared networks' CIDR space
        (policy)."""
        vpc = _instances_vpc(rtb)
        if not vpc or not self._instances:     # no instances, no group of their own
            return []
        networking = getattr(rtb.model, "networking", None) if rtb else None
        ssh_sgs = list(getattr(networking, "ssh_ingress_security_group_ids", None) or [])
        if ssh_sgs:
            src = ("    security_groups = ["
                   + ", ".join(f'"{s}"' for s in ssh_sgs) + "]")
        else:
            # no relay configured: intra-VPC private space only
            src = "    cidr_blocks = [data.aws_vpc.csis_instances.cidr_block]"
        # these root-level blocks must bind the ALIASED provider explicitly:
        # the collector aliases every configured provider (aggregation-
        # readiness assumes resources live in modules), so an unqualified
        # block falls to the DEFAULT aws provider, which has no configuration
        # and only works when the operator's shell happens to carry ambient
        # AWS credentials
        provider_line = f"  provider    = aws.{utils.super_safe_name(self.name)}"
        return [
            "",
            'data "aws_vpc" "csis_instances" {',
            provider_line,
            f'  id = "{vpc}"',
            "}",
            "",
            'resource "aws_security_group" "csis_instances" {',
            provider_line,
            '  name_prefix = "csis-instances-"',
            '  description = "cs-image-system instances: SSH from the session relay; all egress"',
            "  vpc_id      = data.aws_vpc.csis_instances.id",
            "  ingress {",
            "    from_port   = 22",
            "    to_port     = 22",
            '    protocol    = "tcp"',
            src,
            "  }",
            "  egress {",
            "    from_port   = 0",
            "    to_port     = 0",
            '    protocol    = "-1"',
            '    cidr_blocks = ["0.0.0.0/0"]',
            "  }",
            _group_tags_line(self._get_context()),
            "  # replacements must create the successor first: instances",
            "  # wear this group, so a delete-first plan hits",
            "  # DependencyViolation (found live)",
            "  lifecycle { create_before_destroy = true }",
            "}",
        ]

    # ------------------------------------------------------------ the module call
    def _module_args(self, ctx, rtb, instance: Instance, params: dict[str, Any] | None = None) -> dict[str, Any]:
        label = utils.super_safe_name(instance.get_name())
        args: dict[str, Any] = {"name": instance.get_name()}
        # Pinned build first (DESIGN §3F5): once bound, an instance keeps its
        # build until an explicit upgrade moves the pin; a rebuild of its
        # image's series never touches it.
        from cs_image_system.base.lineage import pinned_instance_build
        pinned = pinned_instance_build(ctx, instance) if hasattr(ctx, "meta_state") else None
        # AMI via the image's provider-specific image
        psi = (ctx.get_provider_specific_image(instance.image, rtb.get_name())
               if rtb and instance.image else None)
        if pinned:
            args["ami_id"] = pinned
        elif psi is not None and psi.is_resolved():
            args["ami_id"] = psi.identifier
        elif psi is not None:
            # The image is built later (deferred PSI): reference the per-instance
            # variable (filled in by finalization from the packer manifest) with
            # the most-recent name-pattern lookup as fallback.
            args["ami_id"] = f"var.{self._image_var(label)}"
            args["ami_name_pattern"] = f"{psi.deferred_name_pattern}*"
        else:
            log.warning(f"No provider-specific image for image {instance.image!r} of "
                        f"instance {instance.get_name()}; the module call will not resolve an AMI")
        if rtb:
            mt = getattr(instance, "machine_type", None)
            args["instance_type"] = mt if mt else rtb.get_default_machine_type()
            # No public IP: the VPC has no internet gateway, so a public
            # address is unroutable and poisons sftd's advertised endpoint.
            args["associate_public_ip_address"] = False
            if _instances_vpc(rtb):
                # our own group, plus any existing groups the runtime says
                # instances must wear (e.g. OKTA-GATEWAY, whose membership
                # the session relay requires on the target)
                networking = getattr(rtb.model, "networking", None)
                addl = list(getattr(networking, "addl_security_groups", None) or [])
                args["vpc_security_group_ids"] = [
                    HclRaw("aws_security_group.csis_instances.id"), *addl]
            networking = getattr(rtb.model, "networking", None)
            subnet = getattr(networking, "default_subnet_id", None) if networking else None
            if subnet:
                args["subnet_id"] = subnet
            profile_fn = getattr(rtb, "session_instance_profile", None)
            profile = profile_fn() if callable(profile_fn) else None
            if profile:
                args["iam_instance_profile"] = profile
        from cs_image_system.base.lineage import config_tags
        tags = {**(instance.get_tags() or {}), **config_tags(ctx)}     # the machine carries the id
        if tags:
            args["tags"] = dict(tags)
        # Launch parameters (N26) are added only when the caller computed them
        # (generate_items_during); the AMI wiring above stands on its own.
        if params is not None:
            args.update(self._launch_args(ctx, label, params))
        return args

    def _launch_args(self, ctx, label: str, params: dict[str, Any]) -> dict[str, Any]:
        """user_data (templatefile over the recorded launch parameters) and
        EBS attachments -- every runtime value by terraform reference."""
        out: dict[str, Any] = {}
        group = params.get("group")
        gid = self._gid_expression_for(group)
        template_vars: dict[str, Any] = {}
        if gid is not None:
            template_vars["group_gid"] = HclRaw(gid)
        efs: dict[str, Any] = {}
        ebs: dict[str, Any] = {}
        for m in params.get("mounts", []):
            sb = m.get("builder") or self._storage_builder_name(m["storage"])
            if not sb:
                continue
            ref = (f"data.terraform_remote_state.{utils.super_safe_name(sb)}"
                   f".outputs.storage_{utils.super_safe_name(m['storage'])}")
            if m["type"] == "ebs":
                ebs[m["storage"]] = {"volume_id": HclRaw(f"{ref}.volume_id"),
                                     "device_name": m["device"]}
            elif m["type"] == "efs":
                ap = (f'{ref}.access_point_ids["{group}"]' if group and not m.get("public_read")
                      else f"{ref}.public_read_access_point_id")
                efs[m["storage"]] = {"file_system_id": HclRaw(f"{ref}.file_system_id"),
                                     "access_point_id": HclRaw(ap)}
        template_vars["efs"] = efs
        # the template resolves Nitro device names from the volume id
        template_vars["ebs"] = ebs
        enrollment = params.get("enrollment") or {}
        token_expr = f"var.{ENROLLMENT_TOKEN_VARIABLE}"
        if enrollment and group:
            # IaC-managed enrollment tokens: the group's identity plugin
            # supplies the credential by reference; the operator var stays as
            # explicit override and as the no-plugin fallback.
            gb = group_builder_of(self._get_context(), group)
            ref = gb.enrollment_token_reference(group) if gb else None
            if ref:
                token_expr = (f'(var.{ENROLLMENT_TOKEN_VARIABLE} != "" '
                              f"? var.{ENROLLMENT_TOKEN_VARIABLE} : {ref})")
        template_vars[ENROLLMENT_TOKEN_VARIABLE] = (
            HclRaw(token_expr) if enrollment else "")
        tpl = self._user_data_template_name(label)
        out["user_data"] = HclRaw(f'templatefile("${{path.module}}/{tpl}", {hcl_expr(template_vars, 2)})')
        if ebs:
            out["ebs_volumes"] = ebs
        return out
