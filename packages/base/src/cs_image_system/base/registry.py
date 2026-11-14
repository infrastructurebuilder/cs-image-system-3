# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import operator
from dataclasses import fields, is_dataclass
from functools import cache, reduce
from importlib.metadata import entry_points
from typing import Any, NamedTuple

from cs_image_system.contract.core import (
    BuilderProtocol,
    NameTypedProtocol,
    ParentPropertyHoldingProtocol,
    PluginArtifactProtocol,
    PluginMetadataProtocol,
)

log = logging.getLogger(__name__)

from cs_image_system.contract.constants import DEFAULT, FK_ALSO_SET_ON_UPDATE, OOPS_DEFAULTS, VCT

#: What joins a namespace to a name in the qualified form of a registration
#: (``<namespace>/<name>``). No canonical name and no alias carries it: the
#: load refuses ``/`` in an alias, so the split is never ambiguous.
NAMESPACE_SEPARATOR = "/"

#: The namespace of the core's own registrations: what ``base`` registers
#: through its entry point (the generic version checker, the storage
#: mapping item model), derived from its distribution name like any
#: plugin's.
CORE_NAMESPACE = "base"


class RegistrationKey(NamedTuple):
    """The one key every class-level registry table is keyed by: the
    classification a class registers under, the namespace of the plugin
    that registered it (derived from its distribution, or the
    ``namespace`` its metadata names) and the class's canonical name. A
    typed tuple, never a joined string: the tables are read by the key's
    fields, and the qualified form is for a tree and a message."""

    classification: VCT
    namespace: str
    name: str

    @property
    def qualified(self) -> str:
        """``<namespace>/<name>``: what a tree writes to name this
        registration and no other."""
        return f"{self.namespace}{NAMESPACE_SEPARATOR}{self.name}"


class InstanceKey(NamedTuple):
    """The one key every instance-level registry table is keyed by: the
    classification an instance is registered under, the namespace of the
    plugin that serves it (its class's, :meth:`Registry.namespace_of_class`),
    its ancestry (the global id of the item it is declared in; empty for an
    item a tree declares at its top level, :func:`ancestry_of`) and its name
    or one of its aliases. A typed tuple like :class:`RegistrationKey`, read
    by its fields: the model's ``name`` and ``global_id`` are untouched, and
    the joined form is for a message and for a tree that writes it."""

    classification: VCT
    namespace: str
    ancestry: str
    name: str

    @property
    def qualified(self) -> str:
        """``<namespace>/<name>`` for a top-level instance,
        ``<namespace>/<ancestry>/<name>`` for one declared in another item:
        what a tree writes to name this instance and no other."""
        parts = (self.namespace, self.ancestry, self.name) if self.ancestry else (self.namespace, self.name)
        return NAMESPACE_SEPARATOR.join(parts)


#: The field that holds an item's parent by reference: the contract's
#: ``ParentPropertyHoldingProtocol`` names it, and ``fields.parent_field``
#: declares it.
PARENT_REFERENCE_FIELD = "_model_id"

#: The property a foreign key names in ``also_set_on_update`` when the
#: model it references is also the item's parent (a group's or a user's
#: ``type``).
PARENT_SETTER = "model_id"


@cache
def _served_by_its_parent(cls: type) -> bool:
    """Whether an item of ``cls`` takes its parent from its own ``type``: a
    foreign key other than the parent reference that also sets the parent
    (a group's, a user's), so the parent is the builder that serves the
    item, not an item it is declared in."""
    if not is_dataclass(cls):
        return False
    return any(f.name != PARENT_REFERENCE_FIELD and f.metadata.get(FK_ALSO_SET_ON_UPDATE) == PARENT_SETTER
               for f in fields(cls))


def ancestry_of(item: Any) -> str:
    """The ancestry an instance is keyed by: the global id of the item it
    is declared in (its parent reference), read only from an item that
    holds its parent by reference; empty for an item a tree declares at its
    top level, which includes an item whose parent is the builder that
    serves it (:func:`_served_by_its_parent`) and every builder."""
    if isinstance(item, BuilderProtocol) or not isinstance(item, ParentPropertyHoldingProtocol):
        return ""
    if _served_by_its_parent(type(item)):
        return ""
    return item.model_id or ""


def _own_name(instance: Any) -> str:
    """The name an instance registers under: its model's for a builder."""
    model = instance.model if isinstance(instance, BuilderProtocol) else instance
    return model.get_name()


