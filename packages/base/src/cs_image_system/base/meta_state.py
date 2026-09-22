# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Cross-run meta-state (DESIGN §3B, N5/N6, rev-14 derived rule).

Meta-state is the set of committed, human-readable YAML files that carry the
system's memory between runs: the identity and storage read-models, the pin
file (instance -> build and image -> base-build edges), image lineage, the
storage state machine's authoritative state + transition history, recorded
launch parameters, and a run journal.

Two invariants are enforced here rather than trusted to callers:

* **Location** -- meta-state lives at ``<config root>/meta-state/``, OUTSIDE
  every per-lifecycle generated directory, so a lifecycle wipe (Q5) can never
  touch it.
* **Publicness** -- the config repo is public by design (DESIGN standing
  constraint, rev 8). Every write is scanned for secret-shaped material and
  refused if any is found.
"""
from __future__ import annotations

import datetime
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import field
from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from pathlib import Path
from typing import Any

import yaml

from .constants import RUN_LOCAL_FILENAMES
from .encryption import decrypt_tree, decrypted_plaintexts
from .public_safe import (PRIVATE_DIRNAME, REFUSED_PATHS, PublicSafeError,  # noqa: F401
                          allow_from_config, assert_public_safe,
                          config_for, refused_path, scan_file, scan_for_plaintexts)

log = logging.getLogger(__name__)

META_STATE_DIRNAME = "meta-state"

IDENTITY_READ_MODEL = "identity.yaml"
STORAGE_READ_MODEL = "storage.yaml"
STORAGE_STATE = "storage-state.yaml"
LINEAGE = "lineage.yaml"
PINS = "pins.yaml"
LAUNCH_PARAMS = "launch-params.yaml"
RUNS = "runs.yaml"
VERIFICATIONS = "verifications.yaml"   # ephemeral / verified instances (stage 10.1)
IMAGE_TESTS = "image-tests.yaml"       # post-bake test results per build (stage 14)
STATE_LOCATIONS = "state-locations.yaml"  # every workspace's resolved state location, and the migrations (stage 46)
INSTANCE_STATE = "instance-state.yaml"  # generations: one machine each, and the superseded records (stage 60)
LOGIN_PROOFS = "login-proofs.yaml"     # CI logged in through the managed policy: every verdict (stage 56)

ALL_FILES = (IDENTITY_READ_MODEL, STORAGE_READ_MODEL, STORAGE_STATE, LINEAGE, PINS,
             LAUNCH_PARAMS, RUNS, STATE_LOCATIONS)

# Public-safe by construction (stage 35): the scanner lives in public_safe.py
# and is the same one behind the commit gate, `just public-safe` and the
# pre-commit hook; these names are kept for the callers of the first gate.
MetaStateSecretError = PublicSafeError
NEVER_STAGED = REFUSED_PATHS
never_staged = refused_path


def _never_staged_pathspecs() -> list[str]:
    """git pathspecs excluding REFUSED_PATHS names at any depth, appended to
    the run's ``add`` and ``commit`` so those files are never picked up --
    not even one the operator had staged by hand under the same trees."""
    # The private mirror is NOT excluded here. It was, from stage 49 until
    # stage 54 gave the configuration root a .gitignore that names it: an
    # `:(exclude)` pathspec makes git consider the path, and `git add -A`
    # then exits 1 saying it is ignored, which failed the whole run's commit.
    # Three things still keep it out -- .gitignore, `refused_path` in the
    # commit gate, and the scanner's own skip -- and none of them makes git
    # name a path it has been told to ignore.
    return [f":(exclude,glob)**/{pat}" for pat in REFUSED_PATHS]


def _run_local_exclude_pathspecs() -> list[str]:
    """stage 43: the run-local files (``run-summary.json``,
    ``state-report.json``) are excluded from the run's ``add``; the emitted
    root ``.gitignore`` names them too. Records (``final_execution.sh``,
    ``meta-state/runs.yaml``) are not run-local and stay."""
    return [f":(exclude,glob)**/{name}" for name in RUN_LOCAL_FILENAMES]


def _set_aside_tracked_run_local_files(top: Path, generated_root: Path) -> list[tuple[Path, Path]]:
    """Where an older tree TRACKS a run-local file, move it out of the working
    tree for the duration of the commit and return the moves to undo.

    A partial commit (one made with pathspecs, as the run's is) records HEAD's
    tree plus the WORKING-TREE state of the paths it names -- the index is not
    consulted -- so a tracked file leaves the repository only when it is absent
    from the working tree at commit time. Setting it aside is what lets one
    run remove it from the index; the file itself is put back untouched."""
    moves: list[tuple[Path, Path]] = []
    for name in RUN_LOCAL_FILENAMES:
        file = Path(generated_root) / name
        tracked = subprocess.run(["git", "-C", str(top), "ls-files", "--error-unmatch", "--", str(file)],
                                 check=False, capture_output=True).returncode == 0
        if tracked and file.exists():
            holding = Path(tempfile.mkdtemp(prefix="csis-run-local-")) / name
            shutil.move(str(file), str(holding))
            moves.append((file, holding))
    if moves:
        log.info("Meta-state commit: " + ", ".join(m[0].name for m in moves)
                 + " leave the index (run-local files are never committed; the files stay on disk)")
    return moves


def _dump(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=True, default_flow_style=False, allow_unicode=True)


@dataclass(config=CSIS_MODEL_CONFIG)
class MetaState:
    """Typed access to the meta-state directory. Reads are lazy; writes are
    immediate, atomic per file, and secret-scanned."""

    root: Path
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ io
    @classmethod
    def at(cls, config_root: Path) -> "MetaState":
        return cls(Path(config_root) / META_STATE_DIRNAME)

    def path(self, name: str) -> Path:
        return self.root / name

    def read(self, name: str) -> dict[str, Any]:
        if name in self._cache:
            return self._cache[name]
        p = self.path(name)
        data: dict[str, Any] = {}
        if p.is_file():
            loaded = yaml.safe_load(p.read_text()) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Meta-state file {p} must hold a mapping at the top level")
            # stage 50: a record carries the ciphertext it was written from, so
            # a read opens it again and every recorded-vs-declared comparison
            # is between PLAINTEXTS -- two markers for one value differ after a
            # rotation, and comparing those would report drift that is not
            # there. A record with no marker needs no identity.
            data = decrypt_tree(loaded, source=str(p))
        self._cache[name] = data
        return data

    def write(self, name: str, data: dict[str, Any]) -> Path:
        assert_public_safe(data, where=f"meta-state/{name}")
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.path(name)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(_dump(data))
        tmp.replace(p)
        self._cache[name] = data
        return p

    def exists(self) -> bool:
        return self.root.is_dir()

    def invalidate(self) -> None:
        self._cache.clear()

    # --------------------------------------------------------- read-models
    def write_identity_read_model(self, model: dict[str, Any]) -> Path:
        return self.write(IDENTITY_READ_MODEL, model)

    def identity_read_model(self) -> dict[str, Any]:
        return self.read(IDENTITY_READ_MODEL)

    def write_storage_read_model(self, model: dict[str, Any]) -> Path:
        return self.write(STORAGE_READ_MODEL, model)

    def storage_read_model(self) -> dict[str, Any]:
        return self.read(STORAGE_READ_MODEL)

    # ------------------------------------------------- storage state machine
    def storage_states(self) -> dict[str, dict[str, Any]]:
        """``{storage name: {state, history: [...]}}`` -- the authoritative
        current state of every storage the system has ever managed."""
        return self.read(STORAGE_STATE).setdefault("storages", {})

    def storage_state(self, name: str) -> str | None:
        entry = self.storage_states().get(name)
        return entry.get("state") if entry else None

    def record_storage_transition(self, name: str, from_state: str | None, to_state: str,
                                  run_id: str, action: str | None = None,
                                  facts: dict[str, Any] | None = None) -> None:
        """One transition into the authoritative record. A destroyed -> active
        transition is a REGENERATION (stage 10.12): the entry's generation
        counter moves on and the history keeps the earlier life. ``facts``
        (owning builder, type, bucket name) let an undeclared storage still
        be planned and wiped after its entry left the YAML."""
        from .models.storage import STORAGE_STATE_ACTIVE, STORAGE_STATE_DESTROYED
        data = self.read(STORAGE_STATE)
        storages = data.setdefault("storages", {})
        entry = storages.setdefault(name, {"state": to_state, "history": []})
        entry.setdefault("generation", 1)
        if from_state == STORAGE_STATE_DESTROYED and to_state == STORAGE_STATE_ACTIVE:
            entry["generation"] = int(entry.get("generation") or 1) + 1
        entry["state"] = to_state
        if facts:
            entry["facts"] = {**(entry.get("facts") or {}), **facts}
        entry.setdefault("history", []).append({
            "from": from_state, "to": to_state, "run": run_id, "generation": entry["generation"],
            **({"action": action} if action else {}),
        })
        self.write(STORAGE_STATE, data)

    def storage_generation(self, name: str) -> int:
        entry = self.storage_states().get(name) or {}
        return int(entry.get("generation") or 1)

    # ------------------------------------------ instance generations (stage 60)
    GENERATION_KINDS = ("durable", "ephemeral")

    def instance_states(self) -> dict[str, dict[str, Any]]:
        return dict(self.read(INSTANCE_STATE).get("instances", {}))

    def instance_generation(self, name: str, kind: str = "durable") -> int:
        """How many generations of ``kind`` this instance name has had; 0
        when none was ever recorded. Stage 55 step 4 builds the canonical
        hostname from the DURABLE count."""
        counters = (self.instance_states().get(name) or {}).get("generation") or {}
        return int(counters.get(kind) or 0)

    def current_generation(self, name: str) -> dict[str, Any] | None:
        """The open generation -- the machine that stands now -- or None."""
        cur = (self.instance_states().get(name) or {}).get("current")
        return dict(cur) if cur else None

    def open_generation(self, name: str, *, kind: str, run_id: str, how: str,
                        launch_params: dict[str, Any], identity: dict[str, Any] | None = None) -> int:
        """A machine came into being: the ``kind`` counter moves on and the
        generation opens, carrying a SNAPSHOT of the launch parameters it
        booted with (launch-params.yaml is overwritten on the next launch;
        the snapshot is what the archive keeps). ``how`` says what the claim
        rests on: ``observed`` (the provider's id), ``inferred`` (our own
        control flow), or ``adopted`` (a machine that stood before
        generations were recorded -- generation 1 of the RECORD, not of the
        name). Refuses to open over an open one: close it first, with a why."""
        from datetime import datetime, timezone
        if kind not in self.GENERATION_KINDS:
            raise ValueError(f"generation kind must be one of {self.GENERATION_KINDS}, not {kind!r}")
        data = self.read(INSTANCE_STATE)
        instances = data.setdefault("instances", {})
        entry = instances.setdefault(name, {"generation": {"durable": 0, "ephemeral": 0}, "history": []})
        if entry.get("current"):
            raise ValueError(f"instance {name!r} already has an open generation "
                             f"({entry['current'].get('kind')} {entry['current'].get('number')}); close it first")
        counters = entry.setdefault("generation", {"durable": 0, "ephemeral": 0})
        counters[kind] = int(counters.get(kind) or 0) + 1
        cur: dict[str, Any] = {"number": counters[kind], "kind": kind, "how": how,
                               "opened_run": run_id,
                               "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "launch_params": dict(launch_params)}
        for k in ("instance_id", "provider_hostname"):
            if identity and identity.get(k):
                cur[k] = str(identity[k])
        entry["current"] = cur
        self.write(INSTANCE_STATE, data)
        return counters[kind]

    def note_generation_identity(self, name: str, identity: dict[str, Any]) -> bool:
        """The provider's identity for the open generation, once known. A
        generation opened on inference becomes ``observed`` at this point:
        the machine has now been seen. True when something was written."""
        data = self.read(INSTANCE_STATE)
        cur = ((data.get("instances") or {}).get(name) or {}).get("current")
        if not cur:
            return False
        changed = False
        for k in ("instance_id", "provider_hostname"):
            v = identity.get(k)
            if v and cur.get(k) != str(v):
                cur[k] = str(v)
                changed = True
        if changed and cur.get("how") == "inferred":
            cur["how"] = "observed"
        if changed:
            self.write(INSTANCE_STATE, data)
        return changed

    def close_generation(self, name: str, *, run_id: str, why: str) -> dict[str, Any] | None:
        """The machine is gone (or superseded): the open generation moves
        into the history with the run that closed it and why -- never
        deleted, never overwritten. None when nothing was open."""
        from datetime import datetime, timezone
        data = self.read(INSTANCE_STATE)
        entry = (data.get("instances") or {}).get(name)
        if entry is None:
            return None
        cur = entry.pop("current", None)
        if not cur:
            return None
        closed = {**cur, "closed_run": run_id, "why": why,
                  "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        entry.setdefault("history", []).append(closed)
        self.write(INSTANCE_STATE, data)
        return closed

    # -------------------------------------------------------------- lineage
    def builds(self) -> list[dict[str, Any]]:
        return self.read(LINEAGE).setdefault("builds", [])

    def add_build(self, record: dict[str, Any]) -> None:
        data = self.read(LINEAGE)
        builds = data.setdefault("builds", [])
        if any(b.get("build_id") == record.get("build_id") for b in builds):
            log.debug(f"Build {record.get('build_id')} already recorded in lineage; skipping")
            return
        builds.append(record)
        self.write(LINEAGE, data)

    def remove_build(self, build_id: str) -> dict[str, Any] | None:
        """Drop a build's lineage record (disposal, stage 8.4): the artifact
        is gone from the cloud, so a record would be `missing` drift. The
        git history keeps the record. Returns what was removed."""
        data = self.read(LINEAGE)
        builds = data.setdefault("builds", [])
        rec = next((b for b in builds if b.get("build_id") == build_id), None)
        if rec is not None:
            builds.remove(rec)
            self.write(LINEAGE, data)
        return rec

    def builds_for_series(self, series: str) -> list[dict[str, Any]]:
        return [b for b in self.builds() if b.get("series") == series]

    def build(self, build_id: str) -> dict[str, Any] | None:
        for b in self.builds():
            if b.get("build_id") == build_id:
                return b
        return None

    def series_head(self, series: str, runtime: str | None = None) -> dict[str, Any] | None:
        """Most recently recorded build of a series (lineage is append-only),
        on ``runtime`` when given -- a series has one head PER runtime."""
        builds = [b for b in self.builds_for_series(series)
                  if runtime is None or b.get("runtime") in (None, runtime)]
        return builds[-1] if builds else None

    # ----------------------------------------------------------------- pins
    def _pins(self) -> dict[str, Any]:
        data = self.read(PINS)
        data.setdefault("instances", {})
        data.setdefault("images", {})
        data.setdefault("upgrades", [])
        return data

    def instance_pin(self, instance: str) -> str | None:
        return self._pins()["instances"].get(instance)

    @staticmethod
    def image_pin_key(image: str, runtime: str | None) -> str:
        """Image pins are keyed per runtime (``<image>@<runtime>``): the same
        logical image baked on two runtimes has two parents, two builds and
        therefore two pins. A key without ``@`` is a legacy single-runtime pin."""
        return f"{image}@{runtime}" if runtime else image

    def image_pin(self, image: str, runtime: str | None = None) -> str | None:
        table = self._pins()["images"]
        if runtime:
            keyed = table.get(self.image_pin_key(image, runtime))
            if keyed:
                return keyed
            # legacy key: honoured only when lineage cannot place that build on
            # a DIFFERENT runtime (an AMI must never become a GCE parent)
            legacy = table.get(image)
            if legacy:
                record = self.build(str(legacy))
                if record is None or record.get("runtime") in (None, runtime):
                    return legacy
            return None
        return table.get(image)

    def bind_instance(self, instance: str, build_id: str, run_id: str) -> None:
        data = self._pins()
        data["instances"][instance] = build_id
        data["upgrades"].append({"kind": "instance", "name": instance, "to": build_id,
                                 "run": run_id, "op": "bind"})
        self.write(PINS, data)

    def bind_image(self, image: str, base_build_id: str, run_id: str,
                   runtime: str | None = None) -> None:
        data = self._pins()
        key = self.image_pin_key(image, runtime)
        data["images"][key] = base_build_id
        if runtime and data["images"].get(image) == base_build_id:
            del data["images"][image]  # the legacy key is superseded by the keyed one
        data["upgrades"].append({"kind": "image", "name": key, "to": base_build_id,
                                 "run": run_id, "op": "bind", **({"runtime": runtime} if runtime else {})})
        self.write(PINS, data)

    def move_pin(self, kind: str, name: str, to_build: str, run_id: str,
                 op: str = "upgrade", pending: bool = True) -> str | None:
        """The explicit upgrade operation: move exactly one edge. Returns the
        previous build id. ``op="follow"`` records a policy-driven move
        (stage 9); ``pending=False`` skips the replacement marker (the
        replacement already happened)."""
        if kind not in ("instance", "image"):
            raise ValueError(f"Unknown pin kind {kind!r}")
        data = self._pins()
        table = data["instances" if kind == "instance" else "images"]
        previous = table.get(name)
        if previous is None and kind == "image" and "@" in name:
            # a legacy single-runtime pin moves into its keyed form
            previous = table.pop(name.split("@", 1)[0], None)
        table[name] = to_build
        data["upgrades"].append({"kind": kind, "name": name, "from": previous,
                                 "to": to_build, "run": run_id, "op": op})
        if kind == "instance" and pending:
            data.setdefault("pending_replacements", {})[name] = to_build
        self.write(PINS, data)
        return previous

    def pending_replacements(self) -> dict[str, str]:
        return dict(self._pins().get("pending_replacements", {}))

    def clear_pending_replacement(self, instance: str) -> None:
        data = self._pins()
        data.get("pending_replacements", {}).pop(instance, None)
        self.write(PINS, data)

    def unpin_images_at(self, build_id: str, run_id: str) -> list[str]:
        """Remove every image pin pointing at ``build_id`` (its disposal): a
        pin at a deleted parent would bake the next child FROM nothing.
        Logged as ``op: dispose``; the next bake first-binds to the series
        head again. Returns the pin keys removed."""
        data = self._pins()
        removed = [key for key, b in data["images"].items() if b == build_id]
        for key in removed:
            del data["images"][key]
            data["upgrades"].append({"kind": "image", "name": key, "from": build_id,
                                     "to": None, "run": run_id, "op": "dispose"})
        if removed:
            self.write(PINS, data)
        return removed

    def remove_instance_pin(self, instance: str, run_id: str, op: str = "decommission") -> None:
        data = self._pins()
        if instance in data["instances"]:
            previous = data["instances"].pop(instance)
            data["upgrades"].append({"kind": "instance", "name": instance, "from": previous,
                                     "to": None, "run": run_id, "op": op})
            data.get("pending_replacements", {}).pop(instance, None)
            self.write(PINS, data)

    # -------------------------------------------------------- launch params
    def launch_params(self) -> dict[str, dict[str, Any]]:
        return self.read(LAUNCH_PARAMS).setdefault("instances", {})

    def record_launch_params(self, instance: str, params: dict[str, Any]) -> None:
        data = self.read(LAUNCH_PARAMS)
        data.setdefault("instances", {})[instance] = params
        self.write(LAUNCH_PARAMS, data)

    def remove_launch_params(self, instance: str) -> None:
        data = self.read(LAUNCH_PARAMS)
        if instance in data.get("instances", {}):
            del data["instances"][instance]
            self.write(LAUNCH_PARAMS, data)

    # ----------------------------------------------------------------- runs
    def record_run(self, summary: dict[str, Any]) -> None:
        data = self.read(RUNS)
        runs = data.setdefault("runs", [])
        # One entry per run id: a run may journal twice (before its commit and
        # at exit); the later record replaces the earlier.
        runs[:] = [r for r in runs if r.get("run") != summary.get("run")]
        runs.append(summary)
        # Keep the journal bounded; the git history is the full record.
        del runs[:-200]
        self.write(RUNS, data)

    # -------------------------------------------------------- verifications
    def verifications(self) -> list[dict[str, Any]]:
        return self.read(VERIFICATIONS).setdefault("verifications", [])

    def record_verification(self, record: dict[str, Any]) -> None:
        data = self.read(VERIFICATIONS)
        data.setdefault("verifications", []).append(record)
        del data["verifications"][:-500]
        self.write(VERIFICATIONS, data)

    # ------------------------------------------------- login proofs (stage 56)
    def login_proofs(self) -> list[dict[str, Any]]:
        return self.read(LOGIN_PROOFS).setdefault("proofs", [])

    def record_login_proof(self, record: dict[str, Any]) -> None:
        data = self.read(LOGIN_PROOFS)
        data.setdefault("proofs", []).append(record)
        del data["proofs"][:-500]
        self.write(LOGIN_PROOFS, data)

    # ------------------------------------------- post-bake image tests (stage 14)
    def image_tests(self) -> dict[str, Any]:
        """``{build_id: {"ok", "run", "instance", "runtime", "time", "checks"}}`` --
        the latest post-bake result per build."""
        return self.read(IMAGE_TESTS).setdefault("builds", {})

    def record_image_test(self, build_id: str, record: dict[str, Any]) -> None:
        data = self.read(IMAGE_TESTS)
        data.setdefault("builds", {})[str(build_id)] = record
        self.write(IMAGE_TESTS, data)

    def instance_pins(self) -> dict[str, str]:
        return dict(self._pins()["instances"])

    def image_pins(self) -> dict[str, str]:
        return dict(self._pins()["images"])

    # ------------------------------------------------------ state locations
    @staticmethod
    def location_key(record: dict[str, Any]) -> str:
        """What makes a location THE location (stage 46): the type's rendering of
        it, ``<type>://<container>/<key>`` (stage 47); region, profile and
        encryption are how it is reached, not where it is. A record from before
        the `location` field is read through its S3 fields."""
        location = record.get("location")
        if location:
            return str(location)
        return f"{record.get('type', '')}://{record.get('bucket', '')}/{record.get('key', '')}"

    def state_locations(self) -> dict[str, dict[str, Any]]:
        """workspace -> the location it was last generated against (stage 46.4):
        the backend's name and the settings its ``.tfbackend.hcl`` carried
        (type, bucket, key, region, profile, ...), and the run that recorded
        it. The record, not the emission, is the memory a later run's move
        guard compares against."""
        return {k: dict(v) for k, v in (self.read(STATE_LOCATIONS).get("workspaces") or {}).items()}

    def record_state_locations(self, locations: dict[str, dict[str, Any]], run_id: str) -> None:
        """Merge this run's resolved locations over the record (a scoped run
        generates some workspaces and leaves the others' records alone)."""
        data = self.read(STATE_LOCATIONS)
        workspaces = data.setdefault("workspaces", {})
        for workspace, location in locations.items():
            workspaces[workspace] = {**location, "run": run_id}
        self.write(STATE_LOCATIONS, data)

    def state_migrations(self) -> list[dict[str, Any]]:
        return list(self.read(STATE_LOCATIONS).get("migrations") or [])

    def record_state_migration(self, workspace: str, from_location: dict[str, Any],
                               to_location: dict[str, Any], run_id: str, serial: int | None,
                               backup: str | None) -> None:
        """A performed move (stage 46.4.3.5): from, to, when, the state serial
        and the backup file, appended to the audit list; the workspace's record
        moves with it."""
        data = self.read(STATE_LOCATIONS)
        data.setdefault("migrations", []).append({
            "workspace": workspace, "from": dict(from_location), "to": dict(to_location),
            "run": run_id, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "serial": serial, "backup": backup,
        })
        data.setdefault("workspaces", {})[workspace] = {**to_location, "run": run_id}
        self.write(STATE_LOCATIONS, data)


# ---------------------------------------------------------------- git commit

def git_toplevel(path: Path) -> Path | None:
    try:
        res = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=False)
    except OSError:
        return None
    if res.returncode != 0:
        return None
    return Path(res.stdout.strip())


