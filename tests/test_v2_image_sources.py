# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 106: the image-source catalog and the system's query vocabulary.

The vocabulary (``contract.image.ImageQuery``) is the system's; each runtime
translates it. The catalog has two layers (the release's, the tree's) and
answers a block per family, version and runtime type; an OS builder's own
query and its runtime entry's land on the block key by key. A family may say
what it IS, and everything that branches on a family reads that. ``validate``
refuses an unknown key, an entry with no source, and a key the runtime cannot
translate, naming the entry each time, and prints every resolved query in
both vocabularies. The fingerprint hashes the effective query.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from cs_image_system.contract.image import QUERY_KEYS, ImageQuery

from v2_support import FIXTURE_CONFIG, copy_config, load_context, reset_singletons, stub_environment

AWS_RUNTIME, GCE_RUNTIME = "aws-east2-runtime", "gcloud-east1"
ALMA_AWS_ACCOUNT = "764336703387"


def _block(cat, family: str, version: str, runtime_type: str) -> ImageQuery:
    block = cat.block(family, version, runtime_type)
    assert block is not None, (family, version, runtime_type)
    return block


def _entry(ctx, osb_name: str, image_builder: str):
    osb = ctx.os_builders[osb_name]
    return next(e for e in osb.get_configs_for_image_builders().values() if e.get_image_builder() == image_builder)


def _edit_os_builders(root: Path, change) -> None:
    p = root / "cfg" / "os-builders.yml"
    doc = yaml.safe_load(p.read_text())
    change(doc["os_builders"])
    p.write_text(yaml.safe_dump(doc, sort_keys=False))


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    c = load_context(copy_config(tmp_path))
    try:
        yield c
    finally:
        reset_singletons()


# ------------------------------------------------------------- the vocabulary
def test_the_vocabulary_reads_the_old_spellings_and_refuses_the_unknown():
    q = ImageQuery.from_mapping({"owners": ["self", "amazon"],
                                 "filters": {"name": "RHEL-9*", "root_device_type": "ebs", "virtualization_type": "hvm",
                                             "state": "available", "tag:Env": "prod"}})
    assert q.to_mapping() == {"name": "RHEL-9*", "publisher": ["self", "amazon"], "state": "available",
                              "virtualization": "hvm", "root_device": "ebs", "tags": {"Env": "prod"}}
    assert q.keys() == {"name", "publisher", "state", "virtualization", "root_device", "tags"}
    with pytest.raises(ValueError, match="totally_custom"):
        ImageQuery.from_mapping({"filters": {"totally_custom": "x"}}, where="entry a")
    assert list(ImageQuery.from_mapping({"newest": "false"}).to_mapping()) == ["newest"]


def test_an_override_lands_on_a_query_key_by_key():
    base = ImageQuery.from_mapping({"publisher": ["x"], "name": "a-{version}*", "root_device": "ebs",
                                    "tags": {"a": "1"}, "native": {"p": "q"}})
    over = ImageQuery.from_mapping({"name": "b*", "tags": {"b": "2"}, "publisher": ["self"]})
    merged = base.substituted(version="10").merged(over)
    assert merged.to_mapping() == {"name": "b*", "publisher": ["self"], "root_device": "ebs",
                                   "tags": {"a": "1", "b": "2"}, "native": {"p": "q"}}
    assert base.substituted(version="10").name == "a-10*"      # the one placeholder
    # name and family are two ways to say which image: an override saying one clears the other
    # (found live: the reference's GCE entry names the image, the catalog's rhel block names the
    # family, and the two ANDed found nothing in almalinux-cloud)
    catalog = ImageQuery.from_mapping({"publisher": ["rhel-cloud"], "family": "rhel-10"})
    assert catalog.merged(ImageQuery.from_mapping({"name": "almalinux-10-v*", "owners": ["almalinux-cloud"]})).to_mapping() == {
        "name": "almalinux-10-v*", "publisher": ["almalinux-cloud"]}
    assert ImageQuery(name="x*").merged(ImageQuery(family="f")).to_mapping() == {"family": "f"}
    assert ImageQuery(name="x*").merged(ImageQuery(name="y*", family="f")).to_mapping() == {"name": "y*", "family": "f"}
    assert base.merged(None).to_mapping() == base.to_mapping()


