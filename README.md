# Deep Research Agent

[简体中文](README.zh-Hans.md)

A CLI research agent that turns a Research Question into an HTML Research Report, a Markdown source report, and structured Source metadata.

The current implementation uses LangChain Deep Agents with an OpenAI-compatible model API and [Tavily](https://www.tavily.com/) for web search and Source extraction.

## Requirements

Python 3.11 or later

## Installation

Create a virtual environment and install the project in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Usage

### Configure API access

**Recommended: use a `.env` file** (configure once, works across sessions):

```bash
cp .env.example .env
```

Edit `.env` with your own values, or run the interactive setup:

```bash
deep-research --setup
```

**Alternative: export in the current terminal session** (affects only this session):

```bash
export OPENAI_API_KEY="your-openai-compatible-api-key"
export OPENAI_BASE_URL="https://your-openai-compatible-provider.example/v1"
export OPENAI_REASONING_EFFORT="none"
export TAVILY_API_KEY="your-tavily-api-key"
```

`OPENAI_BASE_URL` is optional when using OpenAI's official API, but required for most OpenAI-compatible providers.

`OPENAI_REASONING_EFFORT` defaults to `none`. Keep this value when an OpenAI-compatible provider does not support function tools together with reasoning on `/v1/chat/completions`.

The default model is `gpt-5.6-sol`. Override it when your provider uses a different model name:

```bash
export DEEP_RESEARCH_MODEL="your-provider-model-name"
```

Confirm that the variables exist without printing their secret values:

```bash
test -n "$OPENAI_API_KEY" && echo "OPENAI_API_KEY configured"
test -n "$OPENAI_BASE_URL" && echo "OPENAI_BASE_URL configured"
test -n "$OPENAI_REASONING_EFFORT" && echo "OPENAI_REASONING_EFFORT configured"
test -n "$TAVILY_API_KEY" && echo "TAVILY_API_KEY configured"
```

These `export` commands affect only the current terminal session.

### Run research

Run a research question from the command line:

```bash
deep-research "What is the history of W3C?"
```

By default, the command writes four files to `research-output/`:

- `report.html`: the primary HTML Research Report
- `report.md`: the same report as Markdown source
- `sources.json`: structured metadata for the Sources used by the report
- `diagnostics.jsonl`: structured stage, budget, failure, and termination events

Open `report.html` directly in a browser. It is a self-contained file with no server
or external assets required. The page includes responsive section navigation,
Source links, citation jumps, status metadata, and print styles.

Choose a different output directory with `--output-dir`:

```bash
deep-research "What is W3C?" --output-dir ./output/w3c
```

Each run uses a conservative Research Budget: at most 3 searches, 3 Source reads,
and 120 elapsed seconds. Override those limits when needed:

```bash
deep-research "Compare LangChain and LangGraph" \
  --max-searches 5 \
  --max-source-reads 5 \
  --max-elapsed-seconds 180
```

Budget values must be positive. The Research Report records the evolving Research
Plan and whether the run stopped because the question was sufficiently answered or
a search, Source-read, or elapsed-time limit was exhausted.

Complete research exits with status `0`. A budget-limited run that retained usable
Sources writes partial HTML and Markdown Research Reports and exits with status `3`;
a run stopped before collecting a usable Source exits with status `1`.

Each report records an explicit `complete`, `partial`, or `failed` Outcome. Partial
reports preserve collected Evidence and include the termination reason, failed
operations, Evidence gaps, and uncertainty. Recoverable search, Source-reading,
Evidence-extraction, or synthesis failures do not discard usable work.

Completed reports contain a direct `Answer`, numbered Evidence summaries, and a
numbered Source list. Answer citations such as `[1]` are validated before a completed
report is accepted. Missing, orphaned, or incomplete citations cause the synthesized
answer to be discarded while collected Evidence is preserved in a partial report.
Search considers several candidates and prefers official documentation, government,
and educational Sources when they are available.

Reports separate the direct Answer from Conflicting Evidence, Evidence Gaps, and
Uncertainty. Search or Source-reading failures that materially limit coverage are
listed under Failed Operations with the affected public URL when known. Unsupported
statements cannot appear as verified Evidence because completed Answer and conflict
statements must carry valid Source citations.

### Configuration reference

| Setting | Required | Default | Validation |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Live runs | None | Must be non-blank |
| `TAVILY_API_KEY` | Live runs | None | Must be non-blank |
| `OPENAI_BASE_URL` | No | OpenAI default | HTTP or HTTPS provider URL |
| `OPENAI_REASONING_EFFORT` | No | `none` | `none`, `minimal`, `low`, `medium`, or `high` |
| `DEEP_RESEARCH_MODEL` | No | `gpt-5.6-sol` | Must be non-blank |
| `--max-searches` | No | `3` | Positive integer |
| `--max-source-reads` | No | `3` | Positive integer |
| `--max-elapsed-seconds` | No | `120` | Positive finite number |

`diagnostics.jsonl` records major stages, external operation counts, safe failure
messages, and the final termination reason. It does not include Source body text, and
configured provider credentials are redacted from recoverable failure messages.

## Development

Run the test suite with the Python standard library:

```bash
python -m unittest discover -s tests
```

Run the opt-in live smoke test only after configuring all provider variables:

```bash
RUN_LIVE_RESEARCH_TEST=1 python -m unittest discover -s tests -p 'test_live.py' -v
```

The default test suite does not call external services. The live smoke test consumes model and Tavily API usage.

The package uses a `src/` layout:

```text
src/deep_research_agent/
├── __main__.py
├── cli.py
└── research.py
```

The research implementation exposes separate model, search, and Source-reading boundaries so deterministic tests can exercise the CLI without external API calls.
