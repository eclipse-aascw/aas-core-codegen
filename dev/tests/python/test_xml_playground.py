# pylint: disable=missing-docstring

# NOTE (mristin):
# This is not really test suite, but a playground to document how streaming XML
# working in Python.
import io
import unittest
import xml.etree.ElementTree as ET


class Test_XML_stream(unittest.TestCase):
    def test_self_closing_element_without_namespace(self) -> None:
        text = """\
<environment/>
"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            prefix, has_prefix, postfix = element.tag.rpartition("}")

            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(
                f"prefix, has_prefix, postfix is {prefix, has_prefix, postfix!r}\n"
            )
            writer.write(f"element.text is {element.text!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'environment'
prefix, has_prefix, postfix is ('', '', 'environment')
element.text is None
event is 'end'
element.tag is 'environment'
prefix, has_prefix, postfix is ('', '', 'environment')
element.text is None
""",
            writer.getvalue(),
        )

    def test_cdata_single(self) -> None:
        text = """\
<something>
<![CDATA[crazy < > content]]>
</something>
"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(f"element.text is {element.text!r}\n")
            writer.write(f"element.tail is {element.tail!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'something'
element.text is '\\ncrazy < > content\\n'
element.tail is None
event is 'end'
element.tag is 'something'
element.text is '\\ncrazy < > content\\n'
element.tail is None
""",
            writer.getvalue(),
        )

    def test_cdata_enclosed(self) -> None:
        text = """\
<something>
<![CDATA[
crazy < > content
]]>
</something>
"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(f"element.text is {element.text!r}\n")
            writer.write(f"element.tail is {element.tail!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'something'
element.text is '\\n\\ncrazy < > content\\n\\n'
element.tail is None
event is 'end'
element.tag is 'something'
element.text is '\\n\\ncrazy < > content\\n\\n'
element.tail is None
""",
            writer.getvalue(),
        )

    def test_self_closing_element_with_namespace(self) -> None:
        text = """\
<environment xmlns="https://admin-shell.io/aas/3/0/RC02"/>
"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            prefix, has_prefix, postfix = element.tag.rpartition("}")

            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(
                f"prefix, has_prefix, postfix is {prefix, has_prefix, postfix!r}\n"
            )

        self.assertEqual(
            """\
event is 'start'
element.tag is '{https://admin-shell.io/aas/3/0/RC02}environment'
prefix, has_prefix, postfix is ('{https://admin-shell.io/aas/3/0/RC02', '}', 'environment')
event is 'end'
element.tag is '{https://admin-shell.io/aas/3/0/RC02}environment'
prefix, has_prefix, postfix is ('{https://admin-shell.io/aas/3/0/RC02', '}', 'environment')
""",
            writer.getvalue(),
        )

    def test_nested_elements_with_text_and_tail(self) -> None:
        text = """\
<something>some prefix<another>another text</another>some suffix</something>"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(f"element.text is {element.text!r}\n")
            writer.write(f"element.tail is {element.tail!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'something'
element.text is 'some prefix'
element.tail is None
event is 'start'
element.tag is 'another'
element.text is 'another text'
element.tail is 'some suffix'
event is 'end'
element.tag is 'another'
element.text is 'another text'
element.tail is 'some suffix'
event is 'end'
element.tag is 'something'
element.text is 'some prefix'
element.tail is None
""",
            writer.getvalue(),
        )

    def test_escapes_in_text(self) -> None:
        text = """\
<something>&#x4D;</something>"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(f"element.text is {element.text!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'something'
element.text is 'M'
event is 'end'
element.tag is 'something'
element.text is 'M'
""",
            writer.getvalue(),
        )

    def test_attrib(self) -> None:
        text = """\
<something that="ok"></something>"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(f"element.attrib is {element.attrib!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'something'
element.attrib is {'that': 'ok'}
event is 'end'
element.tag is 'something'
element.attrib is {'that': 'ok'}
""",
            writer.getvalue(),
        )

    def test_comment(self) -> None:
        text = """\
<something>
<!-- some comment -->
</something>"""

        reader = io.StringIO(text)

        writer = io.StringIO()

        for event, element in ET.iterparse(reader, events=["start", "end"]):
            writer.write(f"event is {event!r}\n")
            writer.write(f"element.tag is {element.tag!r}\n")
            writer.write(f"element.text is {element.text!r}\n")

        self.assertEqual(
            """\
event is 'start'
element.tag is 'something'
element.text is '\\n\\n'
event is 'end'
element.tag is 'something'
element.text is '\\n\\n'
""",
            writer.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