# ----------------------------------------------------------------- the catalog
def test_the_release_catalog_knows_the_families_the_plugins_serve():
    from cs_image_system.base.image_sources import packaged_default_entries
    entries = packaged_default_entries()
    families = {e.family for e in entries}
    assert {"rhel", "alma-linux", "rocky-linux", "debian", "ubuntu", "fedora"} <= families
    assert all(e.block("docker") is not None for e in entries if e.family in ("rhel", "alma-linux", "debian"))
    assert next(e for e in entries if e.family == "alma-linux").is_ == "rhel"


def test_the_tree_layer_lands_on_the_releases_and_a_version_on_the_generic(ctx):
    from cs_image_system.base.image_sources import ImageSourceCatalog, container_reference
    cat = ImageSourceCatalog()
    debian = cat.block("debian", "12", "aws")
    assert debian is not None and debian.publisher == ("self", "amazon", "136693071363")   # the fixture's layer
    assert debian.name == "debian-12-amd64-*" and debian.root_device == "ebs"
    assert _block(cat, "debian", "12", "gcloud").family == "debian-12"                    # the release's, untouched
    assert container_reference(_block(cat, "rhel", "9", "docker")) == "rockylinux:9"
    assert container_reference(_block(cat, "rhel", "10", "docker")) == "almalinux:10"      # the version entry lands
    assert _block(cat, "rhel", "10", "aws").name == "RHEL-10*x86_64*"                      # the generic still answers
    assert _block(cat, "alma-linux", "10", "gcloud").to_mapping() == {"family": "almalinux-10", "publisher": ["almalinux-cloud"]}
    assert cat.block("ubuntu", "24", "gcloud") is None                                     # GCE: declare it


def test_a_family_is_what_the_catalog_says_it_is(ctx):
    from cs_image_system.base.image_sources import ImageSourceCatalog, container_reference
    from cs_image_system.base.mod_tests import test_image_for
    model = ctx.os_builders["basic-rh-10"].model
    assert model.get_vendor_family() == "alma-linux" and model.get_family() == "rhel"
    assert type(model).families() == ("rhel", "alma-linux", "rocky-linux", "centos", "centos-stream")
    assert test_image_for(ctx, ctx.images_map["imgfile-basic-dask"]) == "almalinux:10"
    cat = ImageSourceCatalog()
    # the fixture's custom family: treated as rhel, queried its own way, tested as what it is
    assert cat.effective_family("rhel-from-fixture", "10") == "rhel"
    assert _block(cat, "rhel-from-fixture", "10", "aws").name == "fixture-rhel10-golden-*"
    assert cat.block("rhel-from-fixture", "10", "docker") is None
    stand_in = cat.stand_in_block("rhel-from-fixture", "10")
    assert stand_in is not None and container_reference(stand_in) == "almalinux:10"
    assert cat.effective_family("nobody-knows", "1") == "nobody-knows"


def test_container_references():
    from cs_image_system.base.image_sources import container_reference
    assert container_reference(ImageQuery(publisher=("library",), name="debian", version="12")) == "debian:12"
    assert container_reference(ImageQuery(publisher=("quay.io/centos",), name="centos", version="stream9")) == "quay.io/centos/centos:stream9"
    assert container_reference(ImageQuery(native={"image": "registry.example/ubi10"})) == "registry.example/ubi10"
    assert container_reference(ImageQuery()) is None


