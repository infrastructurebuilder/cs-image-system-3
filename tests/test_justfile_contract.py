# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""stage 16: the Justfile's contract.  Five reserved targets in lifecycle
order (`init`, `build`, `test`, `full-test`, `release`), listed first;
`build` wraps `uv build`; `full-test` runs the slow legs and reports a
missing prerequisite as SKIPPED; `release` (stage 41) probes, bumps,
publishes and only then commits and tags, gated on the bar or on
`full-test` by the index; and the `preflight` command that gates
full-test's cloud-reading legs reads the credential caches without loading
the configuration.

Stage 128: nothing here reads the Justfile's text. A recipe is named by
`just --summary` and judged by its printed plan (`just -n`, the evaluated
commands it would run), so a reworded comment never fails a test and a
changed command always does."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import FIXTURE_CONFIG

REPO = Path(__file__).resolve().parents[1]
STARTER = REPO / "docs" / "examples" / "_skeleton" / "Justfile"      # the starter Justfile the release ships (stage 64)
CONTRACT = ["init", "build", "test", "full-test", "release"]

pytestmark = pytest.mark.skipif(not shutil.which("just"), reason="the recipes are judged through `just` itself")


def _just(*args: str, justfile: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["just"] if justfile is None else ["just", "-f", str(justfile), "-d", str(justfile.parent)]
    return subprocess.run([*cmd, *args], cwd=REPO, capture_output=True, text=True, check=check)


def _summary(justfile: Path | None = None) -> list[str]:
    """The recipe names, in file order (`[private]` ones excluded)."""
    return _just("--summary", "--unsorted", justfile=justfile).stdout.split()


def _plan(*args: str, justfile: Path | None = None) -> str:
    """The recipe's printed plan: what `just <recipe> <args>` would run, evaluated, run by nothing (just prints it on stderr)."""
    return _just("-n", *args, justfile=justfile).stderr


def _closure(name: str, justfile: Path | None = None, *args: str) -> str:
    """The plan of the recipe and of every recipe its plan invokes as `just <name>`
    (release chooses its gate in the body, stage 41)."""
    names = set(_summary(justfile)) | {"config-guard"}
    seen: dict[str, str] = {}
    todo = [(name, args)]
    while todo:
        n, a = todo.pop()
        if n in seen or n not in names:
            continue
        seen[n] = _plan(n, *a, justfile=justfile)
        todo += [(d, ()) for d in re.findall(r"\bjust ([A-Za-z_][\w-]*)", seen[n])]
    return "\n".join(seen.values())


def test_the_five_contract_targets_come_first_in_lifecycle_order():
    assert _summary()[:5] == CONTRACT, _summary()[:8]
    out = _just("--list", "--unsorted").stdout                                   # what an operator sees from bare `just`
    shown = [ln.split()[0] for ln in out.splitlines() if ln.startswith("    ") and ln.split()]
    assert shown[:5] == CONTRACT, shown[:8]
    assert "default" not in shown                        # [private]


def test_build_wraps_uv_build_and_the_gates_hold():
    assert _plan("build").split() == ["uv", "build", "--all-packages"]
    bar = _plan("test")
    assert "pytest" in bar and "ruff" in bar and "pyright" in bar
    assert _plan("verify") == bar                                                # the alias
    full = _plan("full-test")
    assert full.startswith(bar)                                                  # the bar first, then the legs
    # the live legs live in full-test-legs (hygiene V item 2: re-runnable alone after a
    # session renewal); full-test is the bar and then those legs, so its closure does it all
    legs = _closure("full-test")
    for needle in ("just test-mods --strict", "just preflight", "run --all", "state query --strict", "--exclude=./_private",
                   "--exclude=./.tofu-plugin-cache"):   # hygiene XVI item 2
        assert needle in legs, needle
    # and a configuration repository's own full-test copies its tree the same way
    starter = _closure("full-test", STARTER)
    for needle in ("--exclude=./_private", "--exclude=./.tofu-plugin-cache"):
        assert needle in starter, needle
    assert "cs-image-system-3/tfmodules" not in legs, "stage 64: the reference configuration carries its own tfmodules"
    assert legs.count("SKIPPED") >= 2                         # docker leg, credential legs
    # stage 41: the gate follows the index -- the bar for a development release to
    # TestPyPI, full-test (with the mod-test evidence and a clean live checkout) for
    # PyPI -- so it is chosen in the body, never a static dependency
    release = _plan("release", "patch", "test", "yes")
    assert not release.startswith(bar) and "just full-test" in release and "just test" in release and "mod-tests.yaml" in release
    for needle in ("git status --porcelain", "bump-my-version", "uv lock", "just publish test", "git tag -a"):
        assert needle in release, needle
    assert "uv version" not in release and "UV_PUBLISH_URL" not in release and "SKIPPED" not in release   # the tag is no longer the release
    pushes = "\n".join(l for l in release.splitlines() if "after=" not in l and "push with:" not in l)
    assert "git push" not in pushes   # nothing is pushed by the recipe; the closing line only names the operator's pushes (stage 107)


def test_release_cannot_half_release_and_publish_is_its_own_recipe():
    """stage 41: every probe -- the token, the index's knowledge of the version,
    the local tag -- runs before the bump; the upload runs before the commit and
    the tag, so a failed upload leaves an uncommitted bump and never a tagged,
    unpublished version; `publish` cleans, builds and uploads with the check
    URL, and the token is never in the Justfile."""
    body = _plan("release", "patch", "test", "yes")
    order = [body.rindex(s) for s in ("scripts/publish-target-ready", "UV_PUBLISH_TOKEN", "git tag -l", "bump-my-version \"${bump[@]}\"",
                                      "just publish test", "git commit", "git tag -a")]      # the last mention: the dry echo names them first
    assert order == sorted(order), "probe, bump, publish, commit, tag -- in that order"
    # stage 83: the branch first, then the index -- once before the bar and AGAIN after it, before the bump
    assert body.index('case "$branch" in') < body.index("\nready\n")   # the branch guard (main since stage 107) before the index
    calls = [i for i in range(len(body)) if body.startswith("\nready\n", i)]
    assert len(calls) == 2, "the index is asked twice"
    assert calls[0] < body.index("just full-test") and calls[1] > body.rindex("just test") and calls[1] < body.rindex("bump-my-version \"${bump[@]}\"")
    assert "--refuse-held" in body and "exit 75" in body and "scripts/index-knows" not in body
    assert body.rindex("just test") < body.rindex("bump-my-version \"${bump[@]}\"")         # the bar before the bump
    assert "git checkout -- pyproject.toml" in body                                      # the recovery when nothing went up
    # hygiene XIV item 1: when some project holds the version, keep the bump and finish with release-finish
    assert "CSIS_PUBLISH_SUMMARY" in body and "KEEP" in body and "just release-finish test" in body
    assert body.index("KEEP the uncommitted") < body.index("discard it with")
    assert "name=testpypi" in body and "name=pypi" in body
    publish = _plan("publish", "test")
    for needle in ("rm -rf dist", "just build", 'scripts/publish-dist "test" --version "$version" --token-var "$token_var"',
                   "UV_PUBLISH_TOKEN"):
        assert needle in publish, needle
    assert "uv publish" not in publish, "hygiene XIV: the upload is scripts/publish-dist's, one project at a time"
    # stage 83: publish begins with the index, and never prints the index's error page
    assert publish.index("scripts/publish-target-ready") < publish.index("just build")
    assert "--refuse-held" not in publish, "a partial upload is what a re-run of publish completes"
    assert "sixteen" not in publish and "$packages" in publish
    assert "index-ready" in _summary() and "--wait 7200" in _plan("index-ready", "test", "wait")
    assert "--check-url" not in publish, "uv refuses --check-url beside --index; the index's url is the check url"
    # the token is UV_PUBLISH_TOKEN, else the index's own name -- the repository secrets'
    # names, so the operator's one .envrc line serves the shell and CI alike
    for recipe in (body, publish):
        assert "token_var=TEST_PYPI_TOKEN" in recipe and "token_var=PYPI_TOKEN" in recipe
        assert "${!token_var:-}" in recipe
    assert "pypi-" not in publish and "pypi-" not in body                                 # no token shape anywhere
    probe = REPO / "scripts" / "index-knows"
    assert os.access(probe, os.X_OK) and "PEP 700" in probe.read_text()


def test_release_finish_commits_and_tags_only_a_completed_upload():
    """Hygiene XIV item 1: release-finish is on the release branch (main since stage 107), with the bump uncommitted
    and nothing else, asks the index that every project holds the version, and
    only then makes the evidence commit (PyPI), the commit and the tag; it pushes
    nothing."""
    assert "release-finish" in _summary()
    body = _plan("release-finish", "test")
    order = [body.index(s) for s in ('case "$branch" in', 'git show HEAD:pyproject.toml', 'git tag -l "v$new"',
                                     "git status --porcelain", "--all-held", "modification-test evidence",
                                     'git commit -q -m "release $new"', 'git tag -a "v$new"')]
    assert order == sorted(order), "every check before the commit, the commit before the tag"
    pushes = "\n".join(l for l in body.splitlines() if "after=" not in l and "push with:" not in l)
    assert "git push" not in pushes


def test_publish_starters_checks_every_repository_before_it_pushes_any():
    """Stage 66: the template repositories take a final version from its tag, once:
    a development version, a dirty tree, HEAD off the tag or no token (the real form)
    refuse; every repository is read and every tree built and gated before the
    first push, so one that already holds the version refuses them all; the
    starters and their repositories come from scripts/starter-tree --list."""
    body = _plan("publish-starters", "yes")
    for needle in ('*.dev*)', 'git status --porcelain', 'git tag --points-at HEAD',
                   'STARTER_PUSH_TOKEN', 'scripts/starter-tree --list', 'ls-remote --tags origin "refs/tags/v$version"',
                   'public-safe --tree "$work/$name.tree" --config "$work/$name.tree/cfg/_config.yml"',
                   'commit -q -m "cs-image-system $version"', 'tag -a "v$version"'):
        assert needle in body, needle
    first_push = body.index("push -q origin main")
    assert body.index("ls-remote --tags") < body.index("public-safe --tree") < body.index("done < <(") < first_push
    assert body.index('[ "yes" = "yes" ]') < first_push, "the dry form stops before any commit"
    assert "pypi-" not in body and "$STARTER_PUSH_TOKEN\" | base64" in body, "the token only ever as a header"
    # the dry form itself: a development version refuses before the tag check, with exit 1 and nothing published
    dry = _just("publish-starters", "yes", check=False)
    assert dry.returncode in (0, 1) and "git push" not in dry.stdout, dry.stdout + dry.stderr


def test_the_live_configuration_never_reaches_the_fast_suite_and_is_guarded_elsewhere():
    """Stage 28: `just test` needs no live configuration (the tests own the
    frozen fixture), and every recipe that drives one is guarded -- by
    config-guard in its dependency chain, or an inline check of
    cfg/_config.yml (full-test-legs, whose SKIPPED line names the reason)."""
    live = "cs-image-system-testconfig"                       # config_root's default, evaluated into every plan that reads it
    for n in ("test", "init", "build"):
        assert live not in _closure(n), n
    drivers = {"cli", "test-mods", "preflight", "full-test-legs", "release"}
    for n in drivers:
        plan = _closure(n, None, *(("x",) if n == "cli" else ("patch", "test", "yes") if n == "release" else ()))
        assert live in plan, n
        assert "exit 2" in plan and ("cfg/_config.yml" in plan or "just config-guard" in plan), n   # guarded
    # stage 64: the cycle recipes live in a configuration repository's Justfile (the release ships it)
    assert not {"cloud-cycle", "cloud-perform", "cloud-launch", "ci-login-proof", "sft-install", "v2-dry-run",
                "config-drift", "runtime-unchanged", "gce-cycle"} & set(_summary()), _summary()
    guard = _plan("config-guard")
    assert "exit 2" in guard and "tests/fixtures/config" in guard
    # config-drift: the CLI's command (stage 64), reached here as `just cli config-drift`; the normaliser is its module
    body = _plan("config-drift", justfile=STARTER)
    assert body.strip().endswith("config-drift")
    normaliser = (REPO / "packages" / "base" / "src" / "cs_image_system" / "base" / "commands" / "emission.py").read_text()
    for needle in ("<RUN>", "<STAMP>", "RUN_LOCAL_FILENAMES", ".terraform.lock.hcl", "archive"):
        assert needle in normaliser, needle
    assert "<ROOT>" not in body + normaliser and "s#--root-dir" not in body + normaliser   # stage 38: an absolute path in the emission IS drift
    assert not re.search(r"cs-image-system .*--commit", body)   # it never records anything
    decommission = _plan("cloud-decommission", "rt1", "i1", justfile=STARTER)
    assert "--undeclare instance:i1" in decommission and "--overlay" not in decommission


# ------------------------------------------------------------- preflight

def _preflight(monkeypatch, daemon: bool = False, **env: str):
    """`preflight` over the frozen fixture: it LOADS the configuration (stage
    127; the load reaches no cloud and needs no session -- the harness's
    identity and dummies open the tree) and reads the sessions from it.
    ``daemon`` makes the fixture's synthetic docker daemon (stage 128:
    docker-fixture, a context that exists nowhere) answer its probe."""
    from typer.testing import CliRunner
    from cs_image_system.system.cli import app
    from cs_image_system.docker_runtime import docker_runtime_builders
    from harness import reset_singletons, stub_environment
    stub_environment(monkeypatch)
    if daemon:
        monkeypatch.setattr(docker_runtime_builders, "probe_daemon", lambda binary, env, timeout=20: (True, "answers: engine stub"))
    for var in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    reset_singletons()                           # the command's own load, fresh (as load_context does)
    return CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "preflight"])


