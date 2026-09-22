# The team's workload connection and role: setup checklist

*Stage 56 step 1. Executed by the operator in the Okta Privileged Access
(OPA) admin console as a security admin. Written so that another team, in
another organization, can follow it for their own copy of this repository:
every value that is ours is in the table and nowhere else. Once the
workload login has run on `main`, this checklist moves into
[docs/OPERATIONS.md](docs/OPERATIONS.md) and this file is removed.*

## What this builds, and what it deliberately does not

CI has to prove that the policies the system manages grant login to the
machines the system launches, by logging in the way a scientist does:
`sft ssh`, a short-lived OPA certificate, no static key. A GitHub-hosted
runner does that through OPA's **workload** route: the runner presents
GitHub's own OIDC token, OPA validates it against a **Workload
Connection**, maps it to a **Workload Role**, and a **Security Policy**
names that role as a principal for the servers.

Two objects are made by hand, and only two:

- **The connection** is the trust anchor for GitHub's token signer. It is
  scoped to the OPA team, and promoting it from draft to active is a
  security-admin act by design.
- **The role** is the one identity CI has. There is one CI, so there is
  one role, bound to the one connection. A role reaches nothing by itself;
  policies grant reach, and the policies are per group, so one role is
  exactly as much identity as CI needs.

Both are bootstrap objects like the OPA API key pair: created once, named
in the live configuration, referenced by the system from then on.

**Do not create a security policy by hand.** Policies are per group, and
the system manages them beside the `<group>_user` and `<group>_admin`
policies it already emits: one `<group>_v1_security_policy_ci` per group, a
copy of that group's user policy with the role as its only principal
([TODO.md](TODO.md) §56 step 3). The Terraform provider cannot write them
(okta/oktapam 0.7.1 has no workload resources and accepts only groups as
policy principals), so the system does it through the OPA API, the same
way it retires server registrations. Because the policies name the role by
id and are reconciled on every identity run, a recreated role is picked up
by the next run without editing any policy by hand.

The connection is created as a **draft** and left there. A draft validates
tokens but issues no usable access token, so nothing can be reached before
a real token from a real workflow run has been seen to pass (section 6).

## Values to enter

Every value below is decided from the repository or read from GitHub's
published discovery document; none is a guess. Another team replaces the
first four with their own.

| Item | Value | Source |
| --- | --- | --- |
| GitHub Owner | `infrastructurebuilder` | `git remote get-url origin` |
| `repository` claim | `infrastructurebuilder/cs-image-system-3` | same; GitHub's claim is always `owner/name` |
| `repository_owner` claim | `infrastructurebuilder` | same |
| Branch the proof runs from (`ref` claim, added later) | `refs/heads/main` | the `perform` job runs on `main` |
| JWKS URL | `https://token.actions.githubusercontent.com/.well-known/jwks` | [GitHub OIDC discovery document][gh-disc] |
| Connection name | `github-cs-image-system` | chosen here; URL-friendly |
| Role name | `cs-image-system-ci` | chosen here |
| Token TTL | 1 hour | the proof leg runs for minutes |
| OPA team | `nos-coastal-modeling-cloud-sandbox` | `sft list-teams`; `team:` on the okta-tf group builder |
| OPA address (for the CI step, not the console) | `https://noaa.pam.okta.com` | `sft list-teams` |

The claim names come from the `claims_supported` list in the discovery
document; the console labels a claim's name **Source field name**.

## What the names trust: the impersonation edge cases

The claims are matched **by name**, on purpose, so that a person can read
every value off their remote URL and so that the same document serves the
next organization. A name pin trusts *whoever controls that name at the
moment the token is minted*. Read the cases before deciding that is
acceptable for your team; it is for ours.

- **A fork.** A fork's workflow token names the fork as its `repository`
  (`someone-else/cs-image-system-3`), so it never matches. Pull requests
  from forks are not granted an OIDC token in any case.
- **A compromised workflow in the real repository.** It mints a real token
  that matches every pin, by name or by id. No claim closes this; the
  branch pin (`ref`, section 2) narrows it to code that reached `main`,
  and the per-group policies bound what the token can reach.
- **Rename and reuse inside the owner.** The owner renames this repository
  and a different repository takes the old name; its tokens now match. That
  is the owner's decision to make, and it belongs to whoever has
  repository-creation rights in the organization, not only to the person
  who did the rename. Treat a rename as a relocation (next section).
