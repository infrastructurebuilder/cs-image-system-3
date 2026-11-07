# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""In-bake image tests (EXPLORE "Automated Testing for Image Builds").

Two layers, both emitted as the LAST packer provisioner of an image so a
failing assertion fails the bake (and therefore never becomes a build in
lineage):

1. **capability verification** -- derived automatically from the same
   plugin hooks that bake prerequisites: the admin user exists and has the
   keys, every declared identity/storage type's ``verify_commands``, the
   runtime's session agent, and (instance images) the owning group's
   activation;
2. **declared tests** -- a small goss-style ``tests:`` map on an image or
   base image:

   .. code-block:: yaml

      tests:
        files: [{path: /etc/derivative.conf, contains: "version=1.0.0", mode: "0644"}]
        packages: [git]
        commands: [{run: "dask --version", expect_rc: 0, contains: "dask"}]
        services_enabled: [chronyd]
        users: [csisadmin]

Assertions are plain POSIX shell (``test``, ``grep``; the package test is
the OS type's own, through its ``package_present_check`` hook), so they run
inside packer's shell provisioner on any Linux family. The
lineage record notes how many assertions the build passed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .run_context import RunContext


import shlex
from typing import Any

from cs_image_system.base.models.container_builder import ContainerBuilderModel

from .capabilities import (
    admin_public_keys,
    group_builder_of,
    group_builders_by_identity_type,
    image_chain,
    storage_builders_by_type,
)
from .os_types import os_type_for_family

KNOWN_KEYS = {"files", "packages", "commands", "services_enabled", "users"}
# `tests.post_bake` is the same vocabulary plus `mounts`, run ON a
# launched (ephemeral) instance over the runtime's session command by
# `verify instance`, and recorded per build in meta-state/image-tests.yaml
POST_BAKE_KEY = "post_bake"
POST_BAKE_KEYS = KNOWN_KEYS | {"mounts"}


def validate_tests_spec(spec: dict[str, Any], where: str) -> list[str]:
    errors: list[str] = []
    unknown = set(spec or {}) - KNOWN_KEYS - {POST_BAKE_KEY}
    if unknown:
        errors.append(f"{where}: unknown tests keys {sorted(unknown)} (known: {sorted(KNOWN_KEYS | {POST_BAKE_KEY})})")
    errors += _validate_vocabulary(spec, where)
    post = (spec or {}).get(POST_BAKE_KEY)
    if post is not None:
        if not isinstance(post, dict):
            errors.append(f"{where}: tests.post_bake must be a map")
        else:
            unknown = set(post) - POST_BAKE_KEYS
            if unknown:
                errors.append(f"{where}: unknown tests.post_bake keys {sorted(unknown)} (known: {sorted(POST_BAKE_KEYS)})")
            errors += _validate_vocabulary(post, f"{where}.post_bake")
            for m in post.get("mounts", []) or []:
                if not isinstance(m, str) or not m.startswith("/"):
                    errors.append(f"{where}.post_bake: every mounts entry is an absolute mount point")
    return errors


def _validate_vocabulary(spec: dict[str, Any], where: str) -> list[str]:
    errors: list[str] = []
    for f in (spec or {}).get("files", []) or []:
        if not isinstance(f, dict) or not f.get("path"):
            errors.append(f"{where}: every tests.files entry needs a path")
    for c in (spec or {}).get("commands", []) or []:
        if not isinstance(c, dict) or not c.get("run"):
            errors.append(f"{where}: every tests.commands entry needs run")
    return errors


def post_bake_spec(image: Any) -> dict[str, Any]:
    """The image's declared post-bake tests (empty when none)."""
    tests = getattr(image, "tests", None) or {}
    post = tests.get(POST_BAKE_KEY) if isinstance(tests, dict) else None
    return dict(post) if isinstance(post, dict) else {}


def post_bake_assertions(spec: dict[str, Any], *, os_type: type | None = None) -> list[tuple[str, str]]:
    """``[(label, shell assertion)]`` for a post-bake map: the in-bake
    vocabulary plus ``mounts`` (each mount point must be a mounted
    filesystem, `findmnt`). ``os_type`` is the image's OS type, which a
    ``packages`` assertion needs (``declared_test_commands``)."""
    out: list[tuple[str, str]] = []
    base = {k: v for k, v in (spec or {}).items() if k != "mounts"}
    for cmd in declared_test_commands(base, os_type=os_type):
        out.append((cmd, cmd))
    for mp in (spec or {}).get("mounts", []) or []:
        out.append((f"mount {mp}", f"findmnt -n {shlex.quote(str(mp))} >/dev/null 2>&1"))
    return out


def post_bake_script(spec: dict[str, Any], *, os_type: type | None = None) -> str:
    """One session script running every assertion and printing one
    ``CSIS_TEST <n> <PASS|FAIL>`` line each (never aborts on a failure,
    so every outcome is reported)."""
    lines = ["set +e"]
    for i, (_, cmd) in enumerate(post_bake_assertions(spec, os_type=os_type)):
        lines.append(f"if ( {cmd} ); then echo \"CSIS_TEST {i} PASS\"; else echo \"CSIS_TEST {i} FAIL\"; fi")
    return "\n".join(lines) + "\n"


def parse_post_bake_output(spec: dict[str, Any], output: str, *, os_type: type | None = None) -> list[dict[str, Any]]:
    """Per-assertion outcomes from the script's output; an assertion with no
    line reported is a failure (the session died before it ran)."""
    seen: dict[int, bool] = {}
    for line in (output or "").splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0] == "CSIS_TEST" and parts[1].isdigit():
            seen[int(parts[1])] = parts[2] == "PASS"
    return [{"name": label, "ok": seen.get(i, False),
             "detail": "pass" if seen.get(i) else ("FAIL" if i in seen else "no result (session ended early)")}
            for i, (label, _) in enumerate(post_bake_assertions(spec, os_type=os_type))]


