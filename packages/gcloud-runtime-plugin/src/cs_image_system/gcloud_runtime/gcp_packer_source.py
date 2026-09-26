# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``googlecompute`` packer source for an image baked on a GCE runtime
(EXPLORE GCP increment 2).

GCE has two rules AWS does not:

* **names and labels are constrained** -- image names match
  ``[a-z]([-a-z0-9]*[a-z0-9])?`` (max 63), label keys/values are lowercase
  ``[a-z0-9_-]`` (max 63). Every csis tag is mapped ONCE, here, by
  :func:`gce_name` / :func:`gce_label`;
* **image families are native series** -- the bake sets ``image_family``
  to the csis series, so "the latest build of series X" is GCE's own
  ``source_image_family = X`` lookup and a deferred parent needs no
  name-pattern query at all. A pinned parent (N5) bakes from
  ``source_image = <build id>`` (the build id IS the image name).
"""
from __future__ import annotations

import logging
import re
from typing import Any

import hcl2
from hcl2 import Builder

from cs_image_system.base.constants import OOPS_DEFAULTS, SELF
from cs_image_system.hashicorp_utils.hashicorp import FO

log = logging.getLogger(__name__)

GOOGLECOMPUTE = "googlecompute"
_NAME_MAX = 63


def gce_name(value: str) -> str:
    """A valid GCE resource name derived deterministically from ``value``."""
    v = re.sub(r"[^a-z0-9-]+", "-", str(value).lower()).strip("-")
    if not v or not v[0].isalpha():
        v = f"i-{v}" if v else "i"
    return v[:_NAME_MAX].rstrip("-")


def gce_label(value: str) -> str:
    """A valid GCE label key/value derived from ``value``."""
    return re.sub(r"[^a-z0-9_-]+", "-", str(value).lower())[:_NAME_MAX]


def googlecompute_source(model: Any, image: Any, *, runtime: str, source_type: str,
                         subconfig: Any, self_subconfig: Any, psi: Any, tags: dict[str, str],
                         final_name: str, pinned: str | None) -> list[str]:
    from cs_image_system.base.lineage import series_of

    c: dict[str, Any] = {}
    if model.project_id:
        c["project_id"] = model.project_id
    if model.zone:
        c["zone"] = model.zone
    # --- the bake's source image
    if pinned:
        c["source_image"] = gce_name(pinned)
    elif psi.is_resolved():
        c["source_image"] = str(psi.identifier)
        if psi.owner and psi.owner not in OOPS_DEFAULTS and psi.owner != SELF:
            c["source_image_project_id"] = [f'"{psi.owner}"']
    else:
        # deferred: the parent series' family, built earlier in this run
        # or by a previous one -- GCE resolves "latest in family" itself
        c["source_image_family"] = gce_name(str(image.source_image))
    # --- the artifact
    c["image_name"] = gce_name(final_name)
    c["image_family"] = gce_name(series_of(image))
    c["image_labels"] = {gce_label(k): f'"{gce_label(v)}"' for k, v in sorted(tags.items())}
    # bake size, AWS-parity fallback chain (finding 41: a dask bake fell
    # through to the 1 GB runtime default and OOMed at 65 minutes)
    mt = None
    for cand in (getattr(subconfig, "machine_type", None) if subconfig else None,
                 getattr(subconfig, "default_machine_type", None) if subconfig else None):
        if cand and cand not in OOPS_DEFAULTS:
            mt = cand
            break
    c["machine_type"] = mt or model.get_default_machine_type()
    if getattr(model, "service_account_email", None):
        c["service_account_email"] = model.service_account_email
    # finding 54 (found live): packer reached the build VM over its external
    # IP on tcp:22, which only worked while the default VPC's
    # default-allow-ssh rule existed; once that was deleted every bake timed
    # out waiting for SSH. On an IAP runtime the bake tunnels through IAP
    # like sessions do (operator prerequisite: iap.tunnelResourceAccessor
    # for the runner service account); the ephemeral external IP stays for
    # package egress only.
    if str(getattr(model, "session_mechanism", "") or "").lower() == "iap":
        c["use_iap"] = True
        # found live (stage 10 proof): a bake that follows another build in the
        # same run hits IAP's instance-lookup lag ("4047: Failed to lookup
        # instance") for longer than packer's default 30 s tunnel wait, and
        # SSH then times out with a healthy VM; give the tunnel two minutes
        c["iap_tunnel_launch_wait"] = 120
    # GCP-READINESS §6: spot build VMs; a preempted bake re-runs (stage 8.6)
    if getattr(model, "bake_preemptible", False):
        c["preemptible"] = True
    # finding 51: the runtime's bake disk size wins over the image's (which
    # inherits the OS builder's 200 GB default); the boot disk of every
    # instance launched from the image is exactly this size
    # stage 63: the one bake-disk rule the fingerprint also hashes (the
    # runtime's default_disk_size first, finding 51)
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.lineage import bake_disk_size
    size = bake_disk_size(GlobalTypeContext(), image, runtime)
    if size:
        c["disk_size"] = int(size)
    # stage 63 items 22-23: the one resolver, the same the ansible provisioner
    # asks (the runtime's ssh_username used to override the entry here, and
    # the provisioner never read the entry); `packer` is the family default
    # on GCE (googlecompute creates the account from metadata keys)
    from cs_image_system.base.bake_user import resolve_bake_user
    from cs_image_system.base.global_context import GlobalTypeContext
    c["ssh_username"] = resolve_bake_user(GlobalTypeContext(), image, runtime)
    networking = getattr(model, "networking", None)
    if networking is not None:
        if getattr(networking, "network", None) and networking.network not in OOPS_DEFAULTS:
            c["network"] = networking.network
        subnet = getattr(networking, "default_subnet_id", None)
        if subnet and subnet not in OOPS_DEFAULTS:
            c["subnetwork"] = subnet
        if getattr(networking, "network_tags", None):
            c["tags"] = [f'"{t}"' for t in networking.network_tags]
    for k, v in c.items():
        if isinstance(v, str) and not (v.startswith("var.") or v.startswith("data.")):
            c[k] = f'"{v}"'
    doc = Builder()
    doc.block("source", labels=[f'"{source_type}"', f'"{image.name}"'], **c)
    return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()
