# Development Guide

## Project Overview

A CLI research agent that investigates questions against public web sources and produces evidence-backed research reports. Built with [LangChain Deep Agents](https://github.com/langchain-ai/deepagents) as the LLM reasoning layer and [Tavily](https://tavily.com) for web search and content extraction.

**Python code orchestrates, LLMs reason.** The agentic loop is a deterministic Python `while` loop.

## Configuration

Environment variables (loaded from `.env` or `~/.deep-research/.env`):

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes | — | LLM API key (OpenAI-compatible) |
| `TAVILY_API_KEY` | Yes | — | Tavily search API key |
| `DEEP_RESEARCH_MODEL` | No | `gpt-5.6-sol` | Model name |
| `OPENAI_BASE_URL` | No | — | Custom provider base URL |
| `OPENAI_REASONING_EFFORT` | No | `none` | One of: `none`, `minimal`, `low`, `medium`, `high` |
| `DEEP_RESEARCH_SKIP_DOTENV` | No | — | Skip `.env` loading when set |

## Research Depth Presets

| Preset | Searches | Reads | Time |
|--------|----------|-------|------|
| `quick` | 2 | 2 | 60 s |
| `standard` | 3 | 3 | 120 s |
| `deep` | 8 | 8 | 300 s |

Research stops early when the planner returns `"COMPLETE"`, regardless of remaining budget.
