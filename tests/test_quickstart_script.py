# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""scripts/quickstart runs the quickstart page's own commands (specification 002).

The page, docs/QUICKSTART.md, is proved by running it: CI's `quickstart`
job, the Publish workflow's, and `just test-quickstart` in the release's
gate. What these tests hold is the runner's behaviour, with a stubbed
session, build and install check, so nothing here installs, builds or
runs a command (contracts/quickstart-runner.md, "What the tests hold").
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import io
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]


def _script() -> Any:
    loader = importlib.machinery.SourceFileLoader("quickstart_script", str(REPO / "scripts" / "quickstart"))
    spec = importlib.util.spec_from_loader("quickstart_script", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["quickstart_script"] = m
    loader.exec_module(m)
    return m


Q = _script()

PAGE = """# A page

Prose is not run.

```sh
# step 1 -- box 1 of 2 -- v1
uv tool install --upgrade --index-url https://test.pypi.org/simple/ \\
  'cs-image-system[docker]==9.9.9'
export PATH="/somewhere:$PATH"

cs-image-system --version
```

```text
this is shown and never run
```

```sh
# step 2 -- box 2 of 2 -- v1
cs-image-system init-config csis-quickstart --from standard-docker
cs-image-system --root-dir csis-quickstart run --all
```
"""


class _Session:
    """Records each command; fails the one whose text contains ``fail``."""

    def __init__(self, fail: str | None = None):
        self.fail, self.commands = fail, []

    def run(self, command: str) -> int:
        self.commands.append(command)
        return 7 if self.fail and self.fail in command else 0

    def close(self) -> None:
        pass


def _run(tmp_path: Path, page: str = PAGE, *, session: _Session | None = None, installed: list[str] | None = None,
         clock: list[float] | None = None, wheels: Path | None = None, built: list[Path] | None = None, **kw):
    path = tmp_path / "QUICKSTART.md"
    path.write_text(page)
    session = session or _Session()
    said: list[str] = []
    ticks = iter(clock) if clock else None
    built = built if built is not None else []

    def build(out: Path) -> Any:
        built.append(out)
        return Q.Built(version="9.9.9", wheels={"cs-image-system": out / "cs_image_system-9.9.9-py3-none-any.whl"})

    rc = Q.run(page=path, wheels=wheels, passes=kw.get("passes", 1), limit=kw.get("limit", 900), keep=None,
               work=tmp_path / "work", say=said.append, session_factory=lambda env, cwd: session, build=build,
               check_install=lambda tool_dir, b: installed or [], clock=(lambda: next(ticks)) if ticks else None)
    return rc, said, session


def test_the_commands_are_read_in_page_order_continuations_joined_comments_skipped():
    boxes = Q.read_boxes(PAGE)
    assert [b.number for b in boxes] == [1, 2]
    assert boxes[0].commands == [
        "uv tool install --upgrade --index-url https://test.pypi.org/simple/ 'cs-image-system[docker]==9.9.9'",
        'export PATH="/somewhere:$PATH"',
        "cs-image-system --version"]
    assert boxes[1].commands[-1] == "cs-image-system --root-dir csis-quickstart run --all"
    assert all("shown and never run" not in c for b in boxes for c in b.commands)   # a `text` block is never run


def test_every_command_runs_in_one_session_in_order(tmp_path: Path):
    rc, said, session = _run(tmp_path)
    assert rc == 0 and said[-1].startswith("quickstart: passed -- 5 commands in 2 boxes")
    assert session.commands == [c for b in Q.read_boxes(PAGE) for c in b.commands]   # one session: an export holds
    assert "quickstart: box 1 of 2: cs-image-system --version" in said


def test_a_failing_command_is_named_and_the_rest_did_not_run(tmp_path: Path):
    rc, said, session = _run(tmp_path, session=_Session(fail="init-config"))
    assert rc == 1
    failed = [ln for ln in said if ln.startswith("quickstart: FAILED at box 2 of 2:")]
    assert len(failed) == 1 and "init-config" in failed[0] and failed[0].endswith("(exit 7)")
    assert "run --all" not in " ".join(session.commands)
    assert "quickstart: did not run: cs-image-system --root-dir csis-quickstart run --all" in said
    assert said[-1].startswith("quickstart: FAILED -- ")


def test_a_page_with_no_box_fails(tmp_path: Path):
    rc, said, _ = _run(tmp_path, page="# nothing to run\n\n```text\nls\n```\n")
    assert rc == 1 and said[-1].startswith("quickstart: FAILED --") and "`sh` box" in said[-1]


def test_a_page_with_eleven_commands_fails_before_any_runs(tmp_path: Path):
    page = "```sh\n# step 1 -- box 1 of 1 -- v1\n" + "".join(f"echo {i}\n" for i in range(11)) + "```\n"
    rc, said, session = _run(tmp_path, page=page)
    assert rc == 1 and session.commands == []
    assert said[-1].startswith("quickstart: FAILED --") and "11 commands" in said[-1]


def test_an_install_that_is_not_the_build_fails(tmp_path: Path):
    rc, said, session = _run(tmp_path, installed=["cs-image-system-base 0.2.2 came from an index, not the build"])
    assert rc == 1
    assert said[-1].startswith("quickstart: FAILED --") and "cs-image-system-base 0.2.2" in said[-1]
    assert len(session.commands) == 3                     # box 1 ran, box 2 did not


def test_a_run_over_the_limit_fails(tmp_path: Path):
    clock = [0.0] + [0.0, 0.0] + [10.0, 1000.0]           # the start, box 1 begins and ends, box 2 begins and ends
    rc, said, _ = _run(tmp_path, clock=clock + [1000.0] * 8)
    assert rc == 1 and "quickstart: the page took 1000s (limit 900)" in said
    assert said[-1].startswith("quickstart: FAILED --") and "1000s" in said[-1]


def test_two_passes_run_the_page_twice_in_one_directory(tmp_path: Path):
    rc, said, session = _run(tmp_path, passes=2)
    assert rc == 0 and len(session.commands) == 10
    assert said[-1].startswith("quickstart: passed -- 5 commands") and said[-1].endswith("twice")


def test_given_files_are_used_and_nothing_is_built(tmp_path: Path):
    given = tmp_path / "dist" / "01-cs-image-system"
    given.mkdir(parents=True)
    (given / "cs_image_system-9.9.9-py3-none-any.whl").write_bytes(b"")
    (given / "cs_image_system-9.9.9.tar.gz").write_bytes(b"")
    built: list[Path] = []
    rc, said, _ = _run(tmp_path, wheels=tmp_path / "dist", built=built)
    assert rc == 0 and built == []
    assert "quickstart: 1 wheel of 9.9.9 given in " + str(tmp_path / "dist") + " (nothing built)" in said


def test_the_umbrellas_override_carries_the_extras_the_page_asks_for(tmp_path: Path):
    whl = tmp_path / "cs_image_system-9.9.9-py3-none-any.whl"
    base = tmp_path / "cs_image_system_base-0.2.2-py3-none-any.whl"
    lines = Q.override_lines({"cs-image-system": whl, "cs-image-system-base": base}, Q.page_extras(PAGE))
    assert lines == [f"cs-image-system[docker] @ {whl.as_uri()}", f"cs-image-system-base @ {base.as_uri()}"]


def test_an_installed_package_of_the_system_from_an_index_is_named(tmp_path: Path):
    site = tmp_path / "tools" / "cs-image-system" / "lib" / "python3.13" / "site-packages"
    (site / "cs_image_system-9.9.9.dist-info").mkdir(parents=True)
    (site / "cs_image_system-9.9.9.dist-info" / "direct_url.json").write_text('{"url": "file:///w.whl"}')
    (site / "cs_image_system_base-0.2.2.dist-info").mkdir()
    (site / "requests-2.0.dist-info").mkdir()
    built = Q.Built(version="9.9.9", wheels={"cs-image-system": Path("/w.whl"), "cs-image-system-base": Path("/b.whl")})
    problems = Q.installed_from_build(tmp_path / "tools", built)
    assert len(problems) == 1 and problems[0].startswith("cs-image-system-base 0.2.2")


def test_the_prerequisites_are_the_starters_tools_but_those_the_page_installs(tmp_path: Path):
    executables = tmp_path / "executables.yml"
    executables.write_text("executables:\n"
                           "  - {name: docker, binary: docker, version: '>=24'}\n"
                           "  - {name: ansible-playbook, binary: ansible-playbook, version: '>=2.16'}\n"
                           "  - {name: open-tofu, type: tofu, binary: tofu, version: '>1,<2'}\n")
    rows = Q.prerequisites(executables, uv_floor="0.8.0")
    assert [(r.tool, r.version) for r in rows] == [("uv", ">=0.8.0"), ("docker", ">=24"), ("tofu", ">1,<2")]


def test_the_table_check_names_the_first_row_that_differs(tmp_path: Path):
    executables = tmp_path / "executables.yml"
    executables.write_text("executables:\n  - {name: docker, binary: docker, version: '>=24'}\n")
    page = tmp_path / "QUICKSTART.md"
    page.write_text(f"intro\n\n{Q.TABLE_START}\nold\n{Q.TABLE_END}\n\nrest\n")
    said: list[str] = []
    assert Q.table(page, executables, "check", uv_floor="0.8.0", say=said.append) == 1
    assert "row 1" in said[-1]
    assert Q.table(page, executables, "write", uv_floor="0.8.0", say=said.append) == 0
    assert Q.table(page, executables, "check", uv_floor="0.8.0", say=said.append) == 0
    text = page.read_text()
    assert text.startswith("intro\n") and text.endswith("\nrest\n") and "| `docker` | `>=24` |" in text


def test_prepare_refuses_a_download_whose_checksum_differs(tmp_path: Path):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as tar:
        data = b"#!/bin/sh\necho uv 0.8.0\n"
        info = tarfile.TarInfo("uv-x86_64-unknown-linux-gnu/uv")
        info.size, info.mode = len(data), 0o755
        tar.addfile(info, io.BytesIO(data))
    body = payload.getvalue()

    def fetch(url: str) -> bytes:
        if url.endswith(".sha256"):
            return f"{'0' * 64}  uv-x86_64-unknown-linux-gnu.tar.gz\n".encode()
        return body
    with pytest.raises(Q.PrepareFailed, match="uv: the download's sha256 is .* not the published 0000"):
        Q.prepare_tool("uv", "0.8.0", tmp_path, fetch=fetch)

    def fetch_good(url: str) -> bytes:
        if url.endswith(".sha256"):
            return f"{hashlib.sha256(body).hexdigest()}  uv-x86_64-unknown-linux-gnu.tar.gz\n".encode()
        return body
    assert Q.prepare_tool("uv", "0.8.0", tmp_path, fetch=fetch_good) == tmp_path / "bin" / "uv"
    assert (tmp_path / "bin" / "uv").stat().st_mode & 0o111
