# 120. A provider-neutral terraform root

**Status: OPEN 2026-11-04. Waits for "do 120". First of the seam
stages. The single most valuable change for the forward goal, and the
one TODO.md's plan does not contain (REEXAMINE1 §5.7 step A;
REEXAMINE3 §3.1 flaw 1).**

tf-gcp and tf-docker subclass `TofuInstanceBuilder`,
`TofuStorageBuilder` and their two models from tf-ebs-instance (eight
cross-family import sites; both pyprojects pin it), and tf-ebs-instance
imports `aws_client` from aws-runtime, so installing the GCE or docker
roots installs boto3. The shared base is AWS-shaped: it requires and
configures the `aws` provider by default, renders `data "aws_vpc"` and
`resource "aws_security_group"`, dispatches mounts on `ebs`/`efs`, and
carries `_aws_client` and `_aws_cli_flags`; tf-gcp overrides ten of
its thirty methods and tf-docker thirteen to undo this, and `_ami_var`
leaked an AWS variable into a GCE root once. The `tofu` version
checker is registered only inside tf-ebs-instance.

1. The neutral base. `TofuInstanceBuilderBase`, `TofuStorageBuilderBase`,
   the two models and `TofuVersionChecker` move into hashicorp-utils,
   which already holds the HCL builder, the collector and the root
   mixin. **YOUR DECISION:** hashicorp-utils (the default) or a new
   `tofu-roots` package (one more project to release). The base keeps
   what no provider owns: the root layout, state-location resolution,
   the collector binding, the runner lines, the version check, and
   mount dispatch as an abstract hook. Everything AWS moves down: the
   default provider block, the vpc and security-group HCL,
   `_aws_client`, `_aws_cli_flags`, `_ami_var`, the ebs/efs dispatch.
2. tf-ebs-instance keeps its distribution name and becomes the AWS
   subclass beside tf-gcp and tf-docker. **YOUR DECISION:** no rename
   here (the default; a rename is a new PyPI project, a starter and
   reference change, and the standing decision on stable names);
   `tf-aws` is [§126](STAGE-126.md)'s to decide.
3. tf-gcp and tf-docker subclass the base; the overrides that existed
   only to undo AWS are deleted (counts before and after in the
   squash); their pyprojects drop tf-ebs-instance; tf-ebs-instance
   keeps aws-runtime, which is right for an AWS root.
4. The instance keys (`tofu`, `tofu-gce`, `tofu-docker`) do not
   change; that is a config change for every tree and [§126](STAGE-126.md)'s.
5. The proof: a test builds an environment from the lock without
   aws-runtime, tf-ebs-instance and boto3, imports tf-gcp and
   tf-docker, loads a tree declaring only a GCE or docker runtime, and
   passes `validate`. The closure script ([§124](STAGE-124.md) item 4) gains a
   cross-plugin edge report; the edges crossing a family read zero
   (tf-gcp → gcloud-runtime and tf-docker → docker-runtime are inside
   a family and stay).
6. Documents owed: the three root plugins' READMEs ("Prerequisites
   and integration"), hashicorp-utils README, DESIGN §3P's layered
   picture, PLUGINS.md.

**Out of scope**: packer's keys and the core's provider strings
([§121](STAGE-121.md)); gcloud-runtime's `AWS_ONLY_QUERY_KEYS` ([§121](STAGE-121.md)); any rename.

**Acceptance**: emission byte-identical for the fixture and the
reference; the isolation test green; `just test` green; the override
counts fall; one squash, branch kept, no bracket tags (one standing
bracket, §30's, is enough: REEXAMINE1 §3.4). Records: the squash;
this section goes at "merge 120".
