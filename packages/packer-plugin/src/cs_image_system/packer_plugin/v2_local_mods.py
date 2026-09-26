# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Local modification bundles (EXPLORE "Locally Installing Modifications").

Every instance-image bake also installs its modifications ON the image, at
``/opt/csis/mods/``: one directory per modification (``NN-<name>/``) holding
the playbook(s) or script(s) exactly as baked, a ``run.sh`` wrapper, and a
``MANIFEST.yaml`` carrying the same record lineage keeps (type, content
hash, run id, idempotence). A tiny POSIX runner, ``csis-mods``, re-applies
them in order (``csis-mods rerun [name]``) or lists them (``csis-mods list``).

Debugging an image then means: stand it up, ``csis-mods rerun``, inspect.
The bundle is staged beside the packer root (``csis-mods/<image>/``) so it is
reviewable, and uploaded with a ``file`` provisioner after the image's
modifications and activation have run.

Limitation (recorded): the bundle holds THIS bake's modifications; a chained
image's parent bakes keep their own bundles in lineage, not on disk.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from cs_image_system.base.lineage import mod_records

if TYPE_CHECKING:
    from cs_image_system.base.global_context import GlobalTypeContext

log = logging.getLogger(__name__)

BUNDLE_DIRNAME = "csis-mods"
IMAGE_MODS_ROOT = "/opt/csis/mods"
RUNNER_NAME = "csis-mods"

RUNNER_SCRIPT = """#!/bin/sh
# csis-mods: re-run the modifications baked into this image (cs-image-system).
# Usage: csis-mods list | csis-mods rerun [name]
set -eu
ROOT="${CSIS_MODS_ROOT:-/opt/csis/mods}"
cmd="${1:-list}"; want="${2:-}"
case "$cmd" in
  list)
    for d in "$ROOT"/[0-9][0-9]-*/; do [ -d "$d" ] || continue; printf '%s\\n' "$(basename "$d")"; done ;;
  rerun)
    for d in "$ROOT"/[0-9][0-9]-*/; do
      [ -d "$d" ] || continue
      name="$(basename "$d")"
      case "$name" in *-"$want"|"$want") match=1 ;; *) match=0 ;; esac
      if [ -z "$want" ] || [ "$match" = 1 ]; then
        echo "== csis-mods: $name"
        ( cd "$d" && sh ./run.sh )
      fi
    done ;;
  *) echo "usage: csis-mods list | rerun [name]" >&2; exit 2 ;;
esac
"""


def _run_sh_for(mod: Any, files: list[str]) -> str:
    """The wrapper that re-applies one modification from its bundle dir."""
    lines = ["#!/bin/sh", "set -eu", 'cd "$(dirname "$0")"']
    playbooks = list(getattr(mod, "playbooks", None) or [])
    if playbooks:
        lines.append("command -v ansible-playbook >/dev/null 2>&1 || { echo 'ansible-playbook not present on this image; cannot re-run' >&2; exit 3; }")
        for pb in playbooks:
            lines.append(f"ansible-playbook -i localhost, -c local '{Path(str(pb)).name}'")
    for sf in list(getattr(mod, "scripts", None) or []):
        lines.append(f"sh '{Path(str(sf)).name}'")
    if getattr(mod, "script", None):
        lines.append("sh ./inline.sh")
    return "\n".join(lines) + "\n"


def stage_local_mods(ctx: "GlobalTypeContext", image: Any, block_dir: Path,
                     source_label: str) -> list[str]:
    """Write the bundle under ``block_dir/csis-mods/<image>/`` and return the
    packer provisioner lines that install it on the image."""
    mods = list(getattr(image, "modifications", None) or [])
    if not mods:
        return []
    bundle = block_dir / BUNDLE_DIRNAME / image.get_name()
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    (bundle / RUNNER_NAME).write_text(RUNNER_SCRIPT)
    (bundle / RUNNER_NAME).chmod(0o755)
    records = mod_records(ctx, image)
    index: list[dict[str, Any]] = []
    for n, (mod, rec) in enumerate(zip(mods, records), start=1):
        if isinstance(mod, dict):
            continue
        d = bundle / f"{n:02d}-{mod.get_name()}"
        d.mkdir()
        files: list[str] = []
        for src in list(getattr(mod, "playbooks", None) or []) + list(getattr(mod, "scripts", None) or []):
            candidates = [block_dir / str(src), Path(ctx.working_path) / str(src), Path(str(src))]
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                log.warning(f"local mods: {src} for {mod.get_name()} not found; the bundle will lack it")
                continue
            shutil.copy2(found, d / found.name)
            files.append(found.name)
        # stage 63: the guarded `ensure` lines come first, the order the bake ran
        # them, so `csis-mods rerun` re-applies the declarative form too
        ensure = mod.ensure_lines() if callable(getattr(mod, "ensure_lines", None)) else []
        inline = list(ensure) + list(getattr(mod, "script", None) or [])
        if inline:
            (d / "inline.sh").write_text("#!/bin/sh\nset -eu\n" + "\n".join(inline) + "\n")
            files.append("inline.sh")
        (d / "run.sh").write_text(_run_sh_for(mod, files))
        manifest = {**rec, "files": files, "image": image.get_name()}
        (d / "MANIFEST.yaml").write_text(yaml.safe_dump(manifest, sort_keys=True))
        index.append({"dir": d.name, **{k: rec[k] for k in ("name", "type", "operation", "content_hash", "idempotent") if k in rec}})
    (bundle / "MANIFEST.yaml").write_text(yaml.safe_dump(
        {"image": image.get_name(), "run": ctx.run_id, "mods": index}, sort_keys=True))
    rel = f"{BUNDLE_DIRNAME}/{image.get_name()}/"
    return [
        f"  # local modification bundle for {image.get_name()} -> {IMAGE_MODS_ROOT} (re-run with `csis-mods rerun`)",
        # scp cannot create the destination directory (found live: "scp:
        # /tmp/csis-mods: Not a directory"); make it first
        '  provisioner "shell" {',
        f'    only   = ["{source_label}"]',
        '    inline = ["mkdir -p /tmp/csis-mods"]',
        "  }",
        '  provisioner "file" {',
        f'    only        = ["{source_label}"]',
        f'    source      = "{rel}"',
        '    destination = "/tmp/csis-mods"',
        "  }",
        '  provisioner "shell" {',
        f'    only   = ["{source_label}"]',
        "    inline = [",
        f'      "sudo rm -rf {IMAGE_MODS_ROOT} && sudo mkdir -p {Path(IMAGE_MODS_ROOT).parent}",',
        f'      "sudo mv /tmp/csis-mods {IMAGE_MODS_ROOT}",',
        f'      "sudo install -m 0755 {IMAGE_MODS_ROOT}/{RUNNER_NAME} /usr/local/bin/{RUNNER_NAME}",',
        f'      "sudo chmod -R go-w {IMAGE_MODS_ROOT}",',
        "    ]",
        "  }",
    ]
