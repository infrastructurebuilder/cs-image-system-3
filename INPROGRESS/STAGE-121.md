# 121. The core names no runtime

**Status: OPEN 2026-11-04. Waits for "do 121", after §120.**

"Every opinion about a specific cloud lives at the edge" (DESCRIPTION)
is not yet true (REEXAMINE1 §3.3, §5.3; REEXAMINE3 §3.2). `preflight`
recognises sessions by provider substring (`"aws" in provider`,
`"docker"`, `"gc"`) and reads the AWS SSO cache, the gcloud ADC file
and `docker version` itself; `load_failures` matches botocore, gcloud
and docker exception strings; `emission.py` hardcodes `KNOWN_RUNTIMES`
and the `ami-` and `projects/…/images/` regexes; `base` ships the
vendor image catalogue for all three clouds; the bootstrap's GitHub
section hardcodes the AWS, GCP and docker secret names; packer carries
three per-runtime keys whose models differ "only in name" while the
runtime hooks packer needs already exist on the runtime base;
`LEGACY_SOURCE_TYPE = "amazon-ebs"` is a core constant; gcloud-runtime
carries `AWS_ONLY_QUERY_KEYS` to filter the core's AWS vocabulary out.
A fourth runtime edits the core in each place.

1. One packer key. `packer` builds images for every runtime; the
   source type, source blocks and bake variables come from the
   runtime's existing hooks (`packer_source_type`,
   `packer_source_blocks`, `bake_ansible_vars`). `packer-gce` and
   `packer-docker` stay as aliases for one release with a `validate`
   notice naming the replacement; `LEGACY_SOURCE_TYPE` goes.
2. Preflight is a hook. The runtime and state-backend protocols gain
   a session check (named in the contract's style) that returns a
   verdict and a message; the SSO cache reading, `aws sts`, the ADC
   file and `docker version` move into their plugins; `preflight.py`
   iterates the declared runtimes and backends and prints what they
   return; `load_failures.py`'s exception matching moves the same way,
   each plugin classifying its own exceptions.
3. The image-source catalogue splits by runtime and ships as package
   data of aws-runtime, gcloud-runtime and docker-runtime;
   `image_sources.py` merges what the loaded runtimes contribute.
   **YOUR DECISION:** a runtime protocol method (the default) or an
   entry point. `KNOWN_RUNTIMES` and the image-reference regexes in
   `emission.py` become one runtime hook.
4. The bootstrap: the GitHub section's secret names come from each
   runtime's and backend's bootstrap contribution (`facts.py` and
   `github.py` keep the mechanism and lose the names), the shape the
   standing decision on the bootstrap already asks for.
5. gcloud-runtime's `AWS_ONLY_QUERY_KEYS` goes once the core stops
   passing AWS keys (follows item 3).
6. The test: a grep-test over `contract`, `base` and `system` for the
   provider words (`aws`, `ami-`, `boto`, `sso`, `amazon-ebs`,
   `gcloud`, `gce`, `docker`) with a committed exception list; the
   stage ends when the list holds only what the operator accepts.
   **YOUR DECISION:** empty (the default) or the CLI's help text only.
7. Documents: CONFIGURATION (the packer key and its aliases),
   OPERATIONS (preflight), the three runtime READMEs, packer README,
   PLUGINS.md's "what a runtime provides".

**Out of scope**: storage mounts and identity ([§122](STAGE-122.md)); the OS family
branching ([§122](STAGE-122.md)).

**Acceptance**: emission byte-identical for trees that keep the old
packer keys (the fixture and the reference keep them this stage;
**YOUR DECISION:** the reference moves to `packer` in the same take,
default no); the grep-test green with its list; the isolation test of
§120 still green; `just test`; one squash, branch kept. Records: the
squash; this section goes at "merge 121".
