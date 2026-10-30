# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GCP utility functions for Compute Engine image and network queries."""

from __future__ import annotations

import json
import logging

from cs_image_system.contract.image import ImageQuery
import re
from collections.abc import Mapping
from typing import Any, Sequence, cast

from google.api_core import exceptions as gcp_exceptions
from google.cloud import compute_v1

from cs_image_system.contract.constants import SELF

log = logging.getLogger(__name__)


class ImageNotFoundError(Exception):
    """Raised when no image is found matching the query."""

    pass


class ImageQueryError(Exception):
    """Raised when an image query fails."""

    pass


# Generic query filter keys -> Compute Engine image resource fields usable in a
# list() filter expression.
GCP_DI_MAP: dict[str, str] = {
    "name": "name",
    "image_name": "name",
    "image_id": "name",
    # The image family this image belongs to.
    "family": "family",
    # The status of the image ( READY | PENDING | FAILED | DELETING ).
    "state": "status",
    "status": "status",
    # The image architecture ( X86_64 | ARM64 ).
    "architecture": "architecture",
    "description": "description",
    # RFC3339 creation timestamp; supports comparison operators.
    "creation_date": "creationTimestamp",
    "creation_timestamp": "creationTimestamp",
}

# Query keys that only make sense for AWS/EC2.  They have no Compute Engine
# equivalent, so they are dropped (with a log line) instead of being pushed
# into the post-query filter where they would exclude every result.
AWS_ONLY_QUERY_KEYS: set[str] = {
    "root_device_type",
    "root-device-type",
    "virtualization_type",
    "virtualization-type",
    "ena_support",
    "sriov_net_support",
    "hypervisor",
    "platform",
    "is_public",
    "owner_alias",
    "owner_id",
    "kernel_id",
    "ramdisk_id",
    "free_tier_eligible",
    "image_allowed",
    "manifest_location",
    "product_code",
}

# Common owner aliases -> GCP public image projects.
GCP_OWNER_PROJECT_MAP: dict[str, str] = {
    "debian": "debian-cloud",
    "ubuntu": "ubuntu-os-cloud",
    "rhel": "rhel-cloud",
    "centos": "centos-cloud",
    "rocky": "rocky-linux-cloud",
    "fedora": "fedora-cloud",
    "suse": "suse-cloud",
    "windows": "windows-cloud",
    "cos": "cos-cloud",
    "google": "debian-cloud",
}

# AWS-specific owner aliases that must never be treated as GCP projects even
# though they are syntactically valid project ids.
AWS_ONLY_OWNER_ALIASES: set[str] = {"amazon", "aws-marketplace", "aws-backup-vault"}

# Valid GCP project id: 6-30 chars, lowercase letter first, letters/digits/hyphens.
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")

_GCP_STATUS_MAP: dict[str, str] = {
    "available": "READY",
    "pending": "PENDING",
    "failed": "FAILED",
}

_GCP_ARCH_MAP: dict[str, str] = {
    "x86_64": "X86_64",
    "amd64": "X86_64",
    "i386": "X86_64",
    "arm64": "ARM64",
    "aarch64": "ARM64",
}


def _gcp_status(value: Any) -> str:
    return _GCP_STATUS_MAP.get(str(value).lower(), str(value).upper())


def _gcp_architecture(value: Any) -> str:
    return _GCP_ARCH_MAP.get(str(value).lower(), str(value).upper())


def _generic_architecture(value: Any) -> str:
    """Map a GCP architecture value back to the generic x86_64/arm64 form."""
    v = str(value).lower()
    return v if v in ("x86_64", "arm64") else "x86_64"


def make_credentials(session_config: Mapping[str, Any]) -> Any | None:
    creds_cfg = session_config.get("credentials") or {}
    key_file = creds_cfg.get("service_account_key_file")
    if key_file:
        from google.oauth2 import service_account  # noqa: PLC0415

        return service_account.Credentials.from_service_account_file(key_file)
    return None


def _make_images_client(session_config: Mapping[str, Any]) -> compute_v1.ImagesClient:
    creds = make_credentials(session_config)
    return compute_v1.ImagesClient(credentials=creds) if creds else compute_v1.ImagesClient()


