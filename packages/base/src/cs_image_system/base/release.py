# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``release`` lifecycle (EXPLORE "Systemic Purpose": formally release
images known to be correct for a given model).

A release is a recorded, reviewable mark on a *build* (a lineage record):
``meta-state/releases.yaml`` holds every release ever made and, per model,
the current released build of each image series. Releasing requires
evidence: the build exists in lineage, it passed its in-bake verification
(a build only exists if the bake -- including the verify provisioner --
succeeded, and lineage records the assertion count), and every
modification it carries has no failed local mod test on record (a missing
mod test is tolerated unless ``config.require_mod_tests`` is true).

The lifecycle itself (registered after ``instance-image``) regenerates the
release read-model under ``generated/release/`` and defers the artifact
marking (e.g. tagging the AMI) to its runner script, applied only when
``config.apply_release`` is true -- the same gate discipline as everything
else. With ``config.require_released_builds: true`` an instance may pin only
to a released build of its image (a validator; the first bind of an
unreleased build is refused).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml

from .lifecycle import ExecutionLifecyclePhase
from .lifecycles import LifecycleLike, LifecycleSpec
from .meta_state import MetaState
from .utils import apply_enabled

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

RELEASES_FILE = "releases.yaml"
MOD_TESTS_FILE = "mod-tests.yaml"
RELEASE_LIFECYCLE = LifecycleSpec(name="release", after="instance-image", phases=(),
                                  description="mark tested builds as released for a model")
DEFAULT_MODEL = "default"


class ReleaseError(ValueError):
    pass


def releases(ms: MetaState) -> dict[str, Any]:
    data = ms.read(RELEASES_FILE)
    data.setdefault("releases", [])
    data.setdefault("current", {})
    return data


def released_builds(ms: MetaState, image: str, model: str | None = None) -> set[str]:
    data = releases(ms)
    out: set[str] = set()
    for m, images in data["current"].items():
        if model and m != model:
            continue
        b = images.get(image)
        if b:
            out.add(str(b))
    return out


def release(ctx: "GlobalTypeContext", image: str, build_id: str, model: str = DEFAULT_MODEL,
            note: str = "") -> dict[str, Any]:
    ms = ctx.meta_state
    record = ms.build(build_id)
    if record is None:
        raise ReleaseError(f"build {build_id!r} is not recorded in lineage; only baked builds can be released")
    if record.get("series") != image:
        raise ReleaseError(f"build {build_id!r} belongs to series {record.get('series')!r}, not {image!r}")
    tests = record.get("tests") or {}
    if not tests.get("in_bake"):
        raise ReleaseError(f"build {build_id!r} carries no in-bake verification record; "
                           "rebuild it with the verify provisioner before releasing")
    mod_results = ms.read(MOD_TESTS_FILE).get("results", {}) or {}
    require = bool(ctx.config.get("require_mod_tests", False))
    for m in record.get("mods", []) or []:
        r = mod_results.get(m.get("content_hash"))
        if r is None:
            if require:
                raise ReleaseError(f"modification {m.get('name')!r} of build {build_id!r} has no local "
                                   "mod-test result (config.require_mod_tests)")
            continue
        if r.get("status") != "pass" or r.get("idempotent") is False:
            raise ReleaseError(f"modification {m.get('name')!r} of build {build_id!r} failed its local "
                               f"mod test (status={r.get('status')}, idempotent={r.get('idempotent')})")
    # stage 14.3: an image that declares post-bake tests releases only a build
    # with a PASSING record (config.require_image_tests, default on)
    from .image_tests import post_bake_spec
    img = ctx.images_map.get(image)
    if post_bake_spec(img) if img is not None else False:
        if ctx.config.get("require_image_tests", True):
            result = ms.image_tests().get(str(build_id))
            if result is None:
                raise ReleaseError(f"build {build_id!r} has no post-bake test record while {image!r} declares "
                                   "tests.post_bake -- launch it (ephemeral) and verify first "
                                   "(config.require_image_tests)")
            if not result.get("ok"):
                failed = [c.get("name") for c in result.get("checks", []) if not c.get("ok")]
                raise ReleaseError(f"build {build_id!r} failed its post-bake tests in run {result.get('run')}: "
                                   f"{'; '.join(str(f) for f in failed)[:300]}")
    data = releases(ms)
    entry = {"image": image, "build_id": build_id, "model": model, "run": ctx.run_id,
             "note": note, "name": record.get("name"), "capabilities": record.get("capabilities")}
    data["releases"].append(entry)
    data["current"].setdefault(model, {})[image] = build_id
    ms.write(RELEASES_FILE, data)
    log.info(f"Released {image} build {build_id} for model {model}")
    return entry


# ---------------------------------------------------------- lifecycle hooks

def declared_release_targets(ctx: "GlobalTypeContext") -> list[tuple[str, str, str, str]]:
    """``[(image, runtime, build_id, model)]`` -- for every image declaring
    ``release: {model}``, each runtime's series head that has a PASSING
    post-bake record and is not already the model's current release
    (stage 14; recomputed at execution by the deferred `release` step)."""
    from .image_tests import post_bake_spec
    ms = ctx.meta_state
    tests = ms.image_tests()
    current = releases(ms).get("current") or {}
    out: list[tuple[str, str, str, str]] = []
    for name, image in sorted(ctx.images_map.items()):
        rel = getattr(image, "release", None)
        model = rel.get("model") if isinstance(rel, dict) else None
        if not model:
            continue
        runtimes = sorted({str(b.get("runtime") or "") for b in ms.builds() if b.get("series") == name})
        for rt in runtimes:
            head = ms.series_head(name, rt) or {}
            build_id = str(head.get("build_id") or "")
            if not build_id or (current.get(model) or {}).get(name) == build_id:
                continue
            if post_bake_spec(image) and not (tests.get(build_id) or {}).get("ok"):
                continue                                   # no passing record: `release` would refuse
            out.append((name, rt, build_id, str(model)))
    return out


