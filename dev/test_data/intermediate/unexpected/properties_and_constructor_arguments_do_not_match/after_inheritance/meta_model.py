class SomethingAbstract:
    property_a: str
    property_b: str

    property_c: Optional[str]
    property_d: Optional[str]

    def __init__(
        self,
        property_a: str,
        property_b: str,
        property_c: Optional[str] = None,
        property_d: Optional[str] = None,
    ) -> None:
        self.property_a = property_a
        self.property_b = property_b
        self.property_c = property_c
        self.property_d = property_d


class Something(SomethingAbstract):
    property_e: str
    property_f: str

    property_g: Optional[str]
    property_h: Optional[str]

    # NOTE (mristin):
    # The order of the inherited and defined properties do not match the order of
    # the constructor arguments.

    def __init__(
        self,
        property_e: str,
        property_f: str,
        property_a: str,
        property_b: str,
        property_g: Optional[str] = None,
        property_h: Optional[str] = None,
        property_c: Optional[str] = None,
        property_d: Optional[str] = None,
    ) -> None:
        SomethingAbstract.__init__(
            self,
            property_a=property_a,
            property_b=property_b,
            property_c=property_c,
            property_d=property_d,
        )

        self.property_e = property_e
        self.property_f = property_f
        self.property_g = property_g
        self.property_h = property_h


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