def resolve_project(session_config: Mapping[str, Any]) -> str | None:
    """Resolve the project id for SELF from the session configuration.

    Falls back to the ``project_id`` recorded in a service account key file when
    the config does not carry an explicit project.
    """
    project = session_config.get("project")
    if project:
        return str(project)
    creds_cfg = session_config.get("credentials") or {}
    key_file = creds_cfg.get("service_account_key_file")
    if key_file:
        try:
            with open(key_file) as f:
                return cast(str | None, json.load(f).get("project_id"))
        except (OSError, ValueError) as e:
            log.warning(f"Could not read project_id from key file {key_file}: {e}")
    return None


def resolve_projects(
    owners: Sequence[Any] | None, session_config: Mapping[str, Any]
) -> list[str]:
    """Map generic owner entries to GCP projects to search for images.

    ``self`` resolves to the session project; known distro aliases resolve to
    the corresponding public image projects; entries that cannot be a GCP
    project id (e.g. AWS account numbers, "amazon") are dropped with a warning.
    """
    projects: list[str] = []
    for owner in owners or [SELF]:
        o = str(owner).strip().strip('"')
        if o.lower() == SELF:
            self_project = resolve_project(session_config)
            if not self_project:
                raise ValueError(
                    "Owner 'self' requires a project: set project_id on the GCP runtime "
                    "(stage 63: a runtime declares no credentials, so no key file can supply one)."
                )
            projects.append(self_project)
        elif o.lower() in GCP_OWNER_PROJECT_MAP:
            projects.append(GCP_OWNER_PROJECT_MAP[o.lower()])
        elif o.lower() in AWS_ONLY_OWNER_ALIASES:
            log.debug(f"Dropping AWS-only owner alias {o!r} for GCP query.")
        elif _PROJECT_ID_RE.match(o):
            projects.append(o)
        else:
            log.warning(f"Owner {o!r} is not a valid GCP project or known alias; skipping.")
    # Dedup, preserving order.
    seen: set[str] = set()
    return [p for p in projects if not (p in seen or seen.add(p))]


def build_filter_expression(terms: Mapping[str, Any]) -> str:
    """Build a Compute Engine list() filter expression from field/value terms."""
    parts: list[str] = []
    for k, v in terms.items():
        if isinstance(v, bool):
            parts.append(f"({k} = {str(v).lower()})")
        else:
            parts.append(f'({k} = "{v}")')
    return " AND ".join(parts)


#: stage 106: the keys of the system's image-query vocabulary Compute
#: Engine's images.list can answer, and the field each becomes.
GCP_QUERY_KEYS: frozenset[str] = frozenset({"name", "family", "architecture", "publisher", "state", "tags",
                                            "newest", "native"})
GCP_FIELD_NAMES: dict[str, str] = {"name": "name", "family": "family", "architecture": "architecture", "state": "status"}


def translate_image_query(query: ImageQuery) -> dict[str, Any]:
    """The system's query in Compute Engine's words (stage 106):
    ``{"projects": [...], "terms": {<image field>: value}, "filter": <the
    list() expression>, "most_recent": bool}``; ``query_image`` takes it.
    ``state`` defaults to ``available`` (READY); ``architecture`` and
    ``state`` values are mapped; ``tags`` become ``labels.<k>``. A key the
    API cannot answer (the EC2 particulars) raises ValueError naming it
    (``validate`` refuses it first); ``native`` keys are image fields,
    passed verbatim."""
    unsupported = sorted(k for k in query.keys() if k not in GCP_QUERY_KEYS)
    if unsupported:
        raise ValueError(f"GCE cannot translate image query key(s) {', '.join(unsupported)}")
    terms: dict[str, Any] = {}
    for key, name in GCP_FIELD_NAMES.items():
        value = getattr(query, key)
        if value is None:
            continue
        if name == "status":
            value = _gcp_status(value)
        elif name == "architecture":
            value = _gcp_architecture(value)
        terms[name] = value
    terms.setdefault("status", "READY")
    for k, v in sorted(query.tags.items()):
        terms[f"labels.{k}"] = v
    for k, v in query.native.items():
        terms[str(k)] = v
    return {"projects": list(query.publisher), "terms": terms, "filter": build_filter_expression(terms),
            "most_recent": True if query.newest is None else bool(query.newest)}


