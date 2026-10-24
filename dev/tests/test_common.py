import unittest

import aas_core_codegen.common


class Test_wrap_text_into_lines(unittest.TestCase):
    def test_empty(self) -> None:
        got = aas_core_codegen.common.wrap_text_into_lines(text="")

        self.assertListEqual([""], got)

    def test_short_word(self) -> None:
        got = aas_core_codegen.common.wrap_text_into_lines(text="something short")

        self.assertListEqual(["something short"], got)

    # noinspection SpellCheckingInspection
    def test_normal_text(self) -> None:
        text = (
            "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, "
            "sed diam nonumy eirmod tempor invidunt ut labore et dolore magna "
            "aliquyam erat, sed diam voluptua. At vero eos et accusam et "
            "justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea "
            "takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit "
            "amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt "
            "ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos "
            "et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, "
            "no sea takimata sanctus est Lorem ipsum dolor sit amet."
        )

        expected = [
            "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, ",
            "sed diam nonumy eirmod tempor invidunt ut labore et dolore ",
            "magna aliquyam erat, sed diam voluptua. At vero eos et ",
            "accusam et justo duo dolores et ea rebum. Stet clita kasd ",
            "gubergren, no sea takimata sanctus est Lorem ipsum dolor ",
            "sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing ",
            "elitr, sed diam nonumy eirmod tempor invidunt ut labore et ",
            "dolore magna aliquyam erat, sed diam voluptua. At vero eos ",
            "et accusam et justo duo dolores et ea rebum. Stet clita ",
            "kasd gubergren, no sea takimata sanctus est Lorem ipsum ",
            "dolor sit amet.",
        ]

        got = aas_core_codegen.common.wrap_text_into_lines(text=text)
        self.assertListEqual(expected, got)

    def test_very_long_word(self) -> None:
        word = "1234567890" * 90

        text = f"prefix {word} suffix"

        expected = ["prefix ", f"{word} ", "suffix"]

        got = aas_core_codegen.common.wrap_text_into_lines(text=text)
        self.assertListEqual(expected, got)

    def test_article_kept_on_the_same_line(self) -> None:
        somethings = " ".join(["a something"] * 10)

        text = f"prefix {somethings} suffix"

        expected = [
            "prefix a something a something a something a something ",
            "a something a something a something a something a something ",
            "a something suffix",
        ]

        got = aas_core_codegen.common.wrap_text_into_lines(text=text)
        self.assertListEqual(expected, got)

    def test_only_articles(self) -> None:
        text = " ".join(["a an the"] * 60)
        expected = [
            "a an the a an the a an the a an the a an the a an the a an ",
            "the a an the a an the a an the a an the a an the a an the a ",
            "an the a an the a an the a an the a an the a an the a an ",
            "the a an the a an the a an the a an the a an the a an the a ",
            "an the a an the a an the a an the a an the a an the a an ",
            "the a an the a an the a an the a an the a an the a an the a ",
            "an the a an the a an the a an the a an the a an the a an ",
            "the a an the a an the a an the a an the a an the a an the a ",
            "an the a an the a an the a an the a an the a an the a an ",
            "the a an the",
        ]

        got = aas_core_codegen.common.wrap_text_into_lines(text=text)
        self.assertListEqual(expected, got)


if __name__ == "__main__":
    unittest.main()