def test_preflight_reports_absent_sessions_and_exits_2(monkeypatch):
    # conftest: an empty AWS dir, no ADC -- every session absent
    result = _preflight(monkeypatch)
    assert result.exit_code == 2, result.output
    assert "aws-east2-runtime" in result.output and "gcloud-east1" in result.output and "docker-fixture" in result.output
    assert "not in" in result.output or "no SSO token" in result.output      # the aws line's reason
    assert "does not answer" in result.output                               # the synthetic daemon's (stage 128)
    assert "Application Default Credentials" in result.output
    assert "EXPIRED" in result.output and "renew" in result.output
    assert not (FIXTURE_CONFIG / "meta-state").exists()                     # the load wrote nothing into the frozen fixture


def test_preflight_passes_with_static_keys_and_an_adc(monkeypatch, tmp_path):
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    result = _preflight(monkeypatch, daemon=True, AWS_ACCESS_KEY_ID="AKIA-test", GOOGLE_APPLICATION_CREDENTIALS=str(adc))
    assert result.exit_code == 0, result.output
    assert "env keys" in result.output and "authorized_user" in result.output and "engine stub" in result.output
    # hygiene XII item 17: keys are present and NOT JUDGED, never "every session present"
    assert "every session present" not in result.output and "NOT JUDGED" in result.output


