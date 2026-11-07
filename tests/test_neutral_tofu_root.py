# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The provider-neutral terraform root: no root plugin depends on another
provider's root, and the GCE and docker roots install without the AWS one.

Three proofs. The import graph: no source file of tf-gcp or tf-docker
imports tf-ebs-instance or aws-runtime, and the AWS root imports no other
provider's runtime; the neutral bases in tofu-roots import no provider
plugin at all. The declared dependencies: the two pyprojects name no
AWS package. The install: an environment synced from the lock for the two
plugins alone holds neither the AWS root, nor aws-runtime, nor boto3, and
both plugins import, register and construct their builders there.

History: stage 120.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGES = REPO / "packages"

ROOTS = {"tf-gcp-plugin": "tf_gcp_plugin", "tf-docker-plugin": "tf_docker_plugin",
         "tf-ebs-instance-plugin": "tf_ebs_instance_plugin"}
AWS = {"cs_image_system.tf_ebs_instance_plugin", "cs_image_system.aws_runtime", "boto3", "botocore"}
OTHER_PROVIDERS = {"cs_image_system.gcloud_runtime", "cs_image_system.docker_runtime",
                   "cs_image_system.tf_gcp_plugin", "cs_image_system.tf_docker_plugin"}


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def _sources(package: str) -> list[Path]:
    return sorted((PACKAGES / package / "src").rglob("*.py"))


def _crossing(package: str, forbidden: set[str]) -> list[str]:
    hits: list[str] = []
    for f in _sources(package):
        for mod in _imports(f):
            if any(mod == x or mod.startswith(x + ".") for x in forbidden):
                hits.append(f"{f.relative_to(REPO)}: {mod}")
    return hits


def test_the_gce_and_docker_roots_import_nothing_of_aws():
    assert _crossing("tf-gcp-plugin", AWS) == []
    assert _crossing("tf-docker-plugin", AWS) == []


def test_the_aws_root_imports_no_other_providers_runtime_or_root():
    assert _crossing("tf-ebs-instance-plugin", OTHER_PROVIDERS) == []


def test_the_neutral_bases_import_no_provider_plugin():
    bases = {"cs_image_system.aws_runtime", "cs_image_system.gcloud_runtime", "cs_image_system.docker_runtime",
             "cs_image_system.tf_ebs_instance_plugin", "cs_image_system.tf_gcp_plugin", "cs_image_system.tf_docker_plugin"}
    hits = [f"{f.name}: {m}" for f in _sources("tofu-roots")
            for m in _imports(f) if any(m == x or m.startswith(x + ".") for x in bases)]
    assert hits == []


def test_every_root_subclasses_the_neutral_bases():
    text = "\n".join(f.read_text() for p in ROOTS for f in _sources(p))
    for base in ("TofuInstanceBuilderBase", "TofuStorageBuilderBase",
                 "TofuInstanceBuilderModelBase", "TofuStorageBuilderModelBase"):
        assert re.search(rf"\(\s*{base}\b", text), base
    assert "class TofuGceInstanceBuilder(TofuInstanceBuilderBase[" in text
    assert "class TofuDockerInstanceBuilder(TofuInstanceBuilderBase[" in text
    assert "class TofuInstanceBuilder(TofuInstanceBuilderBase[" in text


@pytest.mark.parametrize("package", ["tf-gcp-plugin", "tf-docker-plugin"])
def test_the_gce_and_docker_pyprojects_name_no_aws_package(package: str):
    deps = tomllib.loads((PACKAGES / package / "pyproject.toml").read_text())["project"]["dependencies"]
    assert not [d for d in deps if "tf-ebs-instance" in d or "aws-runtime" in d or d.startswith("boto")], deps


def test_every_root_plugin_registers_the_tofu_version_checker():
    from cs_image_system.tofu_roots.tofu_instance_builder import TofuVersionChecker
    for module in ("cs_image_system.tf_ebs_instance_plugin.main", "cs_image_system.tf_gcp_plugin.main",
                   "cs_image_system.tf_docker_plugin.main"):
        md = __import__(module, fromlist=["initialize"]).initialize()
        assert any(TofuVersionChecker in classes for classes in md.services.values()), module


# that the registry takes the one checker from the three roots as one
# registration is proved in tests/test_registration_namespaces.py
# (test_the_same_class_under_three_namespaces_is_one_registration)


_ISOLATION = """
import importlib.util, sys
for absent in ("boto3", "botocore", "cs_image_system.aws_runtime", "cs_image_system.tf_ebs_instance_plugin"):
    assert importlib.util.find_spec(absent) is None, absent + " is installed"
from cs_image_system.tf_gcp_plugin.main import initialize as gcp
from cs_image_system.tf_docker_plugin.main import initialize as docker
from cs_image_system.tofu_roots.tofu_instance_builder import TofuInstanceBuilderBase, TofuVersionChecker
from cs_image_system.tofu_roots.tofu_storage_builder import TofuStorageBuilderBase
seen = set()
for md in (gcp(), docker()):
    for classes in md.services.values():
        seen.update(classes)
    for model, builder in md.builders_for_models.items():
        assert issubclass(builder, (TofuInstanceBuilderBase, TofuStorageBuilderBase)), builder
assert TofuVersionChecker in seen
assert not any(m.startswith("cs_image_system.aws_runtime") or m.startswith("cs_image_system.tf_ebs") for m in sys.modules), \\
    sorted(m for m in sys.modules if "aws" in m or "tf_ebs" in m)
print("isolated: ok")
"""


def test_the_gce_and_docker_roots_install_and_register_without_the_aws_root(tmp_path: Path):
    """An environment synced from the lock for the two plugins alone (about
    half a minute from the cache): no AWS root, no aws-runtime, no boto3;
    both plugins import, register and build on the neutral bases."""
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(tmp_path / "venv")}
    sync = subprocess.run(["uv", "sync", "--frozen", "--no-dev", "--package", "cs-image-system-tf-gcp-plugin",
                           "--package", "cs-image-system-tf-docker-plugin"],
                          cwd=REPO, env=env, capture_output=True, text=True)
    assert sync.returncode == 0, sync.stderr[-2000:]
    python = tmp_path / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run = subprocess.run([str(python), "-c", _ISOLATION], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-1000:] + run.stderr[-3000:]
    assert "isolated: ok" in run.stdout
