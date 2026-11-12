# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker runtime's builder: every hook the core asks a
runtime for, answered against a daemon that speaks the Docker Engine API
through the ``docker`` CLI. Images live in the daemon's own store; a build
is its image id, its names are tags, and what a label cannot say after the
build (a parent bound later, a release) is said by a tag that MOVES."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.builder_base_container import ContainerBuilderBase
from cs_image_system.base.models.executable import ExecutableModel
from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage
from cs_image_system.contract import power_state
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.core import PluginArtifactProtocol
from cs_image_system.contract.image import ImageQuery
from cs_image_system.contract.image_sources import container_reference
from cs_image_system.contract.launch_vocabulary import LAUNCH_MARKER_PATH
from cs_image_system.contract.lineage_vocabulary import CONFIG_TAG, TAG_PREFIX
from cs_image_system.contract.runtime import LAUNCH_DELIVERY_SESSION
from cs_image_system.contract.secrets import is_marker, open_marker
from cs_image_system.contract.session import LoadFailureReport, SessionStatus

from .docker_names import (
    full_id,
    is_digest_reference,
    is_image_id,
    label_key_problem,
    movable_tag,
    parse_movable_tag,
    same_repository,
    short_id,
    tag_name,
    tag_problem,
)
from .docker_packer_source import DOCKER_SOURCE, bake_container_name, docker_source, docker_tag_post_processor
from .docker_provider_specific_image import DockerProviderSpecificImage
from .docker_runtime_models import DockerContainerBuilderModel
from .local_target import make_local_target

DOCKER_RUNTIME: str = "docker"
#: the keys of the system's image-query vocabulary a daemon can answer: a
#: repository (`name`), a tag (`version`), a registry namespace (`publisher`),
#: a platform (`architecture`), and `native.image` verbatim
DOCKER_QUERY_KEYS: frozenset[str] = frozenset({"name", "version", "publisher", "architecture", "native"})
_PLATFORMS = {"x86_64": "linux/amd64", "amd64": "linux/amd64", "arm64": "linux/arm64", "aarch64": "linux/arm64"}

log = logging.getLogger(__name__)


class DockerUnreachable(RuntimeError):
    """The daemon could not be reached (one line; load failures classify it)."""


#: the environment names the docker CLI reads its daemon and TLS settings from
CREDENTIAL_ENVIRONMENT_PREFIXES: tuple[str, ...] = ("DOCKER_",)
#: what renews a daemon's "session": there is no login, the daemon must answer
DOCKER_RENEW = "start the daemon (OrbStack, Docker Desktop, the engine on the host), or fix the runtime's `host` / `context`"
DOCKER_REMEDY = ("the runtime's daemon must answer `docker version` from this machine: start it (OrbStack, Docker "
                 "Desktop, the engine on the host), or fix the runtime's `host` / `context`; `preflight` says which")


def probe_daemon(binary: str, env: dict[str, str], timeout: int = 20) -> tuple[bool, str]:
    """``docker version`` against ONE daemon: ``(answers, what it said)``
    -- the engine and API versions, or the first line of why not. The one
    cloud-like call the preflight makes on this runtime's behalf: a
    daemon's "session" is its reachability, and nothing else can be read
    for it."""
    full = dict(os.environ)
    full.update(env)
    try:
        res = subprocess.run([binary, "version", "--format", "{{.Server.Version}} (api {{.Server.APIVersion}})"],
                             capture_output=True, text=True, check=False, timeout=timeout, env=full)
    except FileNotFoundError:
        return False, f"{binary} is not an executable on this machine"
    except subprocess.TimeoutExpired:
        return False, f"no answer within {timeout}s"
    if res.returncode == 0 and (res.stdout or "").strip():
        return True, f"answers: engine {(res.stdout or '').strip()}"
    err = ((res.stderr or res.stdout or "").strip().splitlines() or ["no answer"])[0]
    return False, f"does not answer: {err[:160]}"