def _declared(instance: Any) -> str:
    """An instance as a tree declared it, for a message: the name it wrote
    and its class, never its repr (a model's carries every field)."""
    model = instance.model if isinstance(instance, BuilderProtocol) else instance
    written = getattr(model, "display_name", None) or _own_name(instance)
    return f"{written!r} (a {type(instance).__name__})"


def split_qualified(word: str) -> tuple[str | None, str]:
    """A ``type:`` word as (namespace, name): ``("some-plugin", "x")`` for
    ``some-plugin/x``, ``(None, "x")`` for the bare ``x``."""
    namespace, sep, name = word.partition(NAMESPACE_SEPARATOR)
    return (namespace, name) if sep else (None, word)


def bare_name(word: str) -> str:
    """The name part of a bare or a qualified ``type:`` word."""
    return split_qualified(word)[1]


class AmbiguousTypeError(ValueError):
    """A bare ``type:`` word that several DIFFERENT classes answer to under
    one classification, each from its own namespace: the tree must say
    which, by the qualified form. Raised by every lookup that resolves a
    word; ``validate`` prints it as one configuration error."""

    def __init__(self, classification: VCT, word: str, keys: list["RegistrationKey"]) -> None:
        self.classification = classification
        self.word = word
        self.keys = sorted(keys)
        forms = ", ".join(k.qualified for k in self.keys)
        super().__init__(f"type {word!r} is ambiguous under {classification.value}: "
                         f"{len(self.keys)} plugins register it; write one of {forms}")


class UnknownTypeError(ValueError):
    """A ``type:`` word no installed plugin registers under its
    classification. Raised where a tree's item is structured; ``validate``
    prints it as one configuration error. The line names the umbrella's
    extra that installs the plugin when the umbrella's table knows the
    word (the table is the umbrella's own module, reached through the
    entry point group :data:`EXTRAS_ENTRY_POINT_GROUP`: the core names no
    provider), else the words the installed plugins do register there."""

    def __init__(self, classification: VCT, word: str, registered: list[str]) -> None:
        self.classification = classification
        self.word = word
        self.registered = sorted(registered)
        super().__init__(unknown_type_message(classification.value, word, self.registered))


#: The entry point group the umbrella declares its extras table in: one
#: entry point naming a module with ``unknown_type_message(classification,
#: word, registered) -> str``; the core composes the line through it.
EXTRAS_ENTRY_POINT_GROUP = "cs_image_system.extras"


def _kind_of(classification: str) -> str:
    return classification.removesuffix("_model").removesuffix("_builder").replace("_", " ")


def unknown_type_message(classification: str, word: str, registered: list[str]) -> str:
    """One line for a ``type:`` word no installed plugin registers under
    ``classification``: the umbrella's table says which extra installs
    the plugin when an umbrella is installed and knows the word; without
    one the line says the word is unknown and lists the registered ones."""
    for ep in entry_points(group=EXTRAS_ENTRY_POINT_GROUP):
        try:
            compose = getattr(ep.load(), "unknown_type_message", None)
        except Exception as e:  # noqa: BLE001 - a broken table never hides the configuration error
            log.debug(f"extras table {ep.value!r} did not load: {e}")
            continue
        if callable(compose):
            return str(compose(classification, word, registered))
    known = ", ".join(sorted(registered)) or "nothing"
    return (f"{_kind_of(classification)} type {word!r} is unknown: no installed plugin registers it under "
            f"{classification}; the installed plugins register {known}")


def sanitize_classifier(classifer:VCT| None) -> VCT:
    if not classifer:
        return None # type: ignore
    if classifer in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
        return VCT.RUNTIME_BUILDER_MODEL
    return classifer


def _resolve(table: dict[RegistrationKey, type], classification: VCT, word: str) -> type | None:
    """The one class ``word`` names in ``table`` under ``classification``.
    A qualified word (``<namespace>/<name>``) reads its key directly. A
    bare word resolves when exactly one class answers to it, whatever the
    namespaces carrying it (one checker three plugins register is one
    class); when different classes answer, :class:`AmbiguousTypeError`
    names every qualified form; when none does, ``None``."""
    namespace, name = split_qualified(word)
    if namespace is not None:
        return table.get(RegistrationKey(classification, namespace, name))
    hits = [(key, cls) for key, cls in table.items() if key.classification == classification and key.name == name]
    if not hits:
        return None
    classes: list[type] = []
    for _key, cls in hits:
        if not any(cls is c for c in classes):
            classes.append(cls)
    if len(classes) > 1:
        raise AmbiguousTypeError(classification, word, [key for key, _cls in hits])
    return classes[0]


