import json
import os
import re
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_research_agent.cli import main
from deep_research_agent.research import (
    PlannedResearchEngine,
    ResearchSynthesis,
    Source,
)


class ScenarioPlanner:
    def __init__(self, investigations):
        self.investigations = investigations

    def next_investigation(self, question, research_plan, evidence_summaries):
        index = len(research_plan)
        return self.investigations[index] if index < len(self.investigations) else None


class ScenarioSearch:
    def __init__(self):
        self.calls = 0

    def search(self, investigation):
        self.calls += 1
        return Source(
            title=investigation,
            url=f"https://evidence.example/{self.calls}",
        )


class ScenarioReader:
    def __init__(self, *, fail_first=False):
        self.calls = 0
        self.fail_first = fail_first

    def read(self, source):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("Source temporarily unavailable")
        return f"Official Source states: {source.title}."


class ScenarioModel:
    def __init__(self, synthesis):
        self.synthesis = synthesis

    def summarize(self, question, source, content):
        return content

    def synthesize(self, question, evidence):
        return self.synthesis


class AcceptanceTests(unittest.TestCase):
    def run_scenario(
        self,
        question,
        investigations,
        synthesis,
        *,
        reader=None,
        budget_arguments=(),
    ):
        search = ScenarioSearch()
        reader = reader or ScenarioReader()
        engine = PlannedResearchEngine(
            planner=ScenarioPlanner(investigations),
            model=ScenarioModel(synthesis),
            search=search,
            source_reader=reader,
        )
        stdout = StringIO()
        stderr = StringIO()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=True
        ):
            started_at = time.monotonic()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [question, *budget_arguments, "--output-dir", directory],
                    research_engine=engine,
                )
            elapsed = time.monotonic() - started_at
            report = (Path(directory) / "report.md").read_text(encoding="utf-8")
            report_html = (Path(directory) / "report.html").read_text(
                encoding="utf-8"
            )
            sources = json.loads(
                (Path(directory) / "sources.json").read_text(encoding="utf-8")
            )
            events = [
                json.loads(line)
                for line in (Path(directory) / "diagnostics.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
        return {
            "exit_code": exit_code,
            "report": report,
            "report_html": report_html,
            "sources": sources,
            "events": events,
            "elapsed": elapsed,
            "search_calls": search.calls,
            "read_calls": reader.calls,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }

    def assert_citation_integrity(self, result):
        cited_claim_sections = result["report"].split("## Evidence\n\n", 1)[0]
        citations = {
            int(value) for value in re.findall(r"\[(\d+)\]", cited_claim_sections)
        }
        self.assertTrue(citations)
        self.assertEqual(citations, set(range(1, len(result["sources"]) + 1)))
        source_urls = [source["url"] for source in result["sources"]]
        self.assertEqual(len(source_urls), len(set(source_urls)))
        for source in result["sources"]:
            self.assertEqual(set(source), {"title", "url"})
            self.assertTrue(source["url"].startswith("https://"))

    def assert_common_thresholds(self, result):
        self.assertLess(result["elapsed"], 1.0)
        self.assertLessEqual(result["search_calls"], 3)
        self.assertLessEqual(result["read_calls"], 3)
        self.assertEqual(result["events"][-1]["event"], "research_finished")
        outcome = re.search(r"## Outcome\n\n([^\n]+)", result["report"]).group(1)
        termination = re.search(
            r"## Termination Reason\n\n([^\n]+)", result["report"]
        ).group(1)
        self.assertEqual(
            result["events"][-1]["detail"], f"{outcome}: {termination}"
        )
        if result["exit_code"] == 0:
            self.assertEqual(outcome, "complete")
            self.assertIn("Research complete:", result["stdout"])
        elif result["exit_code"] == 3:
            self.assertEqual(outcome, "partial")
            self.assertIn("Research partial:", result["stdout"])
            self.assertIn(termination, result["stdout"])

    def test_direct_factual_research_acceptance(self):
        result = self.run_scenario(
            "In what year was Project Atlas launched?",
            [
                "Project Atlas launched in 2024",
                "The official history confirms the 2024 launch year",
            ],
            ResearchSynthesis(
                answer="Project Atlas launched in 2024 [1] [2]."
            ),
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("Project Atlas launched in 2024", result["report"])
        self.assertEqual(len(result["sources"]), 2)
        self.assert_citation_integrity(result)
        self.assert_common_thresholds(result)

    def test_multi_source_synthesis_acceptance(self):
        result = self.run_scenario(
            "Compare the documented capabilities of Alpha, Beta, and Gamma.",
            [
                "Alpha has a narrow documented scope",
                "Beta has a broader documented scope",
                "Gamma has a specialized documented scope",
            ],
            ResearchSynthesis(
                answer="Alpha, Beta, and Gamma differ in scope [1] [2] [3]."
            ),
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(len(result["sources"]), 3)
        self.assert_citation_integrity(result)
        self.assert_common_thresholds(result)

    def test_conflicting_evidence_acceptance(self):
        result = self.run_scenario(
            "What value did the two official measurements report?",
            ["The first official measurement reports 10", "The second reports 12"],
            ResearchSynthesis(
                answer="The official measurements disagree [1] [2].",
                conflicts=("One Source reports 10 [1], while another reports 12 [2].",),
                uncertainty=("The discrepancy cannot be resolved from available Evidence.",),
            ),
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("## Conflicting Evidence", result["report"])
        self.assertIn("cannot be resolved", result["report"])
        self.assert_citation_integrity(result)
        self.assert_common_thresholds(result)

    def test_insufficient_evidence_acceptance(self):
        result = self.run_scenario(
            "Can one Source establish the claim conclusively?",
            ["One Source supports the claim but cannot independently corroborate it"],
            ResearchSynthesis(answer="unused [1]"),
            budget_arguments=("--max-searches", "1", "--max-source-reads", "1"),
        )

        self.assertEqual(result["exit_code"], 3)
        self.assertIn("## Outcome\n\npartial", result["report"])
        self.assertIn("search limit exhausted", result["report"])
        self.assertIn("Unverified gap", result["report"])
        self.assertEqual(result["search_calls"], 1)
        self.assertEqual(result["read_calls"], 1)
        self.assert_common_thresholds(result)

    def test_recoverable_source_failure_acceptance(self):
        result = self.run_scenario(
            "What do the remaining accessible Sources establish?",
            [
                "Unavailable Source",
                "Accessible Source A supports the conclusion",
                "Accessible Source B independently supports the conclusion",
            ],
            ResearchSynthesis(
                answer="The accessible Sources support the conclusion [1] [2]."
            ),
            reader=ScenarioReader(fail_first=True),
        )

        self.assertEqual(result["exit_code"], 3)
        self.assertIn("Source temporarily unavailable", result["report"])
        self.assertIn("Accessible Source A supports the conclusion", result["report"])
        self.assertEqual(len(result["sources"]), 2)
        self.assert_citation_integrity(result)
        self.assert_common_thresholds(result)

    def test_simplified_chinese_question_produces_simplified_chinese_page(
        self,
    ) -> None:
        """A Simplified Chinese question produces a Simplified Chinese HTML page."""
        result = self.run_scenario(
            "什么是网页标准？",
            ["网页标准的定义", "网页标准的作用"],
            ResearchSynthesis(
                answer="网页标准让不同浏览器一致地呈现内容 [1] [2]。"
            ),
        )

        html = result["report_html"]
        self.assertIn('<html lang="zh-Hans">', html)
        self.assertIn("深度研究报告", html)
        self.assertIn("完整", html)
        self.assertIn("2 个来源", html)
        self.assertIn("目录", html)
        self.assertIn("<h2>回答</h2>", html)
        self.assertIn("<h2>来源</h2>", html)
        self.assertIn("未发现。", html)
        self.assertNotIn("Deep Research Report", html)
        self.assertNotIn(">Complete<", html)
        self.assertNotIn(">Contents<", html)
        self.assertNotIn("None identified.", html)

    def test_simplified_chinese_partial_page_localizes_system_explanations(
        self,
    ) -> None:
        """Partial-result boilerplate remains Simplified Chinese."""

        class ChineseScenarioReader(ScenarioReader):
            def read(self, source: Source) -> str:
                """Return Chinese evidence for the partial-result scenario."""
                self.calls += 1
                return f"官方来源说明：{source.title}。"

        result = self.run_scenario(
            "这个结论有充分证据吗？",
            ["查找支持该结论的权威来源"],
            ResearchSynthesis(answer="unused [1]"),
            reader=ChineseScenarioReader(),
            budget_arguments=("--max-searches", "1", "--max-source-reads", "1"),
        )

        html = result["report_html"]
        self.assertIn("未验证的缺口", html)
        self.assertIn("现有证据可能不完整", html)
        self.assertNotIn("Unverified gap", html)
        self.assertNotIn("Research ended with status", html)
        self.assertNotIn("Synthesis limitation", html)
        self.assertNotIn("The available Evidence may be incomplete", html)

    def test_simplified_chinese_page_hides_raw_english_failure_message(
        self,
    ) -> None:
        """Chinese HTML uses a localized failure summary for provider errors."""

        class ChineseFailOnceReader(ScenarioReader):
            def read(self, source: Source) -> str:
                """Fail once in English, then return Chinese evidence."""
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("Source temporarily unavailable")
                return f"官方来源说明：{source.title}。"

        result = self.run_scenario(
            "剩余来源支持什么结论？",
            ["不可用来源", "可用来源一", "可用来源二"],
            ResearchSynthesis(answer="剩余来源支持该结论 [1] [2]。"),
            reader=ChineseFailOnceReader(),
        )

        html = result["report_html"]
        self.assertIn("读取来源 https://evidence.example/1 时失败。", html)
        self.assertNotIn("Source temporarily unavailable", html)


if __name__ == "__main__":
    unittest.main()
