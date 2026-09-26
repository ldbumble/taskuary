"""Regression test to ensure taskuary.server does not use deprecated Pydantic v1 .dict() calls."""
from pathlib import Path
import re
import unittest


class NoPydanticV1Tests(unittest.TestCase):
    def test_no_pydantic_v1_dict_in_server(self):
        server_path = Path(__file__).parent.parent / "taskuary" / "server.py"
        content = server_path.read_text(encoding="utf-8")

        # Check for any patterns invoking .dict() on request bodies or nested fields
        v1_dict_pattern = re.compile(r"\b(?:body|\.second|\.first)\.dict\s*\(")
        matches = [
            (i + 1, line)
            for i, line in enumerate(content.splitlines())
            if v1_dict_pattern.search(line)
        ]

        self.assertEqual(
            matches,
            [],
            f"Found deprecated Pydantic v1 .dict() calls in {server_path}:\n"
            + "\n".join(f"  Line {lineno}: {line}" for lineno, line in matches),
        )
