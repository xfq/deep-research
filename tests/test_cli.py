import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_research_agent.cli import main
from deep_research_agent.research import (
    DeepAgentReportModel,
    Evidence,
    ResearchBudget,
    ResearchOutcome,
    ResearchResult,
    SingleSourceResearchEngine,
    Source,
    TavilySourceReader,
    TavilyWebSearch,
    TerminationReason,
    build_live_research_engine,
)


class DeterministicModel:
    def summarize(self, question: str, source: Source, content: str) -> str:
        return content


class DeterministicSearch:
    def search(self, question: str) -> Source:
        return Source(
            title="LangChain overview",
            url="https://example.com/langchain",
        )


class DeterministicSourceReader:
    def read(self, source: Source) -> str:
        return "LangChain is a framework for building LLM applications"


class CliTests(unittest.TestCase):
    def test_unhandled_research_failure_has_stable_safe_cli_outcome(self) -> None:
        secret = "secret-runtime-value"

        class FailingEngine:
            def research(self, question, budget):
                raise RuntimeError(f"planner failed with {secret}")

        stderr = StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(stderr):
            exit_code = main(
                ["Question", "--output-dir", directory],
                research_engine=FailingEngine(),
            )

            self.assertTrue((Path(directory) / "report.md").exists())
            self.assertTrue((Path(directory) / "report.html").exists())
            diagnostics = (Path(directory) / "diagnostics.jsonl").read_text(
                encoding="utf-8"
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("research execution failed (RuntimeError)", stderr.getvalue())
        self.assertNotIn(secret, stderr.getvalue())
        self.assertNotIn(secret, diagnostics)
        self.assertIn("research_execution_failed", diagnostics)

    def test_output_write_failure_has_stable_cli_outcome(self) -> None:
        class StaticEngine:
            def research(self, question, budget):
                return ResearchResult(report="Report\n", sources=())

        stderr = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "not-a-directory"
            output_path.write_text("occupied", encoding="utf-8")

            with redirect_stderr(stderr):
                exit_code = main(
                    ["Question", "--output-dir", str(output_path)],
                    research_engine=StaticEngine(),
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("could not write research outputs", stderr.getvalue())

    def test_cli_help_documents_budget_outputs_and_provider_configuration(self) -> None:
        stdout = StringIO()

        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["--help"])

        help_text = stdout.getvalue()
        normalized_help = " ".join(help_text.split())
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("default: 3", normalized_help)
        self.assertIn("default: 120", normalized_help)
        self.assertIn("report.html", help_text)
        self.assertIn("diagnostics.jsonl", help_text)
        self.assertIn("OPENAI_API_KEY", help_text)
        self.assertIn("TAVILY_API_KEY", help_text)

    def test_cli_distinguishes_partial_and_failed_human_readable_outcomes(self) -> None:
        scenarios = (
            (
                ResearchResult(
                    report="Partial report\n",
                    sources=(Source(title="Source", url="https://example.com/1"),),
                    outcome=ResearchOutcome.PARTIAL,
                    termination_reason=TerminationReason.SEARCH_LIMIT,
                ),
                3,
                "Research partial: search limit exhausted",
                False,
            ),
            (
                ResearchResult(
                    report="Failed report\n",
                    sources=(),
                    outcome=ResearchOutcome.FAILED,
                    termination_reason=TerminationReason.SEARCH_LIMIT,
                ),
                1,
                "Research failed: search limit exhausted",
                True,
            ),
        )

        for result, expected_exit, message, uses_stderr in scenarios:
            with self.subTest(outcome=result.outcome), tempfile.TemporaryDirectory() as directory:
                class StaticEngine:
                    def research(self, question, budget):
                        return result

                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        ["Question", "--output-dir", directory],
                        research_engine=StaticEngine(),
                    )

                self.assertEqual(exit_code, expected_exit)
                self.assertIn(message, stderr.getvalue() if uses_stderr else stdout.getvalue())

    def test_research_budget_overrides_are_forwarded_to_the_research_run(self) -> None:
        class RecordingEngine:
            budget = None

            def research(self, question: str, budget: ResearchBudget) -> ResearchResult:
                self.budget = budget
                return ResearchResult(report="Report\n", sources=())

        with tempfile.TemporaryDirectory() as directory:
            engine = RecordingEngine()

            exit_code = main(
                [
                    "What is LangChain?",
                    "--max-searches",
                    "4",
                    "--max-source-reads",
                    "5",
                    "--max-elapsed-seconds",
                    "90",
                    "--output-dir",
                    directory,
                ],
                research_engine=engine,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            engine.budget,
            ResearchBudget(max_searches=4, max_source_reads=5, max_elapsed_seconds=90),
        )

    def test_invalid_research_budget_is_rejected_before_research_starts(self) -> None:
        class EngineThatMustNotRun:
            def research(self, question: str, budget: ResearchBudget):
                raise AssertionError("research must not start")

        invalid_values = (
            ("--max-searches", "0", "positive integer"),
            ("--max-source-reads", "-1", "positive integer"),
            ("--max-elapsed-seconds", "nan", "positive number"),
        )
        for option, value, message in invalid_values:
            with self.subTest(option=option), redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as raised:
                    main(
                        ["Question", option, value],
                        research_engine=EngineThatMustNotRun(),
                    )

                self.assertEqual(raised.exception.code, 2)
                self.assertIn(message, stderr.getvalue())

    def test_researcher_can_create_report_and_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            research_engine = SingleSourceResearchEngine(
                model=DeterministicModel(),
                search=DeterministicSearch(),
                source_reader=DeterministicSourceReader(),
            )

            exit_code = main(
                [
                    "What is LangChain?",
                    "--output-dir",
                    str(output_directory),
                ],
                research_engine=research_engine,
            )

            self.assertEqual(exit_code, 0)
            report_html = (output_directory / "report.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("<!DOCTYPE html>", report_html)
            self.assertIn("What is LangChain?", report_html)
            self.assertIn("LangChain overview", report_html)
            self.assertIn('href="#source-1"', report_html)
            self.assertEqual(
                (output_directory / "report.md").read_text(encoding="utf-8"),
                "# Research Report\n\n"
                "## Research Question\n\nWhat is LangChain?\n\n"
                "## Findings\n\nLangChain is a framework for building LLM applications [1]\n\n"
                "## Sources\n\n[1] https://example.com/langchain\n",
            )
            self.assertEqual(
                json.loads(
                    (output_directory / "sources.json").read_text(encoding="utf-8")
                ),
                [
                    {
                        "title": "LangChain overview",
                        "url": "https://example.com/langchain",
                    }
                ],
            )
            events = [
                json.loads(line)
                for line in (output_directory / "diagnostics.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in events],
                [
                    "research_started",
                    "search_completed",
                    "source_read_completed",
                    "research_finished",
                ],
            )
            diagnostics_text = (output_directory / "diagnostics.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(
                "LangChain is a framework for building LLM applications",
                diagnostics_text,
            )

    def test_blank_research_question_is_rejected_before_research_starts(self) -> None:
        class EngineThatMustNotRun:
            def research(self, question: str, budget: ResearchBudget):
                raise AssertionError("research must not start")

        stderr = StringIO()

        with redirect_stderr(stderr):
            exit_code = main(["   "], research_engine=EngineThatMustNotRun())

        self.assertEqual(exit_code, 2)
        self.assertIn("Research Question must not be blank", stderr.getvalue())

    def test_missing_research_question_has_actionable_cli_error(self) -> None:
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("the following arguments are required: question", stderr.getvalue())

    def test_live_research_requires_provider_credentials_before_writing_output(self) -> None:
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in {"OPENAI_API_KEY", "TAVILY_API_KEY"}
            }

            with patch.dict(os.environ, environment, clear=True), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "What is LangChain?",
                        "--output-dir",
                        str(output_directory),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("OPENAI_API_KEY", stderr.getvalue())
            self.assertIn("TAVILY_API_KEY", stderr.getvalue())
            self.assertFalse((output_directory / "report.md").exists())
            self.assertFalse((output_directory / "report.html").exists())
            self.assertFalse((output_directory / "sources.json").exists())

    def test_live_research_uses_configured_openai_base_url(self) -> None:
        environment = {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_BASE_URL": "https://llm.example.com/v1",
            "TAVILY_API_KEY": "test-tavily-key",
        }

        with patch.dict(os.environ, environment, clear=True):
            engine = build_live_research_engine()

        self.assertIsInstance(engine.model, DeepAgentReportModel)
        self.assertEqual(engine.model.base_url, "https://llm.example.com/v1")

    def test_invalid_live_configuration_identifies_setting_without_secret(self) -> None:
        secret = "secret-openai-key"
        invalid_environments = (
            (
                {
                    "OPENAI_API_KEY": secret,
                    "OPENAI_BASE_URL": "file:///tmp/provider",
                    "TAVILY_API_KEY": "test-tavily-key",
                },
                "OPENAI_BASE_URL",
            ),
            (
                {
                    "OPENAI_API_KEY": secret,
                    "OPENAI_REASONING_EFFORT": "extreme",
                    "TAVILY_API_KEY": "test-tavily-key",
                },
                "OPENAI_REASONING_EFFORT",
            ),
            (
                {
                    "OPENAI_API_KEY": secret,
                    "DEEP_RESEARCH_MODEL": "   ",
                    "TAVILY_API_KEY": "test-tavily-key",
                },
                "DEEP_RESEARCH_MODEL",
            ),
        )

        for environment, setting in invalid_environments:
            with self.subTest(setting=setting), patch.dict(
                os.environ, environment, clear=True
            ):
                with self.assertRaisesRegex(ValueError, setting) as raised:
                    build_live_research_engine()

                self.assertNotIn(secret, str(raised.exception))

    def test_live_research_disables_reasoning_for_tool_compatible_chat_calls(self) -> None:
        environment = {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_BASE_URL": "https://llm.example.com/v1",
            "TAVILY_API_KEY": "test-tavily-key",
        }

        with patch.dict(os.environ, environment, clear=True):
            engine = build_live_research_engine()

        self.assertIsInstance(engine.model, DeepAgentReportModel)
        self.assertEqual(engine.model.reasoning_effort, "none")

    def test_reasoning_effort_override_is_forwarded_to_chat_model(self) -> None:
        captured_options = {}

        class FakeChatOpenAI:
            def __init__(self, **options):
                captured_options.update(options)

        class FakeAgent:
            def invoke(self, inputs):
                return {"messages": [types.SimpleNamespace(content="Finding")]}

        fake_deepagents = types.ModuleType("deepagents")
        fake_deepagents.create_deep_agent = lambda **options: FakeAgent()
        fake_langchain_openai = types.ModuleType("langchain_openai")
        fake_langchain_openai.ChatOpenAI = FakeChatOpenAI
        environment = {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_REASONING_EFFORT": "low",
            "TAVILY_API_KEY": "test-tavily-key",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch.dict(
                sys.modules,
                {
                    "deepagents": fake_deepagents,
                    "langchain_openai": fake_langchain_openai,
                },
            ),
        ):
            engine = build_live_research_engine()
            engine.model.summarize(
                "Question",
                Source(title="Source", url="https://example.com/source"),
                "Evidence",
            )

        self.assertEqual(captured_options["reasoning_effort"], "low")

    def test_deep_agent_rejects_invalid_research_synthesis_schema(self) -> None:
        class FakeChatOpenAI:
            def __init__(self, **options):
                pass

        class FakeAgent:
            def invoke(self, inputs):
                return {
                    "messages": [
                        types.SimpleNamespace(
                            content='{"answer": [], "conflicts": "not-a-list"}'
                        )
                    ]
                }

        fake_deepagents = types.ModuleType("deepagents")
        fake_deepagents.create_deep_agent = lambda **options: FakeAgent()
        fake_langchain_openai = types.ModuleType("langchain_openai")
        fake_langchain_openai.ChatOpenAI = FakeChatOpenAI
        model = DeepAgentReportModel(model_name="test", api_key="test")

        with patch.dict(
            sys.modules,
            {
                "deepagents": fake_deepagents,
                "langchain_openai": fake_langchain_openai,
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "invalid Research synthesis JSON"):
                model.synthesize(
                    "Question",
                    (
                        Evidence(
                            summary="Evidence",
                            source=Source(
                                title="Source", url="https://example.com/source"
                            ),
                        ),
                    ),
                )

    def test_source_reader_rejects_non_public_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, "public HTTP or HTTPS"):
            TavilySourceReader(api_key="unused").read(
                Source(title="Local file", url="file:///etc/passwd")
            )
        with self.assertRaisesRegex(ValueError, "user credentials"):
            TavilySourceReader(api_key="unused").read(
                Source(
                    title="Credential URL",
                    url="https://user:password@example.com/source",
                )
            )

    def test_web_search_limits_provider_query_length(self) -> None:
        captured_query = None

        class FakeTavilyClient:
            def __init__(self, api_key):
                pass

            def search(self, question, **options):
                nonlocal captured_query
                captured_query = question
                return {
                    "results": [
                        {
                            "title": "Source",
                            "url": "https://example.com/source",
                        }
                    ]
                }

        fake_tavily = types.ModuleType("tavily")
        fake_tavily.TavilyClient = FakeTavilyClient

        with patch.dict(sys.modules, {"tavily": fake_tavily}):
            TavilyWebSearch(api_key="test-key").search("x" * 401)

        self.assertEqual(len(captured_query), 400)

    def test_web_search_prefers_an_authoritative_source_over_a_generic_result(self) -> None:
        class FakeTavilyClient:
            def __init__(self, api_key):
                pass

            def search(self, question, **options):
                return {
                    "results": [
                        {
                            "title": "Independent blog",
                            "url": "https://blog.example.com/topic",
                            "score": 0.80,
                        },
                        {
                            "title": "Official documentation",
                            "url": "https://docs.example.com/topic",
                            "score": 0.77,
                        },
                        {
                            "title": "W3C Recommendation",
                            "url": "https://www.w3.org/TR/topic/",
                            "score": 0.78,
                        },
                        {
                            "title": "Unrelated official documentation",
                            "url": "https://docs.example.org/unrelated",
                            "score": 0.10,
                        },
                    ]
                }

        fake_tavily = types.ModuleType("tavily")
        fake_tavily.TavilyClient = FakeTavilyClient

        with patch.dict(sys.modules, {"tavily": fake_tavily}):
            source = TavilyWebSearch(api_key="test-key").search("Question")

        self.assertEqual(source.url, "https://www.w3.org/TR/topic/")


if __name__ == "__main__":
    unittest.main()