- **The owner's name recycled.** GitHub makes a deleted owner's name
  available again after its hold period. Whoever registers
  `infrastructurebuilder` afterwards can create `cs-image-system-3` and mint
  tokens that match both name claims. This is the one case outside the
  owner's control, and the one thing a name pin cannot close. It is closed
  by matching ids instead, at the cost of relocation (below):
  `repository_id` Equals the number `gh api repos/<owner>/<name> --jq .id`
  prints, and `repository_owner_id` Equals `gh api users/<owner> --jq .id`.
  An id survives a rename and a transfer and changes only when the
  repository is deleted and recreated. Our AWS federation pins ids for this
  reason; here we accept the residual risk in exchange for a document
  anyone can follow, and we say so.
- **`repository_owner` beside `repository`.** Redundant on paper, since
  `repository` already carries the owner, and kept deliberately: it makes
  the connection unusable by the same repository name under any other
  owner, so the role cannot be relocated to a different owner without
  editing the trust anchor on purpose.

## When the repository moves: the relocation edge cases

This repository will move. Both hand-made objects carry its name, so a
move is an edit to the trust anchor, done in an order that never leaves
CI able to reach the servers from nowhere and never leaves it unable to
reach them at all.

- **Rename inside the same owner.** `repository` changes, `repository_owner`
  does not, ids do not. Edit the connection's `repository` claim; nothing
  else moves.
