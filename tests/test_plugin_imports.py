# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a plugin may import from the kit.

A plugin is written against the contract; of the kit (``cs_image_system.base``)
it imports only the base classes (``basic/*``), the models it subclasses
(``models/*``) and the two metadata abstractions (which live under
``basic/``). Every other kit module a plugin reaches by import is an
exception, and the exceptions are the committed list below: what the
sources show today, entry by entry, so the list can only be pruned. An
entry that no source carries any more is stale and goes; an import the
list does not carry is a new reach into the kit and is refused here.

The contract surface emptied the list of every function a plugin
reached by import -- they are members of ``ctx.services`` now, or the
contract's own (the enrollment registry, the hostname rule, the secret
marker's opening, the catalog words, the hook set, the bootstrap's facts
protocol) -- down to the four entries that stay, each a read made where
no context exists to reach a service through: two models fetching the
current context (the docker floating tag, the Okta gateway selector; the
one-release shim, pinned by their tests), and two state backends reading the
registry from a class-level ``session_status`` before any run is loaded.
A package that imports nothing from the kit (hashicorp-utils,
contract-example-plugin) has no entry.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = "cs_image_system.base"
NOT_PLUGINS = {"base", "contract", "system"}
ALLOWED_PREFIXES = (f"{KIT}.basic.", f"{KIT}.models.")
METADATA_ABSTRACTIONS = (f"{KIT}.basic.abstract_plugin_metadata", f"{KIT}.basic.abstract_version_checker")

#: (package directory, kit module, imported name); ``<module>`` for a bare
#: ``import cs_image_system.base...``. Generated from the sources; pruned as
#: the vocabulary and the services move.
# --- exceptions begin
EXCEPTIONS: frozenset[tuple[str, str, str]] = frozenset({
    ('docker-runtime-plugin', 'cs_image_system.base.run_context', 'current_context'),
    ('gcs-state-plugin', 'cs_image_system.base.registry', 'current_registry'),
    ('okta-opa-plugin', 'cs_image_system.base.run_context', 'current_context'),
    ('tf-s3-state-plugin', 'cs_image_system.base.registry', 'current_registry'),
})
# --- exceptions end


def _allowed(module: str) -> bool:
    return module.startswith(ALLOWED_PREFIXES) or module in METADATA_ABSTRACTIONS


def kit_imports() -> set[tuple[str, str, str]]:
    """Every (package, kit module, name) a plugin's sources import from the
    kit outside the allowed paths, at any depth, lazily or not."""
    out: set[tuple[str, str, str]] = set()
    for package in sorted((REPO / "packages").iterdir()):
        src = package / "src" / "cs_image_system"
        if not src.exists():
            continue
        for sub in src.iterdir():
            if sub.name in NOT_PLUGINS or not sub.is_dir():
                continue
            for source in sorted(sub.rglob("*.py")):
                for node in ast.walk(ast.parse(source.read_text(), filename=str(source))):
                    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                            and node.module.startswith(KIT) and not _allowed(node.module):
                        out.update((package.name, node.module, alias.name) for alias in node.names)
                    elif isinstance(node, ast.Import):
                        out.update((package.name, alias.name, "<module>") for alias in node.names
                                   if alias.name.startswith(KIT) and not _allowed(alias.name))
    return out


def test_a_plugin_imports_only_the_base_classes_the_models_and_the_listed_exceptions():
    found = kit_imports()
    new = sorted(found - EXCEPTIONS)
    stale = sorted(EXCEPTIONS - found)
    assert not new, "a plugin reaches the kit outside basic/, models/ and the exception list:\n" + \
        "\n".join(f"    {e!r}," for e in new)
    assert not stale, "stale exceptions (no source imports them any more; remove them):\n" + \
        "\n".join(f"    {e!r}," for e in stale)


def test_the_metadata_abstractions_are_where_the_rule_says():
    for module in METADATA_ABSTRACTIONS:
        assert (REPO / "packages/base/src" / Path(*module.split("."))).with_suffix(".py").exists(), module


def test_every_plugin_package_is_covered():
    """The rule reads every package with sources outside the core; a package
    with none (the proof plugin, the library) simply contributes nothing."""
    packages = {p.name for p in (REPO / "packages").iterdir() if (p / "src" / "cs_image_system").exists()}
    assert {"aws-runtime-plugin", "tofu-roots", "hashicorp-utils", "contract-example-plugin", "dummy-plugin"} <= packages
