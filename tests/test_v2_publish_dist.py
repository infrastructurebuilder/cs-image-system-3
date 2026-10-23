# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XIV: scripts/publish-dist uploads the release one project at a time.

Against a fake `uv` that answers each file as planned (uploaded, already
there, 429, 403) and records every call: the order (dependencies first, the
root project last, each project's sdist and wheel together); PyPI's limit on
new projects as exit 75 with what is left; a refused token named by its
variable; the cause lines of a failure; and, when every file was already
there, the token proved by sending one file again without the check.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"

FAKE_UV = """#!{python}
import json, os, sys
plan = json.load(open(os.environ["FAKE_UV_PLAN"]))
with open(os.environ["FAKE_UV_CALLS"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if "--publish-url" in args:                      # the token proof: one file, no check url
    name = os.path.basename(args[-1])
    outcome = plan.get("proof", "200")
    if outcome == "200":
        print(f"Uploading {{name}} (1.0KiB)"); sys.exit(0)
    code = {{"400": "400 Bad Request. Server says: 400 File already exists ('{{}}', with blake2_256 hash 'x')",
            "403": "403 Forbidden. Server says: 403 Invalid or non-existent authentication information."}}[outcome]
    print(f"error: Failed to publish `{{args[-1]}}` to {{args[args.index('--publish-url') + 1]}}")
    print(f"  cause: Server returned status code {{code}}"); sys.exit(2)
print(f"Publishing {{len(args) - 3}} files to https://index.invalid/legacy/")
for path in args[3:]:
    name = os.path.basename(path)
    outcome = plan["files"].get(name, "upload")
    if outcome == "skip":
        print(f"File {{name}} already exists, skipping")
    elif outcome == "upload":
        print(f"Hashing {{name}} (1.0KiB)"); print(f"Uploading {{name}} (1.0KiB)")
    else:
        print(f"Hashing {{name}} (1.0KiB)"); print(f"Uploading {{name}} (1.0KiB)")
        print(f"error: Failed to publish `{{path}}` to https://index.invalid/legacy/")
        if outcome == "429":
            print("  cause: Server returned status code 429 Too Many Requests. Server says: 429 Too many new")
            print("         projects created")
        elif outcome == "403":
            print("  cause: Server returned status code 403 Forbidden. Server says: 403 Invalid or non-existent")
            print("         authentication information.")
        else:
            print("  cause: Server returned status code 500 Internal Server Error.")
        sys.exit(2)
"""


def _script():
    loader = importlib.machinery.SourceFileLoader("publish_dist", str(REPO / "scripts" / "publish-dist"))
    spec = importlib.util.spec_from_loader("publish_dist", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    """A workspace of four projects -- base; a needs base; b needs base and a; the
    root needs all -- with their sdists and wheels built, and the fake uv."""
    root = tmp_path / "repo"
    projects = {"cs-image-system-base": [], "cs-image-system-a": ["cs-image-system-base==0.1.1"],
                "cs-image-system-b": ["cs-image-system-a==0.1.1", "cs-image-system-base>=0.1"]}
    for name, deps in projects.items():
        d = root / "packages" / name.removeprefix("cs-image-system-")
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text(f'[project]\nname = "{name}"\ndependencies = {json.dumps(deps)}\n')
    (root / "pyproject.toml").write_text(f"""[project]
name = "cs-image-system"
dependencies = {json.dumps([f"{n}=={VERSION}" for n in projects] + ["pydantic>=2"])}

[[tool.uv.index]]
name = "testpypi"
url = "https://index.invalid/simple/"
publish-url = "https://index.invalid/legacy/"
explicit = true
""")
    dist = root / "dist"
    dist.mkdir()
    for i, name in enumerate(["cs-image-system", *projects]):
        stem = f"{name.replace('-', '_')}-{VERSION}"
        (dist / f"{stem}.tar.gz").write_bytes(b"s" * (200 + i))
        (dist / f"{stem}-py3-none-any.whl").write_bytes(b"w" * (100 + i))
    uv = tmp_path / "uv"
    uv.write_text(FAKE_UV.format(python=sys.executable))
    uv.chmod(0o755)
    plan, calls = tmp_path / "plan.json", tmp_path / "calls.jsonl"
    plan.write_text(json.dumps({"files": {}}))
    monkeypatch.setenv("CSIS_UV", str(uv))
    monkeypatch.setenv("FAKE_UV_PLAN", str(plan))
    monkeypatch.setenv("FAKE_UV_CALLS", str(calls))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return root, plan, calls, tmp_path / "summary"


def _plan(plan: Path, files: dict[str, str], proof: str = "200") -> None:
    plan.write_text(json.dumps({"files": files, "proof": proof}))


def _calls(calls: Path) -> list[list[str]]:
    return [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []


def _run(root: Path, summary: Path) -> int:
    return _script().main(["test", "--version", VERSION, "--root", str(root), "--token-var", "TEST_PYPI_TOKEN",
                           "--summary", str(summary)])


def _summary(path: Path) -> dict[str, str]:
    return dict(line.split(" ", 1) for line in path.read_text().splitlines())


def _wheel(project: str) -> str:
    return f"{project.replace('-', '_')}-{VERSION}-py3-none-any.whl"


def test_one_project_at_a_time_dependencies_first_sdist_with_wheel(world, capsys):
    root, plan, calls, summary = world
    assert _run(root, summary) == 0
    got = _calls(calls)
    assert [c[:3] for c in got] == [["publish", "--index", "testpypi"]] * 4
    names = [[Path(p).name for p in c[3:]] for c in got]
    order = [n[0].split("-0.1.1")[0] for n in names]
    assert order == ["cs_image_system_base", "cs_image_system_a", "cs_image_system_b", "cs_image_system"]
    assert all(n[0].endswith(".tar.gz") and n[1].endswith(".whl") and len(n) == 2 for n in names)
    assert not any("--publish-url" in c for c in got), "something went up: the upload itself proved the token"
    assert _summary(summary) == {"held": "4", "total": "4", "status": "0"}
    assert "8 file(s) uploaded and 0 already there, in 4 projects" in capsys.readouterr().out


def test_the_limit_on_new_projects_is_not_now_and_names_what_is_left(world, capsys):
    root, plan, calls, summary = world
    _plan(plan, {_wheel("cs-image-system-b"): "429"})
    assert _run(root, summary) == 75
    out = capsys.readouterr().out
    assert "2 of 4 project(s) hold 0.1.1" in out
    assert "cause: Server returned status code 429 Too Many Requests" in out       # the cause, not the first lines
    assert "run this again in a day; 2 project(s) left: cs-image-system-b, cs-image-system" in out
    assert len(_calls(calls)) == 3, "nothing after the refused project is tried"
    assert _summary(summary) == {"held": "2", "total": "4", "status": "75"}


def test_a_refused_token_is_named_by_its_variable(world, capsys):
    root, plan, calls, summary = world
    _plan(plan, {_wheel("cs-image-system-base"): "403"})
    assert _run(root, summary) == 1
    out = capsys.readouterr().out
    assert "refused the token (403) -- the one in TEST_PYPI_TOKEN is not valid for testpypi" in out
    assert _summary(summary)["held"] == "0"


def test_a_failure_after_many_skips_still_shows_its_cause(world, capsys):
    root, plan, calls, summary = world
    files = {f: "skip" for f in (p.name for p in (root / "dist").iterdir())}
    files[_wheel("cs-image-system")] = "500"
    _plan(plan, files)
    assert _run(root, summary) == 1
    out = capsys.readouterr().out
    assert "cause: Server returned status code 500" in out and "the whole output" in out
    assert _summary(summary) == {"held": "3", "total": "4", "status": "1"}


@pytest.mark.parametrize("proof, rc, says", [
    ("200", 0, "is accepted by testpypi"),
    ("400", 0, "is accepted by testpypi"),       # "File already exists" comes after the credentials check
    ("403", 1, "REFUSED (403)"),
])
def test_when_everything_was_there_one_file_is_sent_again_to_prove_the_token(world, capsys, proof, rc, says):
    root, plan, calls, summary = world
    _plan(plan, {p.name: "skip" for p in (root / "dist").iterdir()}, proof=proof)
    assert _run(root, summary) == rc
    got = _calls(calls)
    assert got[-1][:3] == ["publish", "--publish-url", "https://index.invalid/legacy/"] and len(got) == 5
    assert "--index" not in got[-1], "the proof is sent without the check url, so it is really sent"
    sent = Path(got[-1][3]).name
    assert sent == _wheel("cs-image-system"), "the smallest file of a project that was entirely there"
    assert says in capsys.readouterr().out


def test_the_workspace_order_comes_from_the_dependencies(world):
    root, *_ = world
    m = _script()
    assert m.upload_order(root) == ["cs-image-system-base", "cs-image-system-a", "cs-image-system-b", "cs-image-system"]
    assert m.upload_order(REPO)[-1] == "cs-image-system"
    assert m.upload_order(REPO).index("cs-image-system-base") < m.upload_order(REPO).index("cs-image-system-system")
