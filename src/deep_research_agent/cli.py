import argparse
from inspect import Parameter, signature
import json
import math
import sys
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import cast, Sequence, TextIO

from deep_research_agent.research import (
    ConfigurationError,
    ProgressReportingResearchEngine,
    ResearchBudget,
    ResearchEngine,
    ResearchEvent,
    ResearchOutcome,
    build_live_research_engine,
)
from deep_research_agent.report_html import render_report_html


_PROGRESS_STAGES: dict[str, tuple[int, str]] = {
    "research_started": (0, "Researching: planning"),
    "investigation_planned": (0, "Researching: planning next search"),
    "search_started": (0, "Researching: searching"),
    "search_completed": (0, "Researching: search complete"),
    "source_read_started": (0, "Researching: reading Source"),
    "source_read_completed": (0, "Researching: Source read complete"),
    "evidence_collected": (0, "Researching: Evidence collected"),
    "synthesis_started": (85, "Researching: synthesizing report"),
    "synthesis_completed": (92, "Researching: synthesis complete"),
    "recoverable_failure": (
        0,
        "Researching: continuing after a recoverable failure",
    ),
    "research_finished": (95, "Preparing output files"),
}


class _ProgressBar:
    """Render interactive Research Budget and stage progress to a terminal."""

    width = 24

    def __init__(self, budget: ResearchBudget, stream: TextIO) -> None:
        """Initialize a progress bar for one research run."""
        self.budget = budget
        self.stream = stream
        self.percent = 0
        self.line_length = 0
        self.enabled = True

    def start(self) -> None:
        """Show the initial research stage immediately."""
        self._render("Researching: planning")

    def update(self, event: ResearchEvent) -> None:
        """Advance the bar from a streamed research event."""
        total_operations = self.budget.max_searches + self.budget.max_source_reads
        completed_operations = min(
            event.searches_used, self.budget.max_searches
        ) + min(event.source_reads_used, self.budget.max_source_reads)
        budget_percent = int(80 * completed_operations / total_operations)
        stage_floor, label = _PROGRESS_STAGES.get(event.event, (0, "Researching"))
        self.percent = max(self.percent, budget_percent, stage_floor)
        self._render(label, event)

    def finish(self) -> None:
        """Complete the bar after all report files have been written."""
        self.percent = 100
        self._render("Report ready")
        self._end_line()

    def stop(self, label: str) -> None:
        """End the current progress line without claiming successful completion."""
        self._render(label)
        self._end_line()

    def _render(self, label: str, event: ResearchEvent | None = None) -> None:
        """Draw one terminal-safe progress frame."""
        if not self.enabled:
            return
        filled = self.width * self.percent // 100
        if filled >= self.width:
            bar = "=" * self.width
        else:
            bar = "=" * filled + ">" + "." * (self.width - filled - 1)
        counts = ""
        if event is not None:
            counts = (
                f" ({event.searches_used}/{self.budget.max_searches} searches, "
                f"{event.source_reads_used}/{self.budget.max_source_reads} Sources)"
            )
        line = f"[{bar}] {self.percent:3d}% {label}{counts}"
        padding = " " * max(0, self.line_length - len(line))
        try:
            self.stream.write(f"\r{line}{padding}")
            self.stream.flush()
        except OSError:
            self.enabled = False
            return
        self.line_length = len(line)

    def _end_line(self) -> None:
        """Move subsequent CLI output onto a fresh line."""
        if not self.enabled:
            return
        try:
            self.stream.write("\n")
            self.stream.flush()
        except OSError:
            self.enabled = False


def _supports_progress_events(engine: ResearchEngine) -> bool:
    """Return whether an engine accepts the optional ``on_event`` callback."""
    try:
        parameters = signature(engine.research).parameters
    except (TypeError, ValueError):
        return False
    on_event = parameters.get("on_event")
    if on_event is not None and on_event.kind != Parameter.POSITIONAL_ONLY:
        return True
    return any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


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
        "--no-open",
        action="store_true",
        help="Do not open report.html in the browser after generation.",
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
    budget = ResearchBudget(
        max_searches=args.max_searches,
        max_source_reads=args.max_source_reads,
        max_elapsed_seconds=args.max_elapsed_seconds,
    )
    progress = _ProgressBar(budget, sys.stderr) if sys.stderr.isatty() else None
    if progress is not None:
        progress.start()
    try:
        if progress is None or not _supports_progress_events(engine):
            result = engine.research(args.question, budget)
        else:
            progress_engine = cast(ProgressReportingResearchEngine, engine)
            result = progress_engine.research(
                args.question, budget, on_event=progress.update
            )
    except Exception as error:
        if progress is not None:
            progress.stop("Research failed")
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
        _maybe_open_report(args, args.output_dir / "report.html")
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
        if progress is not None:
            progress.stop("Could not write output files")
        print(
            f"error: could not write research outputs ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1

    if progress is not None:
        progress.finish()
    report_path = args.output_dir / "report.html"
    _maybe_open_report(args, report_path)
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


def _maybe_open_report(args: argparse.Namespace, report_path: Path) -> None:
    """Open *report_path* in the browser unless ``--no-open`` or running non-interactively."""
    if args.no_open or not sys.stdout.isatty():
        return
    webbrowser.open(f"file://{report_path.resolve()}")


def _write_output_files(output_directory: Path, files: dict[str, str]) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    temporary_paths: dict[str, Path] = {}
    for filename, content in files.items():
        temporary_path = output_directory / f".{filename}.tmp"
        temporary_path.write_text(content, encoding="utf-8")
        temporary_paths[filename] = temporary_path
    for filename, temporary_path in temporary_paths.items():
        temporary_path.replace(output_directory / filename)
