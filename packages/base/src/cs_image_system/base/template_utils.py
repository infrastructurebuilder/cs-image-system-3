# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import copy
import logging
import os
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any
import yaml

log = logging.getLogger(__name__)
# from Cheetah.Template import Template as CheetahTemplate
from jinja2 import Environment, Undefined, nodes, Template

from cs_image_system.contract.constants import NAME, PLUGIN_TYPES
from .encryption import decrypt_tree, decrypted_plaintexts
from .reserved_names import refuse_reserved_names
from .helpers import resolution_stages


def fetch_template_file(template: Path) -> str:
    # if template.suffix == ".templ":
    #     with open(template) as f:
    #         rendered_content = str(CheetahTemplate(f.read(), searchList=[]))
    # # elif template.suffix == ".j2":
    # #     jenv = Environment(loader=FileSystemLoader(template.parent))
    # #     tmpl = jenv.get_template(template.name)
    # #     rendered_content = str(tmpl)
    # else:
    with open(template) as f:
        template_content = f.read()
    rendered_content = template_content
    return rendered_content


def recursive_render_j2_template_string(template_str, context, max_depth=10, add_env = False):
    """
    Renders a Jinja template string recursively until no more tags are found
    or max_depth is reached.
    """
    last_rendered = ""
    current_rendered = template_str
    depth = 0
    ext_context = extend_with_envdata(context, include_ENV=add_env) or {}


    # Continue rendering if the content changed in the last pass
    while current_rendered != last_rendered and depth < max_depth:
        render_ctx = ext_context.copy()
        try:
            ctx_new = yaml.safe_load(current_rendered)
            if isinstance(ctx_new, dict):
                render_ctx.update(ctx_new)
        except Exception:
            # log.debug(f"Rendered content is not valid YAML at depth {depth}: {e}")
            pass
        last_rendered = current_rendered
        # Create a new template from the previous output and render with context
        current_rendered = Template(current_rendered).render(**render_ctx)
        depth += 1
    if depth == max_depth:
        raise ValueError(f"Max rendering depth of {max_depth} reached."
                         " Possible loop in template rendering.")
    return current_rendered

def render_j2_template_string(template_str: str, **kwargs) -> str:
    rendered_content = "ERRORED!"
    jenv = Environment(undefined=KeepUndefined)
    try:
        tmpl = jenv.from_string(template_str)
        rendered_content = tmpl.render(kwargs)
    except Exception as e:
        log.error(f"Error rendering Jinja2 template: {e}")
        raise
    return rendered_content


def render_template_file(template: Path, **kwargs) -> str:
    """Render a template file with the provided keyword arguments.

    Args:
        template: Path to the template file.
        **kwargs: Key-value pairs to replace in the template.

    Returns:
        Rendered template as a string.
    """
    t = fetch_template_file(template)
    if template.suffix == ".j2":
        log.warning(
            f"Rendering Jinja2 template {template} with variables: {list(kwargs.keys())}"
        )
        log.warning(f"Template content:\n{t}")
        rendered_content = render_j2_template_string(t, **kwargs)
    # elif template.suffix == ".templ":
    #     with open(template) as f:
    #         rendered_content = str(CheetahTemplate(f.read(), searchList=[kwargs]))
    else:
        with open(template) as f:
            template_content = f.read()
        rendered_content = template_content.format(**kwargs)
    return rendered_content


def get_path_to_template_as_resource(template_name: str) -> Path | None:
    """Read a template file from the package resources.

    Args:
        template_name (str): Name of the template file to read.

    Returns:
        Path to the template file
            or None if not found.
    """
    try:
        templates_dir_ref = files("cs_image_system.image_builders.templates")
        template = templates_dir_ref.joinpath(template_name)
        with as_file(template) as returned_file:
            return returned_file
    except Exception as e:
        log.error(f"Error reading template {template_name} from resources: {e}")
        return None