def test_preflight_fails_on_a_credential_that_is_set_but_empty(monkeypatch, tmp_path):
    """stage 43: a secret set from a checkout missing its source file passed three
    green CI jobs that ran nothing -- the variable existed and its value was "".
    Set-but-empty is a failure, reported by NAME, never by value."""
    from cs_image_system.base.commands.preflight import empty_environment_credentials
    from cs_image_system.base.loader import load_plugins
    from cs_image_system.base.registry import current_registry
    load_plugins()
    assert empty_environment_credentials(current_registry(),
                                         {"TF_VAR_X": "", "OKTA_API_TOKEN": "", "AWS_PROFILE": "p", "HOME": ""}) == \
        ["OKTA_API_TOKEN", "TF_VAR_X"]
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    result = _preflight(monkeypatch, daemon=True, AWS_ACCESS_KEY_ID="AKIA-test", GOOGLE_APPLICATION_CREDENTIALS=str(adc),
                        TF_VAR_NOS_KEY="")
    assert result.exit_code == 2, result.output
    assert "TF_VAR_NOS_KEY" in result.output and "EMPTY" in result.output and "AKIA-test" not in result.output


def test_the_looser_ci_recipe_is_gone_and_the_tofu_executing_recipes_take_the_lock():
    assert "ci" not in _summary(), "`just ci` (pyright non-blocking) must not return: `just test` is the bar"
    starter = _summary(STARTER)
    for name, args in (("cloud-bake", ("rt",)), ("cloud-cycle", ("rt",)), ("cloud-launch", ("rt",)),
                       ("cloud-decommission", ("rt", "i")), ("run", ("base-image",)), ("release", ("rt",))):
        assert name in starter and "--locked" in _plan(name, *args, justfile=STARTER), name   # may execute the roots (stage 64: the CLI's lock)
    for name in ("config-drift", "cloud-preflight", "dry", "record", "validate"):
        assert "--locked" not in _plan(name, justfile=STARTER), f"{name} never starts tofu and must not contend"
    for name in ("test", "pytest", "golden-regen", "full-test-legs", "fixture-live"):
        assert "--locked" not in _plan(name), f"{name} never starts tofu and must not contend"
    assert not (REPO / "scripts" / "with-tofu-lock").exists()