def commit_meta_state(config_root: Path, generated_root: Path, run_id: str,
                      lifecycles: list[str], dry_run: bool) -> str | None:
    """The single well-formed meta-state commit (DESIGN §3B).

    Stages ``meta-state/`` and the generated-IaC tree and commits them with a
    templated message. Returns the new commit sha, or ``None`` when there was
    nothing to commit or the config root is not inside a git repository (a
    warning, not an error: relocation to a config repo is what makes this
    meaningful). Never runs when the caller did not ask for it.
    """
    top = git_toplevel(config_root)
    if top is None:
        log.warning(f"Config root {config_root} is not inside a git repository; "
                    "meta-state commit skipped")
        return None
    paths = [str(Path(config_root) / META_STATE_DIRNAME), str(generated_root)]
    existing = []
    for candidate in paths:
        if not Path(candidate).exists():
            continue
        # A repo may gitignore a tree (this repo ignores the fixture's
        # generated/); adding it would fail, so skip it with a warning --
        # found live at the first successful bake's meta-state commit.
        ignored = subprocess.run(["git", "-C", str(top), "check-ignore", "-q", candidate],
                                 check=False, capture_output=True).returncode == 0
        if ignored:
            log.warning(f"Meta-state commit: {candidate} is gitignored here; not committing it")
            continue
        existing.append(candidate)
    if not existing:
        return None
    aside = _set_aside_tracked_run_local_files(top, generated_root)
    try:
        return _commit_staged(top, existing, run_id, lifecycles, dry_run, config_root)
    finally:
        for file, holding in aside:
            shutil.move(str(holding), str(file))
            shutil.rmtree(holding.parent, ignore_errors=True)


