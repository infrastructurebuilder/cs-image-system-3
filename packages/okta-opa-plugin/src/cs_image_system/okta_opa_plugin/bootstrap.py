# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The Okta and OPA section of the bootstrap (stage 70 step 6; CI_SETUP.md 3.5).

A read-and-verify section with no terraform module, because by decision
nothing in it is created: the OPA workload connection and role are made in
the console by a DevOps and a security admin (D4), the Okta API services app
by the org's Okta admins (D5, D9), the OPA service user and its key pair by
hand (D10). What the bootstrap does instead is look, and say exactly what is
left:

* the workload connection and role -- named by the ``okta-tf`` group builder,
  else found by what they require (a connection whose conditions name this
  repository, the role bound to it), else suggested -- read through the OPA
  API the system already uses (``GET .../connections/workloads`` and
  ``.../workload-roles``): present, ACTIVE, requiring ``repository`` and
  ``repository_owner``, the role bound to it and pinned to the production
  branch's ``ref``;
* the Okta API services app, asked for a token with its own key and scopes
  exactly as the ``okta`` provider asks (``okta_app_check``).

Every check is an OBSERVED question: each interview asks the world again,
and an answer recorded earlier is only the fallback when the world cannot be
asked; with neither, ``--quiet`` refuses the question by name. Each check
that fails becomes the matching step of CI_SETUP.md 3.5 under "By hand,
still"; none refuses the interview, since a draft connection is a normal
state on the way. The bootstrap never edits ``cfg/``: names the group
builder lacks are printed as the lines to add.
"""

from __future__ import annotations

from typing import Any, Callable

from cs_image_system.base.bootstrap.facts import Facts, collect, real
from cs_image_system.base.bootstrap.questions import Answers, Question, Rendered, Section

from . import okta_app_check

GUIDE = "CI_SETUP.md 3.5"
UNASKABLE_OPA = ("OPA could not be asked: the team's key pair is not in the environment "
                 "(TF_VAR_<team>_key / TF_VAR_<team>_secret), or the API did not answer")
UNASKABLE_OKTA = ("the Okta app could not be tried: OKTA_API_CLIENT_ID, OKTA_API_PRIVATE_KEY and "
                  "OKTA_API_SCOPES are not all in the environment")


# ------------------------------------------------------------------ the tree
def okta_builder(facts: Facts) -> dict[str, Any] | None:
    """The tree's managed OPA group builder (``type: okta-tf``), first one."""
    builders = collect(facts.config_root / "cfg", "group_builders")
    return next((b for b in builders if str(b.get("type", "")).lower() == "okta-tf"), None)


def _builder(facts: Facts, key: str) -> str | None:
    return real((okta_builder(facts) or {}).get(key))


def api_host_default(facts: Facts, answers: Answers) -> str | None:
    raw = (okta_builder(facts) or {}).get("api_host")
    org = answers.get("org")
    if raw and "{{" in str(raw):                   # the starter's template: render the one variable it uses
        raw = str(raw).replace("{{ this.org }}", str(org)) if org and "{{ this.org }}" in str(raw) else None
    return real(raw) or (f"https://{org}.pam.okta.com" if org else None)


