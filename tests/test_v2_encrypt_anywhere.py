# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 49: any value may be an ``ENC[age:…]`` marker, the emission carries
the ciphertext, and the execution materialises it into a private mirror.

The load side is proven here against the fixture's own test identity; the
emission side (``emit``) and the mirror (``materialize``) are proven by
round-tripping a generated artifact. The whole-tree invariant -- no plaintext
of any marker anywhere under ``generated/`` or ``meta-state/`` -- is in
``test_v2_emit_by_reference.py``, which is where the stage-34 rule already
lived.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base.encryption import (
    Decrypted, EncryptedKeyError, InlineMarkerError, MissingIdentityError,
    decrypt_tree, decrypted_plaintexts, emit, encrypt_value, like,
    refuse_markers_at, reset_decrypted_plaintexts, substitute_markers,
)
from cs_image_system.base.materialize import PRIVATE_DIRNAME, materialize, mirror_path
from cs_image_system.base.public_safe import refused_path, scan_for_plaintexts

from v2_support import FIXTURE_CONFIG

IDENTITY = FIXTURE_CONFIG / ".age-identity"
RECIPIENT = (FIXTURE_CONFIG / ".age-recipient").read_text().strip()


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(IDENTITY))
    reset_decrypted_plaintexts()
    yield
    reset_decrypted_plaintexts()


def enc(text: str) -> str:
    return encrypt_value(text, [RECIPIENT])


# ------------------------------------------------------------------ the walk

def test_a_marker_decrypts_wherever_it_stands_and_keeps_its_ciphertext():
    """The point of the stage: no field needs to be typed EncryptedStr."""
    marker = enc("s3://a-bucket")
    out = decrypt_tree({"config": {"module_source_base": marker},
                        "runtime_builders": [{"name": "aws", "type": "aws", "region": enc("us-east-1")}]})
    value = out["config"]["module_source_base"]
    assert value == "s3://a-bucket"
    assert isinstance(value, Decrypted) and value.marker == marker
    assert out["runtime_builders"][0]["region"] == "us-east-1"
    # a plain value is untouched and carries no ciphertext
    assert out["runtime_builders"][0]["name"] == "aws"
    assert not hasattr(out["runtime_builders"][0]["name"], "marker")


def test_the_repr_of_a_decrypted_value_never_shows_it():
    out = decrypt_tree({"k": enc("hunter2")})
    assert repr(out["k"]) == "Decrypted('***')"
    assert "hunter2" not in repr(out)


def test_the_walk_records_what_it_opened():
    decrypt_tree({"a": enc("alpha"), "b": {"c": [enc("bravo")]}})
    assert decrypted_plaintexts() == {"alpha", "bravo"}


def test_a_tree_with_no_markers_loads_with_no_identity(monkeypatch):
    """Identities are resolved lazily, so an unencrypted tree needs none."""
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    assert decrypt_tree({"a": "plain", "b": [1, 2]}) == {"a": "plain", "b": [1, 2]}


def test_any_marker_anywhere_refuses_the_load_naming_its_path(monkeypatch):
    marker = enc("secret")
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    with pytest.raises(MissingIdentityError) as ei:
        decrypt_tree({"users": [{"name": "a"}, {"name": marker}]}, source="groups/users.yaml")
    message = str(ei.value)
    assert "users[1].name" in message and "CSIS_CONFIG_IDENTITY" in message
    assert "secret" not in message


def test_a_marker_as_a_mapping_key_is_refused():
    with pytest.raises(EncryptedKeyError):
        decrypt_tree({"config": {enc("k"): "v"}})


def test_an_embedded_marker_is_refused_naming_the_path():
    with pytest.raises(InlineMarkerError) as ei:
        decrypt_tree({"bucket": f"prefix-{enc('x')}-suffix"})
    assert "bucket" in str(ei.value) and "ENTIRE value" in str(ei.value)


def test_the_walk_is_idempotent():
    once = decrypt_tree({"a": enc("alpha")})
    twice = decrypt_tree(once)
    assert twice["a"] == "alpha" and twice["a"].marker == once["a"].marker


# ------------------------------------------------------------ the exemptions

@pytest.mark.parametrize("doc, needle", [
    ({"encryption": {"recipients": ["ENC[age:AAAA]"]}}, "encryption.recipients"),
    ({"public_safe": {"allow": ["ENC[age:AAAA]"]}}, "public_safe.allow"),
    ({"runtime_builders": [{"name": "aws", "type": "aws", "profile": "ENC[age:AAAA]"}]}, "profile"),
    ({"config": {"apply_instances": "ENC[age:AAAA]"}}, "config.apply_instances"),
])
def test_a_key_the_raw_readers_consume_may_not_be_encrypted(doc, needle, monkeypatch):
    """And the check needs NO identity: those readers run before the load."""
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    with pytest.raises(ValueError) as ei:
        refuse_markers_at(doc, "cfg/_config.yml")
    assert needle in str(ei.value)