def _image_to_dict(image: compute_v1.Image, project: str) -> dict[str, Any]:
    d = cast(dict[str, Any], compute_v1.Image.to_dict(image))
    d["project"] = project
    return d


def query_image(
    query: dict[str, Any],
    post_query_filter: dict[str, Any] | None = None,
    session_config: dict[str, Any] | None = None,
    images_client: Any | None = None,
) -> dict[str, Any] | None:
    """
    Query GCP for a single Compute Engine image matching the provided criteria.

    Lists images in each candidate project using the provided filter
    expression. If multiple images match, the most recently created one is
    returned.

    Parameters
    ----------
    query : dict[str, Any]
        Dictionary containing query parameters:

        - ``projects`` (list[str]): Owners/projects to search. ``self``
          resolves to the session project; known distro aliases (``debian``,
          ``rhel``, ...) resolve to the public image projects.
        - ``filter`` (str): Compute Engine list() filter expression, e.g.
          ``(name = "debian-11-*") AND (status = "READY")``.
        - ``family`` (str): Image family to resolve via getFromFamily when no
          filter expression is provided.

    post_query_filter : dict[str, Any], optional
        Exact-match constraints applied to the result dictionaries after the
        API query (keys are proto field names, e.g. ``family``).

    session_config : dict[str, Any], optional
        Session configuration: ``project``, optional ``credentials`` carrying
        ``service_account_key_file``, optional ``region``/``zone``.

    images_client : Any, optional
        Pre-built ImagesClient (used for testing/injection).

    Returns
    -------
    dict[str, Any] | None
        Dictionary of the image resource (proto field names, e.g. ``name``,
        ``self_link``, ``family``, ``architecture``, ``creation_timestamp``)
        plus ``project``, or None if nothing matched.

    Raises
    ------
    ImageQueryError
        If there is an error communicating with GCP.
    ValueError
        If the query or session configuration is empty.
    """
    if not query:
        raise ValueError("Query dictionary cannot be empty")
    if not session_config:
        raise ValueError("Session configuration cannot be None or empty")

    try:
        client = images_client or _make_images_client(session_config)
    except (gcp_exceptions.GoogleAPIError, OSError, ValueError) as e:
        raise ImageQueryError(f"Failed to create Compute images client: {e}") from e

    projects = resolve_projects(query.get("projects"), session_config)
    if not projects:
        raise ValueError(f"No usable GCP projects resolved from query {query}")

    results: list[dict[str, Any]] = []
    filter_expr = query.get("filter", "")
    family = query.get("family")
    most_recent = query.get("most_recent", True)
    for project in projects:
        if filter_expr:
            results.extend(_query_by_filters(client, project, filter_expr))
        elif family:
            img = _query_by_family(client, project, family)
            if img:
                results.append(img)
        else:
            raise ValueError(
                "No valid query parameters provided. Must include 'filter' or 'family'."
            )

    ilist: list[dict[str, Any]] = []
    for r in results:
        if post_query_filter:
            match = True
            for k, v in post_query_filter.items():
                if r.get(k) != v:
                    match = False
                    break
            if not match:
                continue
        ilist.append(r)
    if not ilist:
        return None
    if len(ilist) > 1:
        if not most_recent:
            raise ImageQueryError(f"{len(ilist)} images match and the query says newest: false; narrow it")
        ilist.sort(key=lambda x: x.get("creation_timestamp", ""), reverse=True)

    return ilist[0]


def _query_by_family(client: Any, project: str, family: str) -> dict[str, Any] | None:
    """Resolve the latest non-deprecated image of a family in a project."""
    try:
        image = client.get_from_family(project=project, family=family)
    except gcp_exceptions.NotFound:
        return None
    except gcp_exceptions.GoogleAPIError as e:
        raise ImageQueryError(
            f"Failed to query image family '{family}' in project '{project}': {e}"
        ) from e
    return _image_to_dict(image, project)


