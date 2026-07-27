import sys
import tempfile
import unittest
import json
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_research_agent.cli import main
from deep_research_agent.research import (
    Evidence,
    PlannedResearchEngine,
    NoUsefulSources,
    ResearchBudget,
    ResearchSynthesis,
    Source,
)


class SequencePlanner:
    def __init__(self, investigations: list[str]):
        self.investigations = investigations

    def next_investigation(self, question, research_plan, evidence_summaries):
        index = len(research_plan)
        return self.investigations[index] if index < len(self.investigations) else None


class RecordingSearch:
    def __init__(self):
        self.questions = []

    def search(self, question: str) -> Source:
        self.questions.append(question)
        return Source(title=question, url=f"https://example.com/{len(self.questions)}")


class RecordingReader:
    def __init__(self):
        self.urls = []

    def read(self, source: Source) -> str:
        self.urls.append(source.url)
        return f"Evidence from {source.title}"


class DeterministicModel:
    def summarize(self, question: str, source: Source, content: str) -> str:
        return content

    def synthesize(
        self, question: str, evidence: tuple[Evidence, ...]
    ) -> ResearchSynthesis | str:
        return " ".join(
            f"{item.summary} [{index}]" for index, item in enumerate(evidence, 1)
        )


class CliResearchTestCase(unittest.TestCase):
    def run_cli(self, engine, *budget_arguments: str, expected_exit_code: int = 0) -> str:
        with tempfile.TemporaryDirectory() as directory:
            exit_code = main(
                ["Question", *budget_arguments, "--output-dir", directory],
                research_engine=engine,
            )
            self.assertEqual(exit_code, expected_exit_code)
            return (Path(directory) / "report.md").read_text(encoding="utf-8")


class ResearchBudgetTests(CliResearchTestCase):

    def test_verbose_planner_output_does_not_exhaust_search_budget(self) -> None:
        verbose_investigation = (
            "Research remains blocked: this session has no public-web browsing "
            "or URL-fetching capability, so no source-verified claims can be made. "
            "Most important remaining evidence gap: verify W3C's identity, mission, "
            "standards process, history, and governance using authoritative sources. "
            "Priority sources include the W3C About, Mission, Standards, Process, "
            "History, Corporation, Governance, and Bylaws pages. "
            "No source-verified factual claims can be added without relying on model "
            "memory."
        )

        class LengthLimitedSearch(RecordingSearch):
            def search(self, question: str) -> Source:
                if len(question) > 400:
                    raise RuntimeError(
                        "Query is too long. Max query length is 400 characters."
                    )
                return super().search(question)

        search = LengthLimitedSearch()
        engine = PlannedResearchEngine(
            planner=SequencePlanner([verbose_investigation] * 3),
            model=DeterministicModel(),
            search=search,
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine)

        self.assertEqual(search.questions, ["Question", "Question", "Question"])
        self.assertIn("## Outcome\n\ncomplete", report)

    def test_search_limit_stops_before_an_extra_external_search(self) -> None:
        search = RecordingSearch()
        reader = RecordingReader()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=DeterministicModel(),
            search=search,
            source_reader=reader,
        )

        report = self.run_cli(
            engine,
            "--max-searches", "1",
            "--max-source-reads", "2",
            "--max-elapsed-seconds", "60",
            expected_exit_code=3,
        )

        self.assertEqual(search.questions, ["first"])
        self.assertEqual(reader.urls, ["https://example.com/1"])
        self.assertIn("search limit exhausted", report)
        self.assertIn("- first\n- second", report)

    def test_source_read_limit_stops_before_an_extra_external_read(self) -> None:
        search = RecordingSearch()
        reader = RecordingReader()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=DeterministicModel(),
            search=search,
            source_reader=reader,
        )

        report = self.run_cli(
            engine,
            "--max-searches", "2",
            "--max-source-reads", "1",
            "--max-elapsed-seconds", "60",
            expected_exit_code=3,
        )

        self.assertEqual(search.questions, ["first", "second"])
        self.assertEqual(reader.urls, ["https://example.com/1"])
        self.assertIn("Source read limit exhausted", report)

    def test_elapsed_limit_stops_before_the_next_external_operation(self) -> None:
        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        class AdvancingSearch(RecordingSearch):
            def search(self, question: str) -> Source:
                source = super().search(question)
                clock.now = 2.0
                return source

        search = AdvancingSearch()
        reader = RecordingReader()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=DeterministicModel(),
            search=search,
            source_reader=reader,
            clock=clock,
        )

        report = self.run_cli(
            engine,
            "--max-searches", "1",
            "--max-source-reads", "1",
            "--max-elapsed-seconds", "1",
            expected_exit_code=1,
        )

        self.assertEqual(search.questions, ["first"])
        self.assertEqual(reader.urls, [])
        self.assertIn("elapsed time limit exhausted", report)


