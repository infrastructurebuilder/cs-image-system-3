# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 34: sensitive values never enter the emission.

A value the configuration carries encrypted (stage 33) is emitted as the SAME
``ENC[age:...]`` ciphertext, referenced through one ``data "external"`` per
root whose program is ``cs-image-system decrypt --json``; a run never stages a
plan, state or key file under ``--commit``. The rule (decided 2026-09-15): no
declared-encrypted value other than a username appears in plaintext in the
emission or the meta-state; an address DERIVED from the email template is
public by construction (username + template) and stays plaintext.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any

import pytest

from cs_image_system.base.encryption import Decrypted, decrypt_marker, encrypt_value
from cs_image_system.base.meta_state import commit_meta_state, never_staged
from cs_image_system.base.models.user import User
from cs_image_system.hashicorp_utils.blocks import Raw
from cs_image_system.hashicorp_utils.collector import TerraformCollector
from v2_support import FIXTURE_CONFIG, V2Run, tree

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MARKER = re.compile(r"ENC\[age:[A-Za-z0-9+/=]+\]")
RECIPIENT = (FIXTURE_CONFIG / ".age-recipient").read_text().strip()


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(FIXTURE_CONFIG / ".age-identity"))
    TerraformCollector().reset()
    yield
    TerraformCollector().reset()


def _user(**over: Any) -> User:
    base: dict[str, Any] = dict(name="pat.trip", first_name="Pat", last_name="Trip")
    base.update(over)
    return User(**base)


def test_a_decrypted_value_remembers_its_ciphertext():
    marker = encrypt_value("pat.trip@example.org", [RECIPIENT])
    u = _user(email=marker)
    assert isinstance(u.email, Decrypted) and u.email == "pat.trip@example.org"
    assert u.email.marker == marker
    assert repr(u.email) == "Decrypted('***')"
    assert not getattr(u.first_name, "marker", "")          # a plain value carries none


def test_the_collector_emits_a_decrypted_value_as_a_reference_to_its_ciphertext():
    col = TerraformCollector()
    marker = encrypt_value("secret", [RECIPIENT])
    ref = col.sensitive_ref("ws", "email_pat_trip", Decrypted("secret", marker))
    assert isinstance(ref, Raw) and ref == 'local.sensitive["email_pat_trip"]'
    assert col.sensitive_ref("ws", "login_x", "plain") == "plain"    # untouched, unregistered
    assert col.sensitive_values("ws") == {"email_pat_trip": marker}
    assert any(p.name == "external" for p in col.merged_providers("ws"))
    text = "\n".join(col.generate_sensitive_blocks("ws"))
    assert 'data "external" "sensitive"' in text and '"cs-image-system"' in text and '"--json"' in text
    assert f'email_pat_trip = "{marker}"' in text
    assert "sensitive = sensitive(data.external.sensitive.result)" in text
    assert "secret" not in text.replace('"sensitive"', "").replace("sensitive", "")
    assert col.generate_sensitive_blocks("other") == []


def test_the_user_lookup_reads_a_declared_email_by_reference_and_a_plain_one_as_a_literal():
    from cs_image_system.okta_opa_plugin.okta_tf_models import OktaTFUser
    col = TerraformCollector()
    marker = encrypt_value("pat.trip@example.org", [RECIPIENT])
    sensitive = lambda key, value: col.sensitive_ref("ws", key, value)   # noqa: E731
    declared = "\n".join(OktaTFUser(_user(email=marker), lookup_depends_on=False, sensitive=sensitive)
                         .generate_terraform_data())
    assert 'value = local.sensitive["email_pat_trip"]' in declared
    assert "pat.trip@example.org" not in declared
    managed = "\n".join(OktaTFUser(_user(email=marker), sensitive=sensitive).generate_terraform())
    assert 'login = local.sensitive["email_pat_trip"]' in managed
    assert 'email = local.sensitive["email_pat_trip"]' in managed
    assert 'first_name = "Pat"' in managed                     # plain stays plain
    assert col.sensitive_values("ws") == {"email_pat_trip": marker}   # one value, both uses
    literal = "\n".join(OktaTFUser(_user(email="pat.trip@example.org"), lookup_depends_on=False,
                                   sensitive=sensitive).generate_terraform_data())
    assert 'value = "pat.trip@example.org"' in literal


def test_a_declared_encrypted_workspace_credential_reaches_the_provider_block_by_reference(monkeypatch):
    from cs_image_system.hashicorp_utils.collector import ConfiguredTerraformProvider
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupBuilderModel
    from cs_image_system.okta_opa_plugin.okta_tf_models import OKTATF
    from cs_image_system.okta_opa_plugin.okta_tf_workspace import OKTAPAM_PROVIDER
    monkeypatch.delenv("TF_VAR_team_key", raising=False)
    monkeypatch.setenv("TF_VAR_team_secret", "s")                    # the secret stays environment-side
    key = encrypt_value("real-key", [RECIPIENT])
    ws = OktaTfGroupBuilderModel(type_=OKTATF, name="ws", org="o", team="team", key=key, required_providers=[
        ConfiguredTerraformProvider(name=OKTAPAM_PROVIDER, source="okta/oktapam", version=">= 0.4")])
    ws.finalize()
    cfg = ws.transform_provider(ws.required_providers[0], "ws").config
    assert str(cfg["oktapam_key"]) == 'local.sensitive["oktapam_key"]'
    assert str(cfg["oktapam_secret"]) == "var.team_secret"
    assert "real-key" not in "\n".join(TerraformCollector().generate_sensitive_blocks("ws"))
    assert TerraformCollector().sensitive_values("ws") == {"oktapam_key": key}


