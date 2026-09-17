"""Represent general entities as strings for testing or debugging."""

import collections.abc
import enum
import inspect
import io
import re
import textwrap
from typing import Sequence, Union, Any, Mapping, List, Tuple, Set

from icontract import require

from aas_core_codegen.common import assert_never, indent_but_first_line

# We have to separate Stringifiable and Sequence[Stringifiable] since recursive types
# are not supported in mypy, see https://github.com/python/mypy/issues/731.
PrimitiveStringifiable = Union[
    bool, int, float, str, "Entity", "Property", "PropertyEllipsis", None
]

Stringifiable = Union[
    PrimitiveStringifiable,
    Sequence[PrimitiveStringifiable],
    Sequence[Sequence[PrimitiveStringifiable]],
    Mapping[str, PrimitiveStringifiable],
    Mapping[str, Sequence[PrimitiveStringifiable]],
]


class Property:
    """Represent a property of an entity to be stringified."""

    def __init__(self, name: str, value: Stringifiable) -> None:
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return dump(self)


class PropertyEllipsis:
    """Represent a property whose value is not displayed."""

    def __init__(self, name: str, ignored_value: Any) -> None:
        """Initialize with the given values."""
        self.name = name

        # The ignored value is usually not used. However, it instructs mypy and
        # other static checkers to raise a warning if its value can not be accessed
        # (*e.g.*, as can happen in a refactoring).
        self.ignored_value = ignored_value

    def __repr__(self) -> str:
        return dump(self)


class Entity:
    """Represent a stringifiable entity which is defined by its properties.

    Think of a dictionary with assigned type identifier.
    """

    def __init__(
        self, name: str, properties: Sequence[Union[Property, PropertyEllipsis]]
    ) -> None:
        """Initialize with the given values."""
        self.name = name
        self.properties = properties

    def __repr__(self) -> str:
        return dump(self)


def dump(stringifiable: Stringifiable) -> str:
    """Produce a string representation of ``stringifiable`` for debugging or testing."""
    if isinstance(stringifiable, (bool, int, float)):
        return repr(stringifiable)

    elif isinstance(stringifiable, str):
        if "\n" not in stringifiable or "\r" in stringifiable or '"""' in stringifiable:
            return repr(stringifiable)

        # NOTE (mristin):
        # A multi-line string literal is much more readable when it comes to diffing.

        escaped = stringifiable.replace("\\", "\\\\")

        indented = "\n".join(f"  {line}" for line in escaped.splitlines())

        return f'textwrap.dedent("""\\\n{indented}""")'

    elif isinstance(stringifiable, Entity):
        if len(stringifiable.properties) == 0:
            return f"{stringifiable.name}()"

        writer = io.StringIO()
        writer.write(f"{stringifiable.name}(\n")

        for i, prop in enumerate(stringifiable.properties):
            if isinstance(prop, Property):
                value_str = dump(prop.value)
                indention = "  "
                writer.write(
                    f"  {prop.name}={indent_but_first_line(value_str, indention)}"
                )
            elif isinstance(prop, PropertyEllipsis):
                value_str = "None" if prop.ignored_value is None else "..."
                writer.write(f"  {prop.name}={value_str}")
            else:
                assert_never(prop)

            if i == len(stringifiable.properties) - 1:
                writer.write(")")
            else:
                writer.write(",\n")

        return writer.getvalue()

    elif isinstance(stringifiable, collections.abc.Sequence):
        if len(stringifiable) == 0:
            return "[]"
        else:
            writer = io.StringIO()
            writer.write("[\n")
            for i, value in enumerate(stringifiable):
                value_str = dump(value)
                writer.write(textwrap.indent(value_str, "  "))

                if i == len(stringifiable) - 1:
                    writer.write("]")
                else:
                    writer.write(",\n")

            return writer.getvalue()

    elif isinstance(stringifiable, collections.abc.Mapping):
        if len(stringifiable) == 0:
            return "{}"
        else:
            writer = io.StringIO()
            writer.write("{\n")
            for i, (key, value) in enumerate(stringifiable.items()):
                key_str = dump(key)

                value_str = dump(value)
                writer.write(textwrap.indent(f"{key_str}: {value_str}", "  "))

                if i == len(stringifiable) - 1:
                    writer.write("}")
                else:
                    writer.write(",\n")

            return writer.getvalue()

    elif stringifiable is None:
        return repr(None)

    elif isinstance(stringifiable, Property):
        value_str = dump(stringifiable.value)
        indention = ""
        return (
            f"Property("
            f"{stringifiable.name}={indent_but_first_line(value_str, indention)}"
            f")"
        )

    elif isinstance(stringifiable, PropertyEllipsis):
        value_str = "None" if stringifiable.ignored_value is None else "..."
        return f"PropertyEllipsis({stringifiable.name}={value_str})"

    else:
        assert_never(stringifiable)

    raise AssertionError("Should not have gotten here")


