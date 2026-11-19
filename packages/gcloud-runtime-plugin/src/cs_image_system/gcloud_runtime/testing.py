# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What stands in for the Google Cloud runtime's calls to Google Cloud in a
stubbed test run.

A test that drives a whole run over a fixture declaring a ``gcloud``
runtime hands :func:`stub` to the test kit (``cs_image_system.system.testing``),
with the fixture's configuration directory. The network discovery, the
vendor image query, the image listing, the post-bake test session and the
relabelling are then answered here, so no test reaches Google Cloud and a
golden can pin the family's emission.

This module is test support shipped with the plugin, so that the family's
own tests and any suite that runs it beside other providers use the same
answers. Nothing in a run imports it.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from . import gcp_utils
from .gcp_runtime_builders import GCPCloudBuilder

#: what a stubbed runtime's vendor image query answers: (image, project)
VENDOR_IMAGE = ("debian-11-v1", "debian-cloud")

#: subnets every stubbed network holds, whatever the fixture declares (the
#: overlay tests name them)
DEFAULT_SUBNETS = ("projects/my-project/regions/us-east1/subnetworks/default",
                   "projects/my-project/regions/us-east1/subnetworks/custom-subnet-1")


def _passing_session(real: Callable[..., tuple[int, str]]) -> Callable[..., tuple[int, str]]:
    """Answer PASS for every assertion a post-bake test script carries; hand
    any other script to ``real`` (its subprocess is what those tests fake)."""
    def _run(self, name, script, timeout=300):
        idx = re.findall(r'CSIS_TEST (\d+) PASS', script)
        if not idx:
            return real(self, name, script, timeout)
        return 0, "".join(f"CSIS_TEST {i} PASS\n" for i in sorted(set(idx), key=int))
    return _run


def network_map(config: Path | None) -> Callable[..., tuple[dict[str, Any], str, dict[str, Any]]]:
    """The network discovery's answer for a fixture: one ``default`` network
    holding :data:`DEFAULT_SUBNETS` and every subnet a ``gcloud`` runtime of
    ``config/cfg/runtime-builders.yml`` names. Which subnets exist is a
    live-account fact; the fixture's ids are data the tests must not
    restate."""
    def _answer(session_config: Any, clients: Any = None) -> tuple[dict[str, Any], str, dict[str, Any]]:
        subnets = [{"subnet_id": s} for s in DEFAULT_SUBNETS]
        declared = (config / "cfg" / "runtime-builders.yml") if config is not None else None
        if declared is not None and declared.is_file():
            d = yaml.safe_load(declared.read_text()) or {}
            for runtime in d.get("runtime_builders", []):
                if runtime.get("type") == "gcloud":
                    for s in (runtime.get("networking", {}) or {}).get("subnets") or []:
                        subnets.append({"subnet_id": s.get("subnet_id")})
        return ({"default": {"subnets": subnets}}, "default", {})
    return _answer


def stub_declared_networks(monkeypatch: Any, runtimes: list[dict[str, Any]]) -> None:
    """Answer the network discovery from ``runtimes`` (runtime declarations
    as a configuration's ``runtime-builders`` files hold them): each
    ``gcloud`` runtime's network, holding the subnets it names. For a test
    over a tree that names its own placeholders, not the fixture's ids."""
    networks: dict[str, dict[str, Any]] = {"default": {"subnets": []}}
    for runtime in runtimes:
        if runtime.get("type") != "gcloud":
            continue
        net = runtime.get("networking") or {}
        entry = networks.setdefault(str(net.get("network") or "default"), {"subnets": []})
        for s in net.get("subnets") or []:
            entry["subnets"].append({"subnet_id": s.get("subnet_id")})
    monkeypatch.setattr(gcp_utils, "get_network_map_and_default_network",
                        lambda session_config, clients=None: (networks, "default", {}))


def stub(monkeypatch: Any, retags: list[tuple[str, dict[str, str]]] | None = None, *,
         config: Path | None = None) -> None:
    """Replace the Google Cloud runtime's calls to Google Cloud for the
    length of the test that owns ``monkeypatch``: the network discovery
    answers :func:`network_map` of ``config`` (the fixture's configuration
    directory), the vendor image query :data:`VENDOR_IMAGE` (with no extra facts), the image
    listing "nothing of ours exists", a post-bake test session PASS, and a
    relabel is appended to ``retags`` (a journal the caller may share with
    other providers' stubs; one is made when none is given)."""
    journal = retags if retags is not None else []
    monkeypatch.setattr(gcp_utils, "get_network_map_and_default_network", network_map(config))
    monkeypatch.setattr(GCPCloudBuilder, "query_provider_image", lambda self, osb: (*VENDOR_IMAGE, {}))
    monkeypatch.setattr(GCPCloudBuilder, "query_images", lambda self, series: [])
    monkeypatch.setattr(GCPCloudBuilder, "run_session_command",
                        _passing_session(GCPCloudBuilder.run_session_command))
    monkeypatch.setattr(GCPCloudBuilder, "retag_image",
                        lambda self, image_id, tags: journal.append((image_id, dict(tags))) or True)
