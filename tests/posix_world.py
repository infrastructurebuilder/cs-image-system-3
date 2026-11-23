# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A fixture world whose instance ``test`` is POSIX-owned, for the tests
of the server registry (spec 010).

The POSIX identity keeps its registry in the configuration's records
(``meta-state/servers.yaml``), so a test seeds the registry by writing
that record, never by stubbing an identity plugin: ``test`` takes the
image ``imgfile-posix``, owned by ``pxgroup`` on the group builder
``posix-local``, and every runtime's report of a machine is answered
in-process. Nothing here reaches a network.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tests.harness import FixtureRun, copy_config

IDENTITY, GROUP, HOSTNAME = "posix-local", "pxgroup", "test-001"
#: the runtime's report of the machine behind ``test``
MACHINE = {"instance_id": "i-0abc", "provider_hostname": "ip-10-0-0-5", "address": "10.0.0.5"}


def make_posix_owned(root: Path, ephemeral: bool = False) -> Path:
    """Give the fixture copy at ``root`` a POSIX-owned ``test``."""
    path = root / "instances" / "instances.yaml"
    data = yaml.safe_load(path.read_text())
    test = next(i for i in data["instances"] if i["name"] == "test")
    test["image"] = "imgfile-posix"
    if ephemeral:
        test["ephemeral"] = True
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return root


def seed_servers(root: Path, servers: Any, group: str = GROUP) -> None:
    """Record ``servers`` (a list of entries) as ``group``'s registry; a
    string is written as the file's text, to make the record unreadable."""
    text = servers if isinstance(servers, str) else yaml.safe_dump({"servers": {IDENTITY: {group: servers}}})
    (root / "meta-state" / "servers.yaml").write_text(text)


def answer_identity(run: FixtureRun, monkeypatch, answers: dict[str, dict[str, str] | None]) -> list[str]:
    """Every runtime answers ``query_instance_identity`` from ``answers``
    (instance name -> report, None for none); returns the names asked."""
    asked: list[str] = []

    def report(self: Any, name: str) -> dict[str, str] | None:
        asked.append(name)
        found = answers.get(name)
        return dict(found) if found else None
    for rtb in {type(b) for b in run.ctx.runtime_builders.values()}:
        monkeypatch.setattr(rtb, "can_query_instance_identity", lambda self: True)
        monkeypatch.setattr(rtb, "query_instance_identity", report)
    return asked


def posix_world(tmp_path: Path, monkeypatch, *, dry_run: bool = False, servers: Any = None,
                answer: dict[str, str] | None = MACHINE, undeclare: list[str] | None = None,
                ephemeral: bool = False) -> tuple[FixtureRun, list[str]]:
    """The run with applies on, and the list of instances the runtime was
    asked about. ``servers``: the entries to record first (see
    ``seed_servers``); ``answer``: the runtime's report of ``test``'s
    machine; ``undeclare``: instances this run leaves out of the tree, as
    `--undeclare` does."""
    root = make_posix_owned(copy_config(tmp_path), ephemeral)
    if servers is not None:
        seed_servers(root, servers)
    run = FixtureRun(tmp_path, monkeypatch, dry_run=dry_run, config_root=root, undeclare=undeclare)
    asked = answer_identity(run, monkeypatch, {"test": answer})
    run.ctx.config["apply_instances"] = True
    return run, asked


def launched(run: FixtureRun, launched_run: str = "run-before", hostname: str = HOSTNAME) -> None:
    """Record ``test`` as launched under ``hostname`` in ``pxgroup``."""
    ms = run.ctx.meta_state
    rec = dict(ms.launch_params().get("test") or {})
    rec.update({"hostname": hostname, "group": GROUP, "launched": True, "launched_run": launched_run})
    ms.record_launch_params("test", rec)


def entry(**over: Any) -> dict[str, Any]:
    """A registry entry for ``test``'s machine, with ``over`` changed."""
    return {"id": "i-0abc", "hostname": HOSTNAME, "address": "10.0.0.5", "canonical_name": HOSTNAME,
            "alt_names": [], "instance_id": "i-0abc", "instance": "test", "registered_run": "run-before", **over}
