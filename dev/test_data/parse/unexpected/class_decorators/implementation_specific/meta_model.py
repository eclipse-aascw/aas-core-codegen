# Only the verification functions and the methods can be implementation-specific.
# A class can not: we would have to provide a snippet not only for the class
# itself, but also for its de/serialization, its verification, its iteration and
# so on, in every single target.


@implementation_specific
class Something:
    x: int

    def __init__(self, x: int) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
