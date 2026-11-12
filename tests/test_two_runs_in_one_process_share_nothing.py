# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Two run contexts loaded in one process are independent.

Every load makes a registry, an image-source catalog, a template resolver
and a context of its own, and binds each model and builder it builds to
them; the process keeps none of the four. So a second context loaded while
a first is still in use (another tree, or the same tree under other
overlays, which is what a nested run needs) reads nothing of the first and
changes nothing the first reads.

The first test looks at the objects: no handle and no model is shared, and
each model and builder answers with its own run's. The second looks at the
behaviour: a run whose load was followed by another run's load AND
generation still emits the golden tree, byte for byte, while the other
run's emission shows what only its own declarations say.

What a run keeps beside its context is its own as well, and is not keyed
by anything two runs could share: two runs loaded at one moment carry one
run id, and still each draws its aliases from its own pool and gives back
only its own. What the process does keep for every run (the installed
plugins, the hook lists, the opened ciphertexts) is listed, with why
sharing it is safe, in the base package's README.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import yaml
from golden import GOLDEN, IGNORED_FILES
from harness import V2Run, copy_config, load_context, stub_environment, tree

from cs_image_system.base import alias_pool, image_sources, registry, run_context
from cs_image_system.base.launch_params import compute_launch_params
from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.models.os_builder_model import OsBuilderModel

#: the fixture's overlay that undeclares this instance for one invocation
#: and lets its runtime's instance root apply
OVERLAY = "gce-cycle-decommission.yaml"
OVERLAY_INSTANCE = "gce-test"
OVERLAY_APPLIES = ["gcloud-east1"]
#: a family only the second tree's catalog layer knows
FAMILY = "only-in-the-second-tree"


def _second_tree(tmp_path: Path) -> Path:
    """A copy of the fixture that differs from it in its own tree: one more
    image-source entry."""
    root = copy_config(tmp_path, "second")
    path = root / "cfg" / "image-sources.yml"
    doc = yaml.safe_load(path.read_text())
    doc["image_sources"].append({"family": FAMILY, "is": "rhel", "sources": {}})
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return root


def _models(ctx) -> list[NameTyped]:
    """Every model the run's object stage holds: the builder models, their
    sub-entries and the domain items."""
    return [m for m in ctx.template_resolver.flattened_map.values() if isinstance(m, NameTyped)]


def _ids(objects) -> set[int]:
    return {id(o) for o in objects}


