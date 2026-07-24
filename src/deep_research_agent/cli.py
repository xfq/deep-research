import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from deep_research_agent.research import (
    ConfigurationError,
    ResearchBudget,
    ResearchEngine,
    ResearchOutcome,
    build_live_research_engine,
)
from deep_research_agent.report_html import render_report_html


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deep-research",
        description="Create an evidence-backed Research Report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Outputs: report.html, report.md, sources.json, diagnostics.jsonl. "
            "Live research requires OPENAI_API_KEY and TAVILY_API_KEY; optional "
            "settings: OPENAI_BASE_URL, OPENAI_REASONING_EFFORT, "
            "DEEP_RESEARCH_MODEL."
        ),
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="The Research Question to investigate.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research-output"),
        help="Directory for report.html, report.md, sources.json, and diagnostics.jsonl.",
    )
    parser.add_argument(
        "--max-searches", type=positive_int, default=3, help="Maximum web searches."
    )
    parser.add_argument(
        "--max-source-reads",
        type=positive_int,
        default=3,
        help="Maximum public Source reads.",
    )
    parser.add_argument(
        "--max-elapsed-seconds",
        type=positive_float,
        default=120,
        help="Maximum elapsed research time in seconds.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Interactively configure API keys and write a .env file.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    research_engine: ResearchEngine | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.setup:
        _interactive_setup()
        return 0
    if not args.question or not args.question.strip():
        print("error: Research Question must not be blank", file=sys.stderr)
        return 2

    try:
        engine = research_engine or build_live_research_engine()
    except ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        result = engine.research(
            args.question,
            ResearchBudget(
                max_searches=args.max_searches,
                max_source_reads=args.max_source_reads,
                max_elapsed_seconds=args.max_elapsed_seconds,
            ),
        )
    except Exception as error:
        print(
            f"error: research execution failed ({type(error).__name__})",
            file=sys.stderr,
        )
        try:
            failure_report = (
                "# Research Report\n\n"
                f"## Research Question\n\n{args.question}\n\n"
                "## Outcome\n\nfailed\n\n"
                "## Termination Reason\n\nUnexpected research execution failure.\n"
            )
            _write_output_files(
                args.output_dir,
                {
                    "report.html": render_report_html(
                        failure_report,
                        question=args.question,
                        sources=(),
                        outcome=ResearchOutcome.FAILED,
                        termination_reason="Unexpected research execution failure.",
                    ),
                    "report.md": failure_report,
                    "sources.json": "[]\n",
                    "diagnostics.jsonl": json.dumps(
                        {
                            "event": "research_execution_failed",
                            "searches_used": 0,
                            "source_reads_used": 0,
                            "detail": type(error).__name__,
                        }
                    )
                    + "\n",
                },
            )
        except OSError:
            pass
        return 1

    try:
        _write_output_files(
            args.output_dir,
            {
                "report.html": render_report_html(
                    result.report,
                    question=args.question,
                    sources=result.sources,
                    outcome=result.outcome,
                    termination_reason=result.termination_reason,
                ),
                "report.md": result.report,
                "sources.json": (
                    json.dumps(
                        [asdict(source) for source in result.sources], indent=2
                    )
                    + "\n"
                ),
                "diagnostics.jsonl": "".join(
                    json.dumps(asdict(event)) + "\n" for event in result.events
                ),
            },
        )
    except (OSError, TypeError) as error:
        print(
            f"error: could not write research outputs ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1

    report_path = args.output_dir / "report.html"
    if result.outcome == ResearchOutcome.COMPLETE:
        print(f"Research complete: {report_path}")
        return 0
    if result.outcome == ResearchOutcome.PARTIAL:
        print(f"Research partial: {result.termination_reason}: {report_path}")
        return 3
    print(f"Research failed: {result.termination_reason}: {report_path}", file=sys.stderr)
    return 1


def entrypoint() -> None:
    raise SystemExit(main())


def _interactive_setup() -> None:
    """Prompt for API keys and write a ``.env`` file in the current directory."""
    from os import chmod
    from stat import S_IRUSR, S_IWUSR

    env_path = Path(".env")
    if env_path.exists():
        print(f"{env_path} already exists. Remove it first or use a different directory.")
        return

    print("Deep Research Agent — interactive setup\n")
    print("Press Enter to skip optional settings.\n")

    openai_key = input("OPENAI_API_KEY: ").strip()
    tavily_key = input("TAVILY_API_KEY: ").strip()

    if not openai_key or not tavily_key:
        print(
            "error: OPENAI_API_KEY and TAVILY_API_KEY are required for live research.",
            file=sys.stderr,
        )
        return

    lines = [
        "# Deep Research Agent configuration",
        f'OPENAI_API_KEY="{openai_key}"',
        f'TAVILY_API_KEY="{tavily_key}"',
    ]

    base_url = input("OPENAI_BASE_URL (optional): ").strip()
    if base_url:
        lines.append(f'OPENAI_BASE_URL="{base_url}"')

    reasoning = input("OPENAI_REASONING_EFFORT [none]: ").strip()
    lines.append(f'OPENAI_REASONING_EFFORT="{reasoning or "none"}"')

    model = input("DEEP_RESEARCH_MODEL [gpt-5.6-sol]: ").strip()
    if model:
        lines.append(f'DEEP_RESEARCH_MODEL="{model}"')

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    chmod(env_path, S_IRUSR | S_IWUSR)
    print(f"\nConfiguration written to {env_path}")


def _write_output_files(output_directory: Path, files: dict[str, str]) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    temporary_paths: dict[str, Path] = {}
    for filename, content in files.items():
        temporary_path = output_directory / f".{filename}.tmp"
        temporary_path.write_text(content, encoding="utf-8")
        temporary_paths[filename] = temporary_path
    for filename, temporary_path in temporary_paths.items():
        temporary_path.replace(output_directory / filename)