def after_generate(ctx: "GlobalTypeContext", lifecycle: LifecycleLike) -> None:
    if lifecycle.value != RELEASE_LIFECYCLE.name:
        return
    # stage 14: declared releases -- a deferred step per image that declares
    # `release:`; it recomputes the target at execution (after this run's
    # bakes and verifications were recorded) and releases the head whose
    # post-bake tests passed. Runs only in a real run (the executable carries
    # --no-dry-run); the operator's explicit `release` command is unchanged.
    from .utils import system_cli_executable_with_config
    declared = [(n, getattr(i, "release", None)) for n, i in sorted(ctx.images_map.items())
                if isinstance(getattr(i, "release", None), dict)]
    if declared:
        for name, rt, build_id, model in declared_release_targets(ctx):
            log.info(f"release: {name}@{rt} {build_id} would be released for model {model!r} "
                     "(recomputed at execution)")
        wd = ctx.generation_path / "release"
        wd.mkdir(parents=True, exist_ok=True)
        execs = [system_cli_executable_with_config(["release", "--declared"], wd)]
        ctx.extend_finalization_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION, execs)
    data = releases(ctx.meta_state)
    out = ctx.generation_path / "releases.yaml"
    out.write_text(yaml.safe_dump({"run": ctx.run_id, "current": data["current"],
                                   "count": len(data["releases"])}, sort_keys=True))
    # Defer the cloud-side marking of every current release to the runner
    # script; it runs only under --no-dry-run and only if apply_release.
    if not apply_enabled("release"):
        return
    execs = []
    for model, images in sorted(data["current"].items()):
        for image, build_id in sorted(images.items()):
            rec = ctx.meta_state.build(build_id) or {}
            rtb = ctx.runtime_builders.get(str(rec.get("runtime", "")))
            if rtb is None:
                continue
            execs.extend(rtb.release_commands(build_id, {"csis_release": model, "csis_series": image}))
    ctx.extend_finalization_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION, execs)


def release_grace(ctx: "GlobalTypeContext", instance: Any, pin: str) -> tuple[str | None, str]:
    """Stage 61 item 4: why an UNRELEASED pin is allowed for now, or why not.

    A durable instance whose volume allows one attachment can only prove a
    new build on itself, after ``upgrade instance`` pinned it to that build
    -- which ``require_released_builds`` refused, so every second release
    needed the flag switched off by hand (2026-09-20 and 2026-09-22). The
    grace makes the sanctioned sequence legal without the switch: the pin
    is the head of the image's series on its runtime, its in-bake tests
    passed (lineage records a build only then), and the instance is either
    a pending replacement onto it or stands on it (the open generation
    booted with that build) with no FAILED post-bake record. The grace ends
    when the release is recorded (the pin is released) or when the proof
    fails (the refusal names it). Returns ``(reason allowed or None, what
    is missing)``."""
    ms = ctx.meta_state
    name = instance.get_name()
    image = str(instance.image)
    build = ms.build(pin)
    if build is None:
        return None, "lineage does not record the build"
    head = ms.series_head(image, str(build.get("runtime")) if build.get("runtime") else None)
    if not head or str(head.get("build_id")) != str(pin):
        return None, f"the build is not the head of series {image!r} on its runtime"
    if not (build.get("tests") or {}).get("in_bake"):
        return None, "the build carries no in-bake verification record"
    result = ms.image_tests().get(str(pin))
    if result is not None and not result.get("ok"):
        return None, f"the build FAILED its post-bake tests in run {result.get('run')}"
    if ms.pending_replacements().get(name) == pin:
        return f"'{name}' is a pending replacement onto series head {pin}: launch it, verify it, release it", ""
    current = ms.current_generation(name) or {}
    if str((current.get("launch_params") or {}).get("build") or "") == str(pin):
        proof = "verified; release it" if result else "launched; verify it, then release it"
        return f"'{name}' stands on series head {pin} ({proof})", ""
    return None, f"'{name}' neither stands on the build nor is a pending replacement onto it"


def validate_released_pins(ctx: "GlobalTypeContext", requested: list[LifecycleLike]) -> list[str]:
    """config.require_released_builds: an instance's pinned build must be a
    released build of its image (for any model) -- or, since stage 61 item
    4, the series head in the middle of its own proof (:func:`release_grace`)."""
    if not ctx.config.get("require_released_builds", False):
        return []
    errors: list[str] = []
    ms = ctx.meta_state
    for inst in ctx.instances:
        pin = ms.instance_pin(inst.get_name())
        if not pin:
            continue
        image = str(inst.image)
        if pin not in released_builds(ms, image):
            allowed, missing = release_grace(ctx, inst, pin)
            if allowed:
                log.warning(f"config.require_released_builds: build {pin} of {image!r} is not released yet, "
                            f"allowed under the release grace: {allowed}")
                continue
            errors.append(f"instance '{inst.get_name()}' is pinned to build {pin} of '{image}', which is not "
                          f"a released build (config.require_released_builds; no grace: {missing})")
    return errors


def register(runner) -> None:
    from .lifecycles import register_lifecycle
    register_lifecycle(RELEASE_LIFECYCLE)
    runner.register_after_generate(after_generate)
    runner.register_validator(validate_released_pins)