def test_each_load_owns_its_registry_catalog_resolver_and_models(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    cwd = os.getcwd()
    try:
        first_root, second_root = copy_config(tmp_path, "first"), _second_tree(tmp_path)
        first = load_context(first_root)
        second = load_context(second_root, overlays=[second_root / "overlays" / OVERLAY])
        runs = (first, second)

        # --- the four handles are each run's own
        assert first.reg is not second.reg
        assert first.image_sources is not second.image_sources
        assert first.template_resolver is not second.template_resolver
        assert first.template_resolver.converter is not second.template_resolver.converter
        assert first.finalizer is not second.finalizer
        for ctx in runs:
            assert ctx.template_resolver.reg is ctx.reg
            assert ctx.template_resolver.converter.binding.reg is ctx.reg
            assert ctx.template_resolver.converter.binding.image_sources is ctx.image_sources

        # --- no object of one run is in the other's registry or resolver map
        # (the run's own scopes in the map, `execution` and `ENV`, included)
        assert not _ids(first.reg.instances_by_global_id.values()) & _ids(second.reg.instances_by_global_id.values())
        assert not _ids(first.template_resolver.flattened_map.values()) & _ids(second.template_resolver.flattened_map.values())
        assert not _ids(first.all_sorted_builders) & _ids(second.all_sorted_builders)

        # --- every model and builder answers with its own run's
        for ctx in runs:
            models = _models(ctx)
            assert len(models) > 50, len(models)
            assert all(m._reg is ctx.reg for m in models)
            os_models = [m for m in models if isinstance(m, OsBuilderModel)]
            assert os_models and all(m._image_sources is ctx.image_sources for m in os_models)
            assert ctx.all_sorted_builders
            for builder in ctx.all_sorted_builders:
                assert builder._get_context() is ctx
                assert builder.model._reg is ctx.reg
            for name, builder in ctx.image_builders.items():
                assert ctx.reg.get_instance_by_name_or_alias(builder.csis_classifier(), name) is builder
            assert all(exe._reg is ctx.reg for exe in ctx.executables.values())

        # --- what one run declares, the other does not see
        names = [{i.get_name() for i in ctx.instances} for ctx in runs]
        assert OVERLAY_INSTANCE in names[0] and OVERLAY_INSTANCE not in names[1]     # the second's overlay undeclared it
        assert first.overlays == [] and [p.name for p in second.overlays] == [OVERLAY]
        assert second.config["apply_instances"] == OVERLAY_APPLIES
        assert first.config["apply_instances"] is False                             # the tree's own, untouched
        assert second.image_sources.effective_family(FAMILY) == "rhel"
        assert first.image_sources.effective_family(FAMILY) == FAMILY                # only a token to the first
        assert [e.family for e in first.image_sources.tree_entries()] == \
            [e.family for e in second.image_sources.tree_entries()][:-1]
        assert first.working_path == first_root.resolve() and second.working_path == second_root.resolve()
        assert first.meta_state is not second.meta_state

        # --- and the first still answers as it did before the second was loaded
        families = {name: osb.model.get_family() for name, osb in first.os_builders.items()}
        again = load_context(second_root)                                            # a third load changes nothing either
        assert {name: osb.model.get_family() for name, osb in first.os_builders.items()} == families
        assert again.reg is not second.reg and OVERLAY_INSTANCE in {i.get_name() for i in again.instances}
        assert OVERLAY_INSTANCE not in {i.get_name() for i in second.instances}
    finally:
        os.chdir(cwd)


def test_the_process_keeps_no_current_context_registry_or_catalog():
    """The fetches a second load used to rebind are gone, with the module
    that kept the old context name importable."""
    assert not hasattr(run_context, "current_context") and not hasattr(run_context, "bind_current")
    assert not hasattr(registry, "current_registry") and not hasattr(registry, "bind_current_registry")
    assert not hasattr(image_sources, "current_catalog") and not hasattr(image_sources, "bind_current_catalog")
    assert importlib.util.find_spec("cs_image_system.base.global_context") is None
    assert importlib.util.find_spec("cs_image_system.base.singleton") is None
    assert not hasattr(alias_pool, "_DRAWN")                 # a run's alias draws are kept beside its context


def test_each_run_keeps_its_own_alias_draws_under_one_run_id(tmp_path, monkeypatch):
    """Two runs that can launch, loaded in one process at one moment (so
    under one run id), each over a tree with a pool of its own: each draws
    its instance's alias from its own pool, the second computation does not
    find the first one's draw, and the first giving back what it drew leaves
    the second's name spent."""
    stub_environment(monkeypatch)
    cwd = os.getcwd()
    try:
        runs = [load_context(copy_config(tmp_path, name), dry_run=False) for name in ("first", "second")]
        first, second = runs
        assert first.run_id == second.run_id
        pools = [alias_pool.pool_path(ctx.working_path) for ctx in runs]
        for ctx, pool, names in zip(runs, pools, ("amber\n", "birch\n"), strict=True):
            ctx.config["apply_instances"] = True
            pool.parent.mkdir(parents=True, exist_ok=True)
            pool.write_text(names)
        instance = {id(ctx): next(i for i in ctx.instances if i.get_name() == "test") for ctx in runs}

        drawn = [compute_launch_params(ctx, instance[id(ctx)]).get("alias") for ctx in runs]
        assert drawn == ["amber", "birch"]
        assert [alias_pool.free_names(pool) for pool in pools] == [[], []]
        assert alias_pool.drawn_this_run(first) == {"test": "amber"}
        assert alias_pool.drawn_this_run(second) == {"test": "birch"}
        # a second computation in each run finds that run's own draw
        assert [compute_launch_params(ctx, instance[id(ctx)]).get("alias") for ctx in runs] == drawn

        assert alias_pool.release_unlaunched(first) == ["amber"]
        assert [alias_pool.free_names(pool) for pool in pools] == [["amber"], []]
        assert alias_pool.drawn_this_run(first) == {}
        assert alias_pool.drawn_this_run(second) == {"test": "birch"}
    finally:
        os.chdir(cwd)


def _emission(run: V2Run) -> dict[str, str]:
    out = {f"generated/{k}": v for k, v in tree(run.generated).items()}
    out.update({f"meta-state/{k}": v for k, v in tree(run.meta_state).items()})
    return {k: v for k, v in out.items() if Path(k).name not in IGNORED_FILES}


def test_a_run_emits_the_golden_tree_with_another_run_loaded_and_generated_beside_it(tmp_path, monkeypatch):
    """The first run is loaded, then a second (another tree, under an
    overlay) is loaded and generates everything, and only then does the
    first generate: its emission is the golden tree, so nothing the second
    load bound or the second run resolved reached it. The second's own
    emission lacks the instance its overlay undeclared."""
    first = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path, "first"))
    try:
        second_root = _second_tree(tmp_path)
        second = V2Run(tmp_path, monkeypatch, config_root=second_root,
                       overlays=[second_root / "overlays" / OVERLAY])
        summary = second.run("all", apply=True)
        assert summary.ok, summary.error
        summary = first.run("all", apply=True)
        assert summary.ok, summary.error

        golden = tree(GOLDEN)
        emitted = _emission(first)
        assert sorted(emitted) == sorted(golden)
        assert [rel for rel in sorted(golden) if emitted[rel] != golden[rel]] == []

        module = f'module "instance_{OVERLAY_INSTANCE.replace("-", "_")}"'
        of_the_second = _emission(second)
        assert any(module in text for text in emitted.values())
        assert not any(module in text for text in of_the_second.values())
        # each wrote under its own root and nowhere else
        assert first.generated.is_dir() and second.generated.is_dir() and first.generated != second.generated
    finally:
        first.restore_cwd()
