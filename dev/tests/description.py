"""Provide parsing functions to get started with testing some of the ReST rendering."""
import io
from typing import Optional

import docutils.nodes
import docutils.core


def parse_restructured_text(text: str) -> docutils.nodes.document:
    """Parse the given ReST ``text``."""
    warnings = io.StringIO()
    # noinspection PyUnusedLocal
    document: Optional[docutils.nodes.document] = None

    document = docutils.core.publish_doctree(
        text, settings_overrides={"warning_stream": warnings}
    )

    warnings_text = warnings.getvalue()
    if warnings_text:
        raise RuntimeError(
            f"Failed to parse the description with docutils:\n"
            f"{warnings_text.strip()}\n\n"
            f"The original text was: {text!r}"
        )

    assert document is not None

    return document
