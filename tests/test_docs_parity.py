# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Documentation parity (docs/PARITY.md): what the code declares is named in
the document that describes it.

* every registered model's declared fields appear in CONFIGURATION.md;
* every recipe `just --summary` prints appears in OPERATIONS.md's recipe
  catalogue;
* every package under `packages/` appears in the root README's list;
* every CLI command (the Typer app's registered commands and sub-commands)
  appears in a table of OPERATIONS.md;
* the starter count the documents state is the count of
  ``cs_image_system.system.starters.STARTERS`` -- the one constant the docs
  tests read.

A failure names the missing word; the cure is a documentation row (or an
allow-list entry here with its reason, for a field documented under
another name or in another document).
"""
from __future__ import annotations

import dataclasses
import re
import subprocess
from pathlib import Path

from harness import REPO

CONFIGURATION = REPO / "docs" / "CONFIGURATION.md"
OPERATIONS = REPO / "docs" / "OPERATIONS.md"
README = REPO / "README.md"

# Fields a registered model declares that CONFIGURATION.md does not name
# under that word, each with its reason; an entry that names a document is
# checked against that document instead, so the list stays honest.
ALLOWED_FIELDS: dict[tuple[str, str], tuple[str, Path | None]] = {
    # The clouds' network facts: filled by `discover` / `validate --online`
    # from the account and recorded in meta-state/runtime-facts.yaml; a tree
    # never declares them (OPERATIONS.md, "Where state lives" and `validate`).
    ("AwsCloudBuilderModel", "vpc_map"): ("a discovered fact, not a declared field", None),
    ("AwsCloudBuilderModel", "default_vpc_id"): ("a discovered fact, not a declared field", None),
    ("AwsCloudBuilderModel", "all_security_groups"): ("a discovered fact, not a declared field", None),
    ("GCPCloudBuilderModel", "network_map"): ("a discovered fact, not a declared field", None),
    ("GCPCloudBuilderModel", "default_network"): ("a discovered fact, not a declared field", None),
    ("GCPCloudBuilderModel", "all_firewall_rules"): ("a discovered fact, not a declared field", None),
    # The contract example plugin is the worked example of the contract, not
    # a type the release documents for operators; its one setting is
    # documented in its own README.
    ("InmemStateBackendModel", "lock_id"): ("the example plugin's setting, documented in its README",
                                            REPO / "packages" / "contract-example-plugin" / "README.md"),
}


def _documents(text: str, field: str) -> bool:
    """A field is documented when the document names it in a code span:
    `` `field` ``, or `` `field: type = default` `` as the storage tables
    write their builder fields."""
    return re.search(r"`" + re.escape(field) + r"(?:[`:\s]|\[)", text) is not None


def _registered_models() -> list[type]:
    from cs_image_system.base.loader import installed_registry
    seen: dict[type, None] = {}
    for cls in installed_registry().models.values():
        if dataclasses.is_dataclass(cls):
            seen.setdefault(cls, None)
    return list(seen)


def test_every_registered_models_fields_appear_in_configuration():
    conf = CONFIGURATION.read_text()
    models = _registered_models()
    assert len(models) >= 40, [m.__name__ for m in models]      # the registry's models, not an empty walk
    missing: list[str] = []
    for cls in models:
        for f in dataclasses.fields(cls):
            if f.name.startswith("_"):                # internal (``_model_id``), never a YAML key
                continue
            if _documents(conf, f.name):
                continue
            allowed = ALLOWED_FIELDS.get((cls.__name__, f.name))
            if allowed is None:
                missing.append(f"{cls.__module__}.{cls.__name__}.{f.name}")
            elif allowed[1] is not None and not _documents(allowed[1].read_text(), f.name):
                missing.append(f"{cls.__name__}.{f.name}: allowed as documented in {allowed[1].relative_to(REPO)}, "
                               "which does not name it")
    assert missing == [], "fields CONFIGURATION.md does not name:\n  " + "\n  ".join(missing)
    stale = [f"{c}.{f}" for (c, f) in ALLOWED_FIELDS if _documents(conf, f)]
    assert stale == [], f"allow-list entries CONFIGURATION.md now documents: {stale}"


def _table_rows(text: str, heading: str | None = None) -> list[str]:
    """The table rows of a document, or of one ``###`` section of it."""
    if heading is not None:
        start = text.index(heading)
        end = re.search(r"^##", text[start + len(heading):], flags=re.M)
        text = text[start: start + len(heading) + (end.start() if end else len(text))]
    return [line for line in text.splitlines() if line.startswith("|")]


def _named(rows: list[str], word: str) -> bool:
    """``word`` (a recipe or a command, sub-commands with their space) is
    named in a row's code span: `` `word` ``, `` `word <args>` ``, with or
    without the ``just`` / ``cs-image-system`` prefix."""
    pattern = re.compile(r"`(?:just |cs-image-system )?" + re.escape(word) + r"(?=[ `…\]|])")
    return any(pattern.search(row) for row in rows)


def test_every_recipe_of_the_justfile_appears_in_the_recipe_catalogue():
    summary = subprocess.run(["just", "--summary"], capture_output=True, text=True, check=True, cwd=REPO).stdout
    recipes = sorted(summary.split())
    assert len(recipes) >= 30, recipes
    rows = _table_rows(OPERATIONS.read_text(), "### Recipe catalogue")
    assert rows, "OPERATIONS.md has no recipe catalogue table"
    missing = [r for r in recipes if not _named(rows, r)]
    assert missing == [], f"recipes the catalogue does not name: {missing}"


def test_every_package_appears_in_the_readmes_list():
    readme = README.read_text()
    packages = sorted(p.name for p in (REPO / "packages").iterdir() if (p / "pyproject.toml").is_file())
    assert len(packages) >= 20, packages
    missing = [p for p in packages if f"packages/{p}/README.md" not in readme]
    assert missing == [], f"packages the README's list does not link: {missing}"


def _cli_commands() -> list[str]:
    import typer

    from cs_image_system.system.cli import app
    group = typer.main.get_command(app)
    out: list[str] = []
    for name, sub in sorted(getattr(group, "commands", {}).items()):
        if getattr(sub, "hidden", False):
            continue
        out.append(name)
        for sub_name, leaf in sorted(getattr(sub, "commands", {}).items()):
            if not getattr(leaf, "hidden", False):
                out.append(f"{name} {sub_name}")
    return out


def test_every_cli_command_appears_in_a_table_of_operations():
    commands = _cli_commands()
    assert len(commands) >= 30, commands
    rows = _table_rows(OPERATIONS.read_text())
    missing = [c for c in commands if not _named(rows, c)]
    assert missing == [], f"commands no table of OPERATIONS.md names: {missing}"


_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                 9: "nine", 10: "ten"}


def test_the_starter_count_the_documents_state_is_the_constant():
    from cs_image_system.system.starters import STARTERS, starters_root
    assert STARTERS, "the release carries no starter tree"
    expected = _NUMBER_WORDS[len(STARTERS)]
    trees = sorted(p.name for p in starters_root().iterdir() if p.is_dir() and not p.name.startswith("_"))
    assert sorted(STARTERS) == trees                    # the constant is the directory, nothing hand-kept
    stated: list[tuple[str, str]] = []
    for doc in (README, OPERATIONS, CONFIGURATION):
        for word in re.findall(r"\b(\w+) starter trees?\b", doc.read_text()):
            if word.lower() in _NUMBER_WORDS.values():
                stated.append((str(doc.relative_to(REPO)), word.lower()))
    assert stated, "no document states the starter count in words"
    wrong = [f"{doc}: {word}" for doc, word in stated if word != expected]
    assert wrong == [], f"documents stating a starter count other than {expected} ({len(STARTERS)}): {wrong}"
