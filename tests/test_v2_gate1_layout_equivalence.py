# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 1 (DESIGN §4, phase A), DEMOTED TO DOCUMENTATION 2026-09-11:
``run --all`` reproduced the V1 generated
files under a declared path mapping.

``tests/fixtures/v1_baseline`` is a frozen snapshot of what the pre-V2 code
generated for the fixture -- then the live tree, since stage 28 the frozen
``tests/fixtures/config`` (pinned timestamp/USER, stubbed cloud + tools;
see ``tests/v2_support.py`` for the exact stubs -- the snapshot used the same
ones). Commit 56b787f passed this gate with strict content identity; later
phases deliberately ADD emission (identity outputs, remote-state references,
access points, provisioners, gated apply commands), so the invariant kept
here is order-preserving: **every V1 line survives, in order, in its V2
counterpart** (a subsequence check), and every V1 file maps to a V2 file.
The exact V2 emission is pinned separately by ``test_v2_golden.py``.

The path mapping (V1 -> V2):

    execution/<builder>/user-generation/...   -> identity/<builder>/user-generation/...
    execution/<builder>/group-generation/...  -> identity/<builder>/group-generation/...
    execution/<builder>/storage-generation/.. -> storage/<builder>/storage-generation/...
    execution/<builder>/image-generation/...  -> instance-image/<builder>/image-generation/...
    execution/<builder>/instance-generation/. -> instance-image/<builder>/instance-generation/...
    base/<builder>/image-generation/...       -> base-image/<builder>/image-generation/...
    execution/final_execution.sh              -> instance-image/run-instance-image.sh
    base/base_image_final_execution.sh        -> base-image/run-base-image.sh
    */.gitignore                              -> generated/.gitignore and each lifecycle's .gitignore

Content normalizers, each an intentional V2 delta with its plan reference:

* ``module_source_base`` now resolves relative to the configuration root
  (§3B relocation residue), so module ``source`` lines gain one ``../`` for
  the extra lifecycle directory level. Both spellings point at the same
  ``tfmodules/`` directory.
* packer build files listed sources in Python *set* order before V2 (a
  per-process nondeterminism); V2 sorts them. Both sides are canonicalized.
* the deferred ``tofu plan`` gained ``-out=tfplan`` so the apply gate (§3C,
  N19) can inspect the very plan that is applied.
* ``ami_name`` now carries the rendered run timestamp (§3F4 unique naming);
  V1 emitted the literal ``{{ execution.timestamp }}``.
* source ``tags`` maps gained lineage tags (§3F4); hcl2 re-aligns the
  existing keys, so assignments are compared single-spaced.
* ``data "okta_user"`` lookups gained ``skip_roles``/``skip_groups``
  (LEDGER.md item 1, least privilege); those lines are ignored.
* the OS update provisioner is policy-driven and records a package
  manifest (EXPLORE targeted updates); header and manifest tail are
  normalized.
* the AWS chain bakes AlmaLinux 10 (stage 13, 2026-09-10): the RHEL
  family's subscription-manager repo names carry major 10 where the
  baseline had 8.
* the dask playbook installs dask (stage 14, 2026-09-10): the baseline
  froze the placeholder; the copied playbook is compared against the
  config's current text.
* the design record was split out of V2_PLAN.md (2026-09-10) and that
  document has since been removed: emitted comments cite ``DESIGN``
  where the frozen baseline still says ``V2_PLAN``.
* the generated .gitignore keeps the LAST occurrence of a restated entry
  (2026-09-11): ``!.terraform.lock.hcl`` follows the configuration's
  ``.*`` instead of preceding it, and the configuration's target rule
  gained its trailing slash (``**/target/``).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from v2_support import FIXED_TIMESTAMP, FIXTURE_CONFIG, V1_BASELINE, V2Run, command_lines, tree

_CURRENT_DASK_PLAYBOOK = (FIXTURE_CONFIG / "setup_dask.yml").read_text()

PHASE_TO_LIFECYCLE = {
    "user-generation": "identity",
    "group-generation": "identity",
    "storage-generation": "storage",
    "image-generation": "instance-image",
    "instance-generation": "instance-image",
}

_MODULE_SOURCE_V1 = re.compile(r'source\s*=\s*"\.\./\.\./\.\./\.\./tfmodules/')
_MODULE_SOURCE_V2 = 'source = "../../../../../tfmodules/'


def _canonical_build_file(text: str) -> str:
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "sources = [")
        end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "]")
    except StopIteration:
        return text
    sources = sorted(l.strip().rstrip(",") for l in lines[start + 1:end])
    body = lines[end + 1:]
    chunks: list[list[str]] = []
    for line in body:
        if line.startswith("# Modifications") or not chunks:
            chunks.append([line])
        else:
            chunks[-1].append(line)
    tail = [c for c in chunks if not c[0].startswith("# Modifications")]
    provs = sorted("\n".join(c) for c in chunks if c[0].startswith("# Modifications"))
    return "\n".join(lines[:start] + ["sources = ["] + sources + ["]"] + provs
                     + ["\n".join(c) for c in tail])


