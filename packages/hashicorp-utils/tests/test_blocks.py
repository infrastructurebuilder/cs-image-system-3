# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the declarative resource/data block model (blocks.py)."""
from cs_image_system.hashicorp_utils.blocks import (
    DataSpec,
    Raw,
    ResourceSpec,
    render_block,
    render_blocks,
)


def test_resource_with_plain_and_raw_args():
    spec = ResourceSpec("oktapam_group", "devs", {
        "name": "devs",                       # plain string -> quoted
        "group": Raw("oktapam_group.root.name"),  # explicit raw address
        "source_var": "var.something",        # address prefix -> raw
        "count_hint": 3,                      # number -> raw
        "enabled": True,                      # bool -> lowercased by hcl2
    })
    hcl = "\n".join(render_block(spec))
    assert 'resource "oktapam_group" "devs" {' in hcl
    assert 'name = "devs"' in hcl
    assert "group = oktapam_group.root.name" in hcl
    assert "source_var = var.something" in hcl
    assert "count_hint = 3" in hcl
    assert "enabled = true" in hcl


def test_nested_children_render_recursively():
    spec = ResourceSpec("oktapam_security_policy", "pol", {"active": True})
    rule = spec.block("rule", name="allow_login")
    rule.block("conditions").block("gateway", traffic_forwarding=True)
    rule.block("privileges").block("principal_account_ssh", enabled=True)
    hcl = "\n".join(render_block(spec))
    assert "rule {" in hcl
    assert 'name = "allow_login"' in hcl
    assert "conditions {" in hcl and "gateway {" in hcl
    assert "traffic_forwarding = true" in hcl
    assert "privileges {" in hcl and "principal_account_ssh {" in hcl


def test_list_and_map_values():
    spec = ResourceSpec("t", "x", {
        "ids": [Raw("a.b.id"), "literal"],
        "labels": {'"system.os_type"': "linux"},
    })
    hcl = "\n".join(render_block(spec))
    assert "a.b.id" in hcl and '"literal"' in hcl
    assert '"system.os_type"' in hcl and '"linux"' in hcl


def test_commented_out_block_and_comment():
    spec = ResourceSpec("oktapam_user", "bob", {"name": "bob"},
                        comment="does not currently function",
                        commented_out=True)
    lines = render_block(spec)
    assert lines[0] == "# does not currently function"
    assert all(line.startswith("#") for line in lines if line.strip())


def test_data_block_kind_and_separator():
    specs = [DataSpec("oktapam_group", "g", {"name": "g"}),
             ResourceSpec("oktapam_group", "g2", {"name": "g2"})]
    lines = render_blocks(specs, separator="")
    hcl = "\n".join(lines)
    assert 'data "oktapam_group" "g" {' in hcl
    assert 'resource "oktapam_group" "g2" {' in hcl
    assert "" in lines  # separator between the two blocks