def test_a_declarations_name_and_type_may_not_be_encrypted():
    for key in ("name", "type"):
        with pytest.raises(ValueError, match=key):
            refuse_markers_at({"storage_builders": [{key: "ENC[age:AAAA]"}]}, "cfg/x.yml")


def test_an_ordinary_value_in_a_declaration_is_allowed():
    refuse_markers_at({"storage_builders": [{"name": "s", "type": "t", "bucket": "ENC[age:AAAA]"}]}, "cfg/x.yml")


# -------------------------------------------------------------- the emission

def test_emit_writes_the_ciphertext_for_a_decrypted_value_and_the_value_otherwise():
    marker = enc("ssh-ed25519 AAAA test@host")
    opened = decrypt_tree({"k": marker})["k"]
    assert emit(opened) == marker
    assert emit("plain") == "plain"


def test_like_carries_the_ciphertext_across_a_reshape():
    """capabilities strips admin keys; str()/strip() would drop the marker."""
    marker = enc("  ssh-ed25519 AAAA test@host  ")
    opened = decrypt_tree({"k": marker})["k"]
    stripped = like(opened, str(opened).strip())
    assert stripped == "ssh-ed25519 AAAA test@host"
    assert isinstance(stripped, Decrypted) and stripped.marker == marker


def test_hcl_value_emits_the_ciphertext():
    from cs_image_system.hashicorp_utils.blocks import hcl_value
    marker = enc("s3://secret-bucket")
    opened = decrypt_tree({"k": marker})["k"]
    assert str(hcl_value(opened).value) == marker
    assert "secret-bucket" not in str(hcl_value(opened).value)


def test_the_admin_key_provisioner_carries_the_ciphertext():
    from cs_image_system.packer_plugin.v2_provisioners import admin_user_commands
    marker = enc("ssh-ed25519 AAAAsecretbody operator@host")
    opened = decrypt_tree({"k": marker})["k"]
    lines = "\n".join(admin_user_commands("csisadmin", [opened]))
    assert marker in lines
    assert "AAAAsecretbody" not in lines


# ---------------------------------------------------------------- the mirror

def test_materialize_substitutes_the_plaintext_into_a_private_copy(tmp_path):
    marker = enc("ssh-ed25519 AAAAbody operator@host")
    decrypt_tree({"k": marker})            # so the map knows it
    src = tmp_path / "generated" / "base-image" / "block-000"
    src.mkdir(parents=True)
    (src / "build.pkr.hcl").write_text(f"inline = [\"echo '{marker}' | sudo tee -a keys\"]\n")
    (src / "note.txt").write_text("no ciphertext here\n")

    dst = mirror_path(tmp_path, src)
    written, substituted = materialize(src, dst)

    assert (written, substituted) == (2, 1)
    assert dst == tmp_path / PRIVATE_DIRNAME / "generated" / "base-image" / "block-000"
    built = (dst / "build.pkr.hcl").read_text()
    assert "ssh-ed25519 AAAAbody operator@host" in built and "ENC[age:" not in built
    # the committed copy is untouched
    assert marker in (src / "build.pkr.hcl").read_text()


def test_the_mirror_sits_beside_generated_so_local_state_paths_still_resolve(tmp_path):
    """ROOT_DEPTH counts directories from the root; a deeper mirror would
    point every local-state root at nothing."""
    src = tmp_path / "generated" / "identity" / "ws" / "phase"
    src.mkdir(parents=True)
    mirror = mirror_path(tmp_path, src)
    assert mirror.relative_to(tmp_path).parts[0] == PRIVATE_DIRNAME
    assert mirror.relative_to(tmp_path / PRIVATE_DIRNAME) == src.relative_to(tmp_path)


def test_materializing_the_mirror_is_a_no_op(tmp_path):
    src = tmp_path / PRIVATE_DIRNAME / "generated" / "x"
    src.mkdir(parents=True)
    assert mirror_path(tmp_path, src) == src


def test_the_mirror_is_never_committed():
    assert refused_path(Path("_private/generated/identity/main.tf"))
    assert refused_path(Path("a/b/_private/x.tf"))
    assert not refused_path(Path("generated/identity/main.tf"))


def test_substitute_markers_uses_what_the_walk_opened(monkeypatch):
    marker = enc("the-value")
    decrypt_tree({"k": marker})
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)   # no second decrypt needed
    assert substitute_markers(f"x={marker};") == "x=the-value;"