# ------------------------------------------------------------------- the stack
def test_the_effective_query_is_the_catalog_under_the_declarations(ctx):
    aws = _entry(ctx, "basic-rh-10", "pckr-ebs-ans")
    assert aws.runtime_type() == "aws"
    assert aws.image_query().to_mapping() == {"name": "AlmaLinux OS 10*x86_64*", "publisher": [ALMA_AWS_ACCOUNT],
                                              "virtualization": "hvm", "root_device": "ebs"}
    gce = _entry(ctx, "basic-rh-10", "pckr-gce-ans")
    assert gce.image_query().to_mapping() == {"family": "almalinux-10", "publisher": ["almalinux-cloud"]}
    # a declared query lands on the catalog's block; declared owners replace its publisher
    rhel9 = _entry(ctx, "basic-rhel-9", "pckr-ebs-ans")
    assert rhel9.image_query().to_mapping() == {"name": "RHEL-9.5*x86_64*", "publisher": ["self", "amazon"],
                                                "virtualization": "hvm", "root_device": "ebs"}
    assert dict(rhel9.query) == {"filters": {"name": "RHEL-9.5*x86_64*", "root_device_type": "ebs"}}   # as declared
    assert rhel9.get_query() == rhel9.image_query().to_mapping()


def test_each_runtime_translates_the_same_query_into_its_own_words(ctx):
    aws = ctx.runtime_builders[AWS_RUNTIME]
    native = aws.translate_image_query(_entry(ctx, "basic-rh-10", "pckr-ebs-ans").image_query())
    assert native == {"owners": [ALMA_AWS_ACCOUNT],
                      "filters": {"name": "AlmaLinux OS 10*x86_64*", "root-device-type": "ebs",
                                  "virtualization-type": "hvm", "state": "available"},
                      "most_recent": True}
    gce = ctx.runtime_builders[GCE_RUNTIME]
    native = gce.translate_image_query(_entry(ctx, "basic-rh-10", "pckr-gce-ans").image_query())
    assert native["projects"] == ["almalinux-cloud"] and native["terms"] == {"family": "almalinux-10", "status": "READY"}
    assert native["filter"] == '(family = "almalinux-10") AND (status = "READY")'
    assert "root_device" in aws.supported_query_keys() and "root_device" not in gce.supported_query_keys()
    assert "family" in gce.supported_query_keys() and "family" not in aws.supported_query_keys()
    assert set(QUERY_KEYS) > aws.supported_query_keys() | gce.supported_query_keys()


def test_the_fingerprint_hashes_the_effective_query(ctx):
    from cs_image_system.base.lineage import _vendor_source
    # the base image exists only after a resolution; the hash reads the OS builder by the image's name
    base = type("BaseImageStandIn", (), {"get_name": lambda self: "basic-rh-10"})()
    source = _vendor_source(ctx, base, AWS_RUNTIME)
    assert source["family"] == "alma-linux"
    assert source["runtime_source"]["query"] == _entry(ctx, "basic-rh-10", "pckr-ebs-ans").image_query().to_mapping()


# ----------------------------------------------------------------- validation
def test_validate_prints_every_resolved_query_in_both_vocabularies(ctx, caplog):
    from cs_image_system.base.commands.validate import check_image_sources
    with caplog.at_level(logging.INFO, logger="cs_image_system.base.commands.validate"):
        assert check_image_sources(ctx) == []
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("image source:")]
    assert any(ln.startswith(f"image source: OS builder 'basic-rh-10' on runtime {AWS_RUNTIME} (aws): name=AlmaLinux OS 10*x86_64*")
               and "'root-device-type': 'ebs'" in ln for ln in lines), lines
    assert any(f"on runtime {GCE_RUNTIME} (gcloud): family=almalinux-10" in ln for ln in lines), lines
    assert len(lines) == 4                                   # my-deb-12, basic-rhel-9, basic-rh-10 x2


def _errors(tmp_path, monkeypatch, change) -> list[str]:
    from cs_image_system.base.commands.validate import check_image_sources
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    _edit_os_builders(root, change)
    c = load_context(root)
    try:
        return [str(e) for e in check_image_sources(c)]
    finally:
        reset_singletons()


