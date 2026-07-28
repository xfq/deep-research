from dataclasses import dataclass, replace
from enum import StrEnum
from ipaddress import ip_address
import json
from os import environ
from pathlib import Path
import re
from time import monotonic
from typing import Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

from deep_research_agent.localization import should_use_simplified_chinese


MAX_SOURCE_BYTES = 1_000_000
MAX_MODEL_CHARACTERS = 100_000
MAX_SEARCH_QUERY_CHARACTERS = 400


def _response_language_instruction(question: str) -> str:
    """Return a Simplified Chinese model-output instruction when needed."""
    if should_use_simplified_chinese(question):
        return " Write all natural-language output in Simplified Chinese."
    return ""


def _load_dotenv() -> None:
    """Load ``.env`` from the current directory and ``~/.deep-research/.env``.

    Variables already present in the environment are never overwritten.
    Project-local ``.env`` is loaded first, so it takes precedence over the
    global fallback file.
    """
    if environ.get("DEEP_RESEARCH_SKIP_DOTENV"):
        return
    paths = [Path(".env"), Path.home() / ".deep-research" / ".env"]
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or key in environ:
                continue
            value = value.strip().strip("'\"")
            environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class ResearchBudget:
    max_searches: int = 3
    max_source_reads: int = 3
    max_elapsed_seconds: float = 120


class TerminationReason(StrEnum):
    ANSWERED = "Research Question sufficiently answered"
    SEARCH_LIMIT = "search limit exhausted"
    SOURCE_READ_LIMIT = "Source read limit exhausted"
    ELAPSED_TIME_LIMIT = "elapsed time limit exhausted"
    RECOVERABLE_FAILURES = "completed with recoverable failures"