def get_full_attribute_path(node):
    """Recursively reconstruct a.b.c from GetAttr nodes."""
    if isinstance(node, nodes.Name):
        return node.name
    elif isinstance(node, nodes.GetAttr):  # type: ignore
        base = get_full_attribute_path(node.node)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def find_all_nested_paths(template_source):
    env = Environment()
    ast = env.parse(template_source)
    paths = set()

    # Walk every node in the tree
    for node in ast.find_all((nodes.GetAttr, nodes.Name)):  # type: ignore
        # If it's a Name, it's a top-level variable
        if isinstance(node, nodes.Name):
            paths.add(node.name)
        # If it's a GetAttr, we need to climb up to get the full path
        elif isinstance(node, nodes.GetAttr):  # type: ignore
            full_path = get_full_attribute_path(node)
            if full_path:
                paths.add(full_path)

    # Filter out paths that are just prefixes of longer paths
    # e.g., if we have 'user.name', we don't need 'user' separately
    sorted_paths = sorted(paths, key=len, reverse=True)
    final_paths = []
    for p in sorted_paths:
        if not any(other.startswith(p + ".") for other in final_paths):
            final_paths.append(p)

    return final_paths


# # Example
# source = "Hello {{ user.profile.name }}, your city is {{ address.city }}."
# print(find_all_nested_paths(source))

class PassthroughUndefined(Undefined):
    def __getattr__(self, name):
        return PassthroughUndefined(name=f"{self._undefined_name}.{name}")

    def __getitem__(self, key):
        # Handles {{ missing['key'] }}
        return PassthroughUndefined(name=f"{self._undefined_name}[{repr(key)}]")

    def __str__(self):
        return f"{{{{ {self._undefined_name} }}}}"

    # Handle all mathematical/comparison operations
    def __add__(self, other): return self
    def __sub__(self, other): return self
    def __mul__(self, other): return self
    def __truediv__(self, other): return self
    def __gt__(self, other): return False
    def __lt__(self, other): return False
    def __le__(self, other): return False
    def __ge__(self, other): return False
    def __eq__(self, other): return isinstance(other, PassthroughUndefined)

    # Ensure it doesn't crash loops or conditionals
    def __iter__(self): return iter([])
    def __bool__(self): return False


class _PassthroughBox(dict):
    """Dict wrapper for Jinja contexts that yields a *path-carrying*
    :class:`PassthroughUndefined` for missing keys.

    Without this, a template that navigates into a container that exists but then
    hits a missing child (``this.os.family`` where the item has no ``os``) loses
    the parent path and degrades to ``{{ family }}``, because Jinja names the
    resulting ``Undefined`` after only the final attribute.  This wrapper keeps
    the full dotted path (``this.os.family``) intact for a later resolution stage,
    while still resolving keys that *are* present.
    """
    def __init__(self, data: dict, path: str):
        super().__init__(data)
        self._path = path

    def _resolve(self, key: str):
        if dict.__contains__(self, key):
            return _wrap_passthrough(dict.__getitem__(self, key), f"{self._path}.{key}")
        if key == "display_name" and dict.__contains__(self, "name"):
            # Synonym: at the string stage the raw dict `name` is already the
            # original-case display name (normalization happens later, on the object),
            # so `{{ this.display_name }}` works at both stages.
            return _wrap_passthrough(dict.__getitem__(self, "name"), f"{self._path}.display_name")
        return PassthroughUndefined(name=f"{self._path}.{key}")

    def __getitem__(self, key):
        return self._resolve(key)

    def __getattr__(self, name):
        # Jinja resolves ``a.b`` via getattr first; only real dict keys reach here
        # (actual attributes like ``_path`` are found by normal lookup).
        return self._resolve(name)


def _wrap_passthrough(val: Any, path: str) -> Any:
    """Wrap dicts as :class:`_PassthroughBox` (recursively, lazily) so nested
    passthrough paths keep their prefix; leave other values untouched."""
    if isinstance(val, _PassthroughBox):
        return val
    if isinstance(val, dict):
        return _PassthroughBox(val, path)
    return val


def _passthrough_context(context: dict) -> dict:
    """Wrap every top-level dict in a Jinja context so missing nested keys render
    as full-path passthroughs (``{{ this.os.family }}``) instead of losing their
    prefix."""
    return {k: _wrap_passthrough(v, k) for k, v in context.items()}