def _normalize(text: str) -> str:
    # series rename basic-rhel-8 -> basic-rh-10 (2026-09-04, stage 1): the
    # baseline is a frozen pre-V2 snapshot, so the rename is declared here
    # (idempotent: the V2 side never contains the old name)
    text = text.replace("basic-rhel-8", "basic-rh-10")
    # the design record moved out of V2_PLAN.md into docs/DESIGN.md (2026-09-10)
    # and that document is now gone; the baseline is frozen, so it keeps the old
    # spelling and this mapping stays:
    # provisioner comments that cite the design record by file name now say
    # DESIGN; the frozen baseline says V2_PLAN (idempotent: the V2 side
    # never contains the old name)
    text = text.replace("V2_PLAN", "DESIGN")
    # AWS EL10 migration (2026-09-10, stage 13): the AWS chain bakes
    # AlmaLinux 10, so the subscription-manager repo names emitted by the
    # RHEL family carry the major 10; the baseline predates it (idempotent:
    # the V2 side never contains the EL8 names)
    text = text.replace("rhel-8-for-x86_64", "rhel-10-for-x86_64").replace("rhel-8-x86_64", "rhel-10-x86_64")
    # generated .gitignore: last occurrence wins (2026-09-11) -- the baseline
    # froze the negation ahead of `.*`; and the fixture's target rule now
    # ends in a slash (idempotent: the V2 side never has the old order or
    # the bare `**/target`)
    text = text.replace("!.terraform.lock.hcl\n.*\n", ".*\n!.terraform.lock.hcl\n")
    text = re.sub(r"\*\*/target(?!/)", "**/target/", text)
    # the dask playbook installs dask (2026-09-10, stage 14): the baseline
    # froze the placeholder playbook the config carried until the first live
    # post-bake test found the "dask" image had no dask; the playbook is
    # configuration copied through, not emission, so its CURRENT text is the
    # expectation (idempotent: the V2 side never contains the placeholder)
    placeholder = (
        "---\n# Fixture playbook: installs a dask stack on the image under construction.\n"
        "- name: Set up dask\n  hosts: all\n  become: true\n  tasks:\n"
        "    - name: Placeholder dask setup task\n      ansible.builtin.debug:\n"
        '        msg: "dask setup would run here"\n')
    if placeholder in text:
        text = text.replace(placeholder, _CURRENT_DASK_PLAYBOOK)
    # tcmet reconciliation (2026-09-05): four OPA users were added to the
    # config to mirror live group membership. The frozen baseline predates
    # them, so strip their okta_user lookup blocks from the V2 side (the
    # baseline never contains these names, so this is a no-op on V1 content).
    text = re.sub(
        r'# Lookup of Okta user (?:parker|quinn_quebec|rileyr|sawyer) by login\n'
        r'data "okta_user".*?\n\}\n',
        "", text, flags=re.DOTALL)
    # ...and the tcmet group's reconciled members/admins map back to the
    # baseline's empty/minimal lists (these exact user-name lists appear only
    # in the tcmet group file, so the replacement cannot touch other groups).
    text = re.sub(r'(members\s*=\s*)\["parker", "quinn_quebec", "rileyr"\]', r"\1[]", text)
    text = re.sub(r'(admins\s*=\s*)\["lennox\.lima", "avery\.alpha", "sawyer"\]',
                  r'\1["avery.alpha"]', text)
    text = _MODULE_SOURCE_V1.sub(_MODULE_SOURCE_V2, text)
    # V1 never resolved the run timestamp in ami_name (unique naming was broken,
    # §3F4); V2 renders it. Compare against the pinned run timestamp.
    text = text.replace("{{ execution.timestamp }}", FIXED_TIMESTAMP)
    text = re.sub(r'source\s*=\s*"\.\./\.\./\.\./\.\./\.\./tfmodules/', _MODULE_SOURCE_V2, text)
    # hcl2 vertically aligns map keys; extra V2 keys (lineage tags) re-pad the
    # V1 ones, so compare with single-spaced assignments.
    text = re.sub(r"[ \t]+=[ \t]+", " = ", text)
    # a V1 source with no tags at all (`tags = {}`) now opens a lineage-tag map
    text = text.replace("tags = {}", "tags = {")
    # least privilege (LEDGER.md item 1): user lookups now skip roles/groups
    text = re.sub(r"^\s*skip_(roles|groups) = true\n", "", text, flags=re.M)
    # per-instance machine_type (stage 1 step 6 finding 25): V1 hardcoded the
    # runtime default; V2 lets the instance declare its size, so compare the
    # line's position, not the value
    text = re.sub(r'^(\s*)instance_type = "[^"]+"', r'\1instance_type = "<machine-type>"',
                  text, flags=re.M)
    # IaC-managed enrollment tokens (PLAN.md): V1 bound the operator var
    # alone; V2 falls back to the identity root's token by reference --
    # compare the binding's position, not its expression
    text = re.sub(r'^(\s*"sft_enrollment_token" = )\(?var\.sft_enrollment_token[^\n]*',
                  r"\1<token-expr>", text, flags=re.M)
    # input fingerprints and the declared-storage-types tag move whenever
    # declared capabilities change (GCP readiness added pd/gcs); compare the
    # lines' positions, not their values
    text = re.sub(r'^(\s*csis_fingerprint\s*= )"[0-9a-f]{16}"', r'\1"<fp>"', text, flags=re.M)
    text = re.sub(r'^(\s*csis_storage_types\s*= )"[a-z0-9,]+"', r'\1"<types>"', text, flags=re.M)
    # targeted updates (EXPLORE): the OS update provisioner is policy-driven
    # (auto_update == policy full) and appends the package-manifest step
    text = re.sub(r"# OS update for base image (\S+) \(policy=full, [^)]*, (\w+)\)",
                  r"# Package-level OS update for base image \1 (auto_update, \2)", text)
    # finding 42: the targeted-package update gained a dnf5-safe check-update
    # guard; strip the guard so the V1 plain form matches its V2 counterpart
    text = re.sub(r'rc=0; sudo dnf -q check-update[^;]* \|\| rc=\$\?; '
                  r'if \[ \\"\$rc\\" -eq 100 \]; then (.*?); '
                  r'elif \[ \\"\$rc\\" -ne 0 \]; then exit \\"\$rc\\"; fi',
                  r"\1", text)
    text = re.sub(r', "sudo mkdir -p /var/lib/csis", "\( rpm -qa[^\]]*\]', "]", text)
    if "sources = [" in text:
        text = _canonical_build_file(text)
    return text