class ResearchOutcome(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class Evidence:
    summary: str
    source: Source


@dataclass(frozen=True)
class ResearchSynthesis:
    answer: str
    conflicts: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailedOperation:
    operation: str
    message: str
    source: Source | None = None


@dataclass(frozen=True)
class ResearchEvent:
    event: str
    searches_used: int = 0
    source_reads_used: int = 0
    detail: str | None = None


ProgressCallback = Callable[[ResearchEvent], None]


class _ResearchEventLog(list[ResearchEvent]):
    """Retain research events while optionally streaming each new event."""

    def __init__(self, on_event: ProgressCallback | None) -> None:
        """Initialize an event log with an optional streaming callback."""
        super().__init__()
        self.on_event = on_event

    def append(self, event: ResearchEvent) -> None:
        """Store and stream one research event."""
        super().append(event)
        if self.on_event is not None:
            self.on_event(event)


class NoUsefulSources(RuntimeError):
    pass


@dataclass(frozen=True)
class ResearchResult:
    report: str
    sources: tuple[Source, ...]
    evidence: tuple[Evidence, ...] = ()
    research_plan: tuple[str, ...] = ()
    termination_reason: TerminationReason = TerminationReason.ANSWERED
    failed_operations: tuple[FailedOperation, ...] = ()
    outcome: ResearchOutcome = ResearchOutcome.COMPLETE
    events: tuple[ResearchEvent, ...] = ()


class ResearchEngine(Protocol):
    def research(self, question: str, budget: ResearchBudget) -> ResearchResult: ...


class ProgressReportingResearchEngine(Protocol):
    """Research engine interface that streams events during execution."""

    def research(
        self,
        question: str,
        budget: ResearchBudget,
        on_event: ProgressCallback | None = None,
    ) -> ResearchResult:
        """Run research while streaming each auditable event to the caller."""
        ...


class ReportModel(Protocol):
    def summarize(self, question: str, source: Source, content: str) -> str: ...

    def synthesize(
        self, question: str, evidence: tuple[Evidence, ...]
    ) -> ResearchSynthesis | str: ...


class WebSearch(Protocol):
    def search(self, question: str) -> Source: ...


class SourceReader(Protocol):
    def read(self, source: Source) -> str: ...


class ResearchPlanner(Protocol):
    def next_investigation(
        self,
        question: str,
        research_plan: tuple[str, ...],
        evidence_summaries: tuple[str, ...],
    ) -> str | None: ...


class BudgetExhausted(RuntimeError):
    def __init__(self, reason: TerminationReason):
        super().__init__(reason.value)
        self.reason = reason


@dataclass
class BudgetedResearchTools:
    search_adapter: WebSearch
    source_reader_adapter: SourceReader
    budget: ResearchBudget
    started_at: float
    clock: Callable[[], float] = monotonic
    searches: int = 0
    source_reads: int = 0

    def ensure_time_remaining(self) -> None:
        if self.clock() - self.started_at >= self.budget.max_elapsed_seconds:
            raise BudgetExhausted(TerminationReason.ELAPSED_TIME_LIMIT)

    def search(self, question: str) -> Source:
        self.ensure_time_remaining()
        if self.searches >= self.budget.max_searches:
            raise BudgetExhausted(TerminationReason.SEARCH_LIMIT)
        self.searches += 1
        return self.search_adapter.search(question)

    def read(self, source: Source) -> str:
        self.ensure_time_remaining()
        if self.source_reads >= self.budget.max_source_reads:
            raise BudgetExhausted(TerminationReason.SOURCE_READ_LIMIT)
        self.source_reads += 1
        return self.source_reader_adapter.read(source)


@dataclass(frozen=True)
class PlannedResearchEngine:
    planner: ResearchPlanner
    model: ReportModel
    search: WebSearch
    source_reader: SourceReader
    clock: Callable[[], float] = monotonic

    def research(
        self,
        question: str,
        budget: ResearchBudget,
        on_event: ProgressCallback | None = None,
    ) -> ResearchResult:
        started_at = self.clock()
        tools = BudgetedResearchTools(
            search_adapter=self.search,
            source_reader_adapter=self.source_reader,
            budget=budget,
            started_at=started_at,
            clock=self.clock,
        )
        research_plan: list[str] = []
        evidence: list[Evidence] = []
        sources: list[Source] = []
        failed_operations: list[FailedOperation] = []
        events = _ResearchEventLog(on_event)
        events.append(ResearchEvent(event="research_started"))
        termination_reason = TerminationReason.ANSWERED

        while True:
            try:
                tools.ensure_time_remaining()
                investigation = self.planner.next_investigation(
                    question,
                    tuple(research_plan),
                    tuple(item.summary for item in evidence),
                )
                tools.ensure_time_remaining()
            except BudgetExhausted as error:
                termination_reason = error.reason
                break
            if investigation is None:
                if len(evidence) >= 2:
                    break
                if tools.searches >= budget.max_searches:
                    termination_reason = TerminationReason.SEARCH_LIMIT
                    break
                if tools.source_reads >= budget.max_source_reads:
                    termination_reason = TerminationReason.SOURCE_READ_LIMIT
                    break
                investigation = (
                    f"{question} 独立、权威的一手来源交叉验证"
                    if should_use_simplified_chinese(question)
                    else (
                        f"{question} independent authoritative primary Source "
                        "corroboration"
                    )
                )
            investigation = _normalize_search_query(
                investigation, fallback=question
            )
            research_plan.append(investigation)
            events.append(
                ResearchEvent(
                    event="investigation_planned",
                    searches_used=tools.searches,
                    source_reads_used=tools.source_reads,
                    detail=investigation,
                )
            )
            events.append(
                ResearchEvent(
                    event="search_started",
                    searches_used=tools.searches,
                    source_reads_used=tools.source_reads,
                )
            )
            try:
                source = tools.search(investigation)
            except BudgetExhausted as error:
                termination_reason = error.reason
                break
            except Exception as error:
                safe_message = _safe_error_message(error)
                failed_operations.append(
                    FailedOperation(
                        operation="search", message=safe_message
                    )
                )
                events.append(
                    ResearchEvent(
                        event="recoverable_failure",
                        searches_used=tools.searches,
                        source_reads_used=tools.source_reads,
                        detail=f"search: {type(error).__name__}",
                    )
                )
                continue
            events.append(
                ResearchEvent(
                    event="search_completed",
                    searches_used=tools.searches,
                    source_reads_used=tools.source_reads,
                    detail=_diagnostic_url(source.url),
                )
            )
            if any(item.source.url == source.url for item in evidence):
                continue
            events.append(
                ResearchEvent(
                    event="source_read_started",
                    searches_used=tools.searches,
                    source_reads_used=tools.source_reads,
                    detail=_diagnostic_url(source.url),
                )
            )
            try:
                content = tools.read(source)
            except BudgetExhausted as error:
                termination_reason = error.reason
                break
            except Exception as error:
                safe_message = _safe_error_message(error)
                failed_operations.append(
                    FailedOperation(
                        operation="Source read",
                        message=safe_message,
                        source=source,
                    )
                )
                events.append(
                    ResearchEvent(
                        event="recoverable_failure",
                        searches_used=tools.searches,
                        source_reads_used=tools.source_reads,
                        detail=(
                            f"Source read for {_diagnostic_url(source.url)}: "
                            f"{type(error).__name__}"
                        ),
                    )
                )
                continue
            events.append(
                ResearchEvent(
                    event="source_read_completed",
                    searches_used=tools.searches,
                    source_reads_used=tools.source_reads,
                    detail=_diagnostic_url(source.url),
                )
            )
            try:
                tools.ensure_time_remaining()
            except BudgetExhausted as error:
                termination_reason = error.reason
                break
            try:
                evidence_summary = self.model.summarize(
                    question, source, content
                ).strip()
                if not evidence_summary:
                    raise RuntimeError("Research model returned no Evidence")
            except Exception as error:
                safe_message = _safe_error_message(error)
                failed_operations.append(
                    FailedOperation(
                        operation="Evidence extraction",
                        message=safe_message,
                        source=source,
                    )
                )
                events.append(
                    ResearchEvent(
                        event="recoverable_failure",
                        searches_used=tools.searches,
                        source_reads_used=tools.source_reads,
                        detail=(
                            f"Evidence extraction for {_diagnostic_url(source.url)}: "
                            f"{type(error).__name__}"
                        ),
                    )
                )
                continue
            sources.append(source)
            evidence.append(Evidence(summary=evidence_summary, source=source))
            events.append(
                ResearchEvent(
                    event="evidence_collected",
                    searches_used=tools.searches,
                    source_reads_used=tools.source_reads,
                    detail=_diagnostic_url(source.url),
                )
            )
            try:
                tools.ensure_time_remaining()
            except BudgetExhausted as error:
                termination_reason = error.reason
                break

        evidence_tuple = tuple(evidence)
        if evidence_tuple and termination_reason == TerminationReason.ANSWERED:
            try:
                tools.ensure_time_remaining()
                events.append(
                    ResearchEvent(
                        event="synthesis_started",
                        searches_used=tools.searches,
                        source_reads_used=tools.source_reads,
                    )
                )
                synthesis = _normalize_synthesis(
                    self.model.synthesize(question, evidence_tuple)
                )
                tools.ensure_time_remaining()
                _validate_synthesis(synthesis, len(evidence_tuple))
                events.append(
                    ResearchEvent(
                        event="synthesis_completed",
                        searches_used=tools.searches,
                        source_reads_used=tools.source_reads,
                    )
                )
            except BudgetExhausted as error:
                termination_reason = error.reason
                synthesis = _partial_synthesis(evidence_tuple, termination_reason)
            except Exception as error:
                safe_message = _safe_error_message(error)
                failed_operations.append(
                    FailedOperation(
                        operation="Research synthesis",
                        message=safe_message,
                    )
                )
                events.append(
                    ResearchEvent(
                        event="recoverable_failure",
                        searches_used=tools.searches,
                        source_reads_used=tools.source_reads,
                        detail=f"Research synthesis: {type(error).__name__}",
                    )
                )
                termination_reason = TerminationReason.RECOVERABLE_FAILURES
                synthesis = _partial_synthesis(evidence_tuple, termination_reason)
        else:
            synthesis = _partial_synthesis(evidence_tuple, termination_reason)
        if failed_operations:
            if termination_reason == TerminationReason.ANSWERED:
                termination_reason = TerminationReason.RECOVERABLE_FAILURES
            synthesis = replace(
                synthesis,
                gaps=synthesis.gaps
                + ("Some Sources could not be searched, accessed, or parsed.",),
                uncertainty=synthesis.uncertainty
                + ("Coverage is limited by failed research operations.",),
            )
        evidence_text = "\n\n".join(
            f"{item.summary} [{index}]"
            for index, item in enumerate(evidence_tuple, 1)
        ) or "No findings were collected."
        plan_text = "\n".join(f"- {item}" for item in research_plan) or "- None"
        sources_text = "\n".join(
            f"[{index}] {source.url}" for index, source in enumerate(sources, 1)
        ) or "None"
        if not evidence_tuple:
            outcome = ResearchOutcome.FAILED
        elif termination_reason == TerminationReason.ANSWERED:
            outcome = ResearchOutcome.COMPLETE
        else:
            outcome = ResearchOutcome.PARTIAL
        events.append(
            ResearchEvent(
                event="research_finished",
                searches_used=tools.searches,
                source_reads_used=tools.source_reads,
                detail=f"{outcome.value}: {termination_reason.value}",
            )
        )
        return ResearchResult(
            report=(
                "# Research Report\n\n"
                f"## Research Question\n\n{question}\n\n"
                f"## Research Plan\n\n{plan_text}\n\n"
                f"## Answer\n\n{synthesis.answer}\n\n"
                "## Conflicting Evidence\n\n"
                f"{_render_items(synthesis.conflicts)}\n\n"
                "## Evidence Gaps\n\n"
                f"{_render_items(synthesis.gaps, label='Unverified gap')}\n\n"
                "## Uncertainty\n\n"
                f"{_render_items(synthesis.uncertainty, label='Synthesis limitation')}\n\n"
                "## Failed Operations\n\n"
                f"{_render_failures(tuple(failed_operations))}\n\n"
                f"## Evidence\n\n{evidence_text}\n\n"
                f"## Outcome\n\n{outcome.value}\n\n"
                f"## Termination Reason\n\n{termination_reason.value}\n\n"
                f"## Sources\n\n{sources_text}\n"
            ),
            sources=tuple(sources),
            evidence=evidence_tuple,
            research_plan=tuple(research_plan),
            termination_reason=termination_reason,
            failed_operations=tuple(failed_operations),
            outcome=outcome,
            events=tuple(events),
        )


def _validate_citations(answer: str, source_count: int) -> None:
    citations = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    if not citations:
        raise RuntimeError("Research Report answer contains no Source citations")
    orphaned = sorted(
        {citation for citation in citations if citation < 1 or citation > source_count}
    )
    if orphaned:
        raise RuntimeError(
            f"Research Report answer contains orphaned citations: {orphaned}"
        )
    uncited_statements = [
        statement
        for statement in re.split(r"(?<=[.!?])\s+|\n+", answer)
        if statement.strip() and not re.search(r"\[\d+\]", statement)
    ]
    if uncited_statements:
        raise RuntimeError("Research Report answer contains uncited statements")
    if source_count >= 2 and len(set(citations)) < 2:
        raise RuntimeError(
            "Research Report answer does not synthesize multiple Sources"
        )


def _validate_synthesis(synthesis: ResearchSynthesis, source_count: int) -> None:
    _validate_citations(synthesis.answer, source_count)
    for conflict in synthesis.conflicts:
        _validate_citations(conflict, source_count)


def _normalize_synthesis(value: ResearchSynthesis | str) -> ResearchSynthesis:
    if isinstance(value, ResearchSynthesis):
        return value
    return ResearchSynthesis(answer=value.strip())


def _partial_synthesis(
    evidence: tuple[Evidence, ...], termination_reason: TerminationReason
) -> ResearchSynthesis:
    return ResearchSynthesis(
        answer=_evidence_only_answer(evidence),
        gaps=(f"Research ended with status: {termination_reason.value}.",),
        uncertainty=("The available Evidence may be incomplete.",),
    )


def _render_items(items: tuple[str, ...], *, label: str | None = None) -> str:
    prefix = f"{label}: " if label else ""
    return "\n".join(f"- {prefix}{item}" for item in items) or "None identified."


def _render_failures(failures: tuple[FailedOperation, ...]) -> str:
    if not failures:
        return "None."
    return "\n".join(
        f"- {failure.operation}"
        f"{f' for {failure.source.url}' if failure.source else ''}: "
        f"{failure.message}"
        for failure in failures
    )


def _safe_error_message(error: Exception) -> str:
    message = str(error)
    for name in ("OPENAI_API_KEY", "TAVILY_API_KEY"):
        secret = environ.get(name)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def _diagnostic_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _evidence_only_answer(evidence: tuple[Evidence, ...]) -> str:
    return " ".join(
        f"{item.summary} [{index}]" for index, item in enumerate(evidence, 1)
    ) or "No supported answer could be established."


@dataclass(frozen=True)
class SingleSourceResearchEngine:
    model: ReportModel
    search: WebSearch
    source_reader: SourceReader

    def research(
        self,
        question: str,
        budget: ResearchBudget = ResearchBudget(),
        on_event: ProgressCallback | None = None,
    ) -> ResearchResult:
        events = _ResearchEventLog(on_event)
        events.append(ResearchEvent(event="research_started"))
        source = self.search.search(question)
        events.append(
            ResearchEvent(
                event="search_completed",
                searches_used=1,
                detail=_diagnostic_url(source.url),
            )
        )
        content = self.source_reader.read(source)
        events.append(
            ResearchEvent(
                event="source_read_completed",
                searches_used=1,
                source_reads_used=1,
                detail=_diagnostic_url(source.url),
            )
        )
        findings = self.model.summarize(question, source, content).strip()
        if not findings:
            raise RuntimeError("Research model returned no findings")
        events.append(
            ResearchEvent(
                event="research_finished",
                searches_used=1,
                source_reads_used=1,
                detail="complete: Research Question sufficiently answered",
            )
        )
        return ResearchResult(
            report=(
                "# Research Report\n\n"
                f"## Research Question\n\n{question}\n\n"
                f"## Findings\n\n{findings} [1]\n\n"
                f"## Sources\n\n[1] {source.url}\n"
            ),
            sources=(source,),
            events=tuple(events),
        )


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class DeepAgentResearchPlanner:
    model_name: str
    api_key: str
    base_url: str | None = None
    reasoning_effort: str = "none"

    def next_investigation(
        self,
        question: str,
        research_plan: tuple[str, ...],
        evidence_summaries: tuple[str, ...],
    ) -> str | None:
        from deepagents import create_deep_agent
        from langchain_openai import ChatOpenAI

        agent = create_deep_agent(
            model=ChatOpenAI(
                model=self.model_name,
                api_key=lambda: self.api_key,
                base_url=self.base_url,
                reasoning_effort=self.reasoning_effort,
            ),
            tools=[],
            system_prompt=(
                "Maintain an evolving Research Plan. Return one focused public-web "
                "search investigation that addresses the most important remaining "
                "Evidence gap, or exactly COMPLETE when the Research Question is "
                "sufficiently answered. Your response is passed directly to a separate "
                "web search tool, so return exactly one plain-text, single-line search "
                "query of at most 400 characters. Do not include explanations, bullets, "
                "or a list of URLs. Do not make factual claims from model memory."
                f"{_response_language_instruction(question)}"
            ),
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Research Question: {question}\n\n"
                            f"Research Plan so far: {list(research_plan)}\n\n"
                            f"Evidence summaries so far: {list(evidence_summaries)}"
                        ),
                    }
                ]
            }
        )
        message = result["messages"][-1]
        text = message.content if hasattr(message, "content") else message["content"]
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Deep Agent returned no Research Plan update")
        investigation = text.strip()
        return None if investigation == "COMPLETE" else investigation