# ----------------------------------------------------------------- the guard

def test_the_guard_finds_a_decrypted_value_standing_in_clear(tmp_path):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "main.tf").write_text('key = "ssh-ed25519 AAAAbody op@host"\n')
    findings = scan_for_plaintexts(tmp_path, {"ssh-ed25519 AAAAbody op@host"})
    assert len(findings) == 1
    assert findings[0].path == "generated/main.tf:1"
    assert "AAAAbody" not in str(findings[0])          # the finding never shows the value


def test_the_guard_matches_whole_tokens_only(tmp_path):
    """A last name is part of the public username, which is emitted by
    decision; a bare substring test would refuse it."""
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "users.tf").write_text('login = "blake.bravo"\n')
    assert scan_for_plaintexts(tmp_path, {"bravo"}) == []
    assert scan_for_plaintexts(tmp_path, {"blake.bravo"}) != []


def test_the_guard_skips_short_values_and_the_mirror(tmp_path):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "a.tf").write_text('x = "ab"\n')
    assert scan_for_plaintexts(tmp_path, {"ab"}) == []
    private = tmp_path / PRIVATE_DIRNAME / "generated"
    private.mkdir(parents=True)
    (private / "a.tf").write_text('x = "the-plaintext"\n')
    assert scan_for_plaintexts(tmp_path, {"the-plaintext"}) == []


def test_materialize_is_incremental_so_a_plan_survives_between_commands(tmp_path):
    """A terraform root is materialised again before each of its commands, so
    wiping the mirror would destroy the tfplan that `plan` wrote before
    `apply` could read it -- and .terraform/ between init and plan."""
    src = tmp_path / "generated" / "identity" / "ws"
    src.mkdir(parents=True)
    (src / "main.tf").write_text('x = "1"\n')
    dst = mirror_path(tmp_path, src)
    materialize(src, dst)

    # what the tools write in the mirror
    (dst / "tfplan").write_bytes(b"\x00plan")
    (dst / ".terraform").mkdir()
    (dst / ".terraform" / "providers").write_text("cached\n")

    materialize(src, dst)

    assert (dst / "tfplan").read_bytes() == b"\x00plan"
    assert (dst / ".terraform" / "providers").read_text() == "cached\n"


def test_materialize_drops_what_the_emission_dropped(tmp_path):
    src = tmp_path / "generated" / "ws"
    src.mkdir(parents=True)
    (src / "a.tf").write_text("a\n")
    (src / "b.tf").write_text("b\n")
    dst = mirror_path(tmp_path, src)
    materialize(src, dst)
    (src / "b.tf").unlink()
    materialize(src, dst)
    assert (dst / "a.tf").is_file() and not (dst / "b.tf").exists()


def test_the_provider_lock_file_comes_back_out_and_nothing_else(tmp_path):
    """`init` runs in the mirror now, and the lock file is a COMMITTED
    artifact; a plan or a state file holds plaintext and stays put."""
    from cs_image_system.base.materialize import sync_back
    src = tmp_path / "generated" / "ws"
    src.mkdir(parents=True)
    (src / "main.tf").write_text('x = "1"\n')
    dst = mirror_path(tmp_path, src)
    materialize(src, dst)
    (dst / ".terraform.lock.hcl").write_text('provider "x" { hashes = ["h1:abc"] }\n')
    (dst / "tfplan").write_text("secrets\n")
    (dst / "terraform.tfstate").write_text("secrets\n")

    moved = sync_back(src, dst)

    assert moved == [".terraform.lock.hcl"]
    assert (src / ".terraform.lock.hcl").is_file()
    assert not (src / "tfplan").exists() and not (src / "terraform.tfstate").exists()
    assert sync_back(src, dst) == [], "an unchanged lock file is not copied again"


# -------------------------------------------- derived values (stage 51)

def test_a_derived_value_inherits_its_inputs_encryption():
    """The stage-51 rule: a value computed from a decrypted one is declared
    nowhere, so its ciphertext is built from the pieces."""
    from types import SimpleNamespace
    from cs_image_system.base.orchestrator import TemplateResolver
    domain = enc("noaa.example")
    decrypt_tree({"email_domain": domain})          # so the map knows it
    ctx = {"user": SimpleNamespace(name="blake.bravo"),
           "builder": SimpleNamespace(domain="noaa.example")}
    out = TemplateResolver().render_inheriting("{{ user.name }}@{{ builder.domain }}", ctx)
    assert out == "blake.bravo@noaa.example"
    assert isinstance(out, Decrypted)
    assert out.marker == f"blake.bravo@{domain}"