def declared_test_commands(spec: dict[str, Any], *, services: bool = True,
                           os_type: type | None = None) -> list[str]:
    """Shell assertions for a ``tests:`` map. ``services=False`` (for
    a bake on a container runtime, which has no init system) answers each
    ``services_enabled`` entry with a comment that the check does not apply
    there, instead of a ``systemctl`` that cannot run. ``os_type`` is the
    image's OS type (``os_types.os_type_for_family``): a ``packages`` entry
    is asserted with its ``package_present_check``, the type's own package
    manager, and refused without one.

    Every line must ABORT the script it is spliced into, not merely exit
    nonzero: these run as packer `inline` lines under `set -e`, and errexit
    does not fire for a command inside an AND-OR list. A line that ends in
    `|| { ... }` is therefore unenforceable however false it is."""
    out: list[str] = []
    spec = spec or {}
    for f in spec.get("files", []) or []:
        path = shlex.quote(str(f["path"]))
        out.append(f"test -e {path}")
        if f.get("mode"):
            out.append(f"test \"$(stat -c %a {path})\" = {shlex.quote(str(f['mode']).lstrip('0') or '0')}")
        if f.get("contains"):
            out.append(f"grep -q -- {shlex.quote(str(f['contains']))} {path}")
    packages = list(spec.get("packages", []) or [])
    if packages and os_type is None:
        raise ValueError(f"a packages test ({', '.join(map(str, packages))}) needs the image's OS type: "
                         "its package manager answers whether a package is installed")
    for p in packages:
        # An `a || { b && c; }` cannot fail a bake, however false it is: POSIX
        # suppresses errexit for a command in an AND-OR list, so `set -e` never
        # fires and packer's shell provisioner carries on to the next line.
        # The first image ever baked went green twice while asserting a package
        # on a system that has no package by that name. The type's test must
        # therefore exit for itself -- and while it is doing that, say which
        # package (tests/test_v2_in_bake_tests_enforce.py holds it to both).
        assert os_type is not None
        out.append(os_type.package_present_check(shlex.quote(str(p))))
    for c in spec.get("commands", []) or []:
        run = str(c["run"]); rc = int(c.get("expect_rc", 0))
        if c.get("contains"):
            out.append(f"( {run} ) 2>&1 | grep -q -- {shlex.quote(str(c['contains']))}")
        else:
            out.append(f"( {run} ) >/dev/null 2>&1; test $? -eq {rc}")
    for svc in spec.get("services_enabled", []) or []:
        if services:
            out.append(f"systemctl is-enabled {shlex.quote(str(svc))} >/dev/null 2>&1")
        else:
            out.append(f"# services_enabled {shlex.quote(str(svc))}: not applicable on a container runtime (no init system)")
    for u in spec.get("users", []) or []:
        out.append(f"id -u {shlex.quote(str(u))} >/dev/null 2>&1")
    return out


def _admin_verify(ctx: "RunContext", base: Any) -> list[str]:
    user = base.admin_user or "csisadmin"
    keys = admin_public_keys(ctx, base=base)
    cmds = [f"# verify: admin user {user}", f"id -u {user} >/dev/null 2>&1",
            f"sudo test -f /home/{user}/.ssh/authorized_keys"]
    for k in keys:
        # match on the key body (second field), independent of comment/spacing
        marker = getattr(k, "marker", None)
        if marker:
            # the committed command carries the ciphertext, and the
            # body is taken in the SHELL, after materialize has substituted the
            # key -- a body computed here would be plaintext in the emission.
            body_expr = f"$(echo {shlex.quote(marker)} | awk '{{print $2}}')"
            cmds.append(f'sudo grep -q -- "{body_expr}" /home/{user}/.ssh/authorized_keys')
            continue
        body = k.split()[1] if len(k.split()) > 1 else k
        cmds.append(f"sudo grep -q -- {shlex.quote(body)} /home/{user}/.ssh/authorized_keys")
    return cmds


