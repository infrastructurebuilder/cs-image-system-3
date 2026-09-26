# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The bash mod builder emits a well-formed packer shell provisioner."""
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.bash_mod_plugin.bash_builder import BashModBuilder
from cs_image_system.bash_mod_plugin.bash_models import BashModItemModel
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase


def _builder(**model_fields):
    fields = {"execute_command": None, "environment_vars": [], "expect_disconnect": False}
    fields.update(model_fields)
    model = SimpleNamespace(**fields)
    # stage 63: the builder asks the model how the script runs
    model.effective_execute_command = lambda: model.execute_command
    b = BashModBuilder.__new__(BashModBuilder)
    b._model = model  # type: ignore[attr-defined]
    return b


def _emit(builder, mod):
    image = SimpleNamespace(name="img")
    items = builder.generate_items_during_modification(
        image, mod, cast(Any, None), ExecutionLifecyclePhase.IMAGE_GENERATION, Path("build.pkr.hcl"))
    return "\n".join(a.value for a in items)


def test_inline_and_scripts_become_two_provisioners_files_first():
    mod = BashModItemModel(name="m", type_="bash-remote", script=['echo "hi"', "id"], scripts=["x.sh"])
    hcl = _emit(_builder(), mod)
    assert hcl.startswith("# Modifications for m of type bash-remote (shell)")
    assert hcl.count('provisioner "shell" {') == 2   # packer: scripts XOR inline per block
    assert hcl.index("scripts = [") < hcl.index("inline = [")
    assert hcl.count('only = ["amazon-ebs.img"]') == 2
    assert 'only = ["amazon-ebs.img"]' in hcl
    assert 'scripts = ["x.sh"]' in hcl
    assert '"echo \\"hi\\"",' in hcl and '"id",' in hcl
    assert hcl.rstrip().endswith("}")
    assert "exit 0" not in hcl


def test_builder_model_options_are_emitted():
    mod = BashModItemModel(name="m", type_="bash-remote", script=["true"])
    assert _emit(_builder(), mod).count('provisioner "shell" {') == 1
    hcl = _emit(_builder(execute_command="sudo -E bash '{{.Path}}'", environment_vars=["A=1"],
                         expect_disconnect=True), mod)
    assert "execute_command = \"sudo -E bash '{{.Path}}'\"" in hcl
    assert 'environment_vars = ["A=1"]' in hcl
    assert "expect_disconnect = true" in hcl


def test_copy_external_assets_copies_script_files(tmp_path, monkeypatch):
    src = tmp_path / "cfg"
    src.mkdir()
    (src / "s.sh").write_text("#!/bin/sh\necho ok\n")
    monkeypatch.chdir(src)
    target = tmp_path / "block"
    mod = BashModItemModel(name="m", type_="bash-remote", scripts=["s.sh"])
    mapping = _builder().copy_external_assets(target, mod)
    assert (target / "s.sh").read_text() == "#!/bin/sh\necho ok\n"
    assert mapping == {"s.sh": Path("s.sh")}
