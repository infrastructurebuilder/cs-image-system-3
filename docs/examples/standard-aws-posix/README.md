# standard-aws-posix: the smallest AWS configuration, with no Okta

The smallest tree a team writes to get going on the AWS plugin set when
its people are **POSIX accounts on the machines** rather than Okta and
OPA identities (stage 75): no Okta org, no OPA team, no identity root, no
credentials beyond AWS's. It is [`standard-aws`](../standard-aws/README.md)
with the identity swapped. Copy it, replace every `REPLACE-ME` value, and
it is a configuration: `just init`, then `just validate`.

What changes, against `standard-aws`:

- **The identity** is the posix plugin's: one group with a declared
  `gid:`, users with a declared `uid:` and their `public_keys:`. The group
  is baked into the instance image; every applying run makes the members'
  accounts, keys and the admins' sudo true on each running machine.
- **The login proof** logs in as the group's proof user (`csis_proof`, a
  service account) over ssh through Session Manager -- no public address
  -- with its private key from the `CSIS_PROOF_SSH_KEY` secret.
- **CI** has no Okta or OPA secrets and no OPA workload probe; the
  guide's Okta section does not apply.

What it declares (one of everything):

| Piece | File | Plugin (`type:`) |
| --- | --- | --- |
| the runtime | [`cfg/runtime-builders.yml`](cfg/runtime-builders.yml) | `aws` |
| the state backend | [`cfg/state-backends.yml`](cfg/state-backends.yml) | `s3` |
| the base image (OS builder) | [`cfg/os-builders.yml`](cfg/os-builders.yml) | `rhel` |
| the image builder | [`cfg/image-builders.yml`](cfg/image-builders.yml) | `packer-ebs` |
| the modification builders | [`cfg/mod-builders.yml`](cfg/mod-builders.yml) | `ansible`, `bash-remote` |
| the instance builder | [`cfg/instance-builders.yml`](cfg/instance-builders.yml) | `tofu` |
| the storage builder | [`cfg/storage-builders.yml`](cfg/storage-builders.yml) | `tf-aws-ebs` |
| the group and user builders | [`cfg/group-builders.yml`](cfg/group-builders.yml) | `posix` |
| the tools | [`cfg/executables.yml`](cfg/executables.yml) | |
| the global settings | [`cfg/_config.yml`](cfg/_config.yml) | |
| one group, two users | [`groups/groups.yaml`](groups/groups.yaml), [`groups/users.yaml`](groups/users.yaml) | |
| one storage | [`storages/storages.yaml`](storages/storages.yaml) | |
| one instance image | [`images/images.yaml`](images/images.yaml) | |
| one instance | [`instances/instances.yaml`](instances/instances.yaml) | |
| its playbook and script | [`playbooks/setup-node.yml`](playbooks/setup-node.yml), [`scripts/post-install.sh`](scripts/post-install.sh) | |
| one overlay | [`overlays/launch.yaml`](overlays/launch.yaml) | |

Every file opens with a comment saying what it declares and where
[CONFIGURATION.md](../../CONFIGURATION.md) documents it. Inside the files,
a `REPLACE-ME` value is a placeholder the team must replace (an account, a
VPC, a subnet, a bucket, a profile, an org); every other line that could
have been written differently carries a `DECISION` comment saying what was
decided and what the alternatives are.

## What is synthetic

- The two users are the frozen fixture's personas (`avery.alpha`,
  `casey.charlie`), encrypted entry by entry as `ENC[age:...]` values to the
  TEST identity committed beside this tree (`.age-identity`, public key
  `.age-recipient`). Export it to load the tree as it stands:
  `CSIS_CONFIG_IDENTITY=<copy>/.age-identity`. Encrypting to a committed
  key protects nothing; replace the recipient in `cfg/_config.yml`, run
  `cs-image-system reencrypt`, and drop the `path:.age-identity` allowance.
- The vendor-image owner (`764336703387`, the AlmaLinux OS Foundation's
  public publishing account) is a public fact, not a team value.

## What travels with the tree

This tree is a whole configuration REPOSITORY, not only the YAML. The
release carries it: `cs-image-system init-config <dir> --from standard-aws`
writes it out, and every part a team needs is then there:

| Part | What it is |
| --- | --- |
| `Justfile` | the single entry point: the five contract targets (`init`, `build`, `test`, `full-test`, `release`) and every daily and cycle recipe, each wrapping the released `cs-image-system` command against this tree |
| `CI_SETUP.md` | setting CI up from scratch (the same guide every starter carries; its OPA section does not apply here): the repository settings, the AWS and GCP federation, the OPA workload objects, CI's age identity, every secret the workflow reads, the proofs in order, and what each first-setup failure means; GitHub in full, GitLab not yet written |
| `.github/workflows/ci.yml` | the repository's own CI: `verify` (no secrets), `live` (read-only against the clouds), `perform` (on `main`, under the write role, records pushed back); every `REPLACE-ME` in it is a team value |
| `.githooks/pre-commit` | the public-safe gate on every commit; `just init` installs it |
| `tfmodules/` | the terraform modules the emitted roots call, at `module_source_base: tfmodules`; the release's, byte for byte (`cs-image-system init-config` writes them, and refreshes them after an upgrade) |
| `scripts/` | the tree's own modification scripts; the recipes need no helper (one tofu process at a time, the CI login token and the emission normaliser are commands of the CLI since stage 64) |
| `.gitignore` | the shell's exports, every credential file, the private mirror, tool residue; `generated/` and `meta-state/` ARE committed |
| `.csis-version` | the release that wrote the tree, which CI installs; `init-config` writes it (absent in this source copy) |

Before CI can run, most of what the guide's GitHub section describes can be
generated: `just bootstrap` interviews you (or takes every default with
`--quiet`), writes `bootstrap.yaml` at the root of this tree and
`generated/bootstrap/` from it -- terraform you apply once, a tfvars with
the answers, a script that sets the secrets from files. Every run
regenerates that directory from the answers; CI_SETUP.md section 3.0 says
what it makes and what is still yours.

The system itself is installed from a release, never cloned beside the
tree: `uv tool install cs-image-system` puts the command on `PATH`, or a
`pyproject.toml` here that depends on it and `export CSIS="uv run
cs-image-system"`. [DAILY_DRIVER.md](../../../DAILY_DRIVER.md) is the
narrative, from the first command on.

## Before the first run

- The released system: `uv tool install cs-image-system`, then `just init`
  (the hook, the plugin cache, a check that the command runs).
- An AWS profile with a live session: the load reads the account's VPCs and
  security groups (`cfg/runtime-builders.yml` `credentials.profile_name`).
- For CI's login proof, a key pair made for the proof user alone
  (`ssh-keygen -t ed25519 -f csis_proof -N ''`): its public half in
  `groups/users.yaml`, its private half the `CSIS_PROOF_SSH_KEY` secret.
- `CSIS_CONFIG_IDENTITY` pointing at an identity that opens the tree's
  `ENC[age:...]` values (`.age-identity` as it stands; your own after
  `reencrypt`).
- `tests/test_docs_examples.py` in the cs-image-system repository loads and
  validates this tree with every cloud and tool stubbed, and holds its
  `Justfile`, workflows, hook, scripts and modules to the release's, so it
  stays a working starter as the code moves.

The Okta twin is [`../standard-aws/`](../standard-aws/README.md), the GCE one
[`../standard-gce/`](../standard-gce/README.md); every field and variation is
in [`../complete/`](../complete/README.md).