def _runtime_of(builder: Any) -> str | None:
    fn = getattr(getattr(builder, "model", None), "get_runtime_provider", None)
    try:
        return str(fn()) if callable(fn) else None
    except ValueError:
        return None


def _has_init_system(ctx: "RunContext", runtime_name: str | None) -> bool:
    """Whether bakes on ``runtime_name`` have an init system to enable
    services with: every runtime but a container one."""
    if not runtime_name:
        return True
    rtb = ctx.runtime_builders.get(str(runtime_name))
    return not isinstance(getattr(rtb, "model", None), ContainerBuilderModel)


def _os_type_of(ctx: "RunContext", osb: Any) -> type | None:
    return os_type_for_family(osb.get_family()) if osb is not None else None


def base_image_verify_commands(ctx: "RunContext", base: Any, runtime_name: str) -> list[str]:
    osb = ctx.os_builders.get(base.get_name())
    family = osb.get_family() if osb is not None else None
    cmds = _admin_verify(ctx, base)
    id_plugins = group_builders_by_identity_type(ctx)
    for itype in sorted(base.identity_types or []):
        for b in id_plugins.get(itype, [])[:1]:
            cmds += b.verify_commands(family)
    st_plugins = storage_builders_by_type(ctx)
    for stype in sorted(base.storage_types or []):
        # only the plugins ON THIS RUNTIME are verified (second-cloud exploration increment 3, gate 1)
        on_runtime = [b for b in st_plugins.get(stype, []) if _runtime_of(b) in (None, runtime_name)]
        for b in on_runtime[:1]:
            cmds += b.verify_commands(family)
    rtb = ctx.runtime_builders.get(runtime_name)
    if rtb is not None:
        cmds += rtb.session_verify_commands(family)
    declared = getattr(base, "tests", None) or {}
    # per-runtime override (finding 40): the os builder's runtime entry may
    # carry its own tests, replacing the builder-level spec for bakes on
    # that runtime (resolved through the entry's image builder)
    if osb is not None:
        for sub in getattr(osb.model, "runtimes", None) or []:
            ib = ctx.image_builders.get(str(getattr(sub, "image_builder", "")))
            if (ib is not None and getattr(sub, "tests", None) is not None
                    and str(ib.model.get_runtime_provider()) == str(runtime_name)):
                declared = sub.tests
                break
    cmds += declared_test_commands(declared, services=_has_init_system(ctx, runtime_name), os_type=_os_type_of(ctx, osb))
    return cmds


def root_os_type(ctx: "RunContext", image: Any) -> type | None:
    """The OS type of the instance image's root base image (None when the
    chain reaches no OS builder)."""
    _, root = image_chain(ctx, image)
    return _os_type_of(ctx, ctx.os_builders.get(root) if root else None)


def instance_image_verify_commands(ctx: "RunContext", image: Any, runtime_name: str | None = None) -> list[str]:
    cmds: list[str] = []
    group = getattr(image, "group", None)
    gb = group_builder_of(ctx, group) if group else None
    if gb is not None:
        g = next((x for x in gb.get_groups_for_builder() if x.get_name() == group), None)
        if g is not None:
            cmds += gb.activation_verify_commands(image, g)
    cmds += declared_test_commands(getattr(image, "tests", None) or {}, services=_has_init_system(ctx, runtime_name),
                                   os_type=root_os_type(ctx, image))
    return cmds


def verify_provisioner(source_label: str, cmds: list[str], what: str) -> list[str]:
    """One shell provisioner running every assertion under ``set -e``; the
    first failing assertion fails the bake."""
    if not cmds:
        return []
    lines = [f"  # in-bake verification for {what}: {sum(1 for c in cmds if not c.startswith('#'))} assertion(s)",
             '  provisioner "shell" {', f'    only   = ["{source_label}"]', "    inline = ["]
    lines.append('      "set -e",')
    for c in cmds:
        lines.append("      " + '"' + c.replace("\\", "\\\\").replace('"', '\\"') + '",')
    lines += ["    ]", "  }"]
    return lines


def assertion_count(cmds: list[str]) -> int:
    return sum(1 for c in cmds if not c.startswith("#"))


def finalize_provisioner(ctx: "RunContext", source_label: str,
                         runtime_name: str, os_family: str | None) -> list[str]:
    """The runtime's bake-finalize commands as the very last provisioner of
    a bake (finding 47) -- cloud-specific image hygiene, after verification
    so the assertions judge the image, not the hygiene."""
    rtb = ctx.runtime_builders.get(runtime_name)
    cmds = rtb.bake_finalize_commands(os_family) if rtb is not None else []
    if not cmds:
        return []
    lines = [f"  # runtime bake finalization ({runtime_name})",
             '  provisioner "shell" {', f'    only   = ["{source_label}"]', "    inline = ["]
    lines.append('      "set -e",')
    for c in cmds:
        lines.append("      " + '"' + c.replace("\\", "\\\\").replace('"', '\\"') + '",')
    lines += ["    ]", "  }"]
    return lines