@dataclass(frozen=True)
class TavilyWebSearch:
    api_key: str

    def search(self, question: str) -> Source:
        from tavily import TavilyClient

        response = TavilyClient(api_key=self.api_key).search(
            _normalize_search_query(question),
            max_results=5,
            search_depth="advanced",
        )
        results = response.get("results", [])
        if not results:
            raise NoUsefulSources("Web search returned no useful public Sources")
        result = max(
            enumerate(results),
            key=lambda item: _source_rank(item[1], item[0]),
        )[1]
        return Source(title=result.get("title") or result["url"], url=result["url"])


def _normalize_search_query(query: str, *, fallback: str | None = None) -> str:
    normalized = " ".join(query.split())
    if len(normalized) <= MAX_SEARCH_QUERY_CHARACTERS:
        return normalized
    if fallback is not None:
        normalized = " ".join(fallback.split())
    return normalized[:MAX_SEARCH_QUERY_CHARACTERS].rstrip()


def _authority_score(result: dict) -> int:
    parsed = urlsplit(result["url"])
    hostname = (parsed.hostname or "").lower()
    title = (result.get("title") or "").lower()
    score = 0
    primary_hosts = {
        "europa.eu",
        "ietf.org",
        "iso.org",
        "un.org",
        "w3.org",
        "who.int",
    }
    if hostname in primary_hosts or any(hostname.endswith(f".{host}") for host in primary_hosts):
        score += 5
    if hostname.endswith((".gov", ".edu")) or ".gov." in hostname or ".ac." in hostname:
        score += 4
    if hostname.startswith(("docs.", "developer.")):
        score += 3
    if any(term in title for term in ("official", "documentation", "specification")):
        score += 2
    return score


