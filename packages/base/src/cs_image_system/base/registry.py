# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any, NamedTuple
import operator
from functools import reduce


from cs_image_system.contract.core import BuilderProtocol, NameTypedProtocol, PluginArtifactProtocol, PluginMetadataProtocol

log = logging.getLogger(__name__)

from cs_image_system.contract.constants import DEFAULT, OOPS_DEFAULTS, VCT

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


class Registry:
    """A registry for mapping type and key identifiers to classes for polymorphic deserialization.
    This registry allows for dynamic registration of classes that can be instantiated based on
    type and key identifiers found in configuration data. It supports multiple categories of
    classes (e.g., builders, executables) and allows for flexible deserialization of complex
    configurations.

    One registry per run (stage 124): the loader makes it, loads the
    installed plugins into it (:func:`~.loader.load_plugins`) and carries it
    as ``ctx.reg``; a builder reads it through its bound context. The
    process holds the one made last for the code that has no context handle
    (a model, a pre-load command) -- :func:`current_registry`, the
    one-release shim that stands where the ``@singleton`` fetch stood.
    """

    # NOTE: state is instance-level (built in __init__), NOT class-level, so
    # two registries share nothing; reset() gives an explicit lifecycle.
    # the class-level tables (what the plugins registered) are keyed by the
    # typed RegistrationKey (classification, namespace, name); the
    # instance-level tables (what the tree declared) by the tree's own names
    registry: dict[RegistrationKey, type]
    vct_type_registry: dict[VCT, list[type]]
    reverse_registry: dict[type, list[RegistrationKey]]
    builder_for_model: dict[type, type]
    # aliases is VCT -> name -> list of aliases
    aliases: dict[VCT, dict[str, list[str]]]
    classified_aliases: dict[VCT, list[str]]
    defaults_registry: dict[VCT, str | None]
    instances: dict[VCT, dict[str, Any]]
    instances_by_global_id: dict[str, Any]
    models: dict[RegistrationKey, type]
    builders: dict[type[NameTypedProtocol], type]

    def __init__(self):
        self._init_state()

    # The registry is an identity object: a model copy (`copy.deepcopy` of an
    # executable or a tag map) keeps its handle to THE registry rather than
    # cloning every registered model and builder (and, since stage 124,
    # through a builder's bound context, the whole run).
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

    def register_plugin_metadata(self, metadata: PluginMetadataProtocol, namespace: str | None = None):
        """Register what one plugin's metadata declares, every class keyed
        by ``namespace`` (the loader passes the one it derived from the
        plugin's distribution; a caller with no distribution behind the
        metadata -- a test -- passes one, or the metadata names it)."""
        ns = self.namespace_of(metadata, namespace)
        for service_group, artifacts in metadata.services.items():
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
        return self.instances.get(classifier, {}).get(name_or_alias, None)
    def builder_keys(self) -> list[type[NameTypedProtocol]]:
        return list(self.builders.keys())
    def builder_values(self) -> list[type]:
        return list(self.builders.values())
    
    def get_instance_by_global_id(self, global_id: str) -> NameTypedProtocol | None:
        return self.instances_by_global_id.get(global_id, None)

    def register_built_instance(self, instance):
        """Registers a built model into the namespaced runtime state tracker."""
        if not isinstance(instance, NameTypedProtocol):
            log.debug(f"No registering instance {instance} of type {type(instance)}")
            return
        # a builder stands for its model; a model stands for itself (the
        # protocol check is the dispatch, stage 125)
        model = instance.model if isinstance(instance, BuilderProtocol) else instance
        if not model:
            raise ValueError(f"Cannot register {instance} because it has no model")
        model_name = model.get_name() if isinstance(model, NameTypedProtocol) else str(model)        
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
        # Register by name within the namespace
        if model.get_name() in self.instances[classifier]:
            log.debug(f"Overwriting instance {model.get_name()} in namespace {classifier}")  # expected: re-registered across resolve passes
        self.instances[classifier][model.get_name()] = instance
        try:
            _gid = instance.global_id
            if _gid:
                self.instances_by_global_id[_gid] = instance
        except Exception as e:
            log.warning(f"Instance {instance} does not have a valid global_id. Skipping registration in global_id registry. Error: {e}")
            
        if classifier in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
            if model_name in self.instances[VCT.RUNTIME_BUILDER_MODEL]:
                raise ValueError(f"Instance name collision: '{model_name}' is already registered in RUNTIME_BUILDER_MODEL namespace!")
            self.instances[VCT.RUNTIME_BUILDER_MODEL][model_name] = instance
        if classifier in [VCT.CLOUD_BUILDER, VCT.CONTAINER_BUILDER]:
            if model_name in self.instances[VCT.RUNTIME_BUILDER]:
                raise ValueError(f"Instance name collision: '{model_name}' is already registered in RUNTIME_BUILDER namespace!")
            self.instances[VCT.RUNTIME_BUILDER][model_name] = instance
        
        # Register aliases within the namespace
        for alias in (model.get_aliases() if isinstance(model, NameTypedProtocol) else set()):
            if alias in self.instances[classifier]:
                raise ValueError(f"Instance Alias Collision: '{alias}' is already in use for {classifier}!")
            self.instances[classifier][alias] = instance
            if classifier in [VCT.CLOUD_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL]:
                if alias in self.instances[VCT.RUNTIME_BUILDER_MODEL]:
                    raise ValueError(f"Instance name collision: '{alias}' is already registered in RUNTIME_BUILDER_MODEL namespace!")
                self.instances[VCT.RUNTIME_BUILDER_MODEL][alias] = instance
            if classifier in [VCT.CLOUD_BUILDER, VCT.CONTAINER_BUILDER]:
                if alias in self.instances[VCT.RUNTIME_BUILDER]:
                    raise ValueError(f"Instance name collision: '{alias}' is already registered in RUNTIME_BUILDER namespace!")
                self.instances[VCT.RUNTIME_BUILDER][alias] = instance

    def get_all_instances_by_classification(self, classifier: VCT) -> dict[str, Any]:
        """Get all registered instances under a specific classification."""
        res: dict[str, Any] = {}
        for k,v  in self.instances.get(classifier, {}).items():
            res[v.get_name()] = v           
        return res
    def get_instance_by_name_or_alias(self, classifier: VCT, name_or_alias: str) -> Any | None:
        """Get a registered instance by its name or any of its aliases under a specific classification."""
        if name_or_alias == DEFAULT:
            d =  self.get_default_for(classifier)
            if d is None:
                log.warning(f"Default value for classification '{classifier}' is not set. Returning None.")
                return None
            name_or_alias = d
        if name_or_alias in self.instances.get(classifier, {}):
            return self.instances[classifier][name_or_alias]
        log.debug(f"Name or alias '{name_or_alias}' not found in instances registry under classification '{classifier}'. Returning None.")
        return None
            
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
        if not self.defaults_registry:
            log.debug("No default values have been set in the registry. Populating....")
            for classifier, inst in self.instances.items():
                for name, instance in inst.items():
                    if self.defaults_registry.get(classifier, None) is not None:
                        continue
                    if instance.get_is_default():
                        self.set_default_for(classifier, name)
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
        rr = self.registry
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
            return self.instances.get(classification, {}).get(target_name, None)
        log.warning(f"Warning: Name or alias '{name_or_alias}' not found in registry under classification '{classification}'. Returning None.")
        return None

    def get_builder_for_model(self, type_name: str, classification: VCT) -> type | None:
        """The service class registered under ``classification`` for a
        model's ``type:`` word, bare or qualified, by the rule of
        :meth:`get_model`."""
        return _resolve(self.registry, classification, type_name)



# --- the one registry of this process (one-release shim, stage 124)
_CURRENT: Registry | None = None


def bind_current_registry(reg: Registry | None) -> None:
    """Make ``reg`` the registry :func:`current_registry` answers with
    (``None`` unbinds). The loader binds the one it made for its run before
    any model of that run is parsed; the test harness unbinds between loads.
    Nothing else should call this."""
    global _CURRENT
    _CURRENT = reg


def current_registry() -> Registry:
    """The registry of the run loaded last in this process, or -- before any
    run is loaded (a pre-load command: the preflight, the catalog, the
    scan) -- one made and bound here on the first ask, for the plugins to
    load into.

    This is the one-release shim that stands in for the retired
    ``Registry()`` singleton fetch: a caller that reaches for it should hold
    the registry instead (a builder has ``self._get_context().reg``; a
    command has ``ctx.reg``; a model holds no context, so a model keeps
    using this until the models are handed theirs)."""
    global _CURRENT
    if _CURRENT is None:
        _CURRENT = Registry()
    return _CURRENT
