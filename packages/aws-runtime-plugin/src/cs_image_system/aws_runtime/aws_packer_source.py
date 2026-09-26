# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``amazon-ebs`` packer source for an image baked on an AWS runtime.

Moved here from the packer plugin (EXPLORE GCP increment 1): the packer
builder is provider-neutral and asks the runtime plugin for the source
block; this module is AWS's answer. Shape unchanged: a ``data "amazon-ami"``
lookup for the bake's source image (exact id when the parent is pinned,
N5) and a ``source "amazon-ebs"`` block carrying the merged tags.
"""
from __future__ import annotations

import logging
from typing import Any

import hcl2
from hcl2 import Builder

from cs_image_system.base.constants import OOPS_DEFAULTS
from cs_image_system.hashicorp_utils.hashicorp import FO

from .aws_runtime_models import AwsCloudBuilderModel, AwsCloudNetworkingModel

log = logging.getLogger(__name__)

AMAZON_EBS = "amazon-ebs"

# Installs and starts the SSM agent when the vendor image lacks it (RHEL and
# Debian vendor AMIs do); Amazon Linux/Ubuntu already run it. Idempotent.
_SSM_BOOTSTRAP = """#!/bin/bash
set -x
dl() { if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"; else wget -qO "$2" "$1"; fi; }
if ! command -v amazon-ssm-agent >/dev/null 2>&1 && [ ! -x /snap/bin/amazon-ssm-agent ]; then
  R=us-east-2
  if command -v curl >/dev/null 2>&1; then R=$(curl -s http://169.254.169.254/latest/meta-data/placement/region || echo us-east-2);
  elif command -v wget >/dev/null 2>&1; then R=$(wget -qO- http://169.254.169.254/latest/meta-data/placement/region || echo us-east-2); fi
  if command -v dnf >/dev/null 2>&1; then dnf install -y "https://s3.$R.amazonaws.com/amazon-ssm-$R/latest/linux_amd64/amazon-ssm-agent.rpm";
  elif command -v yum >/dev/null 2>&1; then yum install -y "https://s3.$R.amazonaws.com/amazon-ssm-$R/latest/linux_amd64/amazon-ssm-agent.rpm";
  elif command -v dpkg >/dev/null 2>&1; then
    command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || { apt-get -o DPkg::Lock::Timeout=600 update -qq; apt-get -o DPkg::Lock::Timeout=600 install -y wget; }
    dl "https://s3.$R.amazonaws.com/amazon-ssm-$R/latest/debian_amd64/amazon-ssm-agent.deb" /tmp/ssm.deb && dpkg -i /tmp/ssm.deb; fi
fi
systemctl enable --now amazon-ssm-agent 2>/dev/null || true
"""


def _root_device(image: Any, psi: Any) -> str:
    """The bake source's root device name: from the resolved vendor query
    when available, else by the chain root's family."""
    raw = getattr(psi, "raw_query_result", None)
    if isinstance(raw, dict) and raw.get("RootDeviceName"):
        return str(raw["RootDeviceName"])
    fam = _chain_root_family(image)
    return {"debian": "/dev/xvda", "amazon": "/dev/xvda"}.get(fam, "/dev/sda1")


def _chain_root_family(image: Any) -> str:
    try:
        from cs_image_system.base.capabilities import image_chain
        from cs_image_system.base.global_context import GlobalTypeContext
        ctx = GlobalTypeContext()
        name = image.get_name()
        root = name if name in ctx.os_builders else image_chain(ctx, image)[1]
        return (ctx.os_builders[root].get_family() or "").lower() if root in ctx.os_builders else ""
    except Exception:
        return ""


def _machine_type(subconfig: Any, model: AwsCloudBuilderModel) -> str:
    for v in (getattr(subconfig, "machine_type", None),
              getattr(subconfig, "default_machine_type", None)):
        if v and v not in OOPS_DEFAULTS:
            return str(v)
    return str(model.get_default_machine_type())


def amazon_ebs_source(model: AwsCloudBuilderModel, image: Any, *, runtime: str, source_type: str,
                      subconfig: Any, self_subconfig: Any, psi: Any, tags: dict[str, str],
                      final_name: str, pinned: str | None) -> list[str]:
    networking: AwsCloudNetworkingModel = model.networking  # type: ignore[assignment]
    query_assets = psi.get_query_assets()
    assert query_assets is not None, (
        f"Provider-specific image for image {image.name} on runtime {runtime} "
        "must have query assets to convert to source configuration.")
    if pinned:
        query_assets = {"filters": {"image-id": f'"{pinned}"'}, "owners": ['"self"']}
    # Credentials for packer's AWS calls: the same named profile the tofu
    # roots put in their provider blocks (found live: without it the
    # amazon-ami datasource fails with "No valid credential sources found").
    # stage 17: credentials is a declared object; get_credentials() is the
    # one conversion point to the mapping every consumer wants.
    creds = model.get_credentials() if hasattr(model, "get_credentials") else {}
    profile = creds.get("profile_name")
    if profile:
        query_assets = {**query_assets, "profile": f'"{profile}"'}

    runtime_data_id = f"{image.name}_{runtime}"
    c: dict[str, Any] = {
        "source_ami": f"data.amazon-ami.{runtime_data_id}.id",
        "ami_name": final_name,
        # bake size: the subconfig's machine_type, else its default_machine_type
        # (what os-builder runtime YAML carries), else the runtime default
        "instance_type": _machine_type(subconfig, model),
        "region": model.region,
        "vpc_id": networking.network,
        "subnet_id": networking.default_subnet_id,
        "tags": {k: f'"{v}"' for k, v in tags.items()},
        "associate_public_ip_address": True,
    }
    if profile:
        c["profile"] = profile
    # stage 63: the runtime's ena_support/sriov_support reach the source when
    # declared (they were accepted and read by nothing); packer's defaults
    # apply when they are not
    for flag in ("ena_support", "sriov_support"):
        value = getattr(model, flag, None)
        if value is not None:
            c[flag] = bool(value)
    # Debug-session parity for BAKES (TODO stage 1 finding, 2026-08-31):
    # this VPC has no internet gateway and operator machines have no route
    # to private IPs, so SSH-from-outside can never reach a build instance.
    # When the runtime declares session_mechanism: ssm, packer connects
    # through Session Manager instead: no public IP, an SSM-capable
    # instance profile, and a user_data bootstrap that installs the agent
    # on vendor AMIs that lack it (outbound via the subnet's NAT).
    mech = str(getattr(model, "session_mechanism", "") or "").strip().lower()
    ssm_profile = getattr(model, "session_instance_profile", None) or model.iam_instance_profile
    if mech == "ssm" and ssm_profile:
        c["ssh_interface"] = "session_manager"
        c["iam_instance_profile"] = ssm_profile
        c["associate_public_ip_address"] = False
        c["ssh_timeout"] = "15m"   # boot + agent install + SSM registration
        # one HCL string line: escape embedded quotes and newlines (real
        # newlines and bare quotes are illegal inside an HCL quoted string)
        c["user_data"] = (_SSM_BOOTSTRAP.rstrip("\n").replace('"', '\\"')
                          .replace("\n", "\\n"))
    # stage 63 items 22-23: the one resolver (the image's entry, the chain
    # root's entry, config_username, the runtime's ssh_username, its
    # default_config_username, the family's vendor user); the runtime's
    # ssh_username used to override every entry here
    from cs_image_system.base.bake_user import resolve_bake_user
    from cs_image_system.base.global_context import GlobalTypeContext
    c["ssh_username"] = resolve_bake_user(GlobalTypeContext(), image, runtime)
    if networking.default_availability_zone:
        c["availability_zone"] = networking.default_availability_zone
    if model.iam_instance_profile and "iam_instance_profile" not in c:
        # the SSM profile wins when both are set (stage 63 item 9, decided
        # 2026-09-24): this assignment used to run after the SSM block and
        # replace it, so a runtime with both baked under the wrong profile
        c["iam_instance_profile"] = model.iam_instance_profile
    lmap = {
        # The SOURCE AMI's real root device, never a hardcoded name: RHEL
        # roots are /dev/sda1, Debian/Amazon Linux roots are /dev/xvda, and
        # on HVM the two names alias one device slot -- a mismatched mapping
        # bakes an AMI carrying TWO root-slot volumes whose derived
        # instances never boot (found live: the deb-11 chain).
        "device_name": f'"{_root_device(image, psi)}"',
        "volume_type": '"gp3"',
        "delete_on_termination": True,
        "volume_size": image.primary_disk_size,
    }
    for k, v in c.items():
        if isinstance(v, str) and not (v.startswith("var.") or v.startswith("data.")):
            c[k] = f'"{v}"'
    c["force_deregister"] = "!var.release"
    doc = Builder()
    doc.block("data", labels=['"amazon-ami"', f'"{runtime_data_id}"'], **query_assets)
    source = doc.block("source", labels=[f'"{source_type}"', f'"{image.name}"'], **c)
    source.block("launch_block_device_mappings", **lmap)
    return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()