def test_a_render_with_no_encrypted_input_stays_a_plain_string():
    from cs_image_system.base.orchestrator import TemplateResolver
    decrypt_tree({"k": enc("something-else")})
    out = TemplateResolver().render_inheriting("{{ a }}-suffix", {"a": "plain"})
    assert out == "plain-suffix" and not isinstance(out, Decrypted)


def test_a_username_is_public_by_decision_and_is_not_marked_in_a_derived_value():
    """A username is the join key between a roster and an access grant, so it
    is emitted in clear -- the stage-34 decision, kept."""
    from cs_image_system.base.orchestrator import TemplateResolver
    name = enc("blake.bravo")
    domain = enc("noaa.example")
    decrypt_tree({"users": [{"name": name}], "email_domain": domain})
    out = TemplateResolver().render_inheriting(
        "{{ a }}@{{ b }}", {"a": "blake.bravo", "b": "noaa.example"})
    assert out.marker == f"blake.bravo@{domain}", "the username stays in clear, the domain does not"


def test_decrypt_file_is_the_inverse_of_encrypt_file(tmp_path):
    from cs_image_system.base.encryption import decrypt_fields_in_text, encrypt_fields_in_text
    original = ("users:\n"
                "  - name: avery.alpha        # a comment\n"
                "    first_name: Avery\n"
                "    last_name: Alpha\n"
                "  # - name: commented.out\n")
    encrypted, n = encrypt_fields_in_text(original, ["first_name", "last_name"], [RECIPIENT])
    assert n == 2 and "Avery" not in encrypted and "ENC[age:" in encrypted
    back, m = decrypt_fields_in_text(encrypted, ["first_name", "last_name"])
    assert m == 2
    assert back == original, "comments, ordering and every other byte survive the round trip"


def test_the_fixture_hides_the_domain_and_not_the_names():
    import yaml
    builders = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "group-builders.yml").read_text())
    ub = next(b for b in builders["user_builders"] if b.get("email_domain"))
    assert is_marker_str(ub["email_domain"]), "the domain is encrypted"
    assert ub["default_user_email_template"].endswith("@{{ builder.email_domain }}")
    users = yaml.safe_load((FIXTURE_CONFIG / "groups" / "users.yaml").read_text())
    names = [u["first_name"] for u in users["users"] if "first_name" in u]
    assert names and not any(is_marker_str(n) for n in names), "first names stand in clear"


def is_marker_str(v) -> bool:
    from cs_image_system.base.encryption import is_marker
    return is_marker(v)


# ----------------------------------------- meta-state records (stage 50)

def test_a_record_carries_the_ciphertext_it_was_written_from(tmp_path):
    """A meta-state write says what it READ, so a record and the configuration
    hold the same marker and a rotation moves both together."""
    from cs_image_system.base.meta_state import MetaState
    marker = enc("a-private-bucket")
    value = decrypt_tree({"bucket": marker})["bucket"]

    ms = MetaState.at(tmp_path)
    ms.write("storage.yaml", {"storages": {"s1": {"bucket": value}}})

    on_disk = (tmp_path / "meta-state" / "storage.yaml").read_text()
    assert marker in on_disk and "a-private-bucket" not in on_disk


def test_a_username_is_recorded_in_clear():
    """The read-model's rosters are the join key between a roster and an
    access grant; ciphertext there would defeat the file's purpose."""
    import yaml
    name = enc("blake.bravo")
    value = decrypt_tree({"groups": [{"members": [name]}]})["groups"][0]["members"][0]
    assert yaml.safe_dump({"members": [value]}).strip() == "members:\n- blake.bravo"


def test_a_record_is_read_back_as_its_plaintext(tmp_path):
    """So a recorded-vs-declared comparison is between plaintexts: two markers
    for one value differ after a rotation, and comparing those would report
    drift that is not there."""
    from cs_image_system.base.meta_state import MetaState
    marker = enc("a-private-bucket")
    value = decrypt_tree({"bucket": marker})["bucket"]

    ms = MetaState.at(tmp_path)
    ms.write("storage.yaml", {"storages": {"s1": {"bucket": value}}})
    ms.invalidate()
    read_back = ms.read("storage.yaml")["storages"]["s1"]["bucket"]

    assert read_back == "a-private-bucket"
    assert isinstance(read_back, Decrypted)
    assert read_back.marker == marker, "and it still knows its ciphertext"


def test_a_record_with_no_markers_needs_no_identity(tmp_path, monkeypatch):
    from cs_image_system.base.meta_state import MetaState
    ms = MetaState.at(tmp_path)
    ms.write("pins.yaml", {"pins": {"i1": "ami-0123"}})
    ms.invalidate()
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    assert ms.read("pins.yaml")["pins"]["i1"] == "ami-0123"