def test_the_performing_recipe_and_the_runtime_guard_hold_their_shape():
    """stage 45: `cloud-perform` is the one recipe that executes a runtime's
    bakes, releases and retention from CI; it is scoped to the runtime, real,
    committed and locked. `runtime-unchanged` compares a runtime's emission
    across records with the same normaliser config-drift uses."""
    body = _plan("cloud-perform", "rt1", justfile=STARTER)
    for needle in ("--locked", "--no-dry-run", "run base-image instance-image release retention",
                   "--only-runtime rt1", "--commit"):
        assert needle in body, needle
    assert "--apply-runtime" not in body and "--all" not in body       # bakes, releases, retention: roots plan and gate only
    assert "state query --strict" in body.splitlines()[0]              # cloud-preflight runs first (its dependency)
    for name in _summary():
        if name not in ("cli", "test-one"):                              # these take arbitrary words
            assert "--migrate-state" not in _plan(name, *(["x"] * _arity(name))), f"{name}: a state migration is the operator's act through `just cli`, never a recipe's (stage 46)"
    for name in _summary(STARTER):
        assert "--migrate-state" not in _plan(name, *(["x"] * _arity(name, STARTER)), justfile=STARTER), name
    guard = _plan("runtime-unchanged", "rt1", "abc", justfile=STARTER)
    assert "runtime-unchanged rt1 --ref abc" in guard                   # stage 64: the CLI's command
    assert "config-drift" in _plan("config-drift", justfile=STARTER)
    record = _plan("record", justfile=STARTER)
    assert record.strip().endswith("run --all --commit") and "--locked" not in record
    assert not (REPO / "scripts" / "normalise-emission").exists()
    text = (REPO / "packages" / "base" / "src" / "cs_image_system" / "base" / "commands" / "emission.py").read_text()
    assert "RUN_LOCAL_FILENAMES" in text and "[0-9]{8}[-_][0-9]{6}" in text


def _arity(name: str, justfile: Path | None = None) -> int:
    """How many positional words the recipe requires (from `just --show`'s header)."""
    header = _just("--show", name, justfile=justfile).stdout.splitlines()
    line = next(ln for ln in header if re.match(rf"^{re.escape(name)}\b", ln))
    params = line.split(":", 1)[0].split()[1:]
    return sum(1 for p in params if "=" not in p and not p.startswith("*"))   # `+X` needs one word, `*X` none


def test_preflight_readiness_marks_presence():
    from cs_image_system.base.commands.preflight import SessionInfo, _merge
    a = SessionInfo("r1", "aws", "profile p", None, "no SSO token cached", present=False)
    b = SessionInfo("r2", "aws", "profile p", None, "no SSO token cached", present=False)
    merged = _merge([a, b])
    assert len(merged) == 1 and merged[0].runtime == "r1, r2" and merged[0].present is False
    assert os.environ.get("CSIS_AWS_DIR")                     # the suite never reads the real caches
