# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``just release-watch <version>`` waits on the runs a release walk started and says one verdict each.

Against a fake shell that answers every command the watch runs -- git, ``gh`` and the probe
scripts -- and a fake clock that ``sleep`` moves: the runs are found by commit (the tag's in this
repository, the take's in the configuration), each waited on until it completes, and one line said
for each; a green Publish run of the tag is read further, for every release, final or development:
TestPyPI must list the version (PyPI is never asked until 1.0) and every template repository must
hold its tag, else it is not good, nor is a run that failed or never started; the configuration's ``main`` run is read for the guard and the bake plan;
the exit is 0 only when every verdict is good. A look ``gh`` does not answer while waiting is no news
and the next interval looks again; ``gh`` absent or holding no token before the first look refuses at
once -- decided without the network, and the stored token it reads is never said -- and no look
answered until the timeout ends the watch on the reason. A ``gh`` too old to read its token without
the network is not asked for it: its first look decides, and a look refused for want of a login
refuses at once.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "release-watch"


def _load():
    loader = importlib.machinery.SourceFileLoader("release_watch", str(SCRIPT))
    spec = importlib.util.spec_from_loader("release_watch", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["release_watch"] = m          # the dataclasses resolve their annotations through the module
    loader.exec_module(m)
    return m


W = _load()

VERSION = "0.1.9"
SYSTEM_SHA = "a" * 40
TAKE_SHA = "b" * 40
RECORD_SHA = "c" * 40
SYSTEM, CONFIG = Path("/system"), Path("/config")
STARTERS = "complete o/cs-image-system-starter-complete\nstandard-aws o/cs-image-system-starter-standard-aws\n"
PERFORM_LOG = "\n".join([
    "perform\tThe full run, recorded\t2001-01-01T00:00:00Z bake plan: base@aws: bake: no build yet",
    "perform\tThe guarded runtime stays out of CI, so a change there fails loudly\t2001-01-01T00:00:01Z "
    "runtime-unchanged: the emission of gcloud is unchanged since abc (base-images)",
    "perform\tThe runtime performs\t2001-01-01T00:00:02Z bake plan: base@aws: bake: no build yet",
    "perform\tThe runtime performs\t2001-01-01T00:00:02Z bake plan: model@aws: skip: current (build 3)",
])


def _run(rid: int, workflow: str, branch: str, conclusion: str = "success", status: str = "completed") -> dict:
    return {"databaseId": rid, "workflowName": workflow, "headBranch": branch, "event": "push", "status": status,
            "conclusion": conclusion if status == "completed" else "", "url": f"https://example.invalid/runs/{rid}"}


def _system_runs(**changes: dict) -> list[dict]:
    runs = {"tag": _run(11, "CI", f"v{VERSION}"), "publish": _run(15, "Publish", f"v{VERSION}"),
            "main": _run(12, "CI", "main"),
            "develop": _run(13, "CI", "develop"), "scratch": _run(14, "CI from scratch", "develop")}
    for name, run in changes.items():
        runs[name] = run
    return [r for r in runs.values() if r]


def _config_runs() -> list[dict]:
    return [_run(21, "CI", "develop"), _run(22, "CI", "main"), _run(20, "CI", "develop", status="queued")]


class FakeShell:
    """Answers each command by the first needle found in its text, a Done or a callable making one;
    records every call."""

    def __init__(self, answers: list[tuple[str, object]]):
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], *, cwd: Path | None = None, env=None):
        self.calls.append(list(cmd))
        if cmd[0].endswith("gh"):
            assert env is not None and env["GH_PAGER"] == "cat"
        text = " ".join(cmd)
        for needle, answer in self.answers:
            if needle in text:
                return answer(cmd) if callable(answer) else answer
        return W.Done(0)

    def count(self, needle: str) -> int:
        return sum(needle in " ".join(c) for c in self.calls)


