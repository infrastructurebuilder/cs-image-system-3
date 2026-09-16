# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins block ordering when a source image is external to the run.

In an execution run, base images are never handed to the image builder (the
base run built them), so a chained image's source_image names an image absent
from the builder's items. The dependency graph must treat that source as an
external, already-satisfied dependency: the chained image becomes a block
root instead of erroring.
"""
from types import SimpleNamespace

from cs_image_system.packer_plugin.packer_ebs_builder import PackerEbsImageBuilder


def _stub_builder():
    stub = SimpleNamespace()
    for meth in ("fetch_image_dependency_graph", "fetch_work_list_order",
                 "order_blocks_from_images"):
        setattr(stub, meth, getattr(PackerEbsImageBuilder, meth).__get__(stub))
    return stub


def _image(name, source):
    return SimpleNamespace(get_name=lambda: name, source_image=source)


def test_external_source_becomes_block_root():
    b = _stub_builder()
    chained = _image("imgfile-basic", "basic-rhel-8")  # base image NOT in items
    derived = _image("imgfile-derived", "imgfile-basic")

    graph = b.fetch_image_dependency_graph([chained, derived])
    assert graph == {"imgfile-basic": set(),  # external dep omitted, no KeyError
                     "imgfile-derived": {"imgfile-basic"}}

    blocks, block_map = b.order_blocks_from_images([chained, derived])
    assert blocks == ["block-000", "block-001"]
    assert block_map["block-000"] == [chained]
    assert block_map["block-001"] == [derived]


def test_all_sources_external_single_block():
    b = _stub_builder()
    imgs = [_image("a", "basic-rhel-8"), _image("b", "basic-rhel-9")]
    blocks, block_map = b.order_blocks_from_images(imgs)
    assert blocks == ["block-000"]
    assert set(i.get_name() for i in block_map["block-000"]) == {"a", "b"}
