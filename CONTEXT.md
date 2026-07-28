# Deep Research Agent

This context describes a local research agent that investigates questions against public web sources and produces evidence-backed reports.

## Language

**Research Question**:
The user's question that defines the subject and intended outcome of one research run.
_Avoid_: Prompt, query

**Research Plan**:
The agent's evolving decomposition of a Research Question into focused investigations.
_Avoid_: Task list, chain of thought

**Source**:
A publicly accessible web resource used as evidence during a research run.
_Avoid_: Document, context

**Evidence**:
Information extracted from a Source and retained with enough provenance to support or challenge a claim.
_Avoid_: Fact, snippet

**Research Report**:
The Markdown deliverable that answers a Research Question and connects key claims to Sources.
_Avoid_: Response, summary

**Research Budget**:
The configured limits on searches, Source reads, and elapsed time for one research run.
_Avoid_: Token budget, quota

**Research Depth**:
The user-facing `quick`, `standard`, or `deep` preset that selects a Research Budget while allowing the agent to stop early when the Research Question is sufficiently answered.
_Avoid_: Search count, iteration count