def _source_rank(result: dict, index: int) -> float:
    relevance = result.get("score")
    if not isinstance(relevance, (int, float)):
        relevance = 1.0 - (index * 0.1)
    return float(relevance) + min(_authority_score(result), 5) * 0.01


def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Source must use a public HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Source URL must not contain user credentials")
    try:
        address = ip_address(parsed.hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Source must use a public network address")


@dataclass(frozen=True)
class TavilySourceReader:
    api_key: str

    def read(self, source: Source) -> str:
        _validate_public_url(source.url)
        from tavily import TavilyClient

        response = TavilyClient(api_key=self.api_key).extract(
            source.url,
            extract_depth="advanced",
            format="markdown",
        )
        results = response.get("results", [])
        content = results[0].get("raw_content", "") if results else ""
        if not content:
            raise RuntimeError(f"Source contained no readable text: {source.url}")
        if len(content.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise RuntimeError(f"Source is larger than {MAX_SOURCE_BYTES} bytes")
        return content


@dataclass(frozen=True)
class DeepAgentReportModel:
    model_name: str
    api_key: str
    base_url: str | None = None
    reasoning_effort: str = "none"

    def summarize(self, question: str, source: Source, content: str) -> str:
        from deepagents import create_deep_agent
        from langchain_openai import ChatOpenAI

        chat_model = ChatOpenAI(
            model=self.model_name,
            api_key=lambda: self.api_key,
            base_url=self.base_url,
            reasoning_effort=self.reasoning_effort,
        )

        agent = create_deep_agent(
            model=chat_model,
            tools=[],
            system_prompt=(
                "Summarize the supplied Source content to answer the Research "
                "Question. Return only concise findings, without a title, Sources "
                "section, or citation markers. Do not use model memory as Evidence."
                f"{_response_language_instruction(question)}"
            ),
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Research Question: {question}\n\n"
                            f"Source title: {source.title}\n"
                            f"Source URL: {source.url}\n\n"
                            f"Source content:\n{content[:MAX_MODEL_CHARACTERS]}"
                        ),
                    }
                ]
            }
        )
        message = result["messages"][-1]
        text = message.content if hasattr(message, "content") else message["content"]
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Deep Agent returned no findings")
        return text.strip()

    def synthesize(
        self, question: str, evidence: tuple[Evidence, ...]
    ) -> ResearchSynthesis:
        from deepagents import create_deep_agent
        from langchain_openai import ChatOpenAI

        agent = create_deep_agent(
            model=ChatOpenAI(
                model=self.model_name,
                api_key=lambda: self.api_key,
                base_url=self.base_url,
                reasoning_effort=self.reasoning_effort,
            ),
            tools=[],
            system_prompt=(
                "Answer the Research Question using only supplied Evidence. Return "
                "JSON with string field answer and string-array fields conflicts, "
                "gaps, and uncertainty. Cite every sourced factual statement with "
                "[n]. Put Source disagreements in conflicts; unsupported conclusions "
                "in gaps; and synthesis limitations in uncertainty."
                f"{_response_language_instruction(question)}"
            ),
        )
        numbered_evidence = "\n\n".join(
            f"[{index}] {item.summary}\nSource: {item.source.url}"
            for index, item in enumerate(evidence, 1)
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Research Question: {question}\n\n"
                            f"Evidence:\n{numbered_evidence}"
                        ),
                    }
                ]
            }
        )
        message = result["messages"][-1]
        text = message.content if hasattr(message, "content") else message["content"]
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Deep Agent returned no Research Report answer")
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise TypeError
            answer = payload.get("answer")
            conflicts = payload.get("conflicts", [])
            gaps = payload.get("gaps", [])
            uncertainty = payload.get("uncertainty", [])
            if not isinstance(answer, str) or not answer.strip():
                raise TypeError
            if not all(
                isinstance(items, list)
                and all(isinstance(item, str) for item in items)
                for items in (conflicts, gaps, uncertainty)
            ):
                raise TypeError
            return ResearchSynthesis(
                answer=answer.strip(),
                conflicts=tuple(conflicts),
                gaps=tuple(gaps),
                uncertainty=tuple(uncertainty),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Deep Agent returned invalid Research synthesis JSON") from error


def build_live_research_engine() -> PlannedResearchEngine:
    openai_api_key = environ.get("OPENAI_API_KEY")
    tavily_api_key = environ.get("TAVILY_API_KEY")
    if openai_api_key is None or tavily_api_key is None:
        missing = [
            name
            for name, value in (
                ("OPENAI_API_KEY", openai_api_key),
                ("TAVILY_API_KEY", tavily_api_key),
            )
            if not value or not value.strip()
        ]
        raise ConfigurationError(
            f"missing required configuration: {', '.join(missing)}"
        )
    if not openai_api_key.strip() or not tavily_api_key.strip():
        missing = [
            name
            for name, value in (
                ("OPENAI_API_KEY", openai_api_key),
                ("TAVILY_API_KEY", tavily_api_key),
            )
            if not value.strip()
        ]
        raise ConfigurationError(
            f"missing required configuration: {', '.join(missing)}"
        )

    model_name = environ.get("DEEP_RESEARCH_MODEL", "gpt-5.6-sol")
    base_url = environ.get("OPENAI_BASE_URL")
    reasoning_effort = environ.get("OPENAI_REASONING_EFFORT", "none")
    if not model_name.strip():
        raise ConfigurationError("DEEP_RESEARCH_MODEL must not be blank")
    if base_url:
        parsed_base_url = urlsplit(base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ConfigurationError(
                "OPENAI_BASE_URL must be an HTTP or HTTPS provider URL"
            )
    allowed_reasoning_efforts = {"none", "minimal", "low", "medium", "high"}
    if reasoning_effort not in allowed_reasoning_efforts:
        raise ConfigurationError(
            "OPENAI_REASONING_EFFORT must be one of: "
            + ", ".join(sorted(allowed_reasoning_efforts))
        )
    return PlannedResearchEngine(
        planner=DeepAgentResearchPlanner(
            model_name=model_name,
            api_key=openai_api_key,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
        ),
        model=DeepAgentReportModel(
            model_name=model_name,
            api_key=openai_api_key,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
        ),
        search=TavilyWebSearch(api_key=tavily_api_key),
        source_reader=TavilySourceReader(api_key=tavily_api_key),
    )