# -------------------------------------------------------------- the world
#: Seams the tests replace: the OPA listings and the Okta app check.
def _listings(api_host: str, team: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    from .opa_gids import OpaGidResolver, credentials_from_env
    try:
        key, secret = credentials_from_env(team)
    except ValueError:
        return None
    client = OpaGidResolver(api_host, team, key, secret)
    connections, roles = client.workload_connections(), client.workload_roles()
    return None if connections is None or roles is None else (connections, roles)


LISTINGS: Callable[[str, str], tuple[list[dict[str, Any]], list[dict[str, Any]]] | None] = _listings
CHECK_APP: Callable[..., okta_app_check.AppCheck] = okta_app_check.check_app


def _opa(facts: Facts, answers: Answers) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    cache = facts.__dict__.setdefault("_okta_cache", {})
    key = ("opa", answers.get("api_host"), answers.get("team"))
    if key not in cache:
        cache[key] = LISTINGS(str(answers["api_host"]), str(answers["team"])) if answers.get("team") and answers.get("api_host") else None
    return cache[key]


def _app(facts: Facts, answers: Answers) -> okta_app_check.AppCheck | None:
    cache = facts.__dict__.setdefault("_okta_cache", {})
    key = ("okta", answers.get("org"), answers.get("okta_base_url"))
    if key not in cache:
        cache[key] = CHECK_APP(str(answers["org"]), str(answers.get("okta_base_url") or "okta.com")) if answers.get("org") else None
    found = cache[key]
    return None if found is None or found.authenticates is None else found


def by_name(records: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    return next((r for r in records if name and str(r.get("name") or "") == name), None)


def conditions_of(record: dict[str, Any] | None) -> dict[str, str]:
    """``{claim: value}`` for every EQUALS condition a record carries."""
    out: dict[str, str] = {}
    for c in (record or {}).get("conditions") or []:
        if str(c.get("matcher") or "").upper() == "EQUALS" and c.get("name"):
            out[str(c["name"])] = str(c.get("value") or "")
    return out


def names_repository(connection: dict[str, Any] | None, repository: str | None) -> bool:
    if not connection or not repository or "/" not in repository:
        return False
    cond = conditions_of(connection)
    return cond.get("repository") == repository and cond.get("repository_owner") == repository.split("/", 1)[0]


def requirement_for(role: dict[str, Any] | None, connection: str | None) -> dict[str, Any] | None:
    for req in (role or {}).get("requirements") or []:
        if str(((req or {}).get("workload_connection") or {}).get("name") or "") == connection:
            return req
    return None


# ---------------------------------------------------------------- defaults
def _connection_default(facts: Facts, answers: Answers) -> str | None:
    named = _builder(facts, "workload_connection")
    if named:
        return named
    listed = _opa(facts, answers)
    if listed:
        for c in listed[0]:
            if names_repository(c, facts.repository):
                return str(c.get("name"))
    return f"github-{facts.repo}" if facts.repo else None


def _role_default(facts: Facts, answers: Answers) -> str | None:
    named = _builder(facts, "workload_role")
    if named:
        return named
    listed = _opa(facts, answers)
    if listed:
        for r in listed[1]:
            if requirement_for(r, answers.get("workload_connection")):
                return str(r.get("name"))
    return f"{facts.repo}-ci" if facts.repo else None


def _observe(fn: Callable[[tuple[list[dict[str, Any]], list[dict[str, Any]]], Answers, Facts], bool]):
    def probe(facts: Facts, answers: Answers) -> bool | None:
        listed = _opa(facts, answers)
        return None if listed is None else bool(fn(listed, answers, facts))
    return probe


def _builder_named(facts: Facts, answers: Answers) -> bool:
    return (_builder(facts, "workload_connection") == answers.get("workload_connection")
            and _builder(facts, "workload_role") == answers.get("workload_role"))


def _app_probe(attr: str):
    def probe(facts: Facts, answers: Answers) -> bool | None:
        found = _app(facts, answers)
        value = None if found is None else getattr(found, attr)
        return None if value is None else bool(value)
    return probe


def _connection_active(listed, a, f) -> bool:
    status = str((by_name(listed[0], a.get("workload_connection")) or {}).get("status") or "")
    return status.upper() == "ACTIVE"


def _role_pinned(listed, a, f) -> bool:
    req = requirement_for(by_name(listed[1], a.get("workload_role")), a.get("workload_connection"))
    return conditions_of(req).get("ref") == f"refs/heads/{a.get('production_branch') or 'main'}"


QUESTIONS: tuple[Question, ...] = (
    Question("builder", "The managed OPA group builder (`type: okta-tf`) in cfg/group-builders.yml",
             default=lambda f, a: real((okta_builder(f) or {}).get("name"))),
    Question("org", "The Okta org name", default=lambda f, a: _builder(f, "org"),
             help="the okta-tf group builder's `org` is unset or still the starter's placeholder"),
    Question("okta_base_url", "The Okta base domain (okta.com, or oktapreview.com for a preview org)",
             default=lambda f, a: _builder(f, "okta_base_url") or "okta.com"),
    Question("team", "The OPA team", default=lambda f, a: _builder(f, "team"),
             help="the okta-tf group builder's `team` is unset or still the starter's placeholder"),
    Question("api_host", "The OPA API host", default=api_host_default),
    Question("production_branch", "The branch the workload role is pinned to (the perform job's)", default="main"),
    Question("workload_connection", "The OPA workload connection CI logs in through", default=_connection_default,
             help="no group builder names one and the repository is unknown"),
    Question("workload_role", "The OPA workload role it maps to", default=_role_default,
             help="no group builder names one and the repository is unknown"),
    Question("builder_names_them", "Does the group builder already name that connection and role?", kind="bool",
             default=_builder_named, observed=True),
    Question("connection_exists", "Does that workload connection exist?", kind="bool", observed=True,
             default=_observe(lambda l, a, f: by_name(l[0], a.get("workload_connection")) is not None),
             help=UNASKABLE_OPA),
    Question("connection_requires_repository", "Does it require `repository` and `repository_owner` to be this "
             "repository's?", kind="bool", observed=True, when=lambda a: bool(a.get("connection_exists")),
             default=_observe(lambda l, a, f: names_repository(by_name(l[0], a.get("workload_connection")), f.repository)),
             help=UNASKABLE_OPA),
    Question("connection_active", "Is it ACTIVE (not a draft)?", kind="bool", observed=True,
             when=lambda a: bool(a.get("connection_exists")), default=_observe(_connection_active), help=UNASKABLE_OPA),
    Question("role_exists", "Does that workload role exist?", kind="bool", observed=True,
             default=_observe(lambda l, a, f: by_name(l[1], a.get("workload_role")) is not None), help=UNASKABLE_OPA),
    Question("role_bound", "Is the role bound to that connection?", kind="bool", observed=True,
             when=lambda a: bool(a.get("role_exists")),
             default=_observe(lambda l, a, f: requirement_for(by_name(l[1], a.get("workload_role")),
                                                              a.get("workload_connection")) is not None),
             help=UNASKABLE_OPA),
    Question("role_pinned", "Is the role pinned to the production branch (`ref` = refs/heads/<branch>)?", kind="bool",
             observed=True, when=lambda a: bool(a.get("role_bound")), default=_observe(_role_pinned), help=UNASKABLE_OPA),
    Question("okta_app_authenticates", "Does the Okta API services app authenticate with its private key and "
             "scopes?", kind="bool", observed=True, default=_app_probe("authenticates"), help=UNASKABLE_OKTA),
    Question("okta_app_read_only", "Were its granted scopes read scopes only (no *.manage)?", kind="bool",
             observed=True, when=lambda a: bool(a.get("okta_app_authenticates")), default=_app_probe("read_only"),
             help=UNASKABLE_OKTA),
    Question("okta_app_readable", "Can the app read its own record (it holds okta.apps.read)?", kind="bool",
             observed=True, when=lambda a: bool(a.get("okta_app_authenticates")), default=_app_probe("readable"),
             help=UNASKABLE_OKTA),
)


def render(answers: Answers) -> Rendered:
    conn, role = str(answers["workload_connection"]), str(answers["workload_role"])
    branch = str(answers.get("production_branch") or "main")
    builder = str(answers.get("builder") or "the okta-tf group builder")
    todo: list[str] = []
    if not answers.get("connection_exists"):
        todo.append(f"Create the workload connection `{conn}` as a DRAFT in the OPA console (a DevOps admin): type GitHub "
                    "Actions, required claims `repository` and `repository_owner` naming this repository, no `ref` "
                    f"claim, TTL 1 hour; then run the OPA workload probe ({GUIDE} steps 1 and 4).")
    else:
        if not answers.get("connection_requires_repository"):
            todo.append(f"The workload connection `{conn}` does not require `repository` and `repository_owner` to be "
                        f"this repository's: correct its required claims ({GUIDE} step 1).")
        if not answers.get("connection_active"):
            todo.append(f"Activate the workload connection `{conn}` once the probe is green (a security admin; "
                        f"{GUIDE} step 5).")
    if not answers.get("role_exists"):
        todo.append(f"Create the workload role `{role}` with `{conn}` selected and no conditions yet (a security "
                    f"admin; {GUIDE} step 2).")
    elif not answers.get("role_bound"):
        todo.append(f"Bind the workload role `{role}` to the connection `{conn}` ({GUIDE} step 2).")
    elif not answers.get("role_pinned"):
        todo.append(f"After the first green login proof from `{branch}`, add the condition `ref` Equals "
                    f"`refs/heads/{branch}` to the workload role `{role}` ({GUIDE} step 6).")
    if not answers.get("builder_names_them"):
        todo.append(f"Name them on `{builder}` in cfg/group-builders.yml, beside `team:` -- "
                    f"`workload_connection: \"{conn}\"` and `workload_role: \"{role}\"` -- then run the identity "
                    f"lifecycle, which makes the per-group CI policies ({GUIDE} step 3).")
    if not answers.get("okta_app_authenticates"):
        todo.append("The Okta API services app did not authenticate with its key and scopes: ask the org's Okta "
                    "admins for it -- an API services app, private-key client authentication, the read scopes "
                    "(okta.users.read, okta.groups.read) granted and no `*.manage` scope, DPoP off -- and put its "
                    f"client id, key id, scopes and private key in your shell and the OKTA_API_PRIVATE_KEY secret ({GUIDE}).")
    else:
        if not answers.get("okta_app_read_only"):
            todo.append("The Okta API services app was granted a `*.manage` scope: ask the org's Okta admins to "
                        f"remove it; the system only reads users and groups ({GUIDE}).")
        if not answers.get("okta_app_readable"):
            todo.append("Ask the org's Okta admins to confirm the API services app grants no `*.manage` scope and "
                        "allows private-key client authentication only: its read scopes cannot see its own "
                        "record, so the bootstrap could not check either.")
    todo.append("The OPA service user and its API key pair (`TF_VAR_KEY` / `TF_VAR_SECRET`) are made by hand in "
                f"the OPA console; set-secrets.sh reads them from files ({GUIDE}).")

    def mark(key: str) -> str:
        return "yes" if answers.get(key) else "no"
    notes = (
        f"OPA team `{answers['team']}` at {answers['api_host']}; the workload connection `{conn}` "
        + (f"exists (active: {mark('connection_active')}; requires this repository: "
           f"{mark('connection_requires_repository')})" if answers.get("connection_exists") else "does not exist yet"),
        f"the workload role `{role}` " + (f"exists (bound to `{conn}`: {mark('role_bound')}; pinned to `{branch}`: "
                                          f"{mark('role_pinned')})" if answers.get("role_exists") else "does not exist yet")
        + f"; named on `{builder}`: {mark('builder_names_them')}",
        "the Okta API services app " + ("authenticates with its key; read scopes only: "
                                        f"{mark('okta_app_read_only')}; its own record readable: {mark('okta_app_readable')}"
                                        if answers.get("okta_app_authenticates") else "did not authenticate"),
        "nothing here is terraform: the section reads and checks, and every check above was made when "
        "`bootstrap` last ran (re-run it to check again)",
    )
    return Rendered(by_hand=tuple(todo), notes=notes)


def wanted(facts: Facts) -> bool:
    """The tree manages OPA groups: it declares an ``okta-tf`` group builder."""
    return okta_builder(facts) is not None


def okta_section() -> Section:
    return Section(name="okta", title="Okta and OPA", questions=QUESTIONS, render=render, wanted=wanted,
                   description="the OPA workload connection and role and the Okta API services app, read and checked")