- **Transfer to another owner** (GitHub's transfer feature). `repository`
  and `repository_owner` change; `repository_id` does not. Edit both claims
  and the connection's **GitHub Owner**. If the console does not allow the
  owner to be edited, this is the next case.
- **A new repository** (clone and push, or a new organization). Everything
  changes, ids included, so id pins would not have helped here. Follow the
  order below.

The order for a move that needs a new connection:

1. Create the new connection as a draft (section 1) with the new names.
2. Run the token test (section 6, step 6.2) from a workflow in the **new**
   repository against the draft. Do not activate until it passes.
3. Activate the new connection. Create the role bound to it (section 2), or
   rebind the existing role if the console allows.
4. Point the live configuration at the new names (`workload_connection`
   and `workload_role` on the okta-tf group builder) and run the identity
   lifecycle: the per-group CI policies are reconciled to the role's id.
5. Run the proof leg from the new repository and see it green.
6. Deactivate the old connection **last**, then delete the old role. Until
   this step the old repository can still log in, so do it the same day.

A rename that reuses the old name for something else is the reverse: the
old name must stop matching **before** anything else takes it, so edit the
claim first, then rename.

## 1. Workload Connection (draft)

Source: [Configure workload connection][wc]. Field labels below are quoted
from that page.

- [ ] 1.1 In the dashboard go to **DevOps Administration > Workload
      connections**.
- [ ] 1.2 Click **Create Workload Connection**.
- [ ] 1.3 Connection type: **GitHub Actions**.
- [ ] 1.4 **Enter your GitHub Owner**: `infrastructurebuilder`. Click
      **Next**.
- [ ] 1.5 **Connection name**: `github-cs-image-system`.
- [ ] 1.6 **Connection description**: `cs-image-system CI proves that the
      managed policies grant login`.
- [ ] 1.7 **Token TTL**: Amount `1`, Unit `hours`.
- [ ] 1.8 **JWKS URL** tab: if the field is empty, enter
      `https://token.actions.githubusercontent.com/.well-known/jwks`. If the
      GitHub Actions type pre-filled it, leave it exactly as shown.
- [ ] 1.9 **Required Claims**, first claim: Source field name
      `repository`, operator **Equals**, value
      `infrastructurebuilder/cs-image-system-3`.
- [ ] 1.10 **Required Claims**, second claim: Source field name
      `repository_owner`, operator **Equals**, value
      `infrastructurebuilder`.
- [ ] 1.11 Add no `ref` claim here. The branch pin goes on the role
      (section 2), where it can be tightened without touching the trust
      anchor.
- [ ] 1.12 If the form shows an **Audience** value anywhere, copy it down
      for the hand-back. GitHub's default audience is
      `https://github.com/infrastructurebuilder`; the CI step must request
      its token with whatever OPA expects.
- [ ] 1.13 Click **Create Workload Connection**. The connection is now a
      **draft**. Do **not** activate it yet.

## 2. Workload Role

Source: [Configure workload roles][wr]. Binding the role to a connection
that is still a draft works (confirmed 2026-09-22). If the console will not
let you add the connection to the role, the account you are using most
likely lacks the security-admin privilege the role needs; get that
privilege rather than working around it.

- [ ] 2.1 Go to **Security Administration > Workload roles** and create a
      role.
- [ ] 2.2 **Name**: `cs-image-system-ci`. **Description**: `The one identity
      cs-image-system's CI holds; policies are per group and system-managed`.
- [ ] 2.3 Under the requirement, **Select a workload connection**:
      `github-cs-image-system`.
- [ ] 2.4 Add no conditions now. The connection already pins the
      repository and its owner. The branch pin is added in step 6.5, after
      the proof has run from `main` once, so that the first runs can come
      from a feature branch.
- [ ] 2.5 Click **Save Workload role**.

## 3. Do not do

- [ ] 3.1 Do not create a security policy. The system creates one per
      group.
- [ ] 3.2 Do not activate the connection before step 6.3.
- [ ] 3.3 Do not add the role to `<group>_v1_security_policy_user` or any
      human policy, now or later. A machine principal inside a human policy
      means a CI change can lock a scientist out.

## 4. Hand-back

- [ ] 4.1 The connection name and the role name exactly as saved.
- [ ] 4.2 The audience value, if step 1.12 showed one.
- [ ] 4.3 Whether the role is bound to the connection. If the console
      would not let you add the connection to the role, say so: it most
      likely means the account needs greater privileges, and nothing
      downstream can start until the role is bound.

## 5. Another team following this document

- [ ] 5.1 Replace the first four rows of the values table with your owner,
      repository and branch, and choose your own connection and role names.
- [ ] 5.2 Decide, having read the impersonation cases, whether to pin by
      name or by id. By name is what the checklist does.
- [ ] 5.3 Put the two names on your okta-tf group builder as
      `workload_connection` and `workload_role`. Nothing in the system
      knows GitHub's owner or repository; only OPA does.

## 6. What happens next

- [x] 6.1 (Claude) The two names go into the live configuration on the
      okta-tf group builder beside `team`: `workload_connection:
      github-cs-image-system` and `workload_role: cs-image-system-ci`.
      **Done 2026-09-22** in the sibling's `cfg/group-builders.yml`.
- [x] 6.2 (Claude) A dispatch-only CI step requests GitHub's OIDC token
      (`permissions: id-token: write`, already granted to the live and
      perform jobs) and runs `sft workload authenticate --team
      nos-coastal-modeling-cloud-sandbox --connection github-cs-image-system
      --role-hint cs-image-system-ci --jwt-env <VAR>` against the
      **draft**. The command is documented in [CLI command for workload
      authentication][cli]. The run's log shows the token validate.
      **Done 2026-09-22 11:44Z**: `just opa-workload-probe` from the
      `OPA workload probe` workflow (run 35723142181, branch
      `feature/ci-logs-in`) -- claims `repository`, `repository_owner`, `aud`
      (`https://github.com/infrastructurebuilder`, GitHub's default; the form
      showed no audience) as pinned; `sft workload authenticate` exit 0 with
      a token on stdout even against the draft. The recipe is `just
      opa-workload-probe`; the runner gets the client from `just sft-install`.
- [x] 6.3 (Operator) Activate the connection: **Workload connections**, the
      draft, promote to active. From here the system refuses the proof
      when either named object is absent or the connection is still a
      draft. **Done 2026-09-22**: the state query reads it as ACTIVE.
- [x] 6.4 (Claude) The identity lifecycle learns the per-group CI policy
      (TODO §56 step 3), then the generic `sft ssh` proof leg lands as
      `cloud-verify ... sft` (steps 4 and 5) and runs from `main`.
      **Built 2026-09-22** on `feature/ci-logs-in`. The identity apply of
      2026-09-22 09:07 created the five CI policies (one per managed
      group) and a fresh state query reads every one as mirroring its user
      policy. The first live login waits on `coops-model` running.
- [x] 6.4a (Operator) **By hand, 2026-09-22 09:35**: `just ci-login-proof
      coops-model` from the code repo, as the enrolled client, passed all
      three checks (one registration, resolves, `id` over `sft ssh`) and
      recorded it. Run `sft login` first when the client's session has
      lapsed: `sft resolve --quiet` cannot open a browser and exits 126.
      As the client the grant is YOUR membership, so this proves the leg
      and the machine; the CI policy is proved by the workload login on
      `main`, which also shows the Unix account a workload lands in.
- [ ] 6.5 (Operator) After the first green run from `main`, add the branch
      pin to the role: condition Source field name `ref`, operator
      **Equals**, value `refs/heads/main`. Renaming the default branch is
      then a relocation of the same kind as a repository rename.
- [ ] 6.6 (Claude) This checklist moves into OPERATIONS and the file is
      deleted.

[wc]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-configure-workload-connection.htm
[wr]: https://help.okta.com/oie/en-us/content/topics/privileged-access/pam-configure-workload-role.htm
[cli]: https://help.okta.com/en-us/content/topics/privileged-access/pam-configure-workload-cli.htm
[gh-disc]: https://token.actions.githubusercontent.com/.well-known/openid-configuration