def compares_against_dict(entity: Entity, obj: object) -> bool:
    """
    Compare that the properties in the ``entity`` and ``obj.__dict__`` match.

    Mind that the dunders and "protected" properties are excluded.
    """
    entity_property_set = {prop.name for prop in entity.properties}

    obj_property_set = {key for key in obj.__dict__.keys() if not key.startswith("_")}

    return entity_property_set == obj_property_set


@require(lambda obj: hasattr(obj, "__dict__"), error=ValueError)
def assert_compares_against_dict(entity: Entity, obj: object) -> None:
    """
    Compare that the properties in the ``entity`` and ``obj.__dict__`` match.

    Mind that the dunders and "protected" properties are excluded.
    """
    entity_property_set = {prop.name for prop in entity.properties}

    obj_property_set = {
        attr
        for attr in dir(obj)
        if not attr.startswith("_") and not inspect.ismethod(getattr(obj, attr))
    }

    if entity_property_set != obj_property_set:
        diff_in_entity = sorted(entity_property_set.difference(obj_property_set))

        diff_in_obj = sorted(obj_property_set.difference(entity_property_set))

        prefix = (
            f"Expected the stringified properties "
            f"of {obj.__class__.__name__!r} to match the object properties, "
            f"but they do not.\n\n"
        )

        if len(diff_in_entity) > 0 and len(diff_in_obj) == 0:
            raise AssertionError(
                f"{prefix}"
                f"The following properties were found in the stringified entity, "
                f"but not in the object: {diff_in_entity}"
            )

        elif len(diff_in_obj) > 0 and len(diff_in_entity) == 0:
            raise AssertionError(
                f"{prefix}"
                f"The following properties were found in the object, "
                f"but not in the stringified entity: {diff_in_obj}"
            )

        else:
            raise AssertionError(
                f"{prefix}"
                f"The following properties were found in the stringified entity, "
                f"but not in the object: {diff_in_entity}\n\n"
                f"The following properties were found in the object, "
                f"but not in the stringified entity: {diff_in_obj}"
            )


def assert_all_public_types_listed_as_dumpables(
    dumpable: Any, types_module: Any
) -> None:
    """Make sure that all classes in ``types_modules`` are listed as dumpables."""

    dumpable_set = set()  # type: Set[str]

    for dumpable_cls in dumpable.__args__:
        dumpable_set.add(dumpable_cls.__name__)

    module_set = set()  # type: Set[str]

    for identifier, cls in inspect.getmembers(types_module, inspect.isclass):
        module_name = getattr(cls, "__module__", None)
        if module_name is None:
            continue

        if module_name != types_module.__name__:
            continue

        if identifier.startswith("_"):
            continue

        if issubclass(cls, enum.Enum):
            continue

        if inspect.isabstract(cls):
            continue

        if cls.__module__ == types_module.__name__:
            module_set.add(identifier)

    if dumpable_set != module_set:
        dumpable_diff = dumpable_set.difference(module_set)
        module_diff = module_set.difference(dumpable_set)

        raise AssertionError(
            f"The following classes were defined as dumpable, "
            f"but not found as concrete classes "
            f"in the module ``_types``: {sorted(dumpable_diff)}\n\n"
            f"The following classes were defined in the module ``_types``, "
            f"but not found in dumpables: {sorted(module_diff)}"
        )


def assert_dispatch_exhaustive(dispatch: Mapping[Any, Any], dumpable: Any) -> None:
    """
    Make sure that ``dispatch_map`` is exhaustive over all the concrete dumpables.

    We need to dispatch a class to its corresponding ``_stringify_*`` function. This is
    mapped in ``dispatch_map``. At the same time, we have to make a union type over all
    the types that can be converted to a stringified entity.
    """
    dumpable_map = {
        id(cls): cls for cls in dumpable.__args__ if not inspect.isabstract(cls)
    }

    dispatch_map = {id(cls): cls for cls in dispatch}

    dumpable_set = set(dumpable_map.keys())
    dispatch_set = set(dispatch_map.keys())

    if dumpable_set != dispatch_set:
        dumpable_diff = dumpable_set.difference(dispatch_set)
        dispatch_diff = dispatch_set.difference(dumpable_set)

        dumpable_diff_names = [
            dumpable_map[cls_id].__name__ for cls_id in dumpable_diff
        ]

        dispatch_diff_names = [
            dispatch_map[cls_id].__name__ for cls_id in dispatch_diff
        ]

        raise AssertionError(
            f"The following concrete classes are found in Dumpable, "
            f"but not in _DISPATCH: {dumpable_diff_names}.\n\n"
            f"The following concrete classes are found in _DISPATCH, "
            f"but not in Dumpable: {dispatch_diff_names}"
        )

    unexpected_function_names = []  # type: List[Tuple[str, str]]
    for cls, func in dispatch.items():
        cls_snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        expected_func_name = f"_stringify_{cls_snake_case}"

        if func.__name__ != expected_func_name:
            unexpected_function_names.append((cls.__name__, func.__name__))

    if len(unexpected_function_names):
        raise AssertionError(
            f"The following dispatch functions had unexpected names "
            f"(as a list of (class, function name)): {unexpected_function_names}"
        )
