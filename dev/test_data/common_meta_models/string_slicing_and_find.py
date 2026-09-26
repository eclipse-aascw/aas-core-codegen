from icontract import DBC, invariant


@invariant(lambda self: len(self) > 0, "At least one character")
class Non_empty_string(str, DBC):
    pass


@verification
def date_before_time_is_long_enough(text: str) -> bool:
    """Check the slice up to the position found with ``find``."""
    position = text.find("T")
    if position == -1:
        return True

    return len(text[:position]) == 10


@verification
def time_after_date_is_long_enough(text: str) -> bool:
    """Check the slice from the position after the one found with ``find``."""
    position = text.find("T")
    if position == -1:
        return True

    return len(text[position + 1 :]) == 8


@verification
def month_is_september(text: str) -> bool:
    """Check ``find`` with a start and the slice between the found positions."""
    first = text.find("-")
    if first == -1:
        return True

    second = text.find("-", first + 1)
    if second == -1:
        return False

    return text[first + 1 : second] == "09"


@verification
def seconds_follow_colon(text: str) -> bool:
    """Check the slices and ``find`` with negative literal positions."""
    position = text.find("T")
    if position == -1:
        return True

    return len(text) < 10 or (
        text[-3:-2] == ":" and text.find(":", -3) != -1 and len(text[:-9]) > 0
    )


@verification
def last_character_is_not_z(text: str) -> bool:
    """
    Check the positions computed at run time which are negative or out of range.

    The transpiled code needs to follow the Python semantics: a negative position
    counts from the end, and the positions out of range are clamped.
    """
    # The position is -1 unless the text contains a hash.
    position = text.find("#")

    return (
        text[position:] != "Z"
        and text[-100:100] == text
        and text[3:1] == ""
        and text.find("", 100) == -1
        and text.find(text[position:], position) >= 0
    )


@verification
def name_starts_with_prefix(name: Non_empty_string) -> bool:
    """Check the slice of a constrained primitive with literal bounds."""
    return len(name) < 4 or name[0:4] == "name"


@verification
def name_has_no_space_after_prefix(name: Non_empty_string) -> bool:
    """Check ``find`` on a constrained primitive and a slice with a literal start."""
    return len(name) < 4 or name[4:].find(" ") == -1


@invariant(
    lambda self: date_before_time_is_long_enough(self.text),
    "Date before the time must have 10 characters",
)
@invariant(
    lambda self: time_after_date_is_long_enough(self.text),
    "Time after the date must have 8 characters",
)
@invariant(
    lambda self: month_is_september(self.text),
    "Month must be September",
)
@invariant(
    lambda self: seconds_follow_colon(self.text),
    "Seconds must follow a colon",
)
@invariant(
    lambda self: last_character_is_not_z(self.text),
    "Last character must not be Z",
)
@invariant(
    lambda self: name_starts_with_prefix(self.name),
    "Name must start with the prefix",
)
@invariant(
    lambda self: name_has_no_space_after_prefix(self.name),
    "Name must contain no space after the prefix",
)
@invariant(
    lambda self: not (len(self.text) >= 1) or self.text[:1] != "X",
    "Text must not start with X",
)
class Something(DBC):
    text: str
    name: Non_empty_string

    def __init__(self, text: str, name: Non_empty_string) -> None:
        self.text = text
        self.name = name


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