def _answers(system: list[dict] | None = None, config: list[dict] | None = None, *, index_rc: int = 0,
             main_pushed: bool = True, log: str = PERFORM_LOG, templates: str = "sha\trefs/tags/v0.1.9\n",
             develop_behind: str = "3\n"):
    taken = f"{RECORD_SHA} cs-image-system dry-run generation x: identity\n{TAKE_SHA} Take {VERSION}\nd first\n"
    return [
        (f"refs/tags/v{VERSION}^{{commit}}", W.Done(0, SYSTEM_SHA + "\n")),
        ("log --first-parent", W.Done(0, taken)),
        ("merge-base --is-ancestor", W.Done(0 if main_pushed else 1)),
        (f"run list --commit {SYSTEM_SHA}", W.Done(0, json.dumps(_system_runs() if system is None else system))),
        (f"run list --commit {RECORD_SHA}", W.Done(0, json.dumps(_config_runs() if config is None else config))),
        ("run view 22 --json jobs", W.Done(0, json.dumps({"jobs": [{"name": "verify", "databaseId": 98},
                                                                   {"name": "perform", "databaseId": 99}]}))),
        ("run view 22 --job 99 --log", W.Done(0, log)),
        ("index-knows", W.Done(index_rc, "index-knows: said\n")),
        ("starter-tree --list", W.Done(0, STARTERS)),
        ("ls-remote --tags", W.Done(0, templates)),
        ("rev-list --count develop..origin/main", W.Done(0, develop_behind)),
    ]


class Clock:
    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _watch(shell: FakeShell, said: list[str], clock: Clock | None = None):
    clock = clock or Clock()
    return W.Watch(VERSION, SYSTEM, CONFIG, run=shell, gh="/bin/gh", sleep=clock.sleep, clock=lambda: clock.now,
                   say=said.append, timeout_minutes=10, interval=60)


def _verdicts(said: list[str]) -> dict[str, str]:
    """label -> verdict, from the lines ``release-watch: <label>: <verdict>`` with a known label."""
    labels = ("system tag v0.1.9 (CI)", "system tag v0.1.9 (Publish)", "system main (CI)", "system develop (CI)", "system develop (CI from scratch)",
              "configuration develop (CI)", "configuration main (CI)")
    out = {}
    for line in said:
        for label in labels:
            if line.startswith(f"release-watch: {label}: "):
                out[label] = line[len(f"release-watch: {label}: "):]
    return out


def test_every_run_green_and_everything_published_is_exit_0_with_one_line_each():
    shell = FakeShell(_answers())
    said: list[str] = []
    assert _watch(shell, said).watch() == 0
    verdicts = _verdicts(said)
    assert len(verdicts) == 7
    url = "https://example.invalid/runs/{}"
    assert verdicts["system main (CI)"] == W.PASSED.format(url=url.format(12))
    assert verdicts["system tag v0.1.9 (CI)"] == W.PASSED.format(url=url.format(11))
    # the tag's Publish run is read further: TestPyPI for a final version too, and the templates
    assert verdicts["system tag v0.1.9 (Publish)"].split("; ") == [
        W.PASSED.format(url=url.format(15)),
        W.INDEX_HOLDS.format(index="testpypi", project="cs-image-system", version=VERSION),
        W.TEMPLATES_HOLD.format(version=VERSION, count=2)]
    # the configuration's main: the guard's verdict and what the performing step baked (not the record's plan)
    assert verdicts["configuration main (CI)"].split("; ") == [
        W.PASSED.format(url=url.format(22)), W.GUARD_PASSED.format(count=1), W.BAKED.format(keys="base@aws")]
    assert verdicts["configuration develop (CI)"] == W.PASSED.format(url=url.format(21))   # the newest push run
    assert said[-2] == f"release-watch: {W.FAST_FORWARD.format(root=CONFIG)}"
    assert said[-1] == f"release-watch: {W.ALL_GOOD}"
    # found by commit: the tag's here, the record the take pushed there; the index by the version's form
    assert shell.count(f"run list --commit {SYSTEM_SHA}") == 1 and shell.count(f"run list --commit {RECORD_SHA}") == 1
    assert shell.count("https://test.pypi.org/simple/ cs-image-system 0.1.9") == 1 and shell.count("ls-remote") == 2
    assert shell.count("https://pypi.org/") == 0                                 # PyPI is never asked until 1.0


@pytest.mark.parametrize(("change", "label", "verdict"), [
    ({"develop": _run(13, "CI", "develop", conclusion="failure")}, "system develop (CI)",
     W.FAILED.format(conclusion="failure", url="https://example.invalid/runs/13")),
    ({"main": _run(12, "CI", "main", conclusion="cancelled")}, "system main (CI)",
     W.FAILED.format(conclusion="cancelled", url="https://example.invalid/runs/12")),
    ({"publish": _run(15, "Publish", f"v{VERSION}", conclusion="failure")}, "system tag v0.1.9 (Publish)",
     W.FAILED.format(conclusion="failure", url="https://example.invalid/runs/15")),
])
def test_one_failed_run_is_named_and_the_exit_is_1(change: dict, label: str, verdict: str):
    said: list[str] = []
    assert _watch(FakeShell(_answers(_system_runs(**change))), said).watch() == 1
    verdicts = _verdicts(said)
    assert verdicts[label] == verdict
    assert sum(not v.startswith("passed") for v in verdicts.values()) == 1
    assert said[-1] == f"release-watch: {W.NOT_ALL_GOOD.format(bad=1, total=7)}"


