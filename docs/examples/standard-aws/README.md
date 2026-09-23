# standard-aws: the smallest AWS configuration

The smallest tree a team writes to get going on the AWS plugin set, in the
shape of a real configuration repository. Copy it, replace every
`REPLACE-ME` value, and it is a configuration:
`cs-image-system --root-dir <copy> validate`.

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
| the group and user builders | [`cfg/group-builders.yml`](cfg/group-builders.yml) | `okta-tf`, `okta-tf-ro` |
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

## Before the first run

- An AWS profile with a live session: the load reads the account's VPCs and
  security groups (`cfg/runtime-builders.yml` `credentials.profile_name`).
- The OPA API pair in the environment as `TF_VAR_<team>_key` and
  `TF_VAR_<team>_secret` (`<team>` with non-alphanumerics replaced by `_`):
  the group builder asserts they exist when it loads, not only at apply.
- The terraform modules reachable at `config.module_source_base`.
- `tests/test_docs_examples.py` in the cs-image-system repository loads and
  validates this tree with every cloud and tool stubbed, so it stays
  loadable as the code moves.

The GCE twin is [`../standard-gce/`](../standard-gce/README.md); every field
and variation is in [`../complete/`](../complete/README.md).
