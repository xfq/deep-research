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
        self.assertNotIn("<h2>Research Question</h2>", html)
        self.assertNotIn("<h2>Outcome</h2>", html)

    def test_escapes_untrusted_report_content_and_detects_chinese_language(self) -> None:
        html = render_report_html(
            "# Research Report\n\n"
            "## Answer\n\n<script>alert('x')</script> [1]\n",
            question="什么是网页标准？",
            sources=(Source(title="Unsafe <title>", url="javascript:alert(1)"),),
            outcome=ResearchOutcome.PARTIAL,
            termination_reason=TerminationReason.SEARCH_LIMIT,
        )

        self.assertIn('<html lang="zh-CN">', html)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("Unsafe &lt;title&gt;", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("Partial", html)

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


if __name__ == "__main__":
    unittest.main()