def _names_under(table: dict[RegistrationKey, type], classification: VCT) -> dict[str, type]:
    """Every class in ``table`` under ``classification`` by the shortest
    word that resolves to it: the bare name where one class answers to it,
    the qualified form where several do."""
    by_name: dict[str, list[tuple[RegistrationKey, type]]] = {}
    for key, cls in table.items():
        if key.classification == classification:
            by_name.setdefault(key.name, []).append((key, cls))
    out: dict[str, type] = {}
    for name, hits in by_name.items():
        first = hits[0][1]
        if all(cls is first for _key, cls in hits):
            out[name] = first
        else:
            for key, cls in hits:
                out[key.qualified] = cls
    return out


class InstanceCollisionError(ValueError):
    """A registration that would take a name, an alias or a global id a
    different instance holds: two declarations under one name, an alias
    another item holds, or a top-level name or alias another plugin's
    instance holds in the same table (the emission names every instance by
    its own name, so two top-level instances of one name could not both be
    written out). Raised before anything is written, so the registry is as
    it was; the message names both declarations and never a model's repr."""


def instance_key_of_word(classification: VCT, word: str) -> InstanceKey | None:
    """The key a qualified word a tree wrote names: ``<namespace>/<name>``
    for a top-level instance, ``<namespace>/<ancestry>/<name>`` for one
    declared in another item; ``None`` for a word of another shape. No
    name, alias or global id carries the separator (the load refuses it in
    a name and an alias), so the split is never ambiguous."""
    parts = word.split(NAMESPACE_SEPARATOR)
    if len(parts) == 2:
        return InstanceKey(classification, parts[0], "", parts[1])
    if len(parts) == 3:
        return InstanceKey(classification, parts[0], parts[1], parts[2])
    return None


def _resolve_instance(table: dict[InstanceKey, Any], classification: VCT, word: str) -> Any | None:
    """The one instance ``word`` names in ``table``. A qualified word reads
    its key directly (:func:`instance_key_of_word`). A bare name or alias
    finds the top-level instance (ancestry empty) that answers to it,
    whatever namespace serves it: registration keeps a top-level name or
    alias to one instance per table across every namespace, so a bare word
    never has two answers. ``None`` when none answers. An item declared in
    another one is never found by a bare word: its siblings in other
    parents share its name."""
    if NAMESPACE_SEPARATOR in word:
        qualified = instance_key_of_word(classification, word)
        return table.get(qualified) if qualified is not None else None
    return next((held for key, held in table.items() if key.name == word and not key.ancestry), None)


def _words_under(table: dict[InstanceKey, Any]) -> dict[str, Any]:
    """Every instance in ``table`` once, in the order it was first
    entered, by the shortest word that names it: a top-level instance's
    bare name (registration keeps it to one instance per table), an item
    declared in another one's qualified form (its siblings in other
    parents share its name). The word is its own key's, the first it is
    entered under (its name comes before its aliases); alias keys name no
    entry."""
    out: dict[str, Any] = {}
    seen: set[int] = set()
    for key, held in table.items():
        if id(held) not in seen:
            seen.add(id(held))
            out[key.qualified if key.ancestry else key.name] = held
    return out


#: the runtime namespace a cloud or container classification is entered in
#: too, so a runtime is found by name whatever its kind
RUNTIME_NAMESPACE_OF: dict[VCT, VCT] = {
    VCT.CLOUD_BUILDER_MODEL: VCT.RUNTIME_BUILDER_MODEL,
    VCT.CONTAINER_BUILDER_MODEL: VCT.RUNTIME_BUILDER_MODEL,
    VCT.CLOUD_BUILDER: VCT.RUNTIME_BUILDER,
    VCT.CONTAINER_BUILDER: VCT.RUNTIME_BUILDER,
}


