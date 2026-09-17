# NOTE (mristin):
# We originally wrote this test to check that the concrete class with descendants
# also implements the interface.


class Parent:
    pass


class Child(Parent):
    pass


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
