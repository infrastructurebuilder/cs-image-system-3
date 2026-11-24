# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Sensitive values never enter the emission.

A value the configuration carries encrypted is emitted as the SAME
``ENC[age:...]`` ciphertext, referenced through one ``data "external"`` per
root whose program is ``cs-image-system decrypt --json``; a run never stages a
plan, state or key file under ``--commit``. The rule: no
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
from harness import FIXTURE_CONFIG, FixtureRun, tree

from cs_image_system.base.encryption import PUBLIC_BY_DECISION_KEYS, Decrypted, decrypt_marker, encrypt_value
from cs_image_system.base.models.user import User
from cs_image_system.engine.materialize import PRIVATE_DIRNAME
from cs_image_system.engine.meta_state import commit_meta_state
from cs_image_system.engine.public_safe import refused_path
from cs_image_system.hashicorp_utils.blocks import Raw
from cs_image_system.hashicorp_utils.collector import TerraformCollector

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MARKER = re.compile(r"ENC\[age:[A-Za-z0-9+/=]+\]")
RECIPIENT = (FIXTURE_CONFIG / ".age-recipient").read_text().strip()


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(FIXTURE_CONFIG / ".age-identity"))


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


def test_the_base_image_emission_carries_the_admin_keys_ciphertext_and_never_the_key(tmp_path, monkeypatch):
    """The same rule on another root, the packer builds: the admin public
    key is declared encrypted in cfg/_config.yml, so the emission carries
    that SAME ciphertext (`materialize` puts the key itself in the private
    copy packer builds from), and neither the key nor its body is in clear."""
    import yaml
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        assert run.run(["base-image"], apply=False).ok
        emitted = tree(run.generated / "base-image")
    finally:
        run.restore_cwd()
    builds = "\n".join(v for k, v in emitted.items() if k.endswith(".pkr.hcl"))
    assert builds, "the base-image lifecycle emitted packer builds"
    declared = {m for f in FIXTURE_CONFIG.rglob("*.y*ml") if "generated" not in f.parts
                for m in MARKER.findall(f.read_text())}
    emitted_markers = set(MARKER.findall(builds))
    assert emitted_markers and emitted_markers <= declared, "the emission carries the SAME ciphertexts as the YAML"
    config = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "_config.yml").read_text())["config"]
    [key_marker] = config["admin_public_keys"]
    assert key_marker in emitted_markers, "the admin key is read by reference"
    key = decrypt_marker(key_marker)
    body = key.split()[1]
    all_text = "\n".join(emitted.values())
    assert key not in all_text and body not in all_text, "the admin key in clear"


def test_no_declared_encrypted_value_but_a_username_reaches_the_emission_or_meta_state_in_clear(tmp_path, monkeypatch):
    """The stage's rule over the whole fixture run: every ciphertext in the
    rosters is decrypted and its text looked for in generated/ and
    meta-state/; usernames are public by ruling and exempt."""
    import yaml
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        assert run.run("all", apply=True).ok
        emitted = "\n".join(tree(run.generated).values()) + "\n" + "\n".join(tree(run.meta_state).values())
    finally:
        run.restore_cwd()
    # EVERY marker in EVERY file under the root, not three fields of
    # one directory -- the feature's scope is "anywhere", so the guard's must
    # be too, or it drifts from the feature by construction. A value read only
    # under a public-by-decision key (a username) stays exempt.
    hidden: set[str] = set()
    public_by_decision: set[str] = set()
    for path in sorted(FIXTURE_CONFIG.rglob("*.y*ml")):
        if "generated" in path.parts or PRIVATE_DIRNAME in path.parts:
            continue
        def walk(node, key=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, str(k))
            elif isinstance(node, list):
                for v in node:
                    walk(v, key)
            elif isinstance(node, str) and MARKER.fullmatch(node):
                (public_by_decision if key in PUBLIC_BY_DECISION_KEYS else hidden).add(decrypt_marker(node))
        walk(yaml.safe_load(path.read_text()) or {})
    hidden -= public_by_decision       # a username also declared elsewhere is still public
    # the fixture hides the ten explicit addresses, not the first and last
    # names: encrypting those bought nothing (its posix user builders derive
    # no address, so no domain is declared to hide)
    assert len(hidden) >= 10, "the fixture declares encrypted addresses"
    assert len([v for v in hidden if EMAIL.fullmatch(v)]) == 10, "the explicit addresses are hidden"
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
    assert refused_path(path) is refused


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
    assert not any(refused_path(p) for p in committed)
    assert (root_dir / "tfplan").exists() and (root_dir / "terraform.tfstate").exists()   # untouched on disk
    staged = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--name-only"],
                            check=True, capture_output=True, text=True).stdout.split()
    assert staged == []                                                                    # and not left in the index
    assert "never staging" in caplog.text and "tfplan" in caplog.text
