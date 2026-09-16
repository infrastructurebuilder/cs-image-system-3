# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""`name` is normalized (lowercased) for lookups; `display_name` preserves the
original human-entered casing/spacing for output."""
from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.models.root_item import RootItem


def test_name_typed_preserves_display_name():
    obj = NameTyped(name="My-Cool-Name", type_="Whatever")
    assert obj.name == "my-cool-name"            # normalized key for lookups
    assert obj.display_name == "My-Cool-Name"    # original preserved
    assert obj.get_display_name() == "My-Cool-Name"


def test_root_item_preserves_display_name_via_inheritance():
    r = RootItem(name="Foo Bar", type_="T")
    assert r.name == "foo_bar"                   # space -> _ and lowercased
    assert r.display_name == "Foo Bar"           # original preserved


def test_display_name_defaults_to_name_when_uncaptured():
    # An instance whose __post_init__ ran always has _display_name; the property
    # falls back to name only if it was never set.
    obj = NameTyped(name="abc", type_="t")
    del obj._display_name
    assert obj.display_name == "abc"
