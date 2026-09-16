# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 33: encrypted configuration values.

A value anywhere in the tree may be ENC[age:<base64>]; a field declared
EncryptedStr decrypts it at load with the identity in CSIS_CONFIG_IDENTITY,
element by element for collections, and hides the plaintext in reprs. The
frozen fixture's rosters are encrypted with its committed TEST identity and
the golden is byte-identical -- proven by tests/test_v2_golden.py; these
tests pin the mechanism.
"""
from __future__ import annotations

from dataclasses import field

import pytest
from pydantic import ValidationError
from pydantic.dataclasses import dataclass

from cs_image_system.base.encryption import (
    IDENTITY_ENV,
    Decrypted,
    EncryptedStr,
    MissingIdentityError,
    decrypt_marker,
    encrypt_fields_in_text,
    encrypt_value,
    is_marker,
    rotate_text,
)
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from v2_support import FIXTURE_CONFIG, V2Run


def _keypair():
    from age.keys.agekey import AgePrivateKey
    k = AgePrivateKey.generate()
    return k, k.public_key().public_string()


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Model:
    email: EncryptedStr
    members: set[EncryptedStr] = field(default_factory=set)
    labels: dict[str, EncryptedStr] = field(default_factory=dict)
    plain: EncryptedStr = "untouched"


def test_marked_values_decrypt_element_by_element_and_hide_in_reprs(monkeypatch):
    k, pub = _keypair()
    monkeypatch.setenv(IDENTITY_ENV, k.private_string())
    m = _Model(email=encrypt_value("bob@example.com", [pub]),
               members={encrypt_value("alice", [pub]), "carol"},
               labels={"team": encrypt_value("coops", [pub]), "env": "test"})
    assert m.email == "bob@example.com" and isinstance(m.email, Decrypted)
    assert m.members == {"alice", "carol"} and m.labels == {"team": "coops", "env": "test"}
    assert repr(m.email) == "Decrypted('***')" and "bob@" not in repr(m)
    assert f"{m.email}" == "bob@example.com"                     # a str in every use
    assert m.plain == "untouched" and not isinstance(m.plain, Decrypted)


def test_a_marked_value_with_no_identity_is_refused_naming_the_variable(monkeypatch):
    _, pub = _keypair()
    monkeypatch.delenv(IDENTITY_ENV, raising=False)
    with pytest.raises(ValidationError, match=IDENTITY_ENV):
        _Model(email=encrypt_value("hidden@example.com", [pub]))
    with pytest.raises(MissingIdentityError):
        decrypt_marker(encrypt_value("x", [pub]))


def test_a_value_encrypted_to_someone_else_is_refused_without_the_plaintext(monkeypatch):
    mine, _ = _keypair()
    _, theirs = _keypair()
    monkeypatch.setenv(IDENTITY_ENV, mine.private_string())
    with pytest.raises(ValidationError) as ei:
        _Model(email=encrypt_value("hidden@example.com", [theirs]))
    assert "other recipients" in str(ei.value) and "hidden@" not in str(ei.value)


def test_the_identity_may_be_a_file_or_a_directory(monkeypatch, tmp_path):
    k, pub = _keypair()
    d = tmp_path / "age"; d.mkdir()
    (d / "me.age-identity").write_text(f"# public key: {pub}\n{k.private_string()}\n")
    marker = encrypt_value("v", [pub])
    monkeypatch.setenv(IDENTITY_ENV, str(d / "me.age-identity"))
    assert decrypt_marker(marker) == "v"
    monkeypatch.setenv(IDENTITY_ENV, str(d))
    assert decrypt_marker(marker) == "v"


def test_multiple_recipients_each_open_the_same_value(monkeypatch):
    a, pa = _keypair(); b, pb = _keypair(); c, _ = _keypair()
    marker = encrypt_value("shared", [pa, pb])
    assert is_marker(marker)
    for k in (a, b):
        monkeypatch.setenv(IDENTITY_ENV, k.private_string())
        assert decrypt_marker(marker) == "shared"
    monkeypatch.setenv(IDENTITY_ENV, c.private_string())
    with pytest.raises(ValueError, match="other recipients"):
        decrypt_marker(marker)


def test_encrypt_fields_in_text_is_textual_and_element_wise(monkeypatch):
    k, pub = _keypair()
    monkeypatch.setenv(IDENTITY_ENV, k.private_string())
    text = ("# keep this comment\n"
            "groups:\n"
            "  - name: x   # group name stays\n"
            "    members:\n"
            "      - alice\n"
            "      - 'bob'      # quoted\n"
            "    admins: []\n"
            "    description: \"{{ group.name }} group\"\n"
            "users:\n"
            "  - name: carol\n"
            "    email: carol@example.com\n")
    out, n = encrypt_fields_in_text(text, ["members", "email"], [pub])
    assert n == 3
    assert "# keep this comment" in out and "name: x   # group name stays" in out
    assert "admins: []" in out and "{{ group.name }}" in out          # flow list and template untouched
    assert "- alice" not in out and "carol@example.com" not in out
    markers = [l.split("- ", 1)[1].split("  #")[0] for l in out.splitlines() if l.strip().startswith("- ENC[")]
    assert [decrypt_marker(m) for m in markers] == ["alice", "bob"]
    assert "      # quoted" in out or "# quoted" in out                 # the trailing comment survives
    again, n2 = encrypt_fields_in_text(out, ["members", "email"], [pub])
    assert n2 == 0 and again == out                                     # already-marked values are left alone


def test_rotate_text_reencrypts_every_marker_to_the_new_recipients(monkeypatch):
    old, pold = _keypair(); new, pnew = _keypair()
    text = f"a: {encrypt_value('one', [pold])}\nb:\n  - {encrypt_value('two', [pold])}\n"
    out, n = rotate_text(text, [old], [pnew])
    assert n == 2
    monkeypatch.setenv(IDENTITY_ENV, new.private_string())
    vals = [decrypt_marker(t) for t in out.split() if t.startswith("ENC[")]
    assert vals == ["one", "two"]
    with pytest.raises(ValueError):                                     # the wrong identity opens nothing, returns nothing
        rotate_text(text, [new], [pnew])


def test_the_fixture_rosters_are_encrypted_and_load_to_the_same_people(tmp_path, monkeypatch):
    users = (FIXTURE_CONFIG / "groups" / "users.yaml").read_text()
    assert "ENC[age:" in users and "@" not in "".join(l for l in users.splitlines() if not l.strip().startswith("#"))
    run = V2Run(tmp_path, monkeypatch)                                  # stub_environment sets the fixture identity
    try:
        groups = {g.get_name(): g for g in run.ctx.groups}
        assert all(isinstance(m, Decrypted) for m in groups["stofs"].members)
        assert "avery.alpha" in groups["stofs"].members
        users_by_name = {u.get_name().lower(): u for u in run.ctx.users}   # names load to their safe form
        assert "blake.bravo" in users_by_name
        assert users_by_name["blake.bravo"].email == "Blake.Bravo@example.com"
        assert repr(users_by_name["blake.bravo"].email) == "Decrypted('***')"
    finally:
        run.restore_cwd()


def test_the_cli_encrypts_and_decrypts_against_the_configurations_recipients(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from cs_image_system.system.cli import app
    monkeypatch.setenv(IDENTITY_ENV, str(FIXTURE_CONFIG / ".age-identity"))
    r = CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "encrypt", "s3cret"])
    assert r.exit_code == 0, r.output
    marker = r.output.strip()
    assert is_marker(marker)
    r = CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "decrypt", marker])
    assert r.exit_code == 0 and r.output == "s3cret"
    # --file/--field over a copy: in place, then the same people load
    copy = tmp_path / "g.yaml"
    copy.write_text("groups:\n  - name: g\n    members:\n      - alice\n")
    r = CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "encrypt", "--file", str(copy), "--field", "members"])
    assert r.exit_code == 0, r.output
    assert "- alice" not in copy.read_text() and "ENC[age:" in copy.read_text()
