# 122. Storage and identity leave the core

**Status: OPEN 2026-11-04. Waits for "do 122", after §121.**

`launch_params.py` hardcodes the EBS device list, the NVMe by-id loop
and the GCE device name and branches on `ebs`, `gce-pd`, `efs`,
`filestore`, `s3`, `gcs`; `ansible_launch.py` does the same
(REEXAMINE3 §3.2). The `User` model carries thirty Okta profile fields
and a dead `as_profile()`; `workload_token.py`, `provider_aliases.py`,
`state_query`'s OPA section and about 180 lines of `cli.py` hardcode
`sft`, `/etc/sft/sftd.yaml` and the OPA workload variables.
posix-identity and okta-opa each hardcode the other's
`/usr/local/sbin/csis-group-login`. Every runtime, storage and
identity plugin branches `fam in ("debian", "ubuntu")` and assumes the
rest is `yum`, which breaks the registered alpine type.

1. Storage owns its device and mount lines: the storage protocol gains
   a device path, a mount snippet and launch metadata (names in the
   contract's style); tf-ebs-instance (ebs, efs, s3), tf-gcp (pd,
   filestore, gcs) and tf-docker (volume) implement them;
   `launch_params.py` and `ansible_launch.py` call the hooks and keep
   only the assembly of the launch script.
2. Identity owns its fields and commands: the `User` model keeps what
   every identity reads (name, email, keys, posix); the Okta profile
   fields become okta-opa's extension of the user model;
   `as_profile()` goes. `workload_token.py`, the sftd part of
   `provider_aliases.py`, `state_query`'s OPA reading and the `verify
   login` and `workload` commands move into okta-opa. **YOUR
   DECISION:** a plugin may register CLI commands (the default,
   through an entry point group the engine owns) or those commands
   stay in `system` and call okta-opa through the protocol.
3. The login hook path is one name declared by the identity protocol
   and read by both plugins; posix-identity's PAM hook stays and its
   README says which OPA behaviour it works around.
4. The OS type owns the package manager: default-os's type gains
   package install, package update and service enable; every plugin
   that writes such a shell line calls it; alpine's `apk` works by
   construction and a dry alpine bake proves it.
5. Documents: CONFIGURATION (user fields by identity), the okta-opa,
   posix-identity, default-os and three root READMEs, DESIGN §2 (one
   new ruling: device and mount lines are the storage's; package
   manager lines are the OS's).

**Out of scope**: the OPA group model; the sftd enrollment flow's
behaviour; any change to what the launch script does on a machine.

**Acceptance**: emission byte-identical (the launch scripts and the
mount lines are in the golden); the alpine dry bake green; the §121
grep-test extended with `okta`, `sft`, `oktapam`, `yum`, `dnf`, `apt`,
`apk` over `contract`, `base` and `system`; `just test`; one squash,
branch kept. Records: the squash; this section goes at "merge 122".
