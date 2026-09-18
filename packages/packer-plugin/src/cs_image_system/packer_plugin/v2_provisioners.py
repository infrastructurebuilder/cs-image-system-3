# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 bake-time provisioners for packer builds (DESIGN §3F1-F3, N9, N23).

Base images bake, in this order after the OS update: the mandatory local
admin user with the operator-supplied public keys; every declared identity
type's prerequisites (dormant); every declared storage type's prerequisites;
the runtime's session agent. Instance images bake the activation for their
owning group (overwriting whatever their parent carried, N23-continued).

Everything here is emitted as reviewable ``provisioner "shell"`` blocks
scoped to one source; nothing runs at generation time.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING, Iterable

from cs_image_system.base.capabilities import (
    admin_public_keys,
    admin_user,
    group_builder_of,
    group_builders_by_identity_type,
    storage_builders_by_type,
)

if TYPE_CHECKING:
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.models.base_image import BaseImage
    from cs_image_system.base.models.image import Image

from cs_image_system.base.encryption import emit

log = logging.getLogger(__name__)


def _quote(cmd: str) -> str:
    """HCL2 string literal: escape backslash/quote AND packer's template
    sequences (${ and %{ start interpolation/directives; $$ and %% render
    the literals) -- found live when rpm's --qf '%{NAME}...' broke fmt."""
    s = cmd.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s.replace("${", "$${").replace("%{", "%%{") + '"'


def shell_provisioner(source_label: str, comment: str, commands: Iterable[str],
                      indent: str = "  ") -> list[str]:
    cmds = [c for c in commands if c is not None]
    if not cmds:
        return []
    lines = [f"{indent}# {comment}", f'{indent}provisioner "shell" {{',
             f'{indent}  only   = ["{source_label}"]', f"{indent}  inline = ["]
    for c in cmds:
        lines.append(f"{indent}    {_quote(c)},")
    lines += [f"{indent}  ]", f"{indent}}}"]
    return lines


def _runtime_of(builder: Any) -> str | None:
    model = getattr(builder, "model", None)
    fn = getattr(model, "get_runtime_provider", None)
    try:
        return str(fn()) if callable(fn) else None
    except ValueError:
        return None


def admin_user_commands(user: str, keys: list[str]) -> list[str]:
    cmds = [
        f"# mandatory local admin user '{user}' (DESIGN Q2/N9): public keys only",
        f"id -u {user} >/dev/null 2>&1 || sudo useradd -m -s /bin/bash {user}",
        f"echo '{user} ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-{user} >/dev/null && sudo chmod 0440 /etc/sudoers.d/90-{user}",
        f"sudo mkdir -p /home/{user}/.ssh && sudo chmod 0700 /home/{user}/.ssh",
        f"sudo rm -f /home/{user}/.ssh/authorized_keys",
    ]
    for key in keys:
        # stage 49: emit() writes the ENC[age:...] the key was read from, when
        # it was encrypted; materialize substitutes the key into the private
        # copy packer actually builds from, so the committed HCL has no key.
        cmds.append(f"echo '{emit(key)}' | sudo tee -a /home/{user}/.ssh/authorized_keys >/dev/null")
    cmds += [
        f"sudo touch /home/{user}/.ssh/authorized_keys && sudo chmod 0600 /home/{user}/.ssh/authorized_keys",
        f"sudo chown -R {user}:{user} /home/{user}/.ssh",
    ]
    return cmds


def base_image_provisioners(ctx: "GlobalTypeContext", image: "BaseImage", source_type: str,
                            runtime_name: str) -> list[str]:
    label = f"{source_type}.{image.get_name()}"
    osb = ctx.os_builders.get(image.get_name())
    family = osb.get_family() if osb is not None else None
    lines: list[str] = []
    # 1. admin user
    user = image.admin_user or admin_user(ctx, image.get_name())
    keys = admin_public_keys(ctx, base=image)
    lines += shell_provisioner(label, f"admin user {user} ({len(keys)} public key(s))",
                               admin_user_commands(user, keys))
    # 2. identity-type prerequisites (dormant)
    id_plugins = group_builders_by_identity_type(ctx)
    for itype in sorted(image.identity_types or []):
        builders = id_plugins.get(itype, [])
        if not builders:
            continue  # validation already refused unknown types
        lines += shell_provisioner(label, f"identity type '{itype}' prerequisites, dormant",
                                   builders[0].base_image_prerequisites(family))
    # 3. storage-type prerequisites -- of the plugins ON THIS RUNTIME only
    # (GCP increment 3, gate 1): a GCE bake never installs EFS tooling.
    st_plugins = storage_builders_by_type(ctx)
    for stype in sorted(image.storage_types or []):
        builders = [b for b in st_plugins.get(stype, [])
                    if _runtime_of(b) in (None, runtime_name)]
        if not builders:
            lines.append(f"  # storage type '{stype}' declared but has no plugin on runtime "
                         f"{runtime_name}: nothing to bake here")
            continue
        lines += shell_provisioner(label, f"storage type '{stype}' prerequisites",
                                   builders[0].base_image_prerequisites(family))
    # 4. session mechanism agent
    rtb = ctx.runtime_builders.get(runtime_name)
    if rtb is not None:
        lines += shell_provisioner(label, f"debug session mechanism ({rtb.session_mechanism()})",
                                   rtb.session_agent_commands(family))
    return lines


def instance_image_provisioners(ctx: "GlobalTypeContext", image: "Image", source_type: str) -> list[str]:
    """Activation for the image's OWN owning group (rewritten at every bake)."""
    group = getattr(image, "group", None)
    if not group:
        return []
    gb = group_builder_of(ctx, group)
    if gb is None:
        return []
    group_obj = next((g for g in gb.get_groups_for_builder() if g.get_name() == group), None)
    if group_obj is None:
        return []
    label = f"{source_type}.{image.get_name()}"
    return shell_provisioner(label, f"identity activation for owning group '{group}' ({gb.identity_type()})",
                             gb.activation_commands(image, group_obj))