class _ThisBox(_PassthroughBox):
    """A :class:`_PassthroughBox` for ``this`` that also exposes ``this.parent`` --
    the dict that *owns* this node.

    ``this`` binds to the nearest enclosing dict; ``this.parent`` walks up the
    ownership chain (``this.parent.parent`` and so on).  Present child dicts are
    themselves wrapped as ``_ThisBox`` with ``parent`` set to the current node, so
    ownership is consistent whether you arrive from above or reach in from a leaf.
    A literal config key named ``parent`` still wins over the synthetic accessor.
    """
    def __init__(self, data: dict, path: str, owner: "_ThisBox | None" = None):
        super().__init__(data, path)
        self._owner = owner

    def _resolve(self, key: str):
        if key == "parent" and not dict.__contains__(self, "parent"):
            if self._owner is not None:
                return self._owner
            return PassthroughUndefined(name=f"{self._path}.parent")
        if dict.__contains__(self, key):
            val = dict.__getitem__(self, key)
            if isinstance(val, dict):
                return _ThisBox(val, f"{self._path}.{key}", owner=self)
            return _wrap_passthrough(val, f"{self._path}.{key}")
        if key == "display_name" and dict.__contains__(self, "name"):
            # See _PassthroughBox._resolve: display_name is a synonym for the raw name.
            return _wrap_passthrough(dict.__getitem__(self, "name"), f"{self._path}.display_name")
        return PassthroughUndefined(name=f"{self._path}.{key}")


def _make_this(ancestors: list) -> Any:
    """Build the ``this`` box for a leaf, given its enclosing dicts (nearest last).

    The nearest dict becomes ``this``; each outer dict becomes ``this.parent``,
    ``this.parent.parent``, ... with matching passthrough paths so unresolved
    references keep their full dotted form.
    """
    if not ancestors:
        return PassthroughUndefined(name="this")
    box: "_ThisBox | None" = None
    n = len(ancestors)
    for i, anc in enumerate(ancestors):          # outermost -> nearest
        depth = n - 1 - i                        # nearest => 0 (".parent" count)
        path = "this" + ".parent" * depth
        box = _ThisBox(anc, path, owner=box)
    return box


def _render_scoped(node: Any, base_context: dict, jenv: Environment, ancestors: list) -> Any:
    """Render a parsed YAML tree, rebinding ``this`` to the nearest enclosing dict.

    Lists are transparent to ownership: a list item's ``this.parent`` is the dict
    that contains the list, not the list itself.
    """
    if isinstance(node, dict):
        new_ancestors = ancestors + [node]
        if ancestors and isinstance(node.get("config"), dict):
            # a nested item's own `config` shadows the enclosing one
            # for its subtree, the rule the top-level item already follows
            # (an OS builder runtime entry's `config` was reachable by nothing)
            base_context = {**base_context, "config": {**(base_context.get("config") or {}), **node["config"]}}
        return {k: _render_scoped(v, base_context, jenv, new_ancestors) for k, v in node.items()}
    if isinstance(node, list):
        return [_render_scoped(item, base_context, jenv, ancestors) for item in node]
    if _is_tagged(node):
        context = {**base_context, "this": _make_this(ancestors)}
        return _rendered_leaf(node, context, jenv)
    return node


class KeepUndefined(Undefined):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        # Returns the original placeholder format
        return f"{{{{ {self._undefined_name} }}}}"

    def __getattr__(self, name):
        # Handles nested attributes (e.g., {{ user.name }})
        return KeepUndefined(name=f"{self._undefined_name}.{name}")

    def __getitem__(self, key):
        # Handles dictionary-style access (e.g., {{ user['name'] }})
        return KeepUndefined(name=f"{self._undefined_name}[{key!r}]")


def os_envdata(include_ENV: bool = False) -> dict[str, Any]:
    """Get OS environment variables as a dictionary with 'ENV.' prefix."""
    return {"ENV": dict(os.environ)} if include_ENV else {"ENV": {}}