class AuditableReportTests(CliResearchTestCase):
    def test_cli_synthesizes_multiple_sources_with_provenance_and_citations(self) -> None:
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=DeterministicModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
        )

        with tempfile.TemporaryDirectory() as directory:
            exit_code = main(
                ["Question", "--output-dir", directory], research_engine=engine
            )
            report = (Path(directory) / "report.md").read_text(encoding="utf-8")
            sources = json.loads(
                (Path(directory) / "sources.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("## Answer", report)
        self.assertIn("## Outcome\n\ncomplete", report)
        self.assertIn("Evidence from first [1]", report)
        self.assertIn("Evidence from second [2]", report)
        self.assertIn("[1] https://example.com/1", report)
        self.assertIn("[2] https://example.com/2", report)
        self.assertEqual(
            sources,
            [
                {"title": "first", "url": "https://example.com/1"},
                {"title": "second", "url": "https://example.com/2"},
            ],
        )


class UncertainEvidenceTests(CliResearchTestCase):
    def test_diagnostics_capture_stages_budget_and_safe_failures(self) -> None:
        secret = "diagnostic-secret"

        class FailOnceSearch(RecordingSearch):
            attempts = 0

            def search(self, question: str) -> Source:
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError(f"temporary failure {secret}")
                return super().search(question)

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second", "third"]),
            model=DeterministicModel(),
            search=FailOnceSearch(),
            source_reader=RecordingReader(),
        )

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"TAVILY_API_KEY": secret}
        ):
            exit_code = main(
                ["Question", "--output-dir", directory], research_engine=engine
            )
            diagnostics_text = (Path(directory) / "diagnostics.jsonl").read_text(
                encoding="utf-8"
            )
            events = [json.loads(line) for line in diagnostics_text.splitlines()]

        self.assertEqual(exit_code, 3)
        self.assertIn("recoverable_failure", [event["event"] for event in events])
        self.assertEqual(events[-1]["event"], "research_finished")
        self.assertEqual(events[-1]["searches_used"], 3)
        self.assertEqual(events[-1]["source_reads_used"], 2)
        self.assertNotIn(secret, diagnostics_text)
        self.assertNotIn("Evidence from", diagnostics_text)

    def test_diagnostics_strip_source_query_parameters(self) -> None:
        class QuerySourceSearch:
            calls = 0

            def search(self, question: str) -> Source:
                self.calls += 1
                return Source(
                    title=f"Source {self.calls}",
                    url=f"https://example.com/{self.calls}?token=secret-{self.calls}",
                )

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=DeterministicModel(),
            search=QuerySourceSearch(),
            source_reader=RecordingReader(),
        )

        with tempfile.TemporaryDirectory() as directory:
            exit_code = main(
                ["Question", "--output-dir", directory], research_engine=engine
            )
            diagnostics = (Path(directory) / "diagnostics.jsonl").read_text(
                encoding="utf-8"
            )

        self.assertEqual(exit_code, 0)
        self.assertNotIn("token=", diagnostics)
        self.assertIn("https://example.com/1", diagnostics)

    def test_cli_surfaces_conflicting_evidence_separately_from_the_answer(self) -> None:
        class ConflictingModel(DeterministicModel):
            def synthesize(
                self, question: str, evidence: tuple[Evidence, ...]
            ) -> ResearchSynthesis:
                return ResearchSynthesis(
                    answer="The Sources disagree about the measured value [1] [2].",
                    conflicts=(
                        "Source one reports 10 [1], while Source two reports 12 [2].",
                    ),
                    uncertainty=("The discrepancy cannot be resolved from these Sources.",),
                )

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=ConflictingModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
        )

        with tempfile.TemporaryDirectory() as directory:
            exit_code = main(
                ["Question", "--output-dir", directory], research_engine=engine
            )
            report = (Path(directory) / "report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("## Answer\n\nThe Sources disagree", report)
        self.assertIn("## Conflicting Evidence", report)
        self.assertIn("Source one reports 10 [1]", report)
        self.assertIn("## Uncertainty", report)
        self.assertIn("cannot be resolved", report)

    def test_cli_records_an_inaccessible_source_and_continues_research(self) -> None:
        class FirstReadFails(RecordingReader):
            def read(self, source: Source) -> str:
                self.urls.append(source.url)
                if len(self.urls) == 1:
                    raise RuntimeError("page could not be parsed")
                return f"Evidence from {source.title}"

        reader = FirstReadFails()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second", "third"]),
            model=DeterministicModel(),
            search=RecordingSearch(),
            source_reader=reader,
        )

        report = self.run_cli(engine, expected_exit_code=3)

        self.assertIn("## Failed Operations", report)
        self.assertIn("https://example.com/1", report)
        self.assertIn("page could not be parsed", report)
        self.assertIn("Evidence from second [1]", report)
        self.assertIn("Evidence from third [2]", report)

    def test_evidence_extraction_failures_without_evidence_return_failure(self) -> None:
        class FailingModel(DeterministicModel):
            def summarize(self, question: str, source: Source, content: str) -> str:
                raise RuntimeError("Evidence extraction failed")

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=FailingModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine, expected_exit_code=1)

        self.assertIn("No supported answer could be established", report)
        self.assertIn("Evidence extraction failed", report)

    def test_synthesis_failure_preserves_evidence_in_a_partial_report(self) -> None:
        class FailingSynthesisModel(DeterministicModel):
            def synthesize(self, question: str, evidence):
                raise RuntimeError("synthesis failed")

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=FailingSynthesisModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine, expected_exit_code=3)

        self.assertIn("Evidence from first [1]", report)
        self.assertIn("Evidence from second [2]", report)
        self.assertIn("synthesis failed", report)

    def test_empty_evidence_extraction_preserves_previous_evidence(self) -> None:
        class EmptyAfterFirstModel(DeterministicModel):
            calls = 0

            def summarize(self, question: str, source: Source, content: str) -> str:
                self.calls += 1
                return content if self.calls == 1 else ""

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second", "third"]),
            model=EmptyAfterFirstModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine, expected_exit_code=3)

        self.assertIn("Evidence from first [1]", report)
        self.assertIn("Research model returned no Evidence", report)
        self.assertIn("## Outcome\n\npartial", report)

    def test_recoverable_search_failure_continues_with_later_evidence(self) -> None:
        class FailOnceSearch(RecordingSearch):
            attempts = 0

            def search(self, question: str) -> Source:
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("temporary search failure")
                return super().search(question)

        search = FailOnceSearch()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second", "third"]),
            model=DeterministicModel(),
            search=search,
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine, expected_exit_code=3)

        self.assertIn("temporary search failure", report)
        self.assertIn("Evidence from second [1]", report)
        self.assertIn("Evidence from third [2]", report)

    def test_cli_reports_no_useful_sources_as_a_failed_run(self) -> None:
        class FailingSearch:
            def search(self, question: str) -> Source:
                raise NoUsefulSources("no useful public Sources")

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first", "second"]),
            model=DeterministicModel(),
            search=FailingSearch(),
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine, expected_exit_code=1)

        self.assertIn("No supported answer could be established", report)
        self.assertIn("## Evidence Gaps", report)
        self.assertIn("## Failed Operations", report)
        self.assertIn("no useful public Sources", report)
        self.assertIn("## Outcome\n\nfailed", report)

    def test_failed_operation_does_not_expose_provider_credentials(self) -> None:
        secret = "secret-provider-key"

        class LeakySearch:
            def search(self, question: str) -> Source:
                raise RuntimeError(f"provider rejected {secret}")

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=DeterministicModel(),
            search=LeakySearch(),
            source_reader=RecordingReader(),
        )

        with patch.dict(os.environ, {"TAVILY_API_KEY": secret}):
            report = self.run_cli(engine, expected_exit_code=1)

        self.assertNotIn(secret, report)
        self.assertIn("[REDACTED]", report)

    def test_cli_marks_single_source_evidence_as_incomplete(self) -> None:
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=DeterministicModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
        )

        report = self.run_cli(
            engine,
            "--max-searches", "1",
            "--max-source-reads", "1",
            expected_exit_code=3,
        )

        self.assertIn("## Evidence Gaps", report)
        self.assertIn("search limit exhausted", report)
        self.assertIn("## Uncertainty", report)
        self.assertIn("Evidence may be incomplete", report)
        self.assertIn("## Outcome\n\npartial", report)

    def test_cli_rejects_missing_and_orphaned_answer_citations(self) -> None:
        invalid_answers = (
            ("Answer without a citation", "no Source citations"),
            ("Answer with invalid Source [0]", "orphaned citations"),
            ("Answer with unknown Source [3]", "orphaned citations"),
            (
                "Supported statement [1]. Unsupported statement.",
                "uncited statements",
            ),
            (
                "First statement [1]. Second statement [1].",
                "does not synthesize multiple Sources",
            ),
        )
        for answer, message in invalid_answers:
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as directory:
                class InvalidCitationModel(DeterministicModel):
                    def synthesize(self, question: str, evidence) -> str:
                        return answer

                engine = PlannedResearchEngine(
                    planner=SequencePlanner(["first"]),
                    model=InvalidCitationModel(),
                    search=RecordingSearch(),
                    source_reader=RecordingReader(),
                )

                exit_code = main(
                    ["Question", "--output-dir", directory], research_engine=engine
                )
                report = (Path(directory) / "report.md").read_text(encoding="utf-8")

                self.assertEqual(exit_code, 3)
                self.assertIn(message, report)
                self.assertIn("Evidence from first [1]", report)
                self.assertIn("## Outcome\n\npartial", report)

    def test_cli_seeks_a_second_independent_source_when_planner_stops_early(self) -> None:
        search = RecordingSearch()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=DeterministicModel(),
            search=search,
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine)

        self.assertEqual(
            search.questions,
            [
                "first",
                "Question independent authoritative primary Source corroboration",
            ],
        )
        self.assertIn("Evidence from first [1]", report)
        self.assertIn("authoritative primary Source corroboration [2]", report)

    def test_duplicate_search_result_is_not_read_again(self) -> None:
        class DuplicateThenUniqueSearch:
            calls = 0

            def search(self, question: str) -> Source:
                self.calls += 1
                suffix = 1 if self.calls < 3 else 2
                return Source(
                    title=f"Source {suffix}", url=f"https://example.com/{suffix}"
                )

        search = DuplicateThenUniqueSearch()
        reader = RecordingReader()
        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=DeterministicModel(),
            search=search,
            source_reader=reader,
        )

        report = self.run_cli(engine)

        self.assertEqual(search.calls, 3)
        self.assertEqual(
            reader.urls, ["https://example.com/1", "https://example.com/2"]
        )
        self.assertIn("[2] https://example.com/2", report)

    def test_evolving_research_plan_can_complete_multiple_investigations(self) -> None:
        search = RecordingSearch()

        class EvidenceDrivenPlanner:
            def next_investigation(
                self, question, research_plan, evidence_summaries
            ):
                if not research_plan:
                    return "first focus"
                if len(research_plan) == 1:
                    return f"verify gap after {evidence_summaries[0]}"
                return None

        engine = PlannedResearchEngine(
            planner=EvidenceDrivenPlanner(),
            model=DeterministicModel(),
            search=search,
            source_reader=RecordingReader(),
        )

        report = self.run_cli(engine)

        self.assertIn("Research Question sufficiently answered", report)
        self.assertIn("- first focus\n- verify gap after Evidence from first focus", report)
        self.assertEqual(
            search.questions,
            ["first focus", "verify gap after Evidence from first focus"],
        )

    def test_elapsed_limit_includes_model_work(self) -> None:
        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        class SlowModel(DeterministicModel):
            def summarize(self, question: str, source: Source, content: str) -> str:
                clock.now = 2.0
                return super().summarize(question, source, content)

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=SlowModel(),
            search=RecordingSearch(),
            source_reader=RecordingReader(),
            clock=clock,
        )

        report = self.run_cli(
            engine,
            "--max-elapsed-seconds", "1",
            expected_exit_code=3,
        )

        self.assertIn("elapsed time limit exhausted", report)

    def test_elapsed_limit_is_checked_after_reading_before_model_work(self) -> None:
        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        class AdvancingReader(RecordingReader):
            def read(self, source: Source) -> str:
                content = super().read(source)
                clock.now = 2.0
                return content

        class ModelThatMustNotRun(DeterministicModel):
            def summarize(self, question: str, source: Source, content: str) -> str:
                raise AssertionError("model must not run after elapsed budget")

        engine = PlannedResearchEngine(
            planner=SequencePlanner(["first"]),
            model=ModelThatMustNotRun(),
            search=RecordingSearch(),
            source_reader=AdvancingReader(),
            clock=clock,
        )

        report = self.run_cli(
            engine,
            "--max-elapsed-seconds", "1",
            expected_exit_code=1,
        )

        self.assertIn("elapsed time limit exhausted", report)
