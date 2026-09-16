# The frozen test fixture

This tree is **owned by the tests** and is not a live configuration. Its
layout is that of a real configuration root; nothing here changes because
a cloud changed, and no run ever commits into it.

- It carries **no `meta-state/`** (records of live cloud resources) and no
  generated output; `tests/v2_support.py:copy_config` copies it into a
  temporary directory for every test. Its instance subjects (`test`,
  `test2`, `gce-test`) are declared in `instances/instances.yaml`;
  `gce-test` is not ephemeral here, and a test that wants ephemerality
  declares it.
- `tests/fixtures/v2_golden/` is exactly what `run --all` emits over it
  (see [GOLDEN.md](../../../GOLDEN.md)); a change here moves the golden.
- Its `module_source_base: ../tfmodules` resolves relative to the copied
  tree, so a copy needs `tfmodules/` beside it (`copy_config` callers that
  run terraform copy it).
- The overlays under `overlays/` are test devices: nothing reads them
  unless an invocation names one with `--overlay`.
- The four modification files at the root (`setup_dask.yml`,
  `setup_data_science.yml`, `modify_image.yml`, `mod_image.sh`) are
  provisioned content whose hash is part of image lineage: editing even a
  comment in them moves the golden and, in a live tree, re-bakes images.

The live configuration lives in its own repository
(`cs-image-system-testconfig`, checked out beside this repo) and is what the
Justfile's `cloud-*`/`gce-*` recipes drive. Nothing under `tests/` reads it;
`tests/test_fixture_independence.py` enforces that.

The rosters here (`groups/users.yaml`, `groups/group-*.yaml`) are encrypted
entry by entry as `ENC[age:...]` values to the fixture's own TEST identity,
`.age-identity` (committed on purpose; its public key is `.age-recipient`
and `cfg/_config.yml` `encryption.recipients`). The harness exports it as
`CSIS_CONFIG_IDENTITY`, so the suite needs nothing from the environment,
and decryption happens at load. Encrypting with a committed key protects
nothing — it exercises the mechanism — so the people are **synthetic**:
nineteen personas with phonetic-alphabet surnames (`avery.alpha` ...
`sawyer`), explicit addresses on example domains and derived ones on
`@example.invalid` (`cfg/group-builders.yml` `default_user_email_template`),
in the shape of a real roster: the same explicit/derived split, one
mixed-case username, the same memberships. `tests/test_fixture_personas.py`
pins that a real roster cannot return unnoticed, and the fixture's
`public_safe.allow` carries no real domain.
