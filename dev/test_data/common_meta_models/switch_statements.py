from enum import Enum

from icontract import DBC, invariant


class Kind(Enum):
    Alpha = "alpha"
    Beta = "beta"
    Gamma = "gamma"
    Delta = "delta"


@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str, DBC):
    pass


@verification
def switch_on_enum_with_a_single_case(kind: Kind) -> bool:
    """Check the switch with a single case and no default."""
    if kind == Kind.Delta:
        return False

    return True


@verification
def switch_on_enum_with_default(kind: Kind) -> bool:
    """Check the switch with a case per form of labels and a default."""
    if kind == Kind.Alpha:
        return True
    elif kind == Kind.Beta or kind == Kind.Gamma:
        return False
    else:
        return True


@verification
def switch_on_enum_with_labels_in_tuple(kind: Kind) -> bool:
    """Check the switch with the labels given as a tuple."""
    if kind in (Kind.Alpha, Kind.Beta, Kind.Gamma):
        return True
    else:
        return False


@verification
def switch_on_enum_with_pass(kind: Kind) -> bool:
    """Check the switch with the branches which pass and complete normally."""
    result = True

    if kind in (Kind.Alpha, Kind.Beta):
        pass
    elif kind == Kind.Gamma:
        result = False
    else:
        pass

    return result


@verification
def switch_on_enum_with_variables_in_cases(kind: Kind, text: str) -> bool:
    """Check the variables defined in the cases of the switch."""
    if kind == Kind.Alpha:
        length = len(text)
        return length > 1
    elif kind == Kind.Beta:
        length = len(text)
        return length > 2
    else:
        return True


@verification
def switch_on_str(text: str) -> bool:
    """Check the switch on a string."""
    if text == "alpha":
        return True
    elif text == "beta" or text == "gamma":
        return False
    elif text in ("delta", "epsilon"):
        return False
    else:
        return len(text) > 0


@verification
def switch_on_constrained_str(text: Non_empty_string) -> bool:
    """Check the switch on a constrained primitive."""
    if text in ("forbidden", "banned"):
        return False
    else:
        return True


@verification
def switch_on_int(number: int) -> bool:
    """Check the switch on an integer."""
    if number == -1:
        return False
    elif number == 0 or number == 1:
        return True
    elif number in (2, 3):
        return False
    else:
        return number > 3


@verification
def nested_switches(kind: Kind, number: int) -> bool:
    """Check the nested switches, including an ``elif`` on another subject."""
    if kind == Kind.Alpha:
        if number == 0:
            return True
        else:
            return number > 10
    elif kind == Kind.Beta:
        if number == 1:
            return False
    elif number == 2:
        return False

    return True


@verification
def switch_with_reassigned_int(kind: Kind, number: int) -> bool:
    """
    Check the integer variable defined with a literal, and re-assigned
    an integer argument in a branch of the switch.
    """
    result = 0
    if kind == Kind.Beta:
        result = number

    return result < 1000


@invariant(
    lambda self: switch_on_enum_with_a_single_case(self.kind),
    "Kind must not be delta",
)
@invariant(
    lambda self: switch_on_enum_with_default(self.kind),
    "Kind must be neither beta nor gamma",
)
@invariant(
    lambda self: switch_on_enum_with_labels_in_tuple(self.kind),
    "Kind must be alpha, beta or gamma",
)
@invariant(
    lambda self: switch_on_enum_with_pass(self.kind),
    "Kind must not be gamma",
)
@invariant(
    lambda self: switch_on_enum_with_variables_in_cases(self.kind, self.text),
    "Text must be long enough for the kind",
)
@invariant(lambda self: switch_on_str(self.text), "Text must be acceptable")
@invariant(
    lambda self: switch_on_constrained_str(self.name),
    "Name must not be forbidden",
)
@invariant(lambda self: switch_on_int(self.number), "Number must be acceptable")
@invariant(
    lambda self: nested_switches(self.kind, self.number),
    "Kind and number must be consistent",
)
@invariant(
    lambda self: switch_with_reassigned_int(self.kind, self.number),
    "Number must be small for beta",
)
class Something(DBC):
    kind: Kind
    text: str
    name: Non_empty_string
    number: int

    def __init__(
        self, kind: Kind, text: str, name: Non_empty_string, number: int
    ) -> None:
        self.kind = kind
        self.text = text
        self.name = name
        self.number = number


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