def extend_with_envdata(data: dict[str, Any], include_ENV: bool = False, addl: dict | None = None) -> dict[str, Any]:
    """Extend the given data dictionary with OS environment variables prefixed by 'ENV.'."""
    addl = addl or {}
    env_data = os_envdata(include_ENV)
    extended_data = data.copy()
    extended_data.update(env_data) # ENV overrides
    extended_data.update(addl) # addl overrides other local data
    return extended_data


def _is_tagged(leaf: Any) -> bool:
    """Whether a string leaf carries a Jinja tag the string stage must render."""
    return isinstance(leaf, str) and (("{{" in leaf and "}}" in leaf) or ("{%" in leaf))


def _tagged_leaves(node: Any) -> list[str]:
    """Every string leaf of a parsed tree that still carries a template tag."""
    if isinstance(node, dict):
        return [t for v in node.values() for t in _tagged_leaves(v)]
    if isinstance(node, list):
        return [t for item in node for t in _tagged_leaves(item)]
    return [node] if _is_tagged(node) else []


def _pass_interpolate(tree: dict, *, addl: dict, cycles: int) -> dict:
    """Built-in string-stage pass: resolve ENV/execution/config across the document.

    (config is used as addl data ONCE so config values can be used in the main yaml
    but not overridden by ENV or other data in it.)
    """
    return interpolate_tree(tree, cycles=cycles, include_ENV=True, addl=addl)


def _pass_scope_this(tree: dict, *, addl: dict, cycles: int) -> dict:
    """Built-in string-stage pass: nearest-``this`` / ``this.parent`` scoping per plugin key."""
    for _plugin_type, plugin_key in PLUGIN_TYPES:
        tree = scope_named_key(tree, plugin_key=plugin_key, cycles=cycles,
                               addl=addl, include_ENV=True)
    return tree


resolution_stages.register_resolution_pass("interpolate", _pass_interpolate, order=10)
resolution_stages.register_resolution_pass("scope-this", _pass_scope_this, order=20)


def string_stage(tree: dict, cycles: int = 10, addl: dict | None = None) -> dict:
    """Run the ordered string-stage pass registry over the parsed ``cfg/`` document.

    The document is the one tree the loader parsed from the files; every pass
    walks that tree and returns it (or a rendered copy of it) for the next.
    Nothing is dumped back to YAML text and nothing is parsed again. Built-in
    passes are ``interpolate`` then ``scope-this``; plugins may register
    additional passes via ``resolution_stages.register_resolution_pass``.
    """
    addl = addl or {}
    current = tree
    for _name, fn in resolution_stages.resolution_passes():
        current = fn(current, addl=addl, cycles=cycles)
    # a tag that remains after the string passes legitimately
    # resolves at the object stage (`{{ group.name }}`, `{{ identified_model.name }}`);
    # it is not a warning. (A comment in the files never reaches the tree.)
    remaining = _tagged_leaves(current)
    if remaining:
        log.debug(f"{len(remaining)} template tag(s) remain after the string passes and resolve at the "
                  f"object stage: {remaining[:5]}")
    return current


def _rendered_leaf(leaf: str, context: dict, jenv: Environment) -> str:
    """Render one tagged string leaf. The result is a STRING and stays one:
    ``port: "{{ config.port }}"`` with ``port: 22`` in ``config`` yields the
    text ``'22'``, not the integer (the structuring stage coerces a declared
    field; a free-form mapping keeps the text). That is what the former
    dump/parse round trip produced too, because the YAML dumper quotes a
    string that would read back as another scalar type."""
    return jenv.from_string(leaf).render(**context)