def _commit_staged(top: Path, existing: list[str], run_id: str, lifecycles: list[str],
                   dry_run: bool, config_root: Path) -> str | None:
    # stage 34: belt to the ignore policy's braces -- a plan, state or key file
    # under the run's trees is never staged, and the operator is told which.
    # The listing excludes the run-local files (never staged, no warning due)
    # but not the refused names, so those are still seen and named.
    would_add = subprocess.run(["git", "-C", str(top), "add", "-A", "--dry-run", "--",
                                *existing, *_run_local_exclude_pathspecs()],
                               check=True, capture_output=True, text=True).stdout
    adds = sorted({m.group(1) for m in re.finditer(r"^add '(.+)'$", would_add, re.M)})
    refused = [rel for rel in adds if never_staged(rel)]
    if refused:
        log.warning(f"Meta-state commit: never staging {', '.join(refused)} "
                    "(plans, state and key material carry decrypted values)")
    # stage 35: the gate -- every file about to be staged is scanned, with the
    # configuration's allowances, before the index is touched; a finding
    # refuses the whole commit and the run never records a secret
    allow = allow_from_config(config_for(config_root))
    findings = [f for rel in adds if not never_staged(rel) for f in scan_file(top, rel, allow)]
    # stage 49: and the primary guard -- no value this run DECRYPTED may stand
    # in clear in what is about to be committed. The system opened those
    # markers, so this does not guess at shapes the way the rules must.
    findings += scan_for_plaintexts(Path(config_root), decrypted_plaintexts())
    if findings:
        raise PublicSafeError(findings, "the run's meta-state commit")
    pathspecs = [*existing, *_never_staged_pathspecs()]
    subprocess.run(["git", "-C", str(top), "add", "-A", "--", *pathspecs, *_run_local_exclude_pathspecs()],
                   check=True, capture_output=True, text=True)
    staged = subprocess.run(["git", "-C", str(top), "diff", "--cached", "--quiet"],
                            check=False, capture_output=True, text=True)
    if staged.returncode == 0:
        log.info("Meta-state commit: nothing changed")
        return None
    mode = "dry-run generation" if dry_run else "run"
    message = (f"cs-image-system {mode} {run_id}: {', '.join(lifecycles) or 'no lifecycles'}\n\n"
               f"Meta-state commit: read-models, pins, lineage, launch parameters and "
               f"generated IaC for lifecycles [{', '.join(lifecycles)}].\n"
               f"Run id: {run_id}")
    # stage 28: commit ONLY the paths this run staged -- the config repo is
    # where operators edit configuration, and a bare `git commit` would sweep
    # whatever they had staged into a "cs-image-system run" commit
    subprocess.run(["git", "-C", str(top), "commit", "-q", "-m", message, "--", *pathspecs],
                   check=True, capture_output=True, text=True)
    sha = subprocess.run(["git", "-C", str(top), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True).stdout.strip()
    log.info(f"Meta-state committed as {sha}")
    return sha
