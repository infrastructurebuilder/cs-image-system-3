# The golden fixture

*What `tests/fixtures/v2_golden/` is, how it is produced, and why nearly every
change in this repository is judged against it.*

## In one sentence

The golden is a pinned, committed copy of everything the system emits for one
known configuration, so that any change to the code can be asked a single
question: **did this change what the system produces?**

## What is in it

125 files under [tests/fixtures/v2_golden/](tests/fixtures/v2_golden/), in two
subtrees.

`generated/` — the emitted infrastructure-as-code, one directory per lifecycle:

| Lifecycle | Files |
| --- | --- |
| `identity` | 14 |
| `storage` | 17 |
| `base-image` | 14 |
| `instance-image` | 71 |
| `release` | 3 |
| `retention` | 1 |

`meta-state/` — three of the system's records: `identity.yaml`, `storage.yaml`
and `launch-params.yaml`. These are the read-models and launch parameters the
run writes. The other meta-state files are deliberately absent, for the reason
in "What it does not cover" below.

## How it is produced

```sh
just golden-regen        # -> uv run python tests/golden.py
```

[tests/golden.py](tests/golden.py) does a real run, not a simulation:

1. It builds a `V2Run`, which copies the test fixture into a throwaway
   directory. The copy excludes `generated/` and
   `meta-state/`, so every run starts from nothing and emits from scratch.
2. It runs **every** lifecycle (`run("all", apply=True)`) and asserts the run
   succeeded.
3. It reads the whole emitted tree plus the meta-state the run wrote.
4. It drops `run-summary.json` and `runs.yaml`, which carry run-local detail
   (timestamps, run ids) and would differ on every run by design. Nothing
   else is normalised: the emitted runner scripts reach the configuration
   root through a variable defined relative to the script, so the emission
   names no absolute path and is compared verbatim.

## How it is enforced

[tests/test_v2_golden.py](tests/test_v2_golden.py) regenerates the emission in
memory and compares it against the committed fixture file by file. It reports
three kinds of problem separately:

- a file in the golden that the run no longer produces,
- a file the run produces that the golden does not have,
- a unified diff for any file whose content changed.

So a failure tells you exactly what moved, not merely that something did.

## Why it matters

This is the project's strongest safety net. A change that touches a hundred
files can be accepted on one fact: the golden came back byte-identical.
That is a far stronger statement than "the tests pass": it says the
system's output did not move by a single byte, on both the AWS and GCE
runtimes, so the change cannot have altered what would be applied to a
cloud account. Ports of the model layer, replacements of the mapping
layer and repository-wide renames have all been accepted that way.

The inverse is just as useful. When the golden *does* move, the diff is the
specification of what you changed.

## Using it

**A byte-identical golden is the acceptance proof for a refactor.** If you
believe a change is behaviour-neutral, regenerate and expect no diff. If one
appears, the change was not neutral.

**A moved golden must be read, never accepted.** `just golden-regen` will
happily write whatever the code now produces. Regenerating to make a test pass
is how a defect becomes the expected output. Read the diff, decide it is what
you meant, and say so in the commit message.

**Two traps found the hard way:**

1. *Provisioned content is hashed.* Rewriting even a comment inside a file that
   is provisioned onto an image (a playbook, a script) changes that
   modification's content hash, which changes the image fingerprint, which
   would re-bake every affected image on both clouds. Documentation passes
   and licence headers therefore never touch provisioned content. If the
   golden shows a `content_hash` or `csis_fingerprint` moving, stop and work
   out why.
2. *A copy of the configuration needs `tfmodules/` beside it.* The generated
   terraform roots reach their modules by a relative path that climbs out of
   the configuration tree. A copy without `tfmodules/` as a sibling fails at
   `tofu init`, and the identity roots do that during generation even in a dry
   run.

## What it does not cover

The golden proves **what the system emits**, not what a cloud does with it. It
says nothing about whether an apply succeeds, whether an image boots, or
whether a storage volume actually mounts. Those are proven separately, by
gated live runs, whose evidence is the live configuration's `meta-state/`
(image tests, verifications, releases).

It also holds only three meta-state files. The records that pin live cloud
resources — `lineage.yaml`, `pins.yaml`, `storage-state.yaml` and the rest —
are excluded from the fixture copy on purpose, because they describe real AMIs,
GCE images and volumes. A test must never inherit them, and the golden must not
encode them.

Finally, the golden is only as meaningful as the configuration behind it is
stable. It pins the emission of one specific tree; when that tree changes, the
golden changes with it, which is why a configuration used for live work and a
configuration used as a test fixture pull in opposite directions.
