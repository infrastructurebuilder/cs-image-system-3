# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 83: a release asks its publish target before it starts.

scripts/publish-target-ready against a local HTTP server answering by path:
every endpoint up; the upload endpoint 503; one project page 503 (the night
of 2026-10-05: most pages down, the one the release asked up); nothing
listening; an unknown target; which projects hold a version; the wait form.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _probe():
    loader = importlib.machinery.SourceFileLoader("publish_target_ready", str(REPO / "scripts" / "publish-target-ready"))
    spec = importlib.util.spec_from_loader("publish_target_ready", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    setattr(m, "TIMEOUT", 3)                  # a dead port answers fast; a test never waits thirty seconds
    return m


class Index:
    """A fake PyPI-kind index: path -> status, and the versions each project holds."""

    def __init__(self) -> None:
        self.status: dict[str, int] = {}
        self.versions: dict[str, list[str]] = {}
        self.fail_first: dict[str, int] = {}

    def handler(self):
        index = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                left = index.fail_first.get(self.path, 0)
                if left:
                    index.fail_first[self.path] = left - 1
                    self.send_response(503); self.end_headers(); self.wfile.write(b"<html>Service Unavailable</html>"); return
                code = index.status.get(self.path, 200)
                name = self.path.strip("/").split("/")[-1]
                if code == 200 and self.path.startswith("/simple/") and name not in index.versions:
                    code = 404
                self.send_response(code)
                if code == 200 and self.path.startswith("/simple/"):
                    body = json.dumps({"name": name, "versions": index.versions[name], "files": []}).encode()
                    self.send_header("Content-Type", "application/vnd.pypi.simple.v1+json"); self.end_headers(); self.wfile.write(body)
                    return
                self.end_headers()
        return H


@pytest.fixture
def world(tmp_path: Path):
    index = Index()
    server = ThreadingHTTPServer(("127.0.0.1", 0), index.handler())
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / "repo"
    (root / "packages" / "a").mkdir(parents=True)
    (root / "packages" / "b").mkdir(parents=True)
    (root / "pyproject.toml").write_text(f"""[project]
name = "cs-image-system"
version = "0.1.1.dev2"

[[tool.uv.index]]
name = "testpypi"
url = "http://127.0.0.1:{port}/simple/"
publish-url = "http://127.0.0.1:{port}/legacy/"
explicit = true
""")
    (root / "packages" / "a" / "pyproject.toml").write_text('[project]\nname = "cs-image-system-a"\n')
    (root / "packages" / "b" / "pyproject.toml").write_text('[project]\nname = "cs-image-system-b"\n')
    index.versions = {"cs-image-system": ["0.1.1.dev1"], "cs-image-system-a": ["0.1.1.dev1"], "cs-image-system-b": ["0.1.1.dev1"]}
    try:
        yield index, root, port
    finally:
        server.shutdown()


def _run(root: Path, *args: str, sleeps: list[float] | None = None) -> int:
    m = _probe()
    return m.main(["publish-target-ready", "test", "--root", str(root), *args],
                  sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_every_endpoint_up_is_ready_and_the_token_is_said_unchecked(world, capsys):
    index, root, _ = world
    assert _run(root) == 0
    out = capsys.readouterr().out
    assert "testpypi is ready: the upload endpoint and 3 project page(s) answer" in out
    assert "the token is not checked" in out
    assert out.count("simple cs-image-system") == 3                     # every project asked, not one


def test_the_upload_endpoint_down_is_not_ready(world, capsys):
    index, root, _ = world
    index.status["/legacy/"] = 503
    assert _run(root, "--quiet") == 75
    out = capsys.readouterr().out
    assert "upload http://127.0.0.1" in out and "503" in out
    assert "cannot take an upload now" in out and "Nothing was changed" in out and "the index's condition" in out


def test_one_project_page_down_is_not_ready_although_the_others_answer(world, capsys):
    index, root, _ = world
    index.status["/simple/cs-image-system-b/"] = 503
    assert _run(root, "--quiet") == 75
    out = capsys.readouterr().out
    assert "simple cs-image-system-b: 503" in out and "simple cs-image-system-a" not in out   # quiet: failures alone


def test_a_project_the_index_never_saw_is_fine(world, capsys):
    index, root, _ = world
    del index.versions["cs-image-system-b"]
    assert _run(root) == 0
    assert "simple cs-image-system-b: 404 (never seen)" in capsys.readouterr().out


def test_nothing_listening_is_not_ready(tmp_path: Path, world):
    _, root, port = world
    s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
    text = (root / "pyproject.toml").read_text().replace(f":{port}/", f":{dead}/")
    (root / "pyproject.toml").write_text(text)
    assert _run(root, "--quiet") == 75


def test_an_unknown_target_is_refused_by_name(world, capsys):
    _, root, _ = world
    m = _probe()
    assert m.main(["publish-target-ready", "gitlab", "--root", str(root)]) == 2
    assert "no checker for the publish target 'gitlab'" in capsys.readouterr().err


def test_which_projects_hold_the_version(world, capsys):
    index, root, _ = world
    assert _run(root, "--version", "0.1.1.dev2", "--refuse-held") == 0
    assert "holds 0.1.1.dev2 for none of the 3 projects: a fresh release" in capsys.readouterr().out
    index.versions["cs-image-system-a"].append("0.1.1.dev2")
    assert _run(root, "--version", "0.1.1.dev2") == 0                    # publish's form: reported, not refused
    assert "for 1 of 3 projects (cs-image-system-a): a partial upload, which `just publish` completes" in capsys.readouterr().out
    assert _run(root, "--version", "0.1.1.dev2", "--refuse-held") == 1   # release's form: never re-cut
    assert "never re-cut" in capsys.readouterr().out
    for p in index.versions.values():
        if "0.1.1.dev2" not in p:
            p.append("0.1.1.dev2")
    assert _run(root, "--version", "0.1.1.dev2", "--refuse-held") == 1
    assert "for all 3 projects" in capsys.readouterr().out


def test_the_wait_form_polls_until_ready_and_gives_up_at_its_limit(world, capsys):
    index, root, _ = world
    index.fail_first["/legacy/"] = 2
    sleeps: list[float] = []
    assert _run(root, "--wait", "600", "--every", "5", "--quiet", sleeps=sleeps) == 0
    out = capsys.readouterr().out
    assert out.count("is not ready") == 2 and sleeps == [5, 5] and "after 3 attempt(s)" in out
    index.status["/legacy/"] = 503
    assert _run(root, "--wait", "0", "--quiet") == 75                    # the limit spent: given up, exit 75
    assert "giving up" in capsys.readouterr().out
