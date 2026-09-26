# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the dead fields, dead code and misleading messages (decided by
the operator field by field, 2026-09-25). One section per package bullet;
every test here failed before its fix.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config, load_context, reset_singletons, stub_environment


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _backend(data: dict, name: str) -> dict:
    return next(b for b in data["state_backends"] if b["name"] == name)


# ------------------------------------------------------ 1. state backends

def _s3(**kw):
    from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import TofuS3StateBuilderModel
    return TofuS3StateBuilderModel(name="s3-x", type="s3", bucket="b", key="k", **kw)


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
    ("access_key", "credentials never live in the configuration tree"),
    ("secret_key", "credentials never live in the configuration tree"),
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
        LocalStateBuilderModel(name="loc", type="local", path=path)
    assert "loc" in str(exc.value)


def test_a_local_backend_path_that_is_fine_still_loads():
    from cs_image_system.local_state_plugin.local_state_models import LocalStateBuilderModel
    for path in ("state", "./state", "a/b/", "/var/lib/csis-state", ".", "./"):
        LocalStateBuilderModel(name="loc", type="local", path=path)


def test_a_state_backend_alias_binds(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "state-backends-3.yml", lambda d: _backend(d, "local-dev").update(aliases=["on-disk"]))
    _edit(root / "cfg" / "group-builders.yml",
          lambda d: next(b for b in d["group_builders"] if b["name"] == "oktagroups").update(
              state_configuration="on-disk"))
    stub_environment(monkeypatch)
    load_context(root)
    try:
        from cs_image_system.hashicorp_utils.collector import TerraformCollector
        reg = TerraformCollector().resolve_backend("on-disk")
        assert reg is not None and reg.name == "local-dev"
        from cs_image_system.base.commands.validate import check_state_locations
        from cs_image_system.base.global_context import GlobalTypeContext
        errors = [str(e) for e in check_state_locations(GlobalTypeContext())]
        assert not any("not declared" in e for e in errors), errors
    finally:
        reset_singletons()


def test_a_state_backends_declared_executable_must_exist(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_state_backend_executables
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "state-backends-3.yml",
          lambda d: _backend(d, "local-dev").update(executable="no-such-tofu"))
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        errors = [str(e) for e in check_state_backend_executables(ctx)]
        assert errors == ["Executable no-such-tofu specified for state backend local-dev not found in "
                          "executables list."], errors
    finally:
        reset_singletons()


def test_a_decrypted_backend_setting_is_written_as_its_ciphertext():
    from cs_image_system.base.encryption import Decrypted
    from cs_image_system.hashicorp_utils.collector import render_backend_value
    value = Decrypted("plain-profile", marker="ENC[age:QUJD]")
    assert render_backend_value(value) == '"ENC[age:QUJD]"'
