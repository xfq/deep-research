import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_research_agent.localization import should_use_simplified_chinese


class LocalizationTests(unittest.TestCase):
    def test_identifies_simplified_chinese_without_matching_other_languages(
        self,
    ) -> None:
        """Only Simplified Chinese questions opt into Simplified Chinese output."""
        self.assertTrue(should_use_simplified_chinese("什么是网页标准？"))
        self.assertTrue(should_use_simplified_chinese("请介绍《網頁標準》"))
        self.assertTrue(should_use_simplified_chinese("HTML 如何工作？"))
        self.assertTrue(should_use_simplified_chinese("北京天气"))
        self.assertTrue(should_use_simplified_chinese("浏览器兼容性"))
        self.assertTrue(should_use_simplified_chinese("W3C 的历史"))
        self.assertTrue(should_use_simplified_chinese("CSS 布局"))
        self.assertFalse(should_use_simplified_chinese("什麼是網頁標準？"))
        self.assertFalse(should_use_simplified_chinese("ウェブ標準とは何ですか？"))
        self.assertFalse(should_use_simplified_chinese("人工知能"))
        self.assertFalse(should_use_simplified_chinese("AI市場規模"))
        self.assertFalse(should_use_simplified_chinese("What are web standards?"))


if __name__ == "__main__":
    unittest.main()