def test_a_run_that_never_starts_is_waited_on_until_the_timeout_and_said_so():
    clock = Clock()
    shell = FakeShell(_answers(_system_runs(scratch={})))
    said: list[str] = []
    assert _watch(shell, said, clock).watch() == 1
    assert clock.now >= 10 * 60 and set(clock.slept) == {60}                         # asked every interval, then given up
    assert shell.count(f"run list --commit {SYSTEM_SHA}") == len(clock.slept) + 1
    assert _verdicts(said)["system develop (CI from scratch)"] == W.NEVER.format(
        workflow="CI from scratch", branch="develop", commit=SYSTEM_SHA[:7], minutes=10)


def test_a_run_still_running_at_the_timeout_is_said_so():
    clock = Clock()
    said: list[str] = []
    running = _run(13, "CI", "develop", status="in_progress")
    assert _watch(FakeShell(_answers(_system_runs(develop=running))), said, clock).watch() == 1
    assert _verdicts(said)["system develop (CI)"] == W.RUNNING.format(minutes=10, url="https://example.invalid/runs/13")


def test_a_run_that_completes_while_waited_on_is_read_again():
    clock = Clock()
    asked: list[int] = []

    def system(cmd: list[str]):
        asked.append(1)
        develop = _run(13, "CI", "develop", status="in_progress" if len(asked) < 3 else "completed")
        return W.Done(0, json.dumps(_system_runs(develop=develop)))
    answers = _answers()
    answers.insert(0, (f"run list --commit {SYSTEM_SHA}", system))
    said: list[str] = []
    assert _watch(FakeShell(answers), said, clock).watch() == 0
    assert clock.slept == [60, 60]


def test_a_green_publish_run_whose_index_lacks_the_version_is_not_good():
    said: list[str] = []
    assert _watch(FakeShell(_answers(index_rc=1)), said).watch() == 1
    tag = _verdicts(said)["system tag v0.1.9 (Publish)"].split("; ")
    assert tag[0].startswith("passed") and tag[1] == W.INDEX_LACKS.format(index="testpypi", project="cs-image-system",
                                                                          version=VERSION)
    assert "index-knows: said" in said


def test_a_template_repository_without_the_tag_is_not_good():
    said: list[str] = []
    assert _watch(FakeShell(_answers(templates="")), said).watch() == 1
    assert W.TEMPLATE_LACKS.format(repo="o/cs-image-system-starter-complete", version=VERSION) in \
        _verdicts(said)["system tag v0.1.9 (Publish)"]


@pytest.mark.parametrize(("log", "reading"), [
    ("perform\tguard\tx runtime-unchanged: the emission of gcloud CHANGED since abc (3 files):",
     W.GUARD_CHANGED.format(line="runtime-unchanged: the emission of gcloud CHANGED since abc (3 files):")),
    ("perform\tGate on the secrets\tx perform: mode DRY", W.GUARD_ABSENT),
])
def test_a_green_main_run_whose_guard_changed_or_never_ran_is_not_good(log: str, reading: str):
    said: list[str] = []
    assert _watch(FakeShell(_answers(log=log)), said).watch() == 1
    main = _verdicts(said)["configuration main (CI)"].split("; ")
    assert main[1] == reading and main[2] == W.BAKED_NOTHING
    assert not any(line == f"release-watch: {W.FAST_FORWARD.format(root=CONFIG)}" for line in said)


def test_without_main_pushed_the_configuration_has_develop_alone():
    said: list[str] = []
    assert _watch(FakeShell(_answers(main_pushed=False)), said).watch() == 0
    assert "configuration main (CI)" not in _verdicts(said) and len(_verdicts(said)) == 6


