from typing import List, Optional, Tuple

from icontract import DBC


class Something(DBC):
    """
    Represent a class whose only refusable content is a floating-point number.

    JSON knows neither an infinity nor a not-a-number, so a float is one of
    the few values a serialization may have to refuse. An integer is another,
    and a target which decides what it has to guard by walking the type of
    a property can confuse the two -- so we give it a class which reaches
    a float and no integer at all, in each of the shapes a float can come in.
    """

    some_float: float

    #: Test a float which may not have been given
    some_optional_float: Optional[float]

    #: Test a float in a list
    some_floats: List[float]

    #: Test a float beside a value which can not be refused
    some_pair: Tuple[str, float]

    def __init__(
        self,
        some_float: float,
        some_floats: List[float],
        some_pair: Tuple[str, float],
        some_optional_float: Optional[float] = None,
    ) -> None:
        self.some_float = some_float
        self.some_optional_float = some_optional_float
        self.some_floats = some_floats
        self.some_pair = some_pair


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