def interpolate_tree(tree: Any, cycles: int = 5, include_ENV: bool = False, addl: dict | None = None) -> Any:
    """Render every tagged string leaf of a parsed document against the
    document itself, ``ENV`` and ``addl``, repeatedly, until a cycle changes
    nothing.

    Templates are rendered against the *parsed* structure -- each string value
    is rendered individually -- never against YAML text. Rendering serialized
    text is unsafe: YAML's own escaping (doubled ``''`` inside single-quoted
    scalars, backslash escapes / line continuations inside double-quoted
    scalars) lands in the middle of ``{{ ... }}`` expressions and produces
    Jinja ``TemplateSyntaxError``s. The values are already-unescaped Python
    strings, so none of that exists here.

    Each cycle rebuilds its context from the previous cycle's tree, so values
    in the document can reference one another; a reference that resolves to
    nothing is kept as written (:class:`PassthroughUndefined`). A tree with no
    tagged leaf is returned as it is, untouched.

    Parameters
    ----------
    tree : dict or list
        The parsed document.

    Returns
    -------
    The rendered document (a new tree when anything rendered).
    """
    addl = addl or {}
    if not _tagged_leaves(tree):
        # No Jinja tags found: the tree is already final
        return tree
    if not isinstance(tree, (dict, list)):
        # Nothing structured to walk (e.g. a bare scalar); leave as-is
        return tree

    data = tree
    jenv = Environment(undefined=PassthroughUndefined)

    for _i in range(cycles):
        # Rebuild the context from the current (partially resolved) data each pass
        # so values in the document can reference one another; ENV and addl
        # (e.g. execution.*) are layered on top.
        base = data if isinstance(data, dict) else {}
        context = _passthrough_context(extend_with_envdata(base, include_ENV, addl))
        try:
            new_data = _render_node(data, context, jenv)
        except Exception as e:
            log.error(f"Error rendering YAML templates: {e}")
            raise
        if new_data == data:
            return new_data
        data = new_data

    log.warning(f"YAML cycling reached max cycles ({cycles}) without convergence.")
    return data


def scope_named_key(tree: Any, plugin_key: str, cycles: int = 10, addl: dict | None = None,
                    include_ENV: bool = False) -> Any:
    """Resolve the templates of the items under ``plugin_key`` with scope-aware
    ``this``, on the parsed document, in place.

    Within each item ``this`` binds to the *nearest enclosing dict* and
    ``this.parent`` is the dict that owns it (``this.parent.parent`` walks further
    up, stopping at the plugin item).  So a top-level ``{{ this.name }}`` is the
    item's name, while inside a nested ``runtimes`` entry ``{{ this.name }}`` is the
    runtime's name and ``{{ this.parent.name }}`` is the owning item's name.

    References that resolve to nothing (e.g. ``{{ this.os.family }}`` where no
    ``os`` exists) are left intact via :class:`PassthroughUndefined`, with their
    full dotted path preserved, for a later resolution stage.  An item's own
    ``config`` shadows the document-level ``config`` so bare ``{{ config.x }}``
    references resolve locally.

    The rest of the document is the context the items render against, as it
    stands when this key is reached: a key scoped earlier in the same pass
    is seen rendered. The list under ``plugin_key`` is replaced on the given
    tree; a document that is not a mapping, or carries no list under the
    key, is returned untouched.
    """
    addl = addl or {}
    if not isinstance(tree, dict):
        return tree
    items = tree.get(plugin_key)
    if not isinstance(items, list):
        # Nothing of this plugin type in the document
        return tree

    jenv = Environment(undefined=PassthroughUndefined)
    new_items: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            new_items.append(item)
            continue
        current = item
        for _i in range(cycles):
            # Base context (available at every scope): document keys, ENV,
            # addl/execution.  An item's own `config` shadows the document `config`.
            base_context = extend_with_envdata(tree, include_ENV, addl)
            if isinstance(current.get("config"), dict):
                base_context["config"] = {**base_context.get("config", {}), **current["config"]}
            base_context = _passthrough_context(base_context)
            # `this` is rebound per-node by the scoped walker; seed with no ancestors
            # so the item itself is the outermost `this`.
            rendered = _render_scoped(current, base_context, jenv, [])
            if rendered == current:
                break
            current = rendered
        new_items.append(current)

    tree[plugin_key] = new_items
    return tree

def _render_node(node: Any, context: dict, jenv: Environment) -> Any:
    """Recursively render Jinja tags in every string *value* of a parsed YAML node.

    Renders parsed values (already-unescaped Python strings), never the
    serialized YAML text, so YAML escaping never reaches Jinja.
    """
    if isinstance(node, dict):
        return {k: _render_node(v, context, jenv) for k, v in node.items()}
    if isinstance(node, list):
        return [_render_node(item, context, jenv) for item in node]
    if _is_tagged(node):
        return _rendered_leaf(node, context, jenv)
    return node