def test_a_development_version_reads_testpypi_and_leaves_the_templates_alone():
    dev = "0.1.9.dev2"
    runs = _system_runs(tag=_run(11, "CI", f"v{dev}"), publish=_run(15, "Publish", f"v{dev}"))
    taken = f"{TAKE_SHA} Take {dev}\n"
    shell = FakeShell([(f"refs/tags/v{dev}^{{commit}}", W.Done(0, SYSTEM_SHA + "\n")),
                       ("log --first-parent", W.Done(0, taken)), ("merge-base --is-ancestor", W.Done(1)),
                       (f"run list --commit {SYSTEM_SHA}", W.Done(0, json.dumps(runs))),
                       (f"run list --commit {TAKE_SHA}", W.Done(0, json.dumps([_run(21, "CI", "develop")]))),
                       *_answers()])
    said: list[str] = []
    w = W.Watch(dev, SYSTEM, CONFIG, run=shell, gh="/bin/gh", sleep=Clock().sleep, say=said.append)
    assert w.watch() == 0
    assert shell.count(f"https://test.pypi.org/simple/ cs-image-system {dev}") == 1
    assert shell.count("ls-remote") == 0 and shell.count("starter-tree") == 0      # the templates take a final release alone
    assert _verdicts(said)["configuration develop (CI)"].startswith("passed")      # the Take commit itself was pushed


def test_no_tag_or_no_take_or_no_gh_is_said_and_never_guessed():
    said: list[str] = []
    untagged = FakeShell([(f"refs/tags/v{VERSION}^{{commit}}", W.Done(1)), *_answers()])
    with pytest.raises(W.Refused) as e:
        _watch(untagged, said).watch()
    assert e.value.code == 2 and e.value.message == f"release-watch: {W.NOT_TAGGED.format(version=VERSION, root=SYSTEM)}"
    untaken = FakeShell([("log --first-parent", W.Done(0, "d first\n")), *_answers()])
    assert _watch(untaken, said).watch() == 1
    assert f"release-watch: {W.NOT_TAKEN.format(version=VERSION, root=CONFIG)}" in said
    refused = FakeShell([("auth token", W.Done(1, "", "no oauth token found for github.com\n")), *_answers()])
    with pytest.raises(W.Refused) as e:
        _watch(refused, said).watch()
    assert e.value.code == 2 and e.value.message == f"release-watch: {W.NO_GH}"
    assert "no oauth token found for github.com" in said
    assert refused.count("run list") == 0                                        # refused before the first look
    with pytest.raises(W.Refused):
        W.Watch("banana", SYSTEM, CONFIG, run=FakeShell([])).watch()


TLS = "failed to get runs: Get https://api.github.com/x: net/http: TLS handshake timeout"


def test_a_look_gh_does_not_answer_while_waiting_is_no_news_and_the_next_one_is_read():
    clock = Clock()
    asked: list[int] = []

    def system(cmd: list[str]):
        asked.append(1)
        if len(asked) == 1:
            return W.Done(1, "", TLS + "\n")
        return W.Done(0, json.dumps(_system_runs()))
    answers = _answers()
    answers.insert(0, (f"run list --commit {SYSTEM_SHA}", system))
    said: list[str] = []
    assert _watch(FakeShell(answers), said, clock).watch() == 0
    assert clock.slept == [60] and len(asked) == 2
    assert f"release-watch: {W.UNANSWERED.format(reason=TLS, interval=60)}" in said
    assert len(_verdicts(said)) == 7 and said[-1] == f"release-watch: {W.ALL_GOOD}"


def test_no_look_answered_until_the_timeout_ends_the_watch_on_the_reason():
    clock = Clock()
    shell = FakeShell([("run list", W.Done(1, "", TLS + "\n")), *_answers()])
    said: list[str] = []
    with pytest.raises(W.Refused) as e:
        _watch(shell, said, clock).watch()
    assert e.value.code == 2 and e.value.message == f"release-watch: {W.NEVER_ANSWERED.format(minutes=10, reason=TLS)}"
    assert clock.now >= 10 * 60 and shell.count("run list") == len(clock.slept) + 1
    assert _verdicts(said) == {}


def test_a_last_look_unanswered_at_the_timeout_keeps_the_verdicts_of_the_look_before():
    clock = Clock()
    asked: list[int] = []
    running = _run(13, "CI", "develop", status="in_progress")

    def system(cmd: list[str]):
        asked.append(1)
        if len(asked) > 1:
            return W.Done(1, "", TLS + "\n")
        return W.Done(0, json.dumps(_system_runs(develop=running)))
    answers = _answers()
    answers.insert(0, (f"run list --commit {SYSTEM_SHA}", system))
    said: list[str] = []
    assert _watch(FakeShell(answers), said, clock).watch() == 1
    assert f"release-watch: {W.LAST_UNANSWERED.format(reason=TLS)}" in said
    assert _verdicts(said)["system develop (CI)"] == W.RUNNING.format(minutes=10, url="https://example.invalid/runs/13")
    assert _verdicts(said)["system main (CI)"].startswith("passed")


