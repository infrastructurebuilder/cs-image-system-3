# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The translation belongs to the runtime, so it is documented with the
runtime. Every runtime plugin's README carries an "Image query
translation" table, one row per key of the system's vocabulary, and the
table says exactly what the plugin's ``supported_query_keys()`` says. The
same README names the plugin's part of the release-owned image-source
catalog, the ``data/image-sources.yml`` it ships, since the catalog no
longer lives in one file of the core."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest

from cs_image_system.contract.image import QUERY_KEYS

REPO = Path(__file__).resolve().parents[1]
HEADING = "### Image query translation"
ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*([^|]*?)\s*\|")


def _runtimes():
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    return [("aws-runtime-plugin", AwsCloudBuilder), ("gcloud-runtime-plugin", GCPCloudBuilder),
            ("docker-runtime-plugin", DockerContainerBuilder)]


def _table(readme: Path) -> dict[str, str]:
    text = readme.read_text()
    assert HEADING in text, f"{readme.relative_to(REPO)} has no '{HEADING}' section"
    section = text.split(HEADING, 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for line in section.splitlines():
        m = ROW.match(line)
        if m and m.group(1) != "key":
            rows[m.group(1)] = m.group(2)
    return rows


@pytest.mark.parametrize("package, builder", _runtimes(), ids=[p for p, _ in _runtimes()])
def test_the_translation_table_says_what_the_plugin_declares(package: str, builder: type):
    rows = _table(REPO / "packages" / package / "README.md")
    missing = [k for k in QUERY_KEYS if k not in rows]
    assert not missing, f"{package}: the table lacks a row for {missing}"
    documented = {k for k, native in rows.items() if native.lower() != "refused"}
    declared = builder.supported_query_keys(cast(Any, None))      # the hook reads nothing of self
    assert documented == declared, (f"{package}: the README says {sorted(documented)} are translated, "
                                    f"the plugin says {sorted(declared)}")


@pytest.mark.parametrize("package, builder", _runtimes(), ids=[p for p, _ in _runtimes()])
def test_the_readme_names_the_catalog_part_the_plugin_ships(package: str, builder: type):
    text = (REPO / "packages" / package / "README.md").read_text()
    data = next(d for d in (REPO / "packages" / package / "src" / "cs_image_system").iterdir()
                if (d / "data" / "image-sources.yml").is_file()) / "data" / "image-sources.yml"
    assert "data/image-sources.yml" in text, f"{package}: the README does not name {data.relative_to(REPO)}"
    assert builder.image_source_entries(), f"{package}: the plugin ships no catalog entries"


def test_the_contract_lists_the_vocabulary_once():
    text = (REPO / "packages" / "contract" / "README.md").read_text()
    for key in QUERY_KEYS:
        assert f"`{key}`" in text, f"the contract README does not name the query key {key}"