class Registry:
    """A registry for mapping type and key identifiers to classes for polymorphic deserialization.
    This registry allows for dynamic registration of classes that can be instantiated based on
    type and key identifiers found in configuration data. It supports multiple categories of
    classes (e.g., builders, executables) and allows for flexible deserialization of complex
    configurations.

    One registry per run: the loader makes it, loads the
    installed plugins into it (:func:`~.loader.load_plugins`) and carries it
    as ``ctx.reg``. A builder reads it through its bound context; a model
    holds the one of the run that structured it (the converter binds each
    model it builds); a command that runs before, or without, a load makes
    one of its own (:func:`~.loader.installed_registry`). The process holds
    none: two registries share nothing, and neither do two runs.
    """

    # NOTE: state is instance-level (built in __init__), NOT class-level, so
    # two registries share nothing; reset() gives an explicit lifecycle.
    # the class-level tables (what the plugins registered) are keyed by the
    # typed RegistrationKey (classification, namespace, name); the
    # instance-level table (what the tree declared) by the typed InstanceKey
    # (classification, namespace, ancestry, name), one dict per
    # classification, so a bare word is answered from its own classification
    registry: dict[RegistrationKey, type]
    vct_type_registry: dict[VCT, list[type]]
    reverse_registry: dict[type, list[RegistrationKey]]
    builder_for_model: dict[type, type]
    # aliases is VCT -> name -> list of aliases
    aliases: dict[VCT, dict[str, list[str]]]
    classified_aliases: dict[VCT, list[str]]
    defaults_registry: dict[VCT, str | None]
    instances: dict[VCT, dict[InstanceKey, Any]]
    instances_by_global_id: dict[str, Any]
    models: dict[RegistrationKey, type]
    builders: dict[type[NameTypedProtocol], type]
    class_namespaces: dict[type, str]

    def __init__(self):
        self._init_state()

    # The registry is an identity object: a model copy (`copy.deepcopy` of an
    # executable or a tag map) keeps its handle to THE registry rather than
    # cloning every registered model and builder (and, through a builder's
    # bound context, the whole run).
    def __deepcopy__(self, memo: dict[int, Any]) -> "Registry":
        memo[id(self)] = self
        return self

    def __copy__(self) -> "Registry":
        return self

    def _init_state(self) -> None:
        self.registry = {}
        self.vct_type_registry = {}
        self.reverse_registry = {}
        self.builder_for_model = {}
        self.aliases = {}
        self.classified_aliases = {}
        self.defaults_registry = {}
        self.instances = {v: {} for v in VCT}
        self.instances_by_global_id = {}
        self.models = {}
        self.builders = {}
        self.class_namespaces = {}

    def reset(self) -> None:
        """Clear all registered models, instances, builders, defaults and aliases.

        A fresh run makes a fresh registry; this empties one in place for a
        holder that keeps it (a unit test's fixture).
        """
        self._init_state()

    @staticmethod
    def namespace_of(metadata: PluginMetadataProtocol, namespace: str | None = None) -> str:
        """The namespace ``metadata``'s registrations carry: the one the
        loader derived from the plugin's distribution (``namespace``), else
        the one the metadata names; neither is the refusal, with the field
        named, because a registration without a namespace has no qualified
        form and nothing could disambiguate it."""
        chosen = namespace or metadata.namespace
        if not chosen:
            raise ValueError("plugin metadata has no distribution to derive a namespace from and names none: "
                             "set PluginMetadata.namespace")
        if NAMESPACE_SEPARATOR in chosen:
            raise ValueError(f"PluginMetadata.namespace {chosen!r} may not contain {NAMESPACE_SEPARATOR!r}")
        return chosen

    def _note_namespace(self, cls: type, namespace: str) -> None:
        """Remember the namespace ``cls`` is registered under, for its
        instances' keys: the first in sort order when several plugins carry
        the one class, so the choice never depends on the load order."""
        held = self.class_namespaces.get(cls)
        self.class_namespaces[cls] = namespace if held is None else min(held, namespace)

    def namespace_of_class(self, cls: type) -> str:
        """The namespace an instance of ``cls`` is keyed by: the one its
        class is registered under; the core's for a class no plugin
        registers (the core's own item models: an image, an instance, a
        group, an image's entries)."""
        return self.class_namespaces.get(cls, CORE_NAMESPACE)

    def instance_key(self, instance: Any) -> InstanceKey:
        """The key ``instance`` is registered under by its own name (its
        aliases take the same key with another name)."""
        return self._key_under(instance.get_classification(), instance)

    def _key_under(self, classifier: VCT, instance: Any) -> InstanceKey:
        return InstanceKey(classifier, self.namespace_of_class(type(instance)), ancestry_of(instance),
                           _own_name(instance))

    def _register_model(self, key: RegistrationKey, cls: type) -> None:
        """One entry of ``models``: the same class under the same key is the
        same registration (a plugin's metadata replayed); the same class
        under another namespace is one registration too, read by its bare
        word (one checker three plugins carry); a DIFFERENT class under
        the same key is the collision."""
        registered = self.models.get(key)
        if registered is not None and registered is not cls:
            raise ValueError(f"Type Collision: {key.qualified} under {key.classification.value} is "
                             f"{registered.__module__}.{registered.__qualname__}, "
                             f"and {cls.__module__}.{cls.__qualname__} registers it too")
        self.models[key] = cls
        self._note_namespace(cls, key.namespace)

    def register_plugin_metadata(self, metadata: PluginMetadataProtocol, namespace: str | None = None):
        """Register what one plugin's metadata declares, every class keyed
        by ``namespace`` (the loader passes the one it derived from the
        plugin's distribution; a caller with no distribution behind the
        metadata -- a test -- passes one, or the metadata names it)."""
        ns = self.namespace_of(metadata, namespace)
        for _service_group, artifacts in metadata.services.items():
            for artifact in artifacts:
                classifier = artifact.csis_classifier()
                
                # =========================================================
                # FIX: Align model registry with loader.py overrides!
                # Treat Cloud and Container models as Runtime models.
                # =========================================================
                classifier = sanitize_classifier(classifier)
                
                self._register_model(RegistrationKey(classifier, ns, artifact.csis_name()), artifact)

        for model_type, builder_type in metadata.builders_for_models.items():
            registered = self.builders.get(model_type)
            if registered is not None and registered is not builder_type:
                raise ValueError(f"Builder for model '{model_type.__name__}' is already registered.")
            self.builders[model_type] = builder_type
        for classifier, model_type in metadata.injected_models.items():
            # an injected item model names itself when it is a plugin artifact
            injected: Any = model_type
            name = injected.csis_name() if isinstance(injected, PluginArtifactProtocol) else model_type.__name__
            self._register_model(RegistrationKey(classifier, ns, name), model_type)
            if metadata.is_injected_models_default:
                self.set_default_for(classifier, name)

    def models_under(self, classifier: VCT) -> dict[str, type]:
        """Every model class registered under ``classifier`` by the word
        that resolves to it: the bare name, or the qualified form where
        different classes share the name."""
        return _names_under(self.models, classifier)

    def registration_keys(self, classifier: VCT | None = None) -> list[RegistrationKey]:
        """Every key of ``models``, under ``classifier`` when given, sorted."""
        return sorted(k for k in self.models if classifier is None or k.classification == classifier)

    def runtime_builder_classes(self) -> dict[str, type]:
        """Every registered runtime builder class by its canonical name:
        the clouds, the containers and the plain runtimes, which the
        loader registers under their own classifications."""
        out: dict[str, type] = {}
        for classifier in (VCT.RUNTIME_BUILDER, VCT.CLOUD_BUILDER, VCT.CONTAINER_BUILDER):
            out.update(self.models_under(classifier))
        return out

    def state_builder_classes(self) -> dict[str, type]:
        """Every registered state backend builder class by its canonical name."""
        return self.models_under(VCT.STATE_BACKEND)

    def get_model(self, classifier: VCT, canonical_name: str) -> type[PluginArtifactProtocol] | None:
        """The model class a ``type:`` word names under ``classifier``: a
        bare word when one class answers to it, a qualified word
        (``<namespace>/<name>``) directly; ``None`` for a word nobody
        registered; :class:`AmbiguousTypeError` for a bare word different
        classes answer to."""
        return _resolve(self.models, classifier, canonical_name)  # type: ignore[return-value]
    def get_instance(self, classifier: VCT, name_or_alias: str) -> NameTypedProtocol | None:
        """The instance a word names under ``classifier`` (:func:`_resolve_instance`)."""
        return _resolve_instance(self.instances.get(classifier, {}), classifier, name_or_alias)
    def builder_keys(self) -> list[type[NameTypedProtocol]]:
        return list(self.builders.keys())
    def builder_values(self) -> list[type]:
        return list(self.builders.values())
    
    def get_instance_by_global_id(self, global_id: str) -> NameTypedProtocol | None:
        return self.instances_by_global_id.get(global_id, None)

    def register_built_instance(self, instance: Any) -> None:
        """Enter a built model or builder in its classification's table
        under its key and its aliases' (:class:`InstanceKey`), in the
        runtime table of its kind too for a cloud or a container, and in
        the global-id index under its id. The same instance again moves to
        its keys now (its parent reference refined moves its ancestry and
        its id); a different instance under any of those keys is refused
        (:meth:`_check_registration`)."""
        self._register(instance, replacing=False)

    def replace_built_instance(self, instance: Any) -> None:
        """Register ``instance`` in place of the instance that holds its
        own key or its global id: the old one's keys, aliases and id are
        removed and the new one takes its place. The one registration that
        replaces on purpose (a provider-specific image made again for the
        same source and runtime); a key a third instance holds is still
        refused."""
        self._register(instance, replacing=True)

    def _register(self, instance: Any, *, replacing: bool) -> None:
        if not isinstance(instance, NameTypedProtocol):
            log.debug(f"No registering instance {instance} of type {type(instance)}")
            return
        # a builder stands for its model; a model stands for itself (the
        # protocol check is the dispatch)
        model = instance.model if isinstance(instance, BuilderProtocol) else instance
        if not model:
            raise ValueError(f"Cannot register {instance} because it has no model")
        # Determine the namespace (classification)
        classifier = instance.get_classification()
        if classifier is None:
            if not isinstance(instance, PluginArtifactProtocol):
                log.warning(f"Object {instance} does not have a get_classification method or"
                            " a csis_classifier method. Skipping registration.")
                return
            classifier = instance.csis_classifier()
        if not classifier:
            log.warning(f"Could not determine classification for instance {instance}. Skipping registration.")
            return
        aliases = list(model.get_aliases()) if isinstance(model, NameTypedProtocol) else []
        # an id is formatted from the classification, the parent reference
        # and the name, and raises nothing for a real instance; it is read
        # before anything is written, so an id that raises leaves the
        # registry as it was
        global_id = instance.global_id
        own = self._key_under(classifier, instance)
        keys = self._keys_of(own, aliases)
        # every key the registration writes is checked before any is
        # written: a refused registration leaves the registry as it was
        displaced = self._check_registration(own, keys, global_id, instance, replacing)
        for table_vct, key in keys:
            self.instances[table_vct][key] = instance
        self._leave_old_keys(instance, keys, displaced)
        if global_id:
            self._enter_global_id(global_id, instance, displaced)

    @staticmethod
    def _keys_of(own: InstanceKey, aliases: list[str]) -> list[tuple[VCT, InstanceKey]]:
        """Every (table, key) a registration under ``own`` writes: its name
        and each alias in its own classification's table, and again in the
        runtime table of its kind for a cloud or a container."""
        names = [own.name, *(a for a in aliases if a != own.name)]
        tables = [own.classification]
        runtime = RUNTIME_NAMESPACE_OF.get(own.classification)
        if runtime is not None:
            tables.append(runtime)
        return [(table, own._replace(classification=table, name=name)) for table in tables for name in names]

    def _check_registration(self, own: InstanceKey, keys: list[tuple[VCT, InstanceKey]], global_id: str,
                            instance: Any, replacing: bool) -> list[Any]:
        """Refuse a registration that would take a key or a global id a
        different instance holds, before anything is written. The same
        instance already under a key is no collision (an item is
        registered again when its parent is set). A replacing registration
        displaces the instance under its own key and the one under its
        global id, and answers them; any other held key is still refused."""
        displaced: list[Any] = []
        if replacing:
            for held in (self.instances[own.classification].get(own), self.instances_by_global_id.get(global_id)):
                if held is not None and held is not instance and not any(held is d for d in displaced):
                    displaced.append(held)
        for table_vct, key in keys:
            taken = self._held_by_another(table_vct, key, [instance, *displaced])
            if taken is not None:
                held_key, held = taken
                kind = "name" if key.name == own.name else "alias"
                raise InstanceCollisionError(
                    f"Instance {kind} collision under {table_vct.value}: {_declared(instance)} takes "
                    f"{key.qualified!r} and {_declared(held)} holds {held_key.qualified!r}; the emission "
                    f"names every instance by its own name, so rename one")
        held = self.instances_by_global_id.get(global_id) if global_id else None
        if held is not None and held is not instance and not any(held is d for d in displaced):
            raise InstanceCollisionError(
                f"Instance id collision under {own.classification.value}: {_declared(instance)} and "
                f"{_declared(held)} both take the global id {global_id!r}; rename one")
        return displaced

    def _held_by_another(self, table_vct: VCT, key: InstanceKey, mine: list[Any]) -> tuple[InstanceKey, Any] | None:
        """The key and the instance, not one of ``mine``, that already
        hold ``key``'s word in ``table_vct``: the same key for an item
        declared in another one (its siblings in other parents may share
        its name), and any top-level key with the same name, whatever its
        namespace, for a top-level instance (a name or alias is one
        instance's per table, across plugins)."""
        table = self.instances[table_vct]
        if key.ancestry:
            held = table.get(key)
            return (key, held) if held is not None and not any(held is m for m in mine) else None
        return next(((k, held) for k, held in table.items()
                     if k.name == key.name and not k.ancestry and not any(held is m for m in mine)), None)

    def _leave_old_keys(self, instance: Any, keys: list[tuple[VCT, InstanceKey]], displaced: list[Any]) -> None:
        """Remove every key ``instance`` held before this registration and
        does not hold now (its ancestry moved with its parent reference, an
        alias dropped), and every key a displaced instance still holds, from
        the tables this registration wrote to. A key the registration wrote
        keeps its place in its table."""
        written = set(keys)
        for table_vct in {t for t, _k in keys}:
            table = self.instances[table_vct]
            gone = [key for key, held in table.items()
                    if (table_vct, key) not in written and (held is instance or any(held is d for d in displaced))]
            for key in gone:
                del table[key]

    def _enter_global_id(self, global_id: str, instance: Any, displaced: list[Any] | None = None) -> None:
        """Index ``instance`` under ``global_id``, its id now. An instance
        registered again under a new id (its parent reference refined, which
        moves the id) leaves every id it was indexed under before, and a
        displaced instance leaves every id it held: an entry under another
        id is removed only when it holds one of those, so the index never
        keeps an id its object no longer has."""
        index = self.instances_by_global_id
        leaving = [instance, *(displaced or [])]
        for old in [key for key, held in index.items()
                    if key != global_id and any(held is x for x in leaving)]:
            del index[old]
        index[global_id] = instance

    def get_all_instances_by_classification(self, classifier: VCT) -> dict[str, Any]:
        """Every instance registered under ``classifier``, once each, by the
        shortest word that names it (:func:`_words_under`): a top-level
        instance's bare name, an item declared in another one's qualified
        form, so no two instances collapse into one entry."""
        return _words_under(self.instances.get(classifier, {}))

    def get_instance_by_name_or_alias(self, classifier: VCT, name_or_alias: str) -> Any | None:
        """Get a registered instance by its name or any of its aliases under a specific classification."""
        if name_or_alias == DEFAULT:
            d =  self.get_default_for(classifier)
            if d is None:
                log.warning(f"Default value for classification '{classifier}' is not set. Returning None.")
                return None
            name_or_alias = d
        found = _resolve_instance(self.instances.get(classifier, {}), classifier, name_or_alias)
        if found is None:
            log.debug(f"Name or alias '{name_or_alias}' not found in instances registry under classification '{classifier}'. Returning None.")
        return found

    def word_for(self, classifier: VCT, word: str) -> str:
        """The word a reference a tree wrote reads as everywhere after the
        load: a qualified word that names an instance under ``classifier``
        becomes the word the registry lists that instance by
        (:meth:`get_all_instances_by_classification`: a top-level
        instance's bare name). Every other word,
        a bare name, an alias or one that names nothing, is returned as it
        was written, so a bare tree reads exactly as before."""
        if not isinstance(word, str) or NAMESPACE_SEPARATOR not in word:
            return word
        table = self.instances.get(classifier, {})
        found = _resolve_instance(table, classifier, word)
        if found is None:
            return word
        return next((listed for listed, held in _words_under(table).items() if held is found), word)
            
    def register_service(self, service: type[PluginArtifactProtocol], 
                         override_classifier:VCT|None = None, *, namespace: str) -> None:
        """Register a service under its classification (or
        ``override_classifier``: the loader registers a cloud's or a
        container's model a second time as a runtime's), keyed by the
        namespace the loader derived for its plugin. A different class
        under a key already taken is refused (``Type Collision``), where
        it used to be overwritten by the plugin that loaded later."""
        if not namespace or NAMESPACE_SEPARATOR in namespace:
            raise ValueError(f"register_service needs a namespace without {NAMESPACE_SEPARATOR!r}, got {namespace!r}")
        classifier = override_classifier if override_classifier is not None else service.csis_classifier()
        key = RegistrationKey(classifier, namespace, service.csis_name())
        registered = self.registry.get(key)
        if registered is not None and registered is not service:
            raise ValueError(f"Type Collision: service {key.qualified} under {classifier.value} is "
                             f"{registered.__module__}.{registered.__qualname__}, "
                             f"and {service.__module__}.{service.__qualname__} registers it too")
        self.registry[key] = service
        self._note_namespace(service, namespace)
        by_classifier = self.vct_type_registry.setdefault(classifier, [])
        if service not in by_classifier:          # one entry per class, however many plugins carry it
            by_classifier.append(service)
        keys = self.reverse_registry.setdefault(service, [])
        if key not in keys:
            keys.append(key)
        
    def register_aliases(self, classifier: VCT, name: str, aliases: list[str]) -> None:
        """Register all aliases for a given builder under a specific classification."""
        m = self.classified_aliases.setdefault(classifier, [])
        for alias in  [name] + list(aliases):  # Include the name itself as an alias for lookup purposes
            if alias in m:
                raise ValueError(f"Alias '{alias}' is already registered "
                                    f"under classification '{classifier}'. "
                                f"Cannot register duplicate alias for builder '{name}'.")
            m.append(alias)
            self.aliases.setdefault(classifier, {}).setdefault(name, []).append(alias)

    def register_builder_for_model(self, model: type, builder: type) -> None:
        """ Register model to it's corresponding builder """
        if model in self.builder_for_model:
            raise ValueError(f"Builder for model '{model.__name__}' is already registered.")
        self.builder_for_model[model] = builder
    
    def set_default_for(self, type: VCT, value: str | None) -> None:
        existing = self.defaults_registry.get(type, None)
        if existing is not None and value != existing:
            raise ValueError(f"Default value for type '{type}' is already set "
                             f"to '{self.defaults_registry[type]}'. Cannot override with '{value}'.")    
        self.defaults_registry[type] = value

    def get_default_for(self, type: VCT) -> str | None:
        """The word that names the default of ``type``: the one set for it,
        else (when nothing set any default) the first top-level instance
        that says it is the default. An item declared in another one is
        never a classification's default: a bare word never finds it."""
        if not self.defaults_registry:
            log.debug("No default values have been set in the registry. Populating....")
            for classifier, inst in self.instances.items():
                for key, instance in inst.items():
                    if key.ancestry or self.defaults_registry.get(classifier, None) is not None:
                        continue
                    if instance.get_is_default():
                        self.set_default_for(classifier, key.name)
        if not type in self.defaults_registry:
            log.debug(f"No default value set for type '{type}'. Populating.")
            return None
        default = self.defaults_registry.get(type, None)
        if default in OOPS_DEFAULTS:
            raise ValueError(f"Default value for type '{type}' cannot be in {OOPS_DEFAULTS}: '{default}'")
        return default

    def get_types_by_classification(self, classification: VCT) -> type | None:
        """
        Get a list of classes registered under a specific classification.
        Returned as a union for use in type annotations for polymorphic deserialization.
        
        """
        clz: list[type] = self.vct_type_registry.get(classification, [])
        classes = tuple(clz + [None])
        if len(classes) == 1:
            raise ValueError(f"No classes found for classification '{classification}'")
        return reduce(operator.or_, classes)

    # def get_registered_types(self, key: str | type, default=None) -> list[type]:
    #     if isinstance(key, type):
    #         key = key.__name__
    #     if default is None:
    #         default = dict
    #     val = self.vct_type_registry.get(key, [default])
    #     if val == [default]:
    #         log.warning(f"Warning: Key '{key}' not found in registry. Returning default value.")
    #     return val


    def get_registered_name_by_name_or_alias(self,classification:VCT, name_or_alias:str) -> str | None:
        """Get the builder name registered for a given alias or name under a specific classification."""
        if DEFAULT == name_or_alias:
            return self.get_default_for(classification) # type: ignore
        if name_or_alias is None:
            return None
        alias_list = self.aliases.get(classification, {})
        if name_or_alias in alias_list:
            for name, aliases in alias_list.items():
                if name_or_alias == name or name_or_alias in aliases:
                    return name
        log.warning(f"Warning: Name or alias '{name_or_alias}' not found in registry under classification '{classification}'. Returning None.")
        return None

    # FIXME: Unused?
    def get_builder_by_alias_or_name(self, classification:VCT, name_or_alias:str) -> type | None:
        """Get a registered builder class by its name or any of its aliases under a specific classification."""
        # First check if it's a direct name match
        target_name = self.get_registered_name_by_name_or_alias(classification, name_or_alias)
        if target_name:
            return _resolve_instance(self.instances.get(classification, {}), classification, target_name)
        log.warning(f"Warning: Name or alias '{name_or_alias}' not found in registry under classification '{classification}'. Returning None.")
        return None

    def get_builder_for_model(self, type_name: str, classification: VCT) -> type | None:
        """The service class registered under ``classification`` for a
        model's ``type:`` word, bare or qualified, by the rule of
        :meth:`get_model`."""
        return _resolve(self.registry, classification, type_name)