def test_the_main_runs_jobs_unread_after_the_wait_is_a_verdict_not_an_exit():
    shell = FakeShell([("run view 22 --json jobs", W.Done(1, "", TLS + "\n")), *_answers()])
    said: list[str] = []
    assert _watch(shell, said).watch() == 1
    main = _verdicts(said)["configuration main (CI)"].split("; ")
    assert main[0].startswith("passed") and main[1] == W.NO_JOBS.format(reason=TLS)


def test_gh_absent_at_the_start_refuses_at_once(tmp_path: Path):
    absent = tmp_path / "gh"
    said: list[str] = []
    w = W.Watch(VERSION, tmp_path, tmp_path, gh=str(absent), sleep=Clock().sleep, say=said.append)
    with pytest.raises(W.Refused) as e:
        w.watch()                                                              # the real shell: nothing to run
    assert e.value.code == 2 and e.value.message.startswith("release-watch: ")
    assert str(absent) in e.value.message and W.GH_FALLBACK in e.value.message
    calls: list[list[str]] = []

    def shell(cmd: list[str], **kw):
        calls.append(cmd)
        return W.run(cmd, **kw)
    with pytest.raises(W.Refused):
        W.Watch(VERSION, tmp_path, tmp_path, run=shell, gh=str(absent), sleep=Clock().sleep, say=said.append).watch()
    assert calls == [[str(absent), "auth", "token", "--no-refresh"]] and said == []


STUB_TOKEN = "stub-token-0f3c-never-said"


def test_the_check_before_the_first_look_asks_no_server_and_never_says_the_token():
    # gh holds a token: it is read locally (`auth token --no-refresh`, never `auth status`), and a
    # network failure is met by the looks as no news
    clock = Clock()
    asked: list[int] = []

    def system(cmd: list[str]):
        asked.append(1)
        return W.Done(1, "", TLS + "\n") if len(asked) == 1 else W.Done(0, json.dumps(_system_runs()))
    answers = [("auth token", W.Done(0, STUB_TOKEN + "\n")), (f"run list --commit {SYSTEM_SHA}", system), *_answers()]
    shell = FakeShell(answers)
    said: list[str] = []
    assert _watch(shell, said, clock).watch() == 0
    assert shell.calls[0] == ["/bin/gh", "auth", "token", "--no-refresh"] and shell.count("auth status") == 0
    assert f"release-watch: {W.UNANSWERED.format(reason=TLS, interval=60)}" in said
    assert not any(STUB_TOKEN in line for line in said)
    # no token: the error is said, never the output (a gh that printed a token and failed keeps it to itself)
    said = []
    shell = FakeShell([("auth token", W.Done(1, STUB_TOKEN + "\n", "no oauth token found for github.com\n")),
                       *_answers()])
    with pytest.raises(W.Refused) as e:
        _watch(shell, said).watch()
    assert e.value.code == 2 and STUB_TOKEN not in e.value.message
    assert not any(STUB_TOKEN in line for line in said) and shell.count("run list") == 0


def _too_old(cmd: list[str]):
    """A gh without ``auth token --no-refresh``; asked without the flag it would print the token."""
    if "--no-refresh" in cmd:
        return W.Done(1, "", f"{W.UNKNOWN_FLAG}\n\nUsage:  gh auth token [flags]\n")
    return W.Done(0, STUB_TOKEN + "\n")


def test_a_gh_too_old_for_no_refresh_is_not_asked_for_its_token_and_its_first_look_decides(capsys):
    shell = FakeShell([("auth token", _too_old), *_answers()])
    said: list[str] = []
    assert _watch(shell, said).watch() == 0
    assert shell.calls[0] == ["/bin/gh", "auth", "token", "--no-refresh"] and shell.count("auth token") == 1
    asked = [c[1:] for c in shell.calls if c[0] == "/bin/gh"]
    assert asked[1][:2] == ["run", "list"]                                       # gh's next call is the first look
    assert not any(STUB_TOKEN in line for line in said) and STUB_TOKEN not in capsys.readouterr().out


