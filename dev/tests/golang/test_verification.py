# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Test generation of Go verification functions."""

import unittest

from aas_core_codegen.golang.lib import (
    _generate_verification as golang_generate_verification,
)
from aas_core_codegen.parse import retree as parse_retree


class TestRegexRenderer(unittest.TestCase):
    """Test literal characters and character-class boundaries."""

    def test_encoded_characters(self) -> None:
        """Preserve the literal meaning of encoded regex characters."""
        for pattern, expected in [
            (r"^a\x2eb$", r"^a\x{2e}b$"),
            (r"^a\u002Eb$", r"^a\x{2e}b$"),
            (r"^\x24aas$", r"^\x{24}aas$"),
            (r"^\x7c\x5e\x5c$", r"^\x{7c}\x{5e}\x{5c}$"),
            (r"^[\x20-\x5B\x5D-\x7E]+$", r"^[\x{20}-\x{5b}\x{5d}-\x{7e}]+$"),
            (r"^[\x5e\x2d\x5d\x5c]+$", r"^[\x{5e}\x{2d}\x{5d}\x{5c}]+$"),
            (r"^[\uE000-\U0010FFFF]+$", r"^[\x{e000}-\x{10ffff}]+$"),
        ]:
            with self.subTest(pattern=pattern):
                regex, error = parse_retree.parse([pattern])
                self.assertIsNone(error)
                if regex is None:
                    self.fail("Expected regex parsing to succeed")

                self.assertEqual(
                    [expected],
                    parse_retree.render(
                        regex=regex,
                        renderer=golang_generate_verification.RegexRenderer(),
                    ),
                )

    def test_unencoded_characters(self) -> None:
        """Keep escaping ordinary regex literals as before."""
        pattern = r"^\.\$\[\]\\$"
        regex, error = parse_retree.parse([pattern])
        self.assertIsNone(error)
        if regex is None:
            self.fail("Expected regex parsing to succeed")

        self.assertEqual(
            [pattern],
            parse_retree.render(
                regex=regex, renderer=golang_generate_verification.RegexRenderer()
            ),
        )


if __name__ == "__main__":
    unittest.main()