def test_decrypt_json_speaks_the_external_data_source_protocol():
    from typer.testing import CliRunner
    from cs_image_system.system.cli import app
    m1, m2 = encrypt_value("one@example.org", [RECIPIENT]), encrypt_value("two", [RECIPIENT])
    query = json.dumps({"email_a": m1, "b": m2, "plain": "left alone"})
    r = CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "decrypt", "--json"], input=query)
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == {"b": "two", "email_a": "one@example.org", "plain": "left alone"}
    bad = CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "decrypt", "--json"], input="[1]")
    assert bad.exit_code == 1 and "JSON object" in bad.output
    none = CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "decrypt"])
    assert none.exit_code == 1 and "marker is required" in none.output


def test_the_fixture_emission_carries_only_ciphertexts_the_configuration_carries(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run("identity", apply=True).ok
        emitted = tree(run.generated)
        users_tf = next(v for k, v in emitted.items() if k.endswith("users-data.tf"))
        root_tf = next(v for k, v in emitted.items() if k.endswith("okta-tf-users-user-generation.tf"))
    finally:
        run.restore_cwd()
    source = (FIXTURE_CONFIG / "groups" / "users.yaml").read_text()
    declared = {m for m in MARKER.findall(source)}
    emitted_markers = set(MARKER.findall(users_tf)) | set(MARKER.findall(root_tf))
    assert emitted_markers and emitted_markers <= declared, "the emission carries the SAME ciphertexts as the YAML"
    # every declared email is read by reference and its text is not in the emission
    declared_emails = [decrypt_marker(m) for m in re.findall(r"^\s+email:\s*(ENC\[age:[^\]]+\])", source, re.M)]
    assert len(declared_emails) == 10
    all_text = "\n".join(emitted.values())
    for email in declared_emails:
        assert email not in all_text
    assert users_tf.count('value = local.sensitive["email_') == 10
    assert 'data "external" "sensitive"' in root_tf and re.search(r'source\s*=\s*"hashicorp/external"', root_tf)


def test_no_declared_encrypted_value_but_a_username_reaches_the_emission_or_meta_state_in_clear(tmp_path, monkeypatch):
    """The stage's rule over the whole fixture run: every ciphertext in the
    rosters is decrypted and its text looked for in generated/ and
    meta-state/; usernames are public (the 2026-08-25 ruling) and exempt."""
    import yaml
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run("all", apply=True).ok
        emitted = "\n".join(tree(run.generated).values()) + "\n" + "\n".join(tree(run.meta_state).values())
    finally:
        run.restore_cwd()
    hidden: set[str] = set()
    for path in (FIXTURE_CONFIG / "groups").glob("*.y*ml"):
        doc = yaml.safe_load(path.read_text()) or {}
        for user in doc.get("users") or []:
            for field_name in ("first_name", "last_name", "email"):
                v = user.get(field_name)
                if isinstance(v, str) and MARKER.fullmatch(v):
                    hidden.add(decrypt_marker(v))
    assert len(hidden) >= 30, "the fixture declares encrypted names and emails"
    # whole tokens only: a last name is a part of the public username
    # (`avery.alpha`, label `avery_alpha`), which is not the declared value
    def in_clear(value: str) -> bool:
        return re.search(rf"(?<![\w.@-]){re.escape(value)}(?![\w.@-])", emitted) is not None
    # a one- or two-letter value (an initial) matches the world; not evidence
    leaked = sorted(v for v in hidden if len(v) >= 3 and in_clear(v))
    assert leaked == [], f"declared-encrypted values in clear: {leaked}"
    assert not EMAIL.search("\n".join(tree(run.meta_state).values())), "meta-state rosters are usernames only"


@pytest.mark.parametrize("path,refused", [
    ("generated/identity/x/tfplan", True), ("generated/a/b/terraform.tfstate", True),
    ("generated/a/terraform.tfstate.backup", True), ("generated/a/prod.tfvars", True),
    (".envrc", True), ("cfg/.private_key.pem", True), ("cfg/.public_key.json", True),
    ("generated/identity/x/x.tf", False), ("meta-state/identity.yaml", False),
    ("generated/a/.terraform.lock.hcl", False), ("generated/a/x.tfbackend.hcl", False),
])
def test_the_never_staged_list(path, refused):
    assert never_staged(path) is refused


def test_a_run_commit_never_stages_a_plan_or_state_file(tmp_path, caplog):
    repo = tmp_path / "cfg"
    (repo / "meta-state").mkdir(parents=True)
    root_dir = repo / "generated" / "identity" / "ws"
    root_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.org"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "meta-state" / "identity.yaml").write_text("groups: {}\n")
    (root_dir / "main.tf").write_text('locals { x = local.sensitive["email_a"] }\n')
    (root_dir / "tfplan").write_bytes(b"PK\x03\x04 a zipped plan holding decrypted values")
    (root_dir / "terraform.tfstate").write_text('{"decrypted": "pat.trip@example.org"}\n')
    sha = commit_meta_state(repo, repo / "generated", "run1", ["identity"], dry_run=True)
    assert sha
    committed = subprocess.run(["git", "-C", str(repo), "show", "--name-only", "--format=", "HEAD"],
                               check=True, capture_output=True, text=True).stdout.split()
    assert "generated/identity/ws/main.tf" in committed and "meta-state/identity.yaml" in committed
    assert not any(never_staged(p) for p in committed)
    assert (root_dir / "tfplan").exists() and (root_dir / "terraform.tfstate").exists()   # untouched on disk
    staged = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--name-only"],
                            check=True, capture_output=True, text=True).stdout.split()
    assert staged == []                                                                    # and not left in the index
    assert "never staging" in caplog.text and "tfplan" in caplog.text