#: what gh says to a look it cannot make for want of a login: its exit code, its error
LOGGED_OUT = [(4, "To get started with GitHub CLI, please run:  gh auth login\n"
                  "Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.\n"),
              (1, "You are not logged into any GitHub hosts. To log in, run: gh auth login\n")]


@pytest.mark.parametrize(("rc", "err"), LOGGED_OUT)
def test_a_look_gh_refuses_for_want_of_a_login_refuses_at_once_and_is_never_waited_on(rc: int, err: str):
    clock = Clock()
    shell = FakeShell([("auth token", _too_old), ("run list", W.Done(rc, "", err)), *_answers()])
    said: list[str] = []
    with pytest.raises(W.Refused) as e:
        _watch(shell, said, clock).watch()
    assert e.value.code == 2 and e.value.message == f"release-watch: {W.NO_GH}"
    assert shell.count("run list") == 1 and clock.slept == []                    # no second look
    assert err.splitlines()[0] in said and _verdicts(said) == {}
    assert not any(STUB_TOKEN in line for line in said)


@pytest.mark.parametrize(("rc", "err"), LOGGED_OUT)
def test_a_perform_log_gh_refuses_for_want_of_a_login_is_the_refusal_not_an_unread_log(rc: int, err: str):
    # every look answered, then gh logged out by the time the perform job's log is read
    shell = FakeShell([("auth token", _too_old), ("run view 22 --job 99 --log", W.Done(rc, STUB_TOKEN + "\n", err)),
                       *_answers()])
    said: list[str] = []
    with pytest.raises(W.Refused) as e:
        _watch(shell, said).watch()
    assert e.value.code == 2 and e.value.message == f"release-watch: {W.NO_GH}"
    assert err.splitlines()[0] in said and not any(W.NO_LOG in line for line in said)
    assert not any(STUB_TOKEN in line for line in said) and STUB_TOKEN not in e.value.message


def test_a_perform_log_unread_for_any_other_reason_is_a_verdict():
    shell = FakeShell([("run view 22 --job 99 --log", W.Done(1, "", TLS + "\n")), *_answers()])
    said: list[str] = []
    assert _watch(shell, said).watch() == 1
    main = _verdicts(said)["configuration main (CI)"].split("; ")
    assert main[0].startswith("passed") and main[1] == W.NO_LOG


def test_the_gh_binary_is_found_on_path_or_at_its_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert W.gh_binary() == W.GH_FALLBACK
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\n")
    gh.chmod(0o755)
    assert W.gh_binary() == str(gh)


def test_the_recipe_is_a_wrapper_over_the_script():
    if not os.access(SCRIPT, os.X_OK):
        pytest.fail("scripts/release-watch is run as a script")
    summary = subprocess.run(["just", "--summary"], cwd=REPO, capture_output=True, text=True).stdout.split()
    assert "release-watch" in summary
    plan = [ln for ln in subprocess.run(["just", "-n", "release-watch", "0.1.9"], cwd=REPO, capture_output=True,
                                        text=True).stderr.splitlines() if ln.strip()]
    assert len(plan) == 1 and f'python "{SCRIPT}" "0.1.9" --root ' in plan[0] and "--config-root " in plan[0]


def test_a_develop_that_already_holds_mains_records_is_said_not_asked():
    shell = FakeShell(_answers(develop_behind="0\n"))
    said: list[str] = []
    assert _watch(shell, said).watch() == 0
    assert said[-2] == f"release-watch: {W.DEVELOP_LEVEL}"
    assert not any(line == f"release-watch: {W.FAST_FORWARD.format(root=CONFIG)}" for line in said)


def test_the_branch_runs_are_looked_for_at_the_commit_the_release_pushed():
    """The release puts the released families back on their ranges in a
    commit right after the tag, and pushes main and develop there: their
    runs are looked for at that commit, the tag's at the tag's own."""
    restored = "c" * 40
    shell = FakeShell([("refs/tags/v0.1.9^{commit}", W.Done(0, SYSTEM_SHA + "\n")),
                       ("v0.1.9..refs/heads/main", W.Done(0, f"{restored} {SYSTEM_SHA} after release 0.1.9: the released "
                                                             "families back on their ranges\n"))])
    w = W.Watch("0.1.9", SYSTEM, CONFIG, run=shell, gh="/bin/gh", sleep=Clock().sleep, say=[].append)
    commits = {e.label: e.commit for e in w.system_runs()}
    assert commits["system tag v0.1.9 (CI)"] == SYSTEM_SHA and commits["system main (CI)"] == restored
    assert commits["system develop (CI)"] == restored