def _is_subsequence(needle: list[str], haystack: list[str]) -> tuple[bool, str | None]:
    it = iter(haystack)
    for line in needle:
        for candidate in it:
            if candidate == line:
                break
        else:
            return False, line
    return True, None


def map_v1_path(kind: str, rel: str) -> str | None:
    """V1 snapshot path -> V2 generated path (None = handled separately)."""
    rel = rel.replace("basic-rhel-8", "basic-rh-10")   # series rename (stage 1)
    parts = Path(rel).parts
    if rel == ".gitignore":
        return None
    if kind == "execution":
        if rel == "final_execution.sh":
            return None
        builder, phase = parts[0], parts[1]
        return str(Path(PHASE_TO_LIFECYCLE[phase], builder, *parts[1:]))
    if kind == "base":
        if rel == "base_image_final_execution.sh":
            return None
        return str(Path("base-image", *parts))
    raise AssertionError(kind)


# Gate 1 was MET and V1 was retired on 2026-09-11 (its CLI placeholders are
# gone; nothing in the system emits the V1 layout any more). The five
# equivalence tests below are therefore DOCUMENTATION of what gate 1 proved --
# that every V1 line survived, in order, in its V2 counterpart -- rather than an
# enforced gate. The frozen baseline stays on disk as the evidence, and today's
# emission is pinned by the golden fixture instead. Delete the `_DEMOTED` marker
# to re-enforce them.
_DEMOTED = pytest.mark.skip(
    reason="gate 1 demoted to documentation on 2026-09-11: V1 is retired and the "
           "golden fixture pins emission now; the baseline is kept as evidence")