# def process_keys_and_defaults(
#     d: Any, depth_str: Optional[str] = None
# ) -> Any:
#     """Recursively process dictionary keys and apply defaults."""
#     if isinstance(d, dict):
#         new_dict = {}
#         for k, v in d.items():
#             new_k = utils.safe_name_dash(k)
#             cur_depth = new_k if depth_str is None else f"{depth_str}|{new_k}"
#             new_v = process_keys_and_defaults(v, depth_str=cur_depth)
#             new_dict[new_k] = new_v
#         return new_dict
#     elif isinstance(d, list):
#         return [process_keys_and_defaults(i, depth_str=depth_str) for i in d]
#     else:
#         return d
def safe_name_dash(name: str) -> str:
    if not name:
        raise ValueError("Name cannot be empty or None.")
    return name.strip().replace("-", "_")


def process_keys(d: Any) -> Any:
    # return d
    """Recursively process dictionary keys to be safe for use as Python identifiers."""
    if isinstance(d, dict):
        # return {utils.safe_name_nocase(k): process_keys(v) for k, v in d.items()}
        ret = {}
        for k, v in d.items():
            new_k = safe_name_dash(k)
            ret[new_k] = process_keys(v)
        return ret
    elif isinstance(d, list):
        return [process_keys(i) for i in d]
    else:
        return d


def read_and_preprocess_yaml_files(
    t: type,
    yaml_files: list[Path],
    cycles: int = 5,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:

    if hasattr(t, "klazz_yaml_key") and callable(t.klazz_yaml_key): # FIXME: This is crazy.  Don't do this
        sub_key = t.klazz_yaml_key()
    else:
        raise ValueError(f"Type {t} must have a callable klazz_yaml_key method to determine the sub-key to extract from YAML files.")

    original_read_dict: dict[str, dict[str, Any]] = {}
    dumped_yaml_strings: dict[str, Any] = {}
    original_read_processed_dicts: dict[str, dict[str, Any]] = {}
    for yaml_file in yaml_files:
        try:
            log.debug(f"Reading {sub_key} from file: {yaml_file}")
            with open(yaml_file) as file:
                ss = file.read()
                file_data = yaml.safe_load(ss)  #  process_keys( yaml.safe_load(ss) )
                # any value may be an ENC[age:...] marker. The
                # rosters' markers are opened here, before structuring, and
                # carry their ciphertext onward for the emission to write back.
                file_data = decrypt_tree(file_data, source=str(yaml_file),
                                         collect=decrypted_plaintexts())
                # after decryption, so an encrypted name is checked as
                # its plaintext; before structuring, so the message names the file
                refuse_reserved_names(file_data, str(yaml_file))
                if not (sub_key and isinstance(file_data, dict)):
                    raise ValueError(
                        f"YAML file {yaml_file} does not contain a top-level "
                        f"dictionary to extract '{sub_key}' from."
                    )
                items = file_data.get(sub_key, [])
                if not isinstance(items, list):
                    raise ValueError(
                        f"YAML file {yaml_file} sub-key '{sub_key}' is not a list."
                    )
                for i in items:
                    name = i.get(NAME, None)
                    if not name:
                        raise ValueError(
                            f"Item in {yaml_file} is missing 'name' field: {i}"
                        )
                    assert name not in original_read_processed_dicts, (
                        f"Duplicate key {name} found in image files."
                    )
                    original_read_processed_dicts[name] = copy.deepcopy(i)
                    if name not in dumped_yaml_strings:
                        clean_dict = i  # utils.recursive_capture_extras(i, t)
                        original_read_dict[name] = clean_dict
                        dumped_yaml_strings[name] = yaml.dump(i, sort_keys=False)
                    else:
                        raise ValueError(f"Duplicate key {name} found in image files.")
        except Exception as e:
            log.error(f"Error parsing {yaml_file}: {e}")
            raise

    return original_read_dict, dumped_yaml_strings, original_read_processed_dicts


