# Quickstart: Every machine and every id recorded once

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

The acceptance. Steps 1 to 3 are this repository's; step 4 is the
reference configuration's, the operator's.

## Step 1: the ids refuse what collides

About 1 minute.

```sh
# step 1 -- box 1 of 1 -- v1
just test-one tests/test_recorded_ids.py tests/test_posix_ids.py -q
```

Expect every case passing: a POSIX id an external identity holds is
refused, naming both; an undeclared name takes its pool's lowest free id
and keeps it across reorderings and pool changes; a POSIX name an
external identity holds takes that identity's id; two external
identities that collide are refused; a removed name's id is never given
away; a dry run shows ids and records none.

## Step 2: one name, one machine, on POSIX

About 3 minutes.

```sh
# step 2 -- box 1 of 1 -- v1
just test-one tests/test_hostname_claims.py tests/test_provider_aliases.py tests/test_login_proof.py tests/test_canonical_names.py tests/test_alias_pool.py tests/test_generations.py tests/test_capabilities.py -q
```

Expect every case passing on the POSIX identity's recorded registry,
none on Okta's.

## Step 3: the acceptance tests with the Okta plugin absent

Once specification 008's Phase 4 has removed the plugin.

```sh
# step 3 -- box 1 of 1 -- v1   (about 25 minutes)
just test
```

Expect lint clean, the type check at zero errors, every test passing,
the isolated runs each `0 skipped`.

## Step 4: the reference records its ids and registers its machines

The operator's, after the release that carries this specification.

```sh
# step 4 -- box 1 of 1 -- v1   (about 3 minutes)
cd ../cs-image-system-testconfig && just record && git diff --stat meta-state/ids.yaml meta-state/servers.yaml
```

Expect `meta-state/ids.yaml` to hold every group's and user's id with
none changed from what the machines hold, and, after the next applying
run, `meta-state/servers.yaml` to hold every launched POSIX-owned
machine, with no relaunch.
