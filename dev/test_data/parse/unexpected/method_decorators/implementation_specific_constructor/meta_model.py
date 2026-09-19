# A constructor can not be implementation-specific. Its body is not only
# transpiled into the constructor of the target language, but also in-lined into
# the constructors of all the descendants, which a snippet can not provide.


class Something:
    x: int

    @implementation_specific
    def __init__(self, x: int) -> None:
        self.x = x


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