def test_validate_refuses_a_key_the_runtime_cannot_translate(tmp_path, monkeypatch):
    def change(entries):
        rh = next(e for e in entries if e["name"] == "basic-rh-10")
        next(r for r in rh["runtimes"] if r["name"] == "gcp-my-rh10")["query"] = {"filters": {"root_device_type": "ebs"}}
    errors = _errors(tmp_path, monkeypatch, change)
    assert len(errors) == 1 and "basic-rh-10" in errors[0] and "(gcloud)" in errors[0]
    assert "cannot translate image query key(s) root_device" in errors[0] and "native:" in errors[0]


def test_validate_refuses_an_unknown_key_by_name_and_place(tmp_path, monkeypatch):
    def change(entries):
        rh = next(e for e in entries if e["name"] == "basic-rh-10")
        next(r for r in rh["runtimes"] if r["name"] == "aws-my-rhel8")["query"] = {"filters": {"totally_custom": "x"}}
    errors = _errors(tmp_path, monkeypatch, change)
    assert len(errors) == 1 and "totally_custom" in errors[0] and "runtime entry aws-my-rhel8" in errors[0]


def test_validate_refuses_an_entry_with_no_source_at_all(tmp_path, monkeypatch):
    def change(entries):
        entries.append({"name": "mystery", "type": "rhel", "family": "nobody-knows", "family_version": "10",
                        "runtimes": [{"name": "aws-mystery", "image_builder": "pckr-ebs-ans"}]})
    errors = _errors(tmp_path, monkeypatch, change)
    assert len(errors) == 1 and "'mystery'" in errors[0] and "no image source" in errors[0]
    assert "no `aws` block for family 'nobody-knows' 10" in errors[0] and "cfg/image-sources.yml" in errors[0]


def test_a_pinned_entry_needs_no_query(tmp_path, monkeypatch):
    def change(entries):
        entries.append({"name": "pinned", "type": "rhel", "family": "nobody-knows", "family_version": "10",
                        "runtimes": [{"name": "aws-pinned", "image_builder": "pckr-ebs-ans", "image_id": "ami-0123456789abcdef0"}]})
    assert _errors(tmp_path, monkeypatch, change) == []


# ------------------------------------------------------- the type and the family
def test_the_type_is_defaulted_from_what_the_family_is(tmp_path, monkeypatch):
    from cs_image_system.default_os_plugin.debian_type import DebianOsBuilderModel
    from cs_image_system.default_os_plugin.rhel_type import RhelOsBuilderModel
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)

    def change(entries):
        for e in entries:
            if e["name"] in ("basic-rh-10", "my-deb-12"):
                del e["type"]
    _edit_os_builders(root, change)
    c = load_context(root)
    try:
        assert isinstance(c.os_builders["basic-rh-10"].model, RhelOsBuilderModel)      # alma-linux IS rhel
        assert isinstance(c.os_builders["my-deb-12"].model, DebianOsBuilderModel)
    finally:
        reset_singletons()


def test_a_type_that_does_not_serve_the_family_is_refused(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)

    def change(entries):
        next(e for e in entries if e["name"] == "basic-rh-10")["type"] = "debian"
    _edit_os_builders(root, change)
    with pytest.raises(Exception, match="family 'alma-linux' is 'rhel'.*which type 'debian' does not serve"):
        load_context(root)
    reset_singletons()


def test_a_family_nobody_serves_needs_a_declared_type(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)

    def change(entries):
        entries.append({"name": "mystery", "family": "nobody-knows", "family_version": "1",
                        "runtimes": [{"name": "aws-mystery", "image_builder": "pckr-ebs-ans",
                                      "query": {"name": "mystery-*", "publisher": ["self"]}}]})
    _edit_os_builders(root, change)
    with pytest.raises(Exception, match="declare `type`"):
        load_context(root)
    reset_singletons()


def test_the_frozen_fixture_carries_the_trees_layer_and_nothing_else_changed():
    doc = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "image-sources.yml").read_text())
    assert [e["family"] for e in doc["image_sources"]] == ["debian", "rhel-from-fixture"]
