# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Okta Privileged Access gid lookup -- the okta plugin's queryable gid shim
(DESIGN N1/N7).

The oktapam terraform provider (0.7.x) exposes no gid on ``oktapam_group``,
so the identity root cannot output gids from provider attributes. Instead
the root emits a ``data "external"`` block whose program is
``cs-image-system identity export-gids``; that program lands here.

Read-only: a service token is obtained with the same key/secret the oktapam
provider uses (``TF_VAR_<team>_key`` / ``TF_VAR_<team>_secret``, or
``OKTAPAM_KEY`` / ``OKTAPAM_SECRET``), then each requested group's server
group (``<name>_user``, the module's user group) is read through the OPA
**Attributes API**, ``GET /v1/teams/{team}/groups/{group}/attributes``
(https://developer.okta.com/docs/api/openapi/opa, tag Attributes), whose
``unix_gid`` attribute is the gid OPA assigns on servers. Verified live
2026-08-26: ``coops_user`` -> 180007 (unix_group_name ``sft_coops_user``).
The documented response is ``{"list": [{attribute_name, attribute_value,
..}]}``; the live service answers ``{"attributes": {"unix_gid": {..}}}`` --
both shapes are accepted. A group without a ``unix_gid`` attribute is
reported missing, which fails the caller loudly rather than inventing a
value (N1: consumers never invent gids).

``transport`` is injectable so the resolver is unit-testable with no network.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Callable, Mapping

from cs_image_system.base.utils import super_safe_name

log = logging.getLogger(__name__)

GID_ATTRIBUTE = "unix_gid"
GROUP_NAME_ATTRIBUTE = "unix_group_name"
USER_GROUP_SUFFIX = "_user"
ADMIN_GROUP_SUFFIX = "_admin"

Transport = Callable[[str, str, dict[str, str], bytes | None], Any]


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Any:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - https to the configured host only
        return json.loads(resp.read().decode() or "{}")


def credentials_from_env(team: str, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    tv = super_safe_name(team)
    key = env.get(f"TF_VAR_{tv}_key") or env.get("OKTAPAM_KEY")
    secret = env.get(f"TF_VAR_{tv}_secret") or env.get("OKTAPAM_SECRET")
    if not key or not secret:
        raise ValueError(
            f"OPA credentials for team {team!r} not found in the environment "
            f"(TF_VAR_{tv}_key/TF_VAR_{tv}_secret or OKTAPAM_KEY/OKTAPAM_SECRET)")
    return key, secret


class OpaGidResolver:
    def __init__(self, api_host: str, team: str, key: str, secret: str,
                 transport: Transport | None = None) -> None:
        self.api_host = api_host.rstrip("/")
        self.team = team
        self.key = key
        self.secret = secret
        self.transport = transport or _urllib_transport
        self._token: str | None = None

    # --------------------------------------------------------------- http
    def _url(self, path: str) -> str:
        return f"{self.api_host}{path}"

    def token(self) -> str:
        if self._token is None:
            body = json.dumps({"key_id": self.key, "key_secret": self.secret}).encode()
            data = self.transport("POST", self._url(f"/v1/teams/{self.team}/service_token"),
                                  {"Content-Type": "application/json"}, body)
            tok = (data or {}).get("bearer_token")
            if not tok:
                raise ValueError("OPA service_token response carried no bearer_token")
            self._token = str(tok)
        return self._token

    def get(self, path: str) -> Any:
        return self.transport("GET", self._url(path),
                              {"Authorization": f"Bearer {self.token()}",
                               "Accept": "application/json"}, None)

    # ------------------------------------------------------------ resolve
    def group_attributes(self, group_name: str) -> dict[str, Any]:
        """``{attribute_name: attribute_value}`` for one OPA group, accepting
        both the documented ``list`` shape and the live ``attributes`` map."""
        data = self.get(f"/v1/teams/{self.team}/groups/{group_name}/attributes") or {}
        out: dict[str, Any] = {}
        if isinstance(data.get("attributes"), dict):
            for name, rec in data["attributes"].items():
                out[str(name)] = rec.get("attribute_value") if isinstance(rec, dict) else rec
        for rec in data.get("list") or []:
            if isinstance(rec, dict) and rec.get("attribute_name"):
                out[str(rec["attribute_name"])] = rec.get("attribute_value")
        return out

    @staticmethod
    def gid_of(attributes: Mapping[str, Any]) -> int | None:
        v = attributes.get(GID_ATTRIBUTE)
        if v in (None, "", 0):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def resolve(self, groups: list[str]) -> dict[str, int]:
        """``{group: gid}`` for every requested group whose server group
        carries a unix_gid attribute; missing groups are simply absent."""
        result: dict[str, int] = {}
        for name in groups:
            for cand in (f"{name}{USER_GROUP_SUFFIX}", name):
                try:
                    attrs = self.group_attributes(cand)
                except Exception as e:  # 404 for an unknown group name, etc.
                    log.debug(f"OPA group attributes for {cand!r} unavailable: {e}")
                    continue
                gid = self.gid_of(attrs)
                if gid is not None:
                    result[name] = gid
                    break
        return result

    def group_users(self, group_name: str) -> list[str] | None:
        """User names in one OPA group (``GET /v1/teams/{team}/groups/{group}/users``),
        or ``None`` when the service does not answer (the state report then
        says nothing about membership rather than something wrong)."""
        try:
            data = self.get(f"/v1/teams/{self.team}/groups/{group_name}/users") or {}
        except Exception as e:
            log.debug(f"OPA group users for {group_name!r} unavailable: {e}")
            return None
        out: list[str] = []
        for rec in data.get("list") or []:
            if isinstance(rec, dict):
                name = rec.get("name") or rec.get("user_name") or rec.get("id")
                if name:
                    out.append(str(name))
        return sorted(out)

    def _login_project(self, group_name: str) -> str | None:
        """The API path prefix of ``group_name``'s ``<group>_rg_login``
        project -- ``/v1/teams/{team}/resource_groups/{rg}/projects/{prj}``
        -- or ``None`` when either level is not there. Servers are reachable
        ONLY under this prefix: the team-level ``/projects/...`` path answers
        ``401 Missing capability`` (found live 2026-09-21, stage 55), and the
        printed name ``coops_rg_login`` is not the project id."""
        rgs = (self.get(f"/v1/teams/{self.team}/resource_groups") or {}).get("list") or []
        rg = next((r for r in rgs if r.get("name") == f"{group_name}_rg"), None)
        if rg is None:
            return None
        prjs = (self.get(f"/v1/teams/{self.team}/resource_groups/{rg['id']}/projects")
                or {}).get("list") or []
        prj = next((p for p in prjs if p.get("name") == f"{group_name}_rg_login"), None)
        if prj is None:
            return None
        return f"/v1/teams/{self.team}/resource_groups/{rg['id']}/projects/{prj['id']}"

    def project_enrollment_tokens(self, group_name: str) -> list[str] | None:
        """Descriptions of the server enrollment tokens on ``group_name``'s
        ``<group>_rg_login`` project, or ``None`` when the service does not
        answer (the state report then says nothing rather than something
        wrong). Read-only; token VALUES are never fetched or returned."""
        try:
            prefix = self._login_project(group_name)
            if prefix is None:
                return None
            toks = (self.get(f"{prefix}/server_enrollment_tokens") or {}).get("list") or []
            return sorted(str(t.get("description") or "") for t in toks if isinstance(t, dict))
        except Exception as e:
            log.debug(f"OPA enrollment tokens for {group_name!r} unavailable: {e}")
            return None

    # ----------------------------------------------- servers (stage 55)
    def registered_servers(self, group_name: str) -> list[dict[str, Any]] | None:
        """Every server enrolled in ``group_name``'s login project, as
        ``{id, hostname, address}``, or ``None`` when the service could not
        be asked. None is NOT an empty list: a caller deciding whether a
        hostname is free must not read silence as freedom (stage 57's rule,
        applied here -- an unreachable OPA is exactly when a second
        registration would otherwise slip through)."""
        try:
            prefix = self._login_project(group_name)
            if prefix is None:
                return None
            data = self.get(f"{prefix}/servers") or {}
        except Exception as e:
            log.debug(f"OPA servers for {group_name!r} unavailable: {e}")
            return None
        out: list[dict[str, Any]] = []
        for rec in data.get("list") or []:
            if not isinstance(rec, dict) or not rec.get("id"):
                continue
            out.append({"id": str(rec["id"]),
                        "hostname": str(rec.get("hostname") or rec.get("canonical_name") or ""),
                        "address": str(rec.get("access_address") or rec.get("bind_address") or "")})
        return sorted(out, key=lambda s: (s["hostname"], s["address"], s["id"]))

    def retire_server(self, group_name: str, server_id: str) -> bool:
        """``DELETE`` one server registration from ``group_name``'s login
        project (204 live, 2026-09-21). True when it is gone at return; a
        404 counts as gone. Anything else raises: a retirement that did not
        happen must not be recorded as one."""
        prefix = self._login_project(group_name)
        if prefix is None:
            raise ValueError(f"OPA login project for group {group_name!r} not found; cannot retire {server_id}")
        try:
            self.transport("DELETE", self._url(f"{prefix}/servers/{server_id}"),
                           {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}, None)
        except Exception as e:
            if "404" in str(e):
                log.info(f"OPA server {server_id} was already gone")
                return True
            raise
        return True

    def user_attributes(self, user_name: str) -> dict[str, Any]:
        """``{attribute_name: attribute_value}`` for one OPA user
        (``GET /v1/teams/{team}/users/{user}/attributes``; verified read-only
        2026-08-27: unix_uid, unix_gid, unix_user_name, windows_user_name,
        active_directory_* -- each with OPA's own ``managed`` flag)."""
        data = self.get(f"/v1/teams/{self.team}/users/{user_name}/attributes") or {}
        out: dict[str, Any] = {}
        if isinstance(data.get("attributes"), dict):
            for name, rec in data["attributes"].items():
                out[str(name)] = rec.get("attribute_value") if isinstance(rec, dict) else rec
        for rec in data.get("list") or []:
            if isinstance(rec, dict) and rec.get("attribute_name"):
                out[str(rec["attribute_name"])] = rec.get("attribute_value")
        return out

    def attribute_conflicts(self) -> list[dict[str, Any]]:
        """``GET /v1/teams/{team}/attributes/conflicts`` (verified read-only
        2026-08-27: ``{"list": []}`` on the live team)."""
        data = self.get(f"/v1/teams/{self.team}/attributes/conflicts") or {}
        return [c for c in (data.get("list") or []) if isinstance(c, dict)]

    def resolve_names(self, groups: list[str]) -> dict[str, str]:
        """``{group: unix_group_name}`` (the local group name sftd creates)."""
        out: dict[str, str] = {}
        for name in groups:
            try:
                attrs = self.group_attributes(f"{name}{USER_GROUP_SUFFIX}")
            except Exception:
                continue
            if attrs.get(GROUP_NAME_ATTRIBUTE):
                out[name] = str(attrs[GROUP_NAME_ATTRIBUTE])
        return out
