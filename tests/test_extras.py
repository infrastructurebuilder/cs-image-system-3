# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The umbrella's extras, and the table that names them.

``uv tool install cs-image-system`` carries no runtime; each provider is
an extra. ``cs_image_system.extras`` (the umbrella's one module) is the static table from a
``type:`` word to the extra that installs the plugin registering it,
written out so it answers when the plugin is absent. Three things hold it
honest: the table regenerated from the installed workspace's registry is
the same table (every registration carries its namespace);
the starters' ``Justfile`` maps the same words to the same extras in its
``extras`` recipe (the two tables are one); and ``validate`` on a tree
declaring a word whose plugin is not installed prints one configuration
line naming the extra -- proved by hiding the gcloud distributions from
the loader and validating the frozen fixture, which declares the runtime
``gcloud-east1`` with ``type: gcloud``.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from harness import REPO, copy_config, stub_environment
from typer.testing import CliRunner

from cs_image_system import extras
from cs_image_system.base import loader
from cs_image_system.base.loader import installed_registry
from cs_image_system.base.registry import UnknownTypeError
from cs_image_system.contract.constants import VCT

SKELETON_JUSTFILE = REPO / "docs/examples/_skeleton/Justfile"
GCLOUD_DISTRIBUTIONS = {"cs-image-system-gcloud-runtime-plugin", "cs-image-system-tf-gcp-plugin",
                        "cs-image-system-gcs-state-plugin"}
runner = CliRunner()


# ------------------------------------------------------------ the table against the registry

def _installed_words() -> dict[tuple[str, str], str]:
    """What the installed workspace registers under the extras' namespaces,
    by the rule the table states: every ``type:`` word of a builder, its
    model or a state backend; the version checkers and the injected item
    models left out."""
    namespace_to_extra = {ns: extra for extra, namespaces in extras.EXTRAS.items() for ns in namespaces}
    out: dict[tuple[str, str], str] = {}
    for key in installed_registry().registration_keys():
        extra = namespace_to_extra.get(key.namespace)
        if extra is None or not extras.is_type_word_classification(key.classification.value):
            continue
        assert out.get((key.classification.value, key.name), extra) == extra, \
            f"{key.qualified} is registered under two extras"
        out[(key.classification.value, key.name)] = extra
    return out


def test_the_static_table_is_what_the_installed_plugins_register():
    """The table cannot drift: regenerated from the registry, it is equal."""
    regenerated = _installed_words()
    assert regenerated == extras.WORDS, {
        "missing from WORDS": sorted(set(regenerated) - set(extras.WORDS)),
        "stale in WORDS": sorted(set(extras.WORDS) - set(regenerated)),
        "mapped elsewhere": sorted(k for k in regenerated if k in extras.WORDS and extras.WORDS[k] != regenerated[k]),
    }


def test_every_extras_namespace_is_an_installed_plugin_and_nothing_of_the_core_needs_one():
    namespaces = {k.namespace for k in installed_registry().registration_keys()}
    for extra, members in extras.EXTRAS.items():
        for ns in members:
            assert ns in namespaces, f"[{extra}] names {ns}, which no installed plugin registers as"
    # a word the bare install carries is never an extra's
    for key in installed_registry().registration_keys():
        if key.namespace not in {ns for members in extras.EXTRAS.values() for ns in members}:
            assert (key.classification.value, key.name) not in extras.WORDS, key.qualified
    assert list(extras.EXTRAS) == ["aws", "gcloud", "docker", "okta"] == list(extras.EXTRA_ORDER)


def test_extra_for_reads_the_bare_or_the_qualified_word():
    assert extras.extra_for("runtime_builder_model", "gcloud") == "gcloud"
    assert extras.extra_for("runtime_builder_model", "gcloud-runtime/gcloud") == "gcloud"
    assert extras.extra_for("state_backend_model", "s3") == "aws"
    assert extras.extra_for("group_builder_model", "okta-tf-ro") == "okta"
    assert extras.extra_for("instance_builder_model", "tofu-docker") == "docker"
    assert extras.extra_for("runtime_builder_model", "nonsense") is None
    assert extras.extra_for("os_builder_model", "rhel") is None, "the bare install carries the OS families"
    assert extras.extra_for("version_checker", "tofu") is None, "a checker is never a reason to install an extra"


def test_the_install_line_names_the_extras_in_order():
    assert extras.install_line([]) == "cs-image-system"
    assert extras.install_line(["okta", "aws"], "0.2.0") == "cs-image-system[aws,okta]==0.2.0"
    assert extras.install_line(extras.EXTRA_ORDER) == "cs-image-system[aws,gcloud,docker,okta]"
    assert extras.words_by_extra()["docker"] == ["docker", "tf-docker-volume", "tofu-docker"]


def test_the_message_names_the_extra_or_the_words_that_are_registered():
    line = extras.unknown_type_message("runtime_builder_model", "gcloud", ["aws", "docker"])
    assert line.startswith("runtime type 'gcloud'") and line.endswith("uv tool install 'cs-image-system[gcloud]'")
    line = extras.unknown_type_message("state_backend_model", "nonsense", ["local", "s3"])
    assert line.startswith("state backend type 'nonsense'") and "no extra" in line and line.endswith("register local, s3")
    assert extras.unknown_type_message("group_builder_model", "x", []).endswith("register nothing")
    e = UnknownTypeError(VCT.RUNTIME_BUILDER_MODEL, "gcloud", ["docker", "aws"])
    assert str(e) == extras.unknown_type_message("runtime_builder_model", "gcloud", [])
    assert e.registered == ["aws", "docker"] and e.classification is VCT.RUNTIME_BUILDER_MODEL


# ------------------------------------------------------------- the Justfile's copy of the table

def justfile_case_mapping(justfile: Path = SKELETON_JUSTFILE) -> dict[str, str]:
    """word -> extra, parsed from the ``case`` of the ``extras`` recipe:
    one ``a|b|c) aws=aws ;;`` line per extra."""
    body = justfile.read_text()
    recipe = body.split("\nextras:\n", 1)[1].split("\n\n", 1)[0]
    out: dict[str, str] = {}
    for words, extra in re.findall(r"^\s+([a-z0-9|-]+)\)\s+([a-z]+)=\2 ;;$", recipe, flags=re.M):
        for word in words.split("|"):
            assert word not in out, f"the Justfile maps {word} twice"
            out[word] = extra
    assert out, "no case mapping found in the extras recipe"
    return out


def test_the_starters_justfile_maps_the_same_words_to_the_same_extras(tmp_path: Path):
    """The two tables are one: every word of WORDS, whatever its
    classification, maps to the same extra in the Justfile, and the
    Justfile names no word the table does not; run over the complete
    starter, the recipe prints every extra in EXTRA_ORDER."""
    flat: dict[str, str] = {}
    for (_classification, word), extra in extras.WORDS.items():
        assert flat.get(word, extra) == extra, f"{word} maps to two extras across classifications"
        flat[word] = extra
    assert justfile_case_mapping() == flat
    recipe = SKELETON_JUSTFILE.read_text().split("\nextras:\n", 1)[1].split("\n\n", 1)[0]
    assert "executables.yml) continue" in recipe, "the checkers' file is not read"
    assert "[private]\nextras:" in SKELETON_JUSTFILE.read_text()
    if shutil.which("just"):                                               # the recipe's effect, in order
        tree = tmp_path / "tree"
        shutil.copytree(REPO / "docs" / "examples" / "complete", tree)
        shutil.copy2(SKELETON_JUSTFILE, tree / "Justfile")
        done = subprocess.run(["just", "-f", str(tree / "Justfile"), "extras"], capture_output=True, text=True, check=True)
        assert done.stdout.strip() == ",".join(extras.EXTRA_ORDER)


def test_take_and_every_workflow_install_the_umbrella_with_the_trees_extras():
    take = re.split(r"\ntake version[^\n]*:\n", SKELETON_JUSTFILE.read_text(), maxsplit=1)[1]   # the recipe's body, whatever its arguments
    assert 'extras=$(just extras)' in take
    assert '"cs-image-system${extras:+[$extras]}==$version"' in take
    workflows = sorted((REPO / "docs/examples").glob("*/.github/workflows/*.yml"))
    assert len(workflows) == 8, "five ci.yml and three OPA probes"
    for wf in workflows:
        text = wf.read_text()
        installs = text.count('uv tool install $indexes "cs-image-system${extras:+[$extras]}${pin}"')
        assert installs == text.count("extras=$(just extras)") == (3 if wf.name == "ci.yml" else 1), wf
        assert 'uv tool install $indexes "cs-image-system${pin}"' not in text, wf
    setup = (REPO / "docs/examples/_skeleton/CI_SETUP.md").read_text()
    assert "just extras" in setup and re.search(r"cs-image-system\[[a-z,]+\]", setup)      # the guide names the recipe and the install shape
    if shutil.which("just"):
        assert subprocess.run(["just", "-f", str(SKELETON_JUSTFILE), "--show", "extras"], capture_output=True).returncode == 0


# -------------------------------------------------- validate names the extra of an absent plugin

class _Points:
    def __init__(self, points: list[Any]) -> None:
        self._points = {p.name: p for p in points}

    def __len__(self) -> int:
        return len(self._points)

    def __iter__(self):
        return iter(self._points.values())

    def __getitem__(self, name: str) -> Any:
        return self._points[name]


@pytest.fixture
def without_gcloud(monkeypatch):
    """The loader sees every installed entry point except the three gcloud
    distributions'; discovery runs again with that view (and once more,
    whole, when the test is done, so the suite's view is restored)."""
    real = loader.entry_points

    def hiding(group: str) -> _Points:
        def shown(point: Any) -> bool:
            dist = getattr(point, "dist", None)
            return dist is None or dist.name not in GCLOUD_DISTRIBUTIONS
        return _Points([p for p in real(group=group) if shown(p)])

    monkeypatch.setattr(loader, "entry_points", hiding)
    loader._discovered_plugins.cache_clear()
    loader.discover_plugins()                 # the plugins are held to the contract BEFORE any hook is stubbed
    try:
        yield
    finally:
        monkeypatch.undo()
        loader._discovered_plugins.cache_clear()
        loader.discover_plugins()


def test_validate_names_the_missing_extra_in_one_line(without_gcloud, tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    assert "gcloud-runtime" not in {k.namespace for k in installed_registry().registration_keys()}
    root = copy_config(tmp_path)
    from cs_image_system.system.cli import app
    result = runner.invoke(app, ["--root-dir", str(root), "validate"], catch_exceptions=False, input="")
    assert result.exit_code == 1, result.output
    assert "runtime type 'gcloud'" in result.output and "cs-image-system[gcloud]" in result.output
    assert "Validation failed with 1 error(s)." in result.output
    assert "Traceback" not in result.output and "UnknownTypeError" not in result.output


def test_a_word_no_extra_carries_is_unknown_with_the_registered_words_listed(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    rb = root / "cfg" / "runtime-builders.yml"
    rb.write_text(rb.read_text().replace("type: gcloud", "type: nonsense", 1))
    from cs_image_system.system.cli import app
    result = runner.invoke(app, ["--root-dir", str(root), "validate"], catch_exceptions=False, input="")
    assert result.exit_code == 1, result.output
    assert "runtime type 'nonsense'" in result.output and "register aws, docker, gcloud" in result.output
    assert "Validation failed with 1 error(s)." in result.output