def _query_by_filters(client: Any, project: str, filter_expr: str) -> list[dict[str, Any]]:
    """List images in a project matching a filter expression (paged)."""
    log.debug(f"Querying project {project} for images with filter: {filter_expr}")
    try:
        request = compute_v1.ListImagesRequest(project=project, filter=filter_expr)
        ilist = [_image_to_dict(image, project) for image in client.list(request=request)]
    except gcp_exceptions.GoogleAPIError as e:
        raise ImageQueryError(
            f"Failed to query images in project '{project}' with filter: {e}"
        ) from e
    log.info(f"Found {len(ilist)} images in project {project} matching filter.")
    return ilist


def get_image_owner(image_info: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the owning project of an image result (the GCP owner analog)."""
    project = image_info.get("project")
    if not project:
        self_link = image_info.get("self_link", "")
        m = re.search(r"/projects/([^/]+)/", str(self_link))
        project = m.group(1) if m else None
    if not project:
        return None
    return {"project": project}



def get_network_map_and_default_network(
    session_config: dict[str, Any],
    clients: Mapping[str, Any] | None = None,
) -> tuple[dict, str | None, dict]:
    """Build the network/subnetwork map for a project (GCP analog of the AWS
    VPC map) plus the default network name and the firewall rules.

    Returns (network_map, default_network_name, firewall_rules) where
    network_map is keyed by network name with a flat ``subnets`` list, and
    firewall_rules is keyed by firewall rule name (the closest analog GCP has
    to security groups).
    """
    project = resolve_project(session_config)
    if not project:
        raise ValueError(
            "A project is required to enumerate GCP networks; set project_id on "
            "the GCP runtime."
        )
    try:
        creds = make_credentials(session_config)
        kwargs: dict[str, Any] = {"credentials": creds} if creds else {}
        clients = clients or {}
        networks_client = clients.get("networks") or compute_v1.NetworksClient(**kwargs)
        subnets_client = clients.get("subnetworks") or compute_v1.SubnetworksClient(**kwargs)
        routes_client = clients.get("routes") or compute_v1.RoutesClient(**kwargs)
        firewalls_client = clients.get("firewalls") or compute_v1.FirewallsClient(**kwargs)

        # Fetch data in bulk
        networks = list(networks_client.list(project=project))
        routes = list(routes_client.list(project=project))
        allfw = {
            fw.name: compute_v1.Firewall.to_dict(fw)
            for fw in firewalls_client.list(project=project)
        }

        network_map: dict[str, Any] = {}
        default_network_name: str | None = None

        for net in networks:
            network_map[net.name] = {"subnets": []}
            # GCP has no "default network" flag; the auto-created network is
            # conventionally named "default".
            if net.name == "default":
                default_network_name = net.name

        # --- ROUTE MAPPING LOGIC ---
        # GCP routes are network-scoped (not subnet-scoped): a network whose
        # default route targets the internet gateway makes all of its subnets
        # internet-capable.
        network_is_public: dict[str, bool] = {}
        for route in routes:
            net_name = str(route.network).rsplit("/", 1)[-1]
            is_default_dest = route.dest_range in ("0.0.0.0/0", "::/0")
            if is_default_dest and route.next_hop_gateway.endswith(
                "/global/gateways/default-internet-gateway"
            ):
                network_is_public[net_name] = True

        # --- PROCESS SUBNETS ---
        agg = subnets_client.aggregated_list(project=project)
        for _scope, scoped_list in agg:
            for sn in getattr(scoped_list, "subnetworks", []) or []:
                net_name = str(sn.network).rsplit("/", 1)[-1]
                if net_name not in network_map:
                    continue
                subnet_data = cast(dict[str, Any], compute_v1.Subnetwork.to_dict(sn))
                s_name = subnet_data.pop("name", None)
                cidr = subnet_data.pop("ip_cidr_range", None)
                self_link = subnet_data.get("self_link", "")
                region = str(subnet_data.get("region", "")).rsplit("/", 1)[-1]

                formatted_subnet = {
                    "subnet_id": s_name,
                    "self_link": self_link,
                    "region": region,
                    "cidr": cidr,
                    "is_public": network_is_public.get(net_name, False),
                    "tags": {},  # GCP subnetworks carry no labels/tags
                    "config": subnet_data,  # All other remaining raw attributes
                }
                network_map[net_name]["subnets"].append(formatted_subnet)

        return network_map, default_network_name, allfw

    except (gcp_exceptions.GoogleAPIError, OSError) as e:
        raise ValueError(f"GCP Error: {e}") from e
