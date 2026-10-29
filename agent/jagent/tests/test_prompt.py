import unittest

from tui.widgets.prompt import normalize_paste


class PromptInputTests(unittest.TestCase):
    def test_multiline_paste_is_flattened(self) -> None:
        self.assertEqual(
            normalize_paste("第一行\n\n  第二行  \r\n第三行"),
            "第一行 第二行 第三行",
        )

    def test_empty_paste(self) -> None:
        self.assertEqual(normalize_paste("\n\n  \r\n"), "")


if __name__ == "__main__":
    unittest.main()