def daemon_where(settings: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    """The daemon environment and its description from a runtime's
    settings (a raw entry or a model's fields): ``host`` (an ENC marker
    opened, never shown) or ``context``."""
    host = settings.get("host")
    context = settings.get("context")
    env: dict[str, str] = {}
    where = "the environment's daemon"
    if host:
        env["DOCKER_HOST"] = open_marker(str(host)) if is_marker(str(host)) else str(host)
        where = "host (encrypted)" if is_marker(str(host)) else f"host {host}"
    elif context:
        env["DOCKER_CONTEXT"] = str(context)
        where = f"context {context}"
    return env, where


def _executable_field(exe: Any, key: str) -> Any:
    """``binary`` / ``name`` of an executables entry, raw (a mapping) or loaded (a model)."""
    return exe.get(key) if isinstance(exe, Mapping) else getattr(exe, key, None)


def translate_image_query(query: ImageQuery) -> dict[str, Any]:
    """The system's query in the daemon's words: ``{"reference":
    "<repository>:<tag>", "platform": "<os/arch>" | None}``. A key the daemon
    cannot answer raises ValueError naming it (``validate`` refuses first)."""
    unsupported = sorted(k for k in query.keys() if k not in DOCKER_QUERY_KEYS)
    if unsupported:
        raise ValueError(f"a container daemon cannot translate image query key(s) {', '.join(unsupported)}")
    reference = container_reference(query)
    if not reference:
        raise ValueError("a container image query names a repository (`name`) or `native.image`")
    platform = _PLATFORMS.get(str(query.architecture)) if query.architecture else None
    return {"reference": reference, "platform": platform}


class DockerContainerBuilder(ContainerBuilderBase[DockerContainerBuilderModel], PluginArtifactProtocol):
    """A daemon speaking the Docker Engine API, as a runtime."""

    @classmethod
    def csis_name(cls) -> str:
        return DOCKER_RUNTIME

    @property
    def model(self) -> DockerContainerBuilderModel:
        return self._model  # type: ignore

    # ------------------------------------------- the session hooks (the CLASS)
    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """The daemon's reachability, in one ``docker version``: the binary
        is the ``executables`` entry the runtime's ``executable`` names
        (default ``docker``), the daemon is ``host`` or ``context``. A
        daemon that answers has been asked, so it is judged (``renews``),
        unlike static keys whose lapse nothing can read."""
        exe = executables.get(str(settings.get("executable") or "docker"))
        binary = str(_executable_field(exe, "binary") or _executable_field(exe, "name") or "docker")
        env, where = daemon_where(settings)
        ok, said = probe_daemon(binary, env)
        return SessionStatus(where, None, said, present=ok, renews=ok, renew=DOCKER_RENEW)

    @classmethod
    def credential_environment_prefixes(cls) -> tuple[str, ...]:
        return CREDENTIAL_ENVIRONMENT_PREFIXES

    @classmethod
    def classify_failure(cls, exc: BaseException) -> LoadFailureReport | None:
        if isinstance(exc, DockerUnreachable):
            return LoadFailureReport("environment", [f"the configuration cannot load: {exc}", f"({DOCKER_REMEDY})"], code=2)
        return None

    def provider_specific_image_class(self) -> type[ProviderSpecificImage]:
        return DockerProviderSpecificImage

    def prepare_provider_specific_image(self, psi: ProviderSpecificImage) -> None:
        """An image of this runtime knows the repository its builds are
        tagged into: the floating tag of a deferred one is read from it."""
        if isinstance(psi, DockerProviderSpecificImage):
            psi.repository = self.model.get_repository()

    # ------------------------------------------------------------ the CLI
    def docker_binary(self) -> str:
        """The docker CLI this runtime runs: the ``binary`` of the
        ``cfg/executables.yml`` entry its ``executable`` names (default
        ``docker``), the one ``validate`` version-checks."""
        name = self.model.get_executable() or "docker"
        exe = (self._get_context().executables or {}).get(name)
        if exe is None:
            raise ValueError(f"docker runtime {self.get_name()}: executable {name!r} is not declared in "
                             f"cfg/executables.yml; declare it (name: {name}, binary: <path to docker>)")
        return str(exe.binary or exe.name)

    def tool_environment(self) -> dict[str, str]:
        """``DOCKER_HOST`` / ``DOCKER_CONTEXT`` (and TLS) for every tool a
        bake on this runtime runs: packer's docker plugin and ansible's
        docker connection both read them."""
        return self.model.daemon_environment()

    def _docker(self, *args: str, timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [self.docker_binary(), *args]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout,
                                 env=self.model.process_environment())
        except FileNotFoundError as e:
            raise DockerUnreachable(f"docker runtime {self.get_name()}: {cmd[0]} is not an executable ({e})") from e
        err = (res.stderr or "").strip()
        if res.returncode != 0 and ("Cannot connect to the Docker daemon" in err or "error during connect" in err
                                    or "connection refused" in err.lower()):
            raise DockerUnreachable(f"docker runtime {self.get_name()}: the daemon at {self.model.where()} cannot be "
                                    f"reached ({err.splitlines()[0][:200]})")
        if check and res.returncode != 0:
            raise RuntimeError(f"docker runtime {self.get_name()}: `docker {' '.join(args[:3])}` failed: {err[-400:]}")
        return res

    def _inspect(self, reference: str) -> dict[str, Any] | None:
        res = self._docker("image", "inspect", reference, check=False)
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout or "[]")
        return dict(data[0]) if data else None

    @staticmethod
    def _record(info: Mapping[str, Any]) -> dict[str, Any]:
        """The parts of an inspect answer the system keeps (serialisable)."""
        cfg = dict(info.get("Config") or {})
        return {"Id": info.get("Id"), "RepoTags": list(info.get("RepoTags") or []),
                "RepoDigests": list(info.get("RepoDigests") or []), "Created": info.get("Created"),
                "Architecture": info.get("Architecture"), "Os": info.get("Os"),
                "Labels": dict(cfg.get("Labels") or {}), "Size": info.get("Size")}

    # ------------------------------------------------------------- the image query
    def supported_query_keys(self) -> frozenset[str]:
        return DOCKER_QUERY_KEYS

    def translate_image_query(self, query: ImageQuery) -> dict[str, Any]:
        return translate_image_query(query)

    #: This runtime's part of the release-owned image-source catalog: the
    #: `docker` blocks, shipped as this package's ``data/image-sources.yml``
    #: (the core reads the file); the local modification tests
    #: read their stand-in container from them.
    image_source_package = "cs_image_system.docker_runtime"

    @classmethod
    def local_test_target(cls) -> Callable[..., Any] | None:
        """The local target the modification tests run on: a throwaway
        container on the host's daemon (``local_target.make_local_target``)."""
        return make_local_target

    def _pull(self, reference: str, platform: str | None) -> dict[str, Any]:
        args = ["pull", "--quiet"]
        if platform:
            args += ["--platform", platform]
        self._docker(*args, reference, timeout=1800)
        info = self._inspect(reference)
        if info is None:
            raise RuntimeError(f"docker runtime {self.get_name()}: {reference} pulled but not inspectable")
        return info

    def _resolved(self, reference: str, info: Mapping[str, Any], publisher: str) -> tuple[str, str, Mapping[str, Any]]:
        """``(identifier, owner, record)``: the identifier is the digest
        reference ``<repository>@sha256:...`` (recorded, so a vendor moving
        a tag shows as a move), the owner the publisher."""
        digests = list(info.get("RepoDigests") or [])
        repo = reference.split("@", 1)[0].rsplit(":", 1)[0] if ("@" in reference or ":" in reference.rsplit("/", 1)[-1]) else reference
        chosen = next((d for d in digests if d.split("@", 1)[0] == repo), digests[0] if digests else None)
        identifier = chosen or str(info.get("Id"))
        return identifier, publisher, self._record(info)

    def query_provider_image(self, os_builder: OSBuilderBaseImageBuilderSubconfig) -> tuple[str, str, Mapping[str, Any]] | None:
        q = os_builder.image_query() if os_builder else ImageQuery()
        native = self.translate_image_query(q)
        reference = str(native["reference"])
        info = self._pull(reference, native.get("platform"))
        publisher = q.publisher[0] if q.publisher else "library"
        return self._resolved(reference, info, str(publisher))

    def query_provider_image_by_id(self, os_builder: OSBuilderBaseImageBuilderSubconfig,
                                   image_id: str) -> tuple[str, str, Mapping[str, Any]] | None:
        """The image an entry pins by ``image_id``: a digest reference
        (``<repository>@sha256:...``), pulled and inspected."""
        if not is_digest_reference(image_id):
            raise ValueError(f"docker runtime {self.get_name()}: image_id {image_id!r} is not a digest reference "
                             "(`<repository>@sha256:<digest>`); a tag moves, a digest does not")
        q = os_builder.image_query() if os_builder else ImageQuery()
        platform = _PLATFORMS.get(str(q.architecture)) if q.architecture else None
        info = self._pull(image_id, platform)
        publisher = q.publisher[0] if q.publisher else "library"
        return image_id, str(publisher), self._record(info)

    # ------------------------------------------------------- the inventory
    def _our_images(self) -> list[dict[str, Any]]:
        """Every image in the store that carries a lineage series label."""
        res = self._docker("image", "ls", "--no-trunc", "--filter", f"label={TAG_PREFIX}series", "--format", "{{.ID}}")
        ids = sorted({ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()})
        out: list[dict[str, Any]] = []
        for iid in ids:
            info = self._inspect(iid)
            if info is not None:
                out.append(self._record(info))
        return out

    def _labels_with_movable(self, record: Mapping[str, Any]) -> dict[str, str]:
        """The image's labels with the movable tags' values on top."""
        labels = {str(k): str(v) for k, v in dict(record.get("Labels") or {}).items()}
        sid = short_id(str(record.get("Id") or ""))
        repo = self.model.get_repository()
        for ref in record.get("RepoTags") or []:
            r, _, tag = str(ref).rpartition(":")
            if not same_repository(r, repo):
                continue
            parsed = parse_movable_tag(tag)
            if parsed and parsed[0] == sid:
                labels[parsed[1]] = parsed[2]
        return labels

    def _display_name(self, record: Mapping[str, Any]) -> str:
        repo = self.model.get_repository()
        for ref in record.get("RepoTags") or []:
            r, _, tag = str(ref).rpartition(":")
            if same_repository(r, repo) and parse_movable_tag(tag) is None:
                return tag
        return short_id(str(record.get("Id") or ""))

    def query_images(self, series: list[str]) -> list[dict[str, Any]]:
        """Every image in the store labelled with ``csis_series`` (read-only),
        narrowed to the series asked about; its lineage facts are its labels
        as built, with what the movable tags say on top."""
        wanted = set(series or [])
        out: list[dict[str, Any]] = []
        for rec in self._our_images():
            labels = self._labels_with_movable(rec)
            if wanted and labels.get(f"{TAG_PREFIX}series") not in wanted:
                continue
            out.append({"image_id": full_id(str(rec.get("Id"))), "name": self._display_name(rec), "state": "available",
                        "created": str(rec.get("Created") or ""), "tags": labels})
        return out

    def inventory(self) -> dict[str, Any]:
        """Every container and every labelled image in the store (read-only),
        and under ``owners`` the ``csis_config`` label each carries."""
        owners: dict[str, dict[str, str]] = {"instances": {}, "images": {}, "disks": {}, "buckets": {}}
        images: list[str] = []
        for rec in self._our_images():
            name = self._display_name(rec)
            images.append(name)
            owner = str(dict(rec.get("Labels") or {}).get(CONFIG_TAG) or "")
            if owner:
                owners["images"][name] = owner
        res = self._docker("ps", "-a", "--format", "{{.Names}}\t{{.Labels}}")
        instances: list[str] = []
        for ln in (res.stdout or "").splitlines():
            name, _, labels = ln.partition("\t")
            if not name.strip():
                continue
            instances.append(name.strip())
            for kv in labels.split(","):
                k, _, v = kv.partition("=")
                if k.strip() == CONFIG_TAG and v.strip():
                    owners["instances"][name.strip()] = v.strip()
        res = self._docker("volume", "ls", "--format", "{{.Name}}\t{{.Labels}}")
        disks: list[str] = []
        for ln in (res.stdout or "").splitlines():
            name, _, labels = ln.partition("\t")
            if not name.strip():
                continue
            disks.append(name.strip())
            for kv in labels.split(","):
                k, _, v = kv.partition("=")
                if k.strip() == CONFIG_TAG and v.strip():
                    owners["disks"][name.strip()] = v.strip()
        return {"instances": sorted(instances), "images": sorted(images), "disks": sorted(disks), "buckets": [],
                "owners": owners}

    # ------------------------------------------------- disposal and tags
    def dispose_image(self, build_id: str) -> bool:
        """Remove one of OUR OWN builds from the store, every tag with it;
        refused while a container was created from it (the container is the
        operator's, and a running one would lose its image)."""
        res = self._docker("ps", "-a", "--filter", f"ancestor={build_id}", "--format", "{{.Names}}", check=False)
        users = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
        if users:
            raise RuntimeError(f"docker runtime {self.get_name()}: image {short_id(build_id)} is in use by "
                               f"container(s) {', '.join(sorted(users))}; decommission them first")
        res = self._docker("image", "rm", "--force", build_id, check=False)
        if res.returncode != 0:
            if "No such image" in (res.stderr or "") or "no such image" in (res.stderr or "").lower():
                log.warning(f"docker image {short_id(build_id)} not found on {self.get_name()}; nothing to remove")
                return False
            raise RuntimeError(f"docker runtime {self.get_name()}: image rm {short_id(build_id)} failed: "
                               f"{(res.stderr or '').strip()[-300:]}")
        log.info(f"docker image {short_id(build_id)} removed from {self.get_name()}")
        return True

    def _move_tags(self, image_id: str, new_tags: list[str], stale_prefixes: list[str]) -> None:
        """Put ``new_tags`` on the image (a tag moves off whatever held it),
        then untag the image's own older tags that begin a stale prefix. New
        first: untagging an image's last reference would remove it."""
        repo = self.model.get_repository()
        for tag in new_tags:
            self._docker("tag", image_id, f"{repo}:{tag}")
        info = self._inspect(image_id) or {}
        for ref in info.get("RepoTags") or []:
            r, _, tag = str(ref).rpartition(":")
            if same_repository(r, repo) and tag not in new_tags and any(tag.startswith(p) for p in stale_prefixes):
                self._docker("rmi", f"{repo}:{tag}", check=False)

    def retag_image(self, image_id: str, tags: dict[str, str]) -> bool:
        """A label is fixed when the image is built, so the lineage facts the
        core stamps after a bake (the parent bound, the fingerprint) are
        carried by MOVABLE TAGS: ``<repository>:<short id>--<key>--<value>``,
        one per key, the older one of the key untagged."""
        if not tags:
            return True
        sid = short_id(image_id)
        new = [movable_tag(image_id, k, str(v)) for k, v in sorted(tags.items())]
        stale = [f"{sid}--{tag_name(k)}--" for k in tags]
        self._move_tags(image_id, new, stale)
        log.info(f"docker image {sid} on {self.get_name()}: {sorted(tags)} moved onto it as tags")
        return True

    def release_commands(self, build_id: str, tags: dict[str, str]):
        """Mark a released build: the tag ``<repository>:<series>--<model>``
        moves onto it (reviewable, gated by config.apply_release)."""
        series = tag_name(str(tags.get("csis_series") or "build"))
        model = tag_name(str(tags.get("csis_release") or "release"))
        e = ExecutableModel(name="docker", type_="executable", binary=self.docker_binary())
        e.args = ["tag", build_id, f"{self.model.get_repository()}:{series}--{model}"]
        e.environment = dict(self.model.daemon_environment())
        return [e]

    def label_key_problem(self, key: str) -> str | None:
        return label_key_problem(key)

    def image_name_as_made(self, name: str) -> str:
        return tag_name(name)

    def image_name_problem(self, name: str) -> str | None:
        return tag_problem(name)

    # ------------------------------------------------ instances (branch 2)
    #: ``docker inspect .State.Status`` in the system's own words. A container
    #: that exited or was only created EXISTS and can be started: STOPPED, the
    #: operator's choice. Paused keeps its memory: SUSPENDED. Nothing here is
    #: a cloud's spelling, and absent is "no such container".
    _DOCKER_POWER = {
        "running": power_state.RUNNING,
        "created": power_state.STOPPED,
        "exited": power_state.STOPPED,
        "paused": power_state.SUSPENDED,
        "restarting": power_state.STARTING,
        "removing": power_state.STOPPING,
        "dead": power_state.UNKNOWN,
    }

    def _container(self, instance_name: str) -> dict[str, Any] | None:
        """``docker inspect`` of the container bearing the instance's name
        (a container's name is unique on a daemon), None when none stands;
        a container of our name that another configuration labelled as its
        own is not ours and reads as absent."""
        res = self._docker("container", "inspect", instance_name, check=False)
        if res.returncode != 0:
            err = (res.stderr or "").lower()
            if "no such" in err or "not found" in err:
                return None
            raise RuntimeError(f"docker runtime {self.get_name()}: `docker container inspect {instance_name}` "
                               f"failed: {(res.stderr or '').strip()[-300:]}")
        data = json.loads(res.stdout or "[]")
        if not data:
            return None
        info = dict(data[0])
        labels = dict((info.get("Config") or {}).get("Labels") or {})
        if self._get_context().services.lineage.belongs_to_another_configuration(labels):
            return None
        return info

    def launch_delivery(self) -> str:
        """A container has no first boot: the instance root uploads the
        launch script at creation and the system runs it by exec after the
        apply."""
        return LAUNCH_DELIVERY_SESSION

    def instance_tags(self, instance_name: str) -> dict[str, str] | None:
        info = self._container(instance_name)
        if info is None:
            return None
        return {str(k): str(v) for k, v in dict((info.get("Config") or {}).get("Labels") or {}).items()}

    def retag_instance(self, instance_name: str, tags: dict[str, str]) -> bool:
        """A container's labels are fixed when it is created: relabel reports
        what a re-create would set and re-creates nothing (an upgrade or a
        decommission and redeclaration makes a container that carries them)."""
        raise NotImplementedError(
            f"docker runtime {self.get_name()}: a container's labels are fixed when it is created; "
            f"{instance_name} would carry {', '.join(f'{k}={v}' for k, v in sorted(tags.items()))} "
            "after a re-create (an upgrade, or a decommission and redeclaration), which relabel does not do")

    def can_query_instance_boot_image(self) -> bool:
        return True

    def query_instance_boot_image(self, instance_name: str) -> str | None:
        """The image id the container was created from (``.Image``): the
        build id itself on this runtime. None when it cannot be read."""
        try:
            info = self._container(instance_name)
        except Exception as e:  # noqa: BLE001 - read-only probe
            log.debug(f"docker runtime {self.get_name()}: boot image of {instance_name!r} unavailable: {e}")
            return None
        if info is None:
            return None
        image = str(info.get("Image") or "")
        return full_id(image) if is_image_id(image) else (image or None)

    def can_query_instance_identity(self) -> bool:
        return True

    def query_instance_identity(self, instance_name: str) -> dict[str, str] | None:
        """The container id (a re-create is a new id, so a new generation, as
        the ledger expects) and the hostname the container was given."""
        try:
            info = self._container(instance_name)
        except Exception as e:  # noqa: BLE001 - read-only probe
            log.debug(f"docker runtime {self.get_name()}: identity of {instance_name!r} unavailable: {e}")
            return None
        if info is None:
            return None
        host = str((info.get("Config") or {}).get("Hostname") or "")
        return {"instance_id": str(info.get("Id") or ""), "provider_hostname": host}

    def can_query_instance_power_state(self) -> bool:
        return True

    def query_instance_power_state(self, instance_name: str) -> str | None:
        try:
            info = self._container(instance_name)
        except Exception as e:  # noqa: BLE001 - read-only probe: unavailable, never fatal
            log.debug(f"docker runtime {self.get_name()}: power state of {instance_name!r} unavailable: {e}")
            return None
        if info is None:
            return power_state.ABSENT
        raw = str((info.get("State") or {}).get("Status") or "")
        mapped = self._DOCKER_POWER.get(raw)
        if mapped is None:
            log.warning(f"docker runtime {self.get_name()}: container {instance_name!r} reports unrecognised "
                        f"status {raw!r}; treating it as unknown")
            return power_state.UNKNOWN
        return mapped

    def can_set_instance_power_state(self) -> bool:
        return True

    def start_instance(self, instance_name: str, timeout: int = 300) -> bool:
        self._docker("start", instance_name, timeout=timeout)
        return self.query_instance_power_state(instance_name) == power_state.RUNNING

    def stop_instance(self, instance_name: str, timeout: int = 300) -> bool:
        self._docker("stop", instance_name, timeout=timeout)
        return power_state.is_off(self.query_instance_power_state(instance_name))

    def run_session_command(self, instance_name: str, script: str, timeout: int = 300) -> tuple[int, str]:
        """``docker exec`` as root, the script on stdin (``bash -s``): the
        session mechanism of a container."""
        cmd = [self.docker_binary(), "exec", "-i", "-u", "root", instance_name, "bash", "-s"]
        try:
            res = subprocess.run(cmd, input=script, capture_output=True, text=True, check=False, timeout=timeout,
                                 env=self.model.process_environment())
        except FileNotFoundError as e:
            raise DockerUnreachable(f"docker runtime {self.get_name()}: {cmd[0]} is not an executable ({e})") from e
        return res.returncode, (res.stdout or "") + (res.stderr or "")

    def ssh_proxy_command(self, instance_name: str) -> list[str] | None:
        return None      # login is by exec, not ssh

    def verify_instance(self, instance_name: str, expected_build: str | None = None,
                        expect_mounts: int = 0, timeout: int = 600,
                        mount_points: list[str] | None = None) -> dict[str, Any]:
        """By exec: the launch marker (the script's last act, so its presence
        means every launch parameter applied), each declared mount point
        in the container's own mount table, and the image the container was
        created from against the expected build."""
        checks: list[dict[str, Any]] = []
        evidence: list[str] = []
        probe = (f"if [ -f {LAUNCH_MARKER_PATH} ]; then echo \"csis-marker: $(cat {LAUNCH_MARKER_PATH})\"; "
                 f"else echo 'csis-marker: absent'; fi\n")
        for mp in mount_points or []:
            probe += (f"if grep -q \" {mp} \" /proc/mounts; then echo 'csis-mount: {mp} mounted'; "
                      f"else echo 'csis-mount: {mp} NOT mounted'; fi\n")
        rc, out = self.run_session_command(instance_name, probe, timeout=min(timeout, 300))
        evidence = [ln for ln in out.splitlines() if ln.startswith("csis-")][-20:]
        marker = next((ln for ln in evidence if ln.startswith("csis-marker:")), "")
        applied = rc == 0 and bool(marker) and "absent" not in marker
        checks.append({"name": "launch script", "ok": applied,
                       "detail": (f"applied ({marker.split(':', 1)[1].strip()})" if applied
                                  else f"no completion marker at {LAUNCH_MARKER_PATH}" if rc == 0
                                  else f"the session failed (exit {rc})")})
        booted = self.query_instance_boot_image(instance_name)
        if expected_build:
            checks.append({"name": "booted image", "ok": booted == expected_build,
                           "detail": f"booted {booted}, expected {expected_build}"})
        else:
            checks.append({"name": "booted image", "ok": booted is not None, "detail": f"booted {booted}"})
        if mount_points:
            seen = [mp for mp in mount_points if f"csis-mount: {mp} mounted" in out]
            missing = [mp for mp in mount_points if mp not in seen]
            checks.append({"name": "data disks mounted", "ok": not missing,
                           "detail": f"mounted: {', '.join(seen) or 'none'}; missing: {', '.join(missing) or 'none'} "
                                     "(each declared mount point in the container's mount table)"})
        elif expect_mounts:
            checks.append({"name": "data disks mounted", "ok": False,
                           "detail": f"{expect_mounts} declared and none named; a container's mounts are checked by name"})
        return {"ok": all(c["ok"] for c in checks), "checks": checks, "evidence": evidence}

    # --------------------------------------------------------- the bake
    def session_mechanism(self) -> str | None:
        return "exec"

    def default_bake_user(self, family: str) -> str | None:
        return "root"

    def bake_ssh_username(self, image=None) -> str | None:
        if image is None:
            return self.default_bake_user("")
        return self._get_context().services.images.resolve_bake_user(image, self.get_name())

    def bake_settle_commands(self, os_family: str | None = None) -> list[str]:
        """A container has no first boot and no fleet management to wait
        for, but a vendor image may lack what every later step uses: sudo
        (the steps are written for a cloud image's unprivileged user) and,
        on Debian, python3 for ansible."""
        return [
            "# a container settles at once; it may lack sudo and python3, which the steps that follow use",
            "if ! command -v sudo >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then "
            "if command -v apt-get >/dev/null 2>&1; then apt-get update -qq && "
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo python3 procps >/dev/null; "
            "elif command -v dnf >/dev/null 2>&1; then dnf -y -q install sudo python3 procps-ng >/dev/null; "
            "elif command -v microdnf >/dev/null 2>&1; then microdnf -y install sudo python3 procps-ng >/dev/null; fi; fi",
        ]

    def bake_ansible_vars(self, image: Any) -> dict[str, str]:
        """Ansible reaches the build container through the daemon, by name
        (packer's ansible provisioner documents this for its docker
        builder); the connection reads the same ``DOCKER_HOST``."""
        return {"ansible_connection": "docker",
                "ansible_host": bake_container_name(str(image.get_name()), self.get_name())}

    def packer_source_type(self) -> str:
        return DOCKER_SOURCE

    def packer_source_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                             self_subconfig: Any, psi: Any, tags: dict[str, str],
                             final_name: str, pinned: str | None) -> list[str]:
        return docker_source(self.model, image, runtime=runtime, source_type=source_type, subconfig=subconfig,
                             self_subconfig=self_subconfig, psi=psi, tags=tags, final_name=final_name, pinned=pinned)

    def packer_post_processor_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                                     final_name: str) -> list[str]:
        prefix = subconfig.get_image_output_name() if subconfig is not None else None
        return docker_tag_post_processor(image, repository=self.model.get_repository(), source_type=source_type,
                                         final_name=final_name, prefix=prefix)

    def build_id_from_artifact(self, artifact_id: str) -> str:
        """The docker builder's manifest artifact_id is the committed image
        id (``sha256:...``), kept whole: a tag is a name, the id is the build."""
        a = (artifact_id or "").strip()
        return full_id(a) if is_image_id(a) else a


class DockerCLIVersionChecker(AbstractVersionChecker):
    """``docker --version``: ``Docker version 29.8.2, build 7fc2dff``."""

    @classmethod
    def csis_name(cls) -> str:
        return DOCKER_RUNTIME

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.VERSION_CHECKER

    def get_regex(self) -> str:
        return r"[Dd]ocker version ([\d\.]+)"
