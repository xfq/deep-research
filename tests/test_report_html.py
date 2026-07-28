import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_research_agent.report_html import render_report_html
from deep_research_agent.research import (
    ResearchOutcome,
    Source,
    TerminationReason,
)


class ReportHtmlTests(unittest.TestCase):
    def test_renders_readable_semantic_report_with_navigation_and_sources(self) -> None:
        html = render_report_html(
            "# Research Report\n\n"
            "## Research Question\n\nWhat is W3C?\n\n"
            "## Answer\n\nW3C develops web standards [1].\n\n"
            "## Evidence\n\n1. Standards are published as Recommendations [1].\n\n"
            "## Outcome\n\ncomplete\n\n"
            "## Termination Reason\n\nResearch Question sufficiently answered\n\n"
            "## Sources\n\n[1] https://www.w3.org/\n",
            question="What is W3C?",
            sources=(Source(title="World Wide Web Consortium", url="https://www.w3.org/"),),
            outcome=ResearchOutcome.COMPLETE,
            termination_reason=TerminationReason.ANSWERED,
        )

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn('<html lang="en">', html)
        self.assertIn('<main id="main-content" tabindex="-1">', html)
        self.assertIn('<nav class="report-nav" aria-label="Report sections">', html)
        self.assertIn('<ul role="list">', html)
        self.assertIn('<ol class="source-list" role="list">', html)
        self.assertIn('href="#answer"', html)
        self.assertIn('id="answer"', html)
        self.assertIn('href="#source-1"', html)
        self.assertIn('id="source-1"', html)
        self.assertIn("World Wide Web Consortium", html)
        self.assertIn('target="_blank" rel="noreferrer"', html)
        self.assertLess(html.index('id="answer"'), html.index('id="sources"'))
        self.assertLess(html.index('id="sources"'), html.index('id="evidence"'))
        self.assertIn('<div class="report-secondary">', html)
        self.assertEqual(html.count('id="sources"'), 1)
        self.assertEqual(html.count("World Wide Web Consortium"), 1)
        self.assertNotIn("<h2>Research Question</h2>", html)
        self.assertNotIn("<h2>Outcome</h2>", html)

    def test_treats_findings_as_the_primary_answer(self) -> None:
        """Single-source findings receive the same emphasis as an answer."""
        html = render_report_html(
            "# Research Report\n\n"
            "## Findings\n\nA concise supported finding [1].\n\n"
            "## Research Plan\n\n- Verify the primary source.\n",
            question="What did the source establish?",
            sources=(Source(title="Primary Source", url="https://example.com/"),),
            outcome=ResearchOutcome.COMPLETE,
            termination_reason=TerminationReason.ANSWERED,
        )

        self.assertIn(
            '<li class="report-nav__item--primary"><a href="#findings">Findings</a>',
            html,
        )
        self.assertLess(html.index('id="findings"'), html.index('id="sources"'))
        self.assertLess(html.index('id="sources"'), html.index('id="research-plan"'))
        self.assertIn('<div class="report-secondary">', html)

    def test_escapes_untrusted_report_content_and_detects_chinese_language(self) -> None:
        html = render_report_html(
            "# Research Report\n\n"
            "## Answer\n\n<script>alert('x')</script> [1]\n",
            question="什么是网页标准？",
            sources=(Source(title="Unsafe <title>", url="javascript:alert(1)"),),
            outcome=ResearchOutcome.PARTIAL,
            termination_reason=TerminationReason.SEARCH_LIMIT,
        )

        self.assertIn('<html lang="zh-Hans">', html)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("Unsafe &lt;title&gt;", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("部分完成", html)
        self.assertIn("1 个来源", html)
        self.assertIn("搜索次数已用尽", html)
        self.assertIn('aria-label="报告章节"', html)
        self.assertIn("<h2>回答</h2>", html)
        self.assertIn("<h2>来源</h2>", html)
        self.assertNotIn("Deep Research Report", html)
        self.assertNotIn(">Contents<", html)

    def test_keeps_failure_details_visible_when_no_report_body_exists(self) -> None:
        html = render_report_html(
            "# Research Report\n\n"
            "## Research Question\n\nQuestion\n\n"
            "## Outcome\n\nfailed\n\n"
            "## Termination Reason\n\nUnexpected research execution failure.\n",
            question="Question",
            sources=(),
            outcome=ResearchOutcome.FAILED,
            termination_reason="Unexpected research execution failure.",
        )

        self.assertIn("<h2>Report details</h2>", html)
        self.assertIn("Unexpected research execution failure.", html)
        self.assertIn("No usable sources were collected.", html)

    def test_localizes_failure_details_for_simplified_chinese_question(self) -> None:
        """Failure-page boilerplate follows a Simplified Chinese question."""
        html = render_report_html(
            "# Research Report\n\n"
            "## Research Question\n\n研究为什么失败？\n\n"
            "## Outcome\n\nfailed\n\n"
            "## Termination Reason\n\nUnexpected research execution failure.\n",
            question="研究为什么失败？",
            sources=(),
            outcome=ResearchOutcome.FAILED,
            termination_reason="Unexpected research execution failure.",
        )

        self.assertIn("<h2>报告详情</h2>", html)
        self.assertIn("研究执行过程中发生意外错误。", html)
        self.assertIn("未收集到可用来源。", html)
        self.assertNotIn("Unexpected research execution failure.", html)
        self.assertNotIn("No usable sources were collected.", html)


if __name__ == "__main__":
    unittest.main()
