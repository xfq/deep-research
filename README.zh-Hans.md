# Deep Research Agent

[English](README.md)

一个CLI版的研究智能体，将研究问题转化为HTML版的研究报告、Markdown源报告和结构化的Source元数据。

当前实现使用LangChain Deep Agents，搭配OpenAI兼容模型API和Tavily进行网络搜索与Source提取。

## 环境要求

Python 3.11或更高版本

## 安装

创建虚拟环境并以可编辑模式安装项目：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## 使用方法

### 配置API访问

在当前终端会话中设置凭据。请将占位符替换为你自己的值：

```bash
export OPENAI_API_KEY="your-openai-compatible-api-key"
export OPENAI_BASE_URL="https://your-openai-compatible-provider.example/v1"
export OPENAI_REASONING_EFFORT="none"
export TAVILY_API_KEY="your-tavily-api-key"
```

使用OpenAI官方API时 `OPENAI_BASE_URL` 为可选项，但大多数OpenAI兼容提供商需要设置此项。

`OPENAI_REASONING_EFFORT` 默认为 `none`。当OpenAI兼容提供商在 `/v1/chat/completions` 上不支持function tools与reasoning同时使用时，请保持此值。

默认模型为 `gpt-5.6-sol`。如果你的提供商使用不同的模型名称，可通过以下方式覆盖：

```bash
export DEEP_RESEARCH_MODEL="your-provider-model-name"
```

确认变量已存在但不打印其密钥值：

```bash
test -n "$OPENAI_API_KEY" && echo "OPENAI_API_KEY configured"
test -n "$OPENAI_BASE_URL" && echo "OPENAI_BASE_URL configured"
test -n "$OPENAI_REASONING_EFFORT" && echo "OPENAI_REASONING_EFFORT configured"
test -n "$TAVILY_API_KEY" && echo "TAVILY_API_KEY configured"
```

这些 `export` 命令仅影响当前终端会话。

### 运行研究

从命令行运行研究问题：

```bash
deep-research "What is W3C?"
```

默认情况下，命令会将四个文件写入 `research-output/`：

- `report.html`：主要的HTML研究报告
- `report.md`：Markdown源报告
- `sources.json`：报告所用Sources的结构化元数据
- `diagnostics.jsonl`：结构化的阶段、预算、失败和终止事件记录

直接在浏览器中打开 `report.html`。它是一个自包含文件，无需服务器或外部资源。页面包含响应式章节导航、Source链接、引用跳转、状态元数据和打印样式。

使用 `--output-dir` 选择不同的输出目录：

```bash
deep-research "W3C是什么？" --output-dir ./output/w3c
```

每次运行使用保守的研究预算：最多3次搜索、3次Source读取和120秒耗时。需要时可覆盖这些限制：

```bash
deep-research "Compare LangChain and LangGraph" \
  --max-searches 5 \
  --max-source-reads 5 \
  --max-elapsed-seconds 180
```

预算值必须为正数。研究报告会记录不断演进的研究计划，以及运行是因问题得到充分回答而停止，还是因搜索、Source读取或耗时限制耗尽而终止。

完整研究以状态码 `0` 退出。预算受限但保留了可用Sources的运行会写入不完整的HTML和Markdown研究报告，并以状态码 `3` 退出；在收集到可用Source之前就被终止的运行以状态码 `1` 退出。

每份报告都记录明确的 `complete`、`partial` 或 `failed` Outcome。不完整报告保留已收集的Evidence，并包含终止原因、失败操作、Evidence缺口和不确定性。可恢复的搜索、Source读取、Evidence提取或综合失败不会丢弃可用工作成果。

完整报告包含直接的 `Answer`、编号的Evidence摘要和编号的Source列表。Answer中的引用（如 `[1]`）在完整报告被接受前会经过验证。缺失、孤立或不完整的引用会导致综合回答被丢弃，但已收集的Evidence会保留在不完整报告中。搜索会考虑多个候选项，并在可用时优先选择官方文档、政府和教育类Sources。

报告将直接Answer与冲突Evidence、Evidence缺口和不确定性分开呈现。对覆盖范围有实质性影响的搜索或Source读取失败会列在 Failed Operations下，并附上已知的受影响公开URL。不受支持的陈述不能作为已验证的Evidence出现，因为完整的Answer和冲突陈述必须带有有效的Source引用。

### 配置参考

| 设置 | 是否必需 | 默认值 | 验证 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 正式运行时 | 无 | 必须非空 |
| `TAVILY_API_KEY` | 正式运行时 | 无 | 必须非空 |
| `OPENAI_BASE_URL` | 否 | OpenAI 默认 | HTTP 或 HTTPS 提供商 URL |
| `OPENAI_REASONING_EFFORT` | 否 | `none` | `none`、`minimal`、`low`、`medium` 或 `high` |
| `DEEP_RESEARCH_MODEL` | 否 | `gpt-5.6-sol` | 必须非空 |
| `--max-searches` | 否 | `3` | 正整数 |
| `--max-source-reads` | 否 | `3` | 正整数 |
| `--max-elapsed-seconds` | 否 | `120` | 正有限数 |

`diagnostics.jsonl` 记录主要阶段、外部操作计数、安全的失败消息以及最终终止原因。它不包含 Source 正文文本，且配置的提供商凭据在可恢复的失败消息中会被脱敏处理。

## 开发

使用Python标准库运行测试套件：

```bash
python -m unittest discover -s tests
```

仅在配置好所有提供商变量后运行可选的在线冒烟测试：

```bash
RUN_LIVE_RESEARCH_TEST=1 python -m unittest discover -s tests -p 'test_live.py' -v
```

默认测试套件不会调用外部服务。在线冒烟测试会消耗模型和 Tavily API 用量。

本包使用 `src/` 布局：

```text
src/deep_research_agent/
├── __main__.py
├── cli.py
└── research.py
```

研究实现暴露了独立的model、search和Source-reading边界，使得确定性测试可以在不调用外部API的情况下测试CLI。