@pytest.fixture(scope="module")
def v2_output(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        run = V2Run(tmp_path_factory.mktemp("gate1"), mp)
        summary = run.run("all", apply=True)
        assert summary.ok, summary.error
        yield run, tree(run.generated)
    finally:
        mp.undo()


@_DEMOTED
def test_every_v1_line_survives_in_order_in_its_v2_file(v2_output):
    _, v2 = v2_output
    v1_exec = tree(V1_BASELINE / "execution")
    v1_base = tree(V1_BASELINE / "base")
    assert v1_exec and v1_base, "baseline fixture missing"
    problems: list[str] = []
    for kind, files in (("execution", v1_exec), ("base", v1_base)):
        for rel, content in files.items():
            target = map_v1_path(kind, rel)
            if target is None:
                continue
            if target not in v2:
                problems.append(f"missing in V2: {kind}/{rel} -> {target}")
                continue
            ok, lost = _is_subsequence(_normalize(content).splitlines(),
                                       _normalize(v2[target]).splitlines())
            if not ok:
                problems.append(f"{kind}/{rel} -> {target}: V1 line lost: {lost!r}")
    assert not problems, "\n".join(problems)


@_DEMOTED
def test_v1_unchanged_files_are_byte_identical(v2_output):
    """Files V2 had no reason to touch stay identical (not merely a superset):
    users root, group module calls and variables, backend partial configs,
    packer variables/plugins/setup files and copied playbooks."""
    _, v2 = v2_output
    v1_exec = tree(V1_BASELINE / "execution")
    v1_base = tree(V1_BASELINE / "base")
    untouched = (
        "user-generation", "-group-generation-group-", "-vars.tf", ".tfbackend.hcl",
        "-vars.pkr.hcl", "-plugins.pkr.hcl", "-ebs-ansible-setup.pkr.hcl", ".yml",
    )
    checked = 0
    for kind, files in (("execution", v1_exec), ("base", v1_base)):
        for rel, content in files.items():
            target = map_v1_path(kind, rel)
            if target is None or not any(tok in rel for tok in untouched):
                continue
            assert _normalize(content) == _normalize(v2[target]), f"{kind}/{rel} changed"
            checked += 1
    assert checked >= 20


@_DEMOTED
def test_runner_scripts_carry_the_v1_deferred_commands(v2_output):
    _, v2 = v2_output
    v1_exec_cmds = command_lines((V1_BASELINE / "execution" / "final_execution.sh")
                                 .read_text().replace("basic-rhel-8", "basic-rh-10"))
    v1_base_cmds = command_lines((V1_BASELINE / "base" / "base_image_final_execution.sh")
                                 .read_text().replace("basic-rhel-8", "basic-rh-10"))
    # The V1 base snapshot script inherited the execution run's commands through
    # a class-level dict (a bug fixed in V2): remove one occurrence of each
    # leaked command so only the base run's own packer block counts.
    leaked = list(v1_exec_cmds)
    own: list[str] = []
    for cmd in v1_base_cmds:
        if cmd in leaked:
            leaked.remove(cmd)
        else:
            own.append(cmd)
    assert not leaked, "baseline base script lacks the expected leaked prefix"
    norm = lambda c: c.replace("tofu plan -input=false -out=tfplan", "tofu plan -input=false")  # noqa: E731
    v2_exec = [norm(c) for c in command_lines(v2["instance-image/run-instance-image.sh"])]
    ok, lost = _is_subsequence(v1_exec_cmds, v2_exec)
    assert ok, f"V1 deferred command lost: {lost}"
    v2_own = [c for c in command_lines(v2["base-image/run-base-image.sh"])
              if "pckr-gce-ans" not in c]  # the GCE bake is a V2 addition
    assert v2_own == own


@_DEMOTED
def test_generation_time_commands_are_identical(v2_output):
    run, _ = v2_output
    v1 = (V1_BASELINE / "execution-commands.txt").read_text() \
        .replace("basic-rhel-8", "basic-rh-10").splitlines()
    v1 += (V1_BASELINE / "base-commands.txt").read_text() \
        .replace("basic-rhel-8", "basic-rh-10").splitlines()
    # Same commands in the same working directories (relative to the lifecycle
    # dir, exactly as they were relative to generated/ before); the identity
    # and storage lifecycles simply run first now.
    v2_journal = [c.replace(" -reconfigure", "") for c in run.journal    # stage 39: init reconfigures
                  if "pckr-gce-ans" not in c and "gcp-pd" not in c and "gcp-gcs" not in c
                  and "tofu-gce" not in c]  # GCE roots are V2 additions
    assert sorted(v2_journal) == sorted(v1)


@_DEMOTED
def test_gitignore_written_at_root_and_per_lifecycle(v2_output):
    _, v2 = v2_output
    v1_ignore = _normalize((V1_BASELINE / "execution" / ".gitignore").read_text())
    assert _normalize(v2[".gitignore"]) == v1_ignore
    for lc in ("identity", "storage", "base-image", "instance-image"):
        assert _normalize(v2[f"{lc}/.gitignore"]) == v1_ignore


def test_generated_gitignore_keeps_the_last_occurrence_of_a_restated_entry(v2_output):
    """A configuration that restates a built-in entry after its own `.*`
    means it there: gitignore reads later rules as overriding earlier ones,
    so the emitted file must keep the LAST occurrence (2026-09-11: the
    first-wins rule silently dropped `!.terraform.lock.hcl` back ahead of
    `.*`, and every lock file stayed ignored)."""
    run, _ = v2_output
    lines = (run.generated / ".gitignore").read_text().splitlines()
    assert lines.count("!.terraform.lock.hcl") == 1
    assert lines.index(".*") < lines.index("!.terraform.lock.hcl") < lines.index("!.gitignore")
    assert len(lines) == len(set(lines))
