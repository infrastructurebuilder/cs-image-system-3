# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``docker`` packer source for an image baked on a docker runtime
(stage 103), from HashiCorp's docker plugin.

A bake starts a container from the parent image, provisions it through the
daemon (no SSH: the plugin's docker communicator runs ``docker exec`` and
``docker cp``) and COMMITS it. The committed image carries the lineage
labels and the keepalive command as Dockerfile instructions (``changes``);
the build's names are tags, put on by the ``docker-tag`` post-processor the
runtime adds to the build block: the final name and the series' floating
tag, which a child image bakes from when its parent is deferred.
"""
from __future__ import annotations

import logging
import shlex
from typing import Any

import hcl2
from hcl2 import Builder

from cs_image_system.contract.constants import OOPS_DEFAULTS, SELF
from cs_image_system.hashicorp_utils.hashicorp import FO

from .docker_names import is_image_id, tag_name

log = logging.getLogger(__name__)

DOCKER_SOURCE = "docker"
#: PID 1's command in every image this runtime bakes (decision 2: no init
#: system; the launcher runs it under ``--init``)
KEEPALIVE_CMD = ["sleep", "infinity"]
#: where the bake writes what must not land in the image (the step runner)
BAKE_TMPFS = ["/run"]

_ARCH_PLATFORM = {"x86_64": "linux/amd64", "amd64": "linux/amd64", "arm64": "linux/arm64", "aarch64": "linux/arm64"}


def bake_container_name(image_name: str, runtime: str) -> str:
    """The build container's name: what ``ansible_host`` names for the
    docker connection, so one per image and runtime."""
    return tag_name(f"csis-bake-{runtime}-{image_name}").lower()


def _label_change(key: str, value: str) -> str:
    v = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'LABEL {key}="{v}"'


def docker_source(model: Any, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                  self_subconfig: Any, psi: Any, tags: dict[str, str], final_name: str,
                  pinned: str | None) -> list[str]:
    c: dict[str, Any] = {}
    # --- the bake's parent image
    if pinned:
        c["image"] = pinned if is_image_id(pinned) else str(pinned)
    elif psi.is_resolved():
        c["image"] = str(psi.identifier)
    else:
        # deferred: the parent series' floating tag, moved by every bake of
        # the series (the daemon's own "newest of the family")
        tag = psi.floating_tag() if hasattr(psi, "floating_tag") else None
        if not tag:
            raise ValueError(f"image {image.get_name()} on runtime {runtime}: no floating tag for its deferred "
                             f"parent {psi.source_name!r}")
        c["image"] = tag
    # the query pulled every vendor image it resolved; our own builds are
    # local and no registry has them
    c["pull"] = False
    c["commit"] = True
    arch = getattr(image, "architecture", None) or getattr(psi, "architecture", None)
    if arch and str(arch) not in OOPS_DEFAULTS and str(arch) in _ARCH_PLATFORM:
        c["platform"] = _ARCH_PLATFORM[str(arch)]
    # --- the build container: named (ansible reaches it by name), under an
    # init, on the runtime's network, with its machine type's limits
    run: list[str] = ["-d", "-i", "-t", "--init", "--name", bake_container_name(image.get_name(), runtime)]
    networking = getattr(model, "networking", None)
    network = getattr(networking, "network", None) if networking is not None else None
    if network and network not in OOPS_DEFAULTS:
        run += ["--network", str(network)]
    mt_name = None
    for cand in (getattr(subconfig, "machine_type", None) if subconfig else None,
                 getattr(subconfig, "default_machine_type", None) if subconfig else None,
                 model.get_default_machine_type()):
        if cand and cand not in OOPS_DEFAULTS:
            mt_name = str(cand)
            break
    mt = (model.get_machine_types() or {}).get(mt_name) if mt_name else None
    if mt is not None:
        if getattr(mt, "cpus", None):
            run += ["--cpus", str(mt.cpus)]
        if getattr(mt, "memory", None):
            run += ["--memory", str(mt.memory)]
    # the shell the bake provisions through is the CONTAINER's command, not an
    # entrypoint: packer's default `--entrypoint=/bin/sh` becomes the committed
    # image's entrypoint, and `ENTRYPOINT []` in `changes` does not clear it
    # (found live: every later `docker run <image> <cmd>` ran `/bin/sh <cmd>`)
    run += ["--", "{{.Image}}", "/bin/sh"]
    c["run_command"] = [f'"{a}"' for a in run]
    c["tmpfs"] = [f'"{t}"' for t in BAKE_TMPFS]
    # --- what the committed image carries
    changes = [_label_change(k, v) for k, v in sorted(tags.items())]
    changes.append("CMD " + "[" + ", ".join(f'"{a}"' for a in KEEPALIVE_CMD) + "]")
    c["changes"] = [f'"{ch.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"' for ch in changes]
    for k, v in c.items():
        if isinstance(v, str):
            c[k] = f'"{v}"'
    doc = Builder()
    doc.block("source", labels=[f'"{source_type}"', f'"{image.get_name()}"'], **c)
    return hcl2.dumps(doc.build(), formatter_options=FO).splitlines()


def docker_tag_post_processor(image: Any, *, repository: str, source_type: str, final_name: str,
                              prefix: str | None) -> list[str]:
    """The ``docker-tag`` post-processor of one image's build: the final name
    and the series' floating tag, in the runtime's repository."""
    names = [tag_name(final_name)] if final_name else []
    if prefix and tag_name(prefix) not in names:
        names.append(tag_name(prefix))
    if not names:
        return []
    return [
        f"  # stage 103: the build's names are tags ({image.get_name()}); the floating tag is the series' newest",
        '  post-processor "docker-tag" {',
        f'    only       = ["{source_type}.{image.get_name()}"]',
        f'    repository = "{repository}"',
        "    tags       = [" + ", ".join(f'"{n}"' for n in names) + "]",
        "  }",
    ]


def quoted(parts: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in parts)


__all__ = ["DOCKER_SOURCE", "KEEPALIVE_CMD", "SELF", "bake_container_name", "docker_source",
           "docker_tag_post_processor"]
