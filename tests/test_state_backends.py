# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""State backends: what a backend declaration takes, refuses and renders.

* the S3 backend's optional arguments pass through when set and stay silent
  at their defaults; credential keys, a misspelt key and plugins are refused
  by name; a local backend's path has one spelling; an alias binds; a
  declared executable must exist; a decrypted setting renders as its
  ciphertext;
* ``use_state_backends: false`` is refused naming every root that reads a
  producer's state;
* the migration's previous-location file carries no record-only key.

History: stage 63 dead-code item 1, item 19 and low-hanging item 6.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from harness import copy_config, load_context, stub_environment


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _backend(data: dict, name: str) -> dict:
    return next(b for b in data["state_backends"] if b["name"] == name)


def _s3(**kw):
    from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import TofuS3StateBuilderModel
    return cast(Any, TofuS3StateBuilderModel)(name="s3-x", type="s3", bucket="b", key="k", **kw)


def test_s3_backend_arguments_pass_through_when_set_and_stay_silent_at_default():
    assert _s3().pass_through() == {}
    m = _s3(allowed_account_ids=["123456789012"], max_retries=9, skip_credentials_validation=True,
            shared_config_file="/etc/aws/config", no_proxy=["a", "b"],
            assume_role={"role_arn": "arn:aws:iam::1:role/r", "session_name": "csis"},
            endpoints={"s3": "https://s3.example.invalid"})
    got = m.pass_through()
    assert got == {"allowed_account_ids": ["123456789012"], "max_retries": 9,
                   "skip_credentials_validation": True, "shared_config_files": ["/etc/aws/config"],
                   "no_proxy": "a,b",
                   "assume_role": {"role_arn": "arn:aws:iam::1:role/r", "session_name": "csis"},
                   "endpoints": {"s3": "https://s3.example.invalid"}}, got
    reg = m.to_backend_registration()
    from cs_image_system.hashicorp_utils.collector import render_backend_value
    text = "\n".join(render_backend_value(v) for v in reg.backend_settings("ws").values())
    assert '{ role_arn = "arn:aws:iam::1:role/r", session_name = "csis" }' in text, text
    assert '["123456789012"]' in text and "9" in text
    assert reg.remote_state_settings("ws")["assume_role"]["role_arn"] == "arn:aws:iam::1:role/r"


@pytest.mark.parametrize("key, needle", [
    ("access_key", "credentials"),
    ("secret_key", "credentials"),
    ("skips_credentials_validation", "`skip_credentials_validation`"),
    ("required_plugins", "a state backend has no plugins"),
])
def test_refused_s3_keys_name_what_to_do(key, needle):
    with pytest.raises(Exception) as exc:
        _s3(**{key: "x" if key != "required_plugins" else []})
    assert needle in str(exc.value) and "s3-x" in str(exc.value), str(exc.value)


@pytest.mark.parametrize("path", ["a/../b", "./x/./y", "..", "/"])
def test_a_local_backend_path_has_one_spelling(path):
    from cs_image_system.local_state_plugin.local_state_models import LocalStateBuilderModel
    with pytest.raises(Exception) as exc:
        cast(Any, LocalStateBuilderModel)(name="loc", type="local", path=path)
    assert "loc" in str(exc.value)


def test_a_local_backend_path_that_is_fine_still_loads():
    from cs_image_system.local_state_plugin.local_state_models import LocalStateBuilderModel
    for path in ("state", "./state", "a/b/", "/var/lib/csis-state", ".", "./"):
        cast(Any, LocalStateBuilderModel)(name="loc", type="local", path=path)


def test_a_state_backend_alias_binds(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "state-backends-3.yml", lambda d: _backend(d, "local-dev").update(aliases=["on-disk"]))
    _edit(root / "cfg" / "group-builders.yml",
          lambda d: next(b for b in d["group_builders"] if b["name"] == "oktagroups").update(
              state_configuration="on-disk"))
    stub_environment(monkeypatch)
    ctx = load_context(root)
    from cs_image_system.hashicorp_utils.collector import terraform_collector
    from cs_image_system.tofu_roots.hooks import state_location_problems
    reg = terraform_collector(ctx).resolve_backend("on-disk")
    assert reg is not None and reg.name == "local-dev"
    errors = [str(e) for e in state_location_problems(ctx)]
    assert not any("not declared" in e for e in errors), errors


def test_a_state_backends_declared_executable_must_exist(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_state_backend_executables
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "state-backends-3.yml",
          lambda d: _backend(d, "local-dev").update(executable="no-such-tofu"))
    stub_environment(monkeypatch)
    ctx = load_context(root)
    errors = [str(e) for e in check_state_backend_executables(ctx)]
    assert len(errors) == 1 and "no-such-tofu" in errors[0] and "local-dev" in errors[0], errors


def test_a_decrypted_backend_setting_is_written_as_its_ciphertext():
    from cs_image_system.base.encryption import Decrypted
    from cs_image_system.hashicorp_utils.collector import render_backend_value
    value = Decrypted("plain-profile", marker="ENC[age:QUJD]")
    assert render_backend_value(value) == '"ENC[age:QUJD]"'


# -------------------------------------- use_state_backends with a producer

def _state_backend_errors(root: Path, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import collect_validation_errors
    stub_environment(monkeypatch)
    ctx = load_context(root)
    return [str(e) for e in collect_validation_errors(ctx) if "use_state_backends" in str(e)]


def _set_flag(root: Path, value: bool) -> None:
    cfg = root / "cfg" / "_config.yml"
    text = cfg.read_text()
    assert "use_state_backends: true" in text
    cfg.write_text(text.replace("use_state_backends: true", f"use_state_backends: {str(value).lower()}"))


def test_the_flag_off_is_refused_naming_every_root_that_reads_a_producer(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _set_flag(root, False)
    errors = _state_backend_errors(root, monkeypatch)
    assert errors, "the flag off loaded and validated with roots that read remote state"
    import re
    consumers = {re.search(r"the root '([^']+)'", e).group(1) for e in errors}   # type: ignore[union-attr]
    # every instance root reads the storage roots and the identity root; the
    # storage roots whose storages carry group gids read the identity root
    cfg = root / "cfg"
    instance_roots = {e["name"] for e in yaml.safe_load((cfg / "instance-builders.yml").read_text())["instance_builders"]}
    storage_roots = {e["name"] for e in yaml.safe_load((cfg / "storage-builders.yml").read_text())["storage_builders"]}
    assert instance_roots <= consumers <= instance_roots | storage_roots, errors
    assert {"aws-ebs", "aws-efs", "gcp-pd"} <= consumers, errors
    by_root = {re.search(r"the root '([^']+)'", e).group(1): e for e in errors}   # type: ignore[union-attr]
    assert "'oktagroups'" in by_root["aws-ebs"] and "'aws-ebs'" in by_root["open-tofu"]


def test_the_flag_on_raises_nothing(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    assert _state_backend_errors(root, monkeypatch) == []


# ------------------------------------ the migration's previous-location file

def test_the_previous_location_file_carries_no_record_only_key():
    from cs_image_system.base.commands.state_migration import RECORD_ONLY_KEYS, render_record
    record = {"backend": "s3-east1", "type": "s3", "run": "r0", "location": "s3://old/statefiles/ws.tfstate",
              "bucket": "old", "key": "statefiles", "region": "us-east-1", "encrypt": True}
    lines = render_record(record, "# previous")
    assert lines == ["# previous", 'bucket = "old"', 'key = "statefiles"', 'region = "us-east-1"', "encrypt = true"], lines
    assert "location" in RECORD_ONLY_KEYS

