from dataclasses import dataclass
from html import escape
import re
from urllib.parse import urlsplit

from deep_research_agent.localization import should_use_simplified_chinese
from deep_research_agent.research import ResearchOutcome, Source, TerminationReason


_CITATION_PATTERN = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\((https?://[^\s)]+)\)|\[(\d+)\]")
_HEADING_PATTERN = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_ORDERED_ITEM_PATTERN = re.compile(r"^\d+\.\s+(.+)$")
_UNORDERED_ITEM_PATTERN = re.compile(r"^[-*]\s+(.+)$")
_OMITTED_SECTIONS = {
    "research question",
    "outcome",
    "termination reason",
    "sources",
}
_PRIMARY_ANSWER_SECTIONS = {"answer", "findings"}
_ZH_SECTION_TITLES = {
    "answer": "回答",
    "conflicting evidence": "冲突证据",
    "evidence": "证据",
    "evidence gaps": "证据缺口",
    "failed operations": "失败操作",
    "findings": "研究结果",
    "report": "报告",
    "report details": "报告详情",
    "research plan": "研究计划",
    "sources": "来源",
    "uncertainty": "不确定性",
}
_ZH_TERMINATION_REASONS = {
    TerminationReason.ANSWERED.value: "研究问题已得到充分回答",
    TerminationReason.SEARCH_LIMIT.value: "搜索次数已用尽",
    TerminationReason.SOURCE_READ_LIMIT.value: "来源读取次数已用尽",
    TerminationReason.ELAPSED_TIME_LIMIT.value: "研究时间已用尽",
    TerminationReason.RECOVERABLE_FAILURES.value: "研究完成，但出现了可恢复的失败",
    "Unexpected research execution failure.": "研究执行过程中发生意外错误。",
}
_ZH_BODY_TEXT = {
    "Coverage is limited by failed research operations.": (
        "研究覆盖范围受到失败操作的限制。"
    ),
    "No findings were collected.": "未收集到研究结果。",
    "No supported answer could be established.": "未能得到有来源支持的答案。",
    "None": "无",
    "None identified.": "未发现。",
    "None.": "无。",
    "Some Sources could not be searched, accessed, or parsed.": (
        "部分来源无法搜索、访问或解析。"
    ),
    "The available Evidence may be incomplete.": "现有证据可能不完整。",
}


@dataclass(frozen=True)
class _Section:
    title: str
    slug: str
    lines: tuple[str, ...]


def render_report_html(
    report: str,
    *,
    question: str,
    sources: tuple[Source, ...],
    outcome: ResearchOutcome,
    termination_reason: TerminationReason | str,
) -> str:
    simplified_chinese = should_use_simplified_chinese(question)
    sections = _parse_sections(report)
    primary_sections = tuple(
        section
        for section in sections
        if section.title.casefold() in _PRIMARY_ANSWER_SECTIONS
    )
    secondary_sections = tuple(
        section
        for section in sections
        if section.title.casefold() not in _PRIMARY_ANSWER_SECTIONS
    )
    source_section = _render_sources(sources, simplified_chinese=simplified_chinese)
    primary_navigation_items = [
        f'<li class="report-nav__item--primary">'
        f'<a href="#{escape(section.slug, quote=True)}">'
        f"{escape(_section_title(section.title, simplified_chinese))}</a></li>"
        for section in primary_sections
    ]
    secondary_navigation_items = [
        f'<li><a href="#{escape(section.slug, quote=True)}">'
        f"{escape(_section_title(section.title, simplified_chinese))}</a></li>"
        for section in secondary_sections
    ]
    sources_title = _section_title("Sources", simplified_chinese)
    source_navigation_item = (
        '<li class="report-nav__item--primary">'
        f'<a href="#sources">{escape(sources_title)}</a></li>'
    )
    if primary_sections:
        navigation_items = [
            *primary_navigation_items,
            source_navigation_item,
            *secondary_navigation_items,
        ]
        content_parts = [
            *(
                _render_section(section, simplified_chinese=simplified_chinese)
                for section in primary_sections
            ),
            source_section,
        ]
        if secondary_sections:
            secondary_content = "\n".join(
                _render_section(section, simplified_chinese=simplified_chinese)
                for section in secondary_sections
            )
            content_parts.append(
                f'<div class="report-secondary">\n{secondary_content}\n</div>'
            )
        content = "\n".join(content_parts)
    else:
        navigation_items = [*secondary_navigation_items, source_navigation_item]
        content = "\n".join(
            [
                *(
                    _render_section(section, simplified_chinese=simplified_chinese)
                    for section in secondary_sections
                ),
                source_section,
            ]
        )
    language = "zh-Hans" if simplified_chinese else "en"
    outcome_value = outcome.value
    outcome_label = (
        {
            ResearchOutcome.COMPLETE: "完整",
            ResearchOutcome.PARTIAL: "部分完成",
            ResearchOutcome.FAILED: "失败",
        }[outcome]
        if simplified_chinese
        else {
            ResearchOutcome.COMPLETE: "Complete",
            ResearchOutcome.PARTIAL: "Partial",
            ResearchOutcome.FAILED: "Failed",
        }[outcome]
    )
    reason = (
        termination_reason.value
        if isinstance(termination_reason, TerminationReason)
        else str(termination_reason)
    )
    if simplified_chinese:
        reason = _ZH_TERMINATION_REASONS.get(reason, reason)
        source_count = f"{len(sources)} 个来源"
        title_suffix = "深度研究"
        skip_link = "跳到报告正文"
        report_kicker = "深度研究报告"
        metadata_label = "报告元数据"
        navigation_label = "报告章节"
        contents_label = "目录"
    else:
        source_label = "source" if len(sources) == 1 else "sources"
        source_count = f"{len(sources)} {source_label}"
        title_suffix = "Deep Research"
        skip_link = "Skip to report"
        report_kicker = "Deep Research Report"
        metadata_label = "Report metadata"
        navigation_label = "Report sections"
        contents_label = "Contents"

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>{escape(question)} | {title_suffix}</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: oklch(97.4% 0.009 83);
      --paper-raised: oklch(99.1% 0.006 83);
      --ink: oklch(24% 0.025 252);
      --muted: oklch(51% 0.025 252);
      --line: oklch(87% 0.018 83);
      --accent: oklch(52% 0.13 252);
      --accent-soft: oklch(93% 0.025 252);
      --complete: oklch(49% 0.105 154);
      --complete-soft: oklch(93% 0.035 154);
      --partial: oklch(53% 0.125 71);
      --partial-soft: oklch(94% 0.045 82);
      --failed: oklch(50% 0.15 27);
      --failed-soft: oklch(94% 0.035 27);
      --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --serif: ui-serif, "Iowan Old Style", "Palatino Linotype",
        "Noto Serif CJK SC", "Songti SC", serif;
      --report-body-size: clamp(1rem, 0.96rem + 0.18vw, 1.12rem);
    }}

    * {{ box-sizing: border-box; }}

    html {{
      scroll-behavior: smooth;
      scroll-padding-top: 2rem;
    }}

    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--serif);
      font-size: var(--report-body-size);
      line-height: 1.78;
      text-rendering: optimizeLegibility;
    }}

    a {{
      color: var(--accent);
      overflow-wrap: anywhere;
      text-decoration-thickness: 0.08em;
      text-underline-offset: 0.18em;
      transition:
        color 160ms cubic-bezier(0.22, 1, 0.36, 1),
        background-color 160ms cubic-bezier(0.22, 1, 0.36, 1);
    }}

    a:hover {{ text-decoration-thickness: 0.13em; }}

    a:active {{ color: color-mix(in oklch, var(--accent), var(--ink) 28%); }}

    a:focus-visible {{
      outline: 3px solid var(--accent);
      outline-offset: 4px;
      border-radius: 0.2rem;
    }}

    .skip-link {{
      position: fixed;
      inset: 0 auto auto 1rem;
      z-index: 10;
      padding: 0.7rem 1rem;
      background: var(--ink);
      color: var(--paper-raised);
      font: 700 0.9rem/1 var(--sans);
      transform: translateY(-120%);
    }}

    .skip-link:focus {{ transform: translateY(1rem); }}

    .report-header {{
      border-bottom: 1px solid var(--line);
      background: var(--paper-raised);
    }}

    .report-header__inner {{
      width: min(100% - 2.5rem, 76rem);
      margin-inline: auto;
      padding-block: clamp(2.75rem, 6vw, 5.5rem) clamp(2rem, 4vw, 3rem);
    }}

    .report-kicker {{
      margin: 0 0 0.9rem;
      color: var(--muted);
      font: 720 0.78rem/1.2 var(--sans);
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    h1, h2, h3 {{
      font-family: var(--sans);
      letter-spacing: -0.035em;
      overflow-wrap: anywhere;
      text-wrap: balance;
    }}

    h1 {{
      max-width: 22ch;
      margin: 0;
      font-size: clamp(2.35rem, 6vw, 5.5rem);
      font-weight: 760;
      line-height: 0.98;
    }}

    .report-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.7rem 1.5rem;
      align-items: center;
      margin-top: clamp(1.5rem, 3vw, 2.25rem);
      color: var(--muted);
      font: 720 0.82rem/1.45 var(--sans);
    }}

    .report-meta__reason {{
      color: var(--muted);
      font-weight: 720;
    }}

    .status {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.45rem 0.75rem;
      border-radius: 999px;
      font-weight: 720;
    }}

    .status::before {{
      width: 0.5rem;
      height: 0.5rem;
      border-radius: 50%;
      background: currentColor;
      content: "";
    }}

    .status--complete {{ color: var(--complete); background: var(--complete-soft); }}
    .status--partial {{ color: var(--partial); background: var(--partial-soft); }}
    .status--failed {{ color: var(--failed); background: var(--failed-soft); }}

    .report-shell {{
      display: grid;
      grid-template-columns: minmax(9rem, 11rem) minmax(0, 48rem);
      gap: clamp(2.5rem, 6vw, 6.5rem);
      width: min(100% - 2.5rem, 76rem);
      margin-inline: auto;
      padding-block: clamp(2.5rem, 5vw, 4.5rem) 8rem;
    }}

    .report-nav {{
      position: sticky;
      top: 2rem;
      align-self: start;
      font-family: var(--sans);
    }}

    .report-nav__title {{
      margin: 0 0 1rem;
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 720;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .report-nav ul {{
      display: grid;
      gap: 0.2rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }}

    .report-nav a {{
      display: block;
      padding: 0.42rem 0;
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 720;
      line-height: 1.35;
      text-decoration: none;
    }}

    .report-nav__item--primary a {{
      color: var(--ink);
      font-size: 0.88rem;
      font-weight: 720;
    }}

    .report-nav a:hover {{ color: var(--accent); }}

    .report-content {{ min-width: 0; overflow-wrap: anywhere; }}

    .report-section {{
      padding-block: 0 3.5rem;
      content-visibility: auto;
      contain-intrinsic-size: auto 32rem;
    }}

    .report-section h2 {{
      margin: 0 0 1.5rem;
      font-size: clamp(1.65rem, 2.4vw, 2.3rem);
      font-weight: 760;
      line-height: 1.08;
    }}

    .report-section h3 {{
      margin: 2rem 0 0.8rem;
      font-size: clamp(1.15rem, 1.5vw, 1.35rem);
      line-height: 1.25;
    }}

    .report-section p,
    .report-section li,
    .report-section blockquote {{
      text-wrap: pretty;
    }}

    .report-section p {{ margin: 0 0 1.25rem; }}

    .report-section--answer,
    .report-section--findings {{
      margin-bottom: 0;
      padding: clamp(1.6rem, 4vw, 2.4rem);
      border: 1px solid var(--line);
      border-radius: 0.8rem;
      background: var(--paper-raised);
      font-size: var(--report-body-size);
    }}

    .report-section--answer h2,
    .report-section--findings h2 {{
      margin-bottom: 1.1rem;
      font-size: clamp(1.65rem, 2.4vw, 2.3rem);
      line-height: 1.08;
    }}

    .report-section--answer > :last-child,
    .report-section--findings > :last-child {{ margin-bottom: 0; }}

    .report-section--sources {{
      padding-block: clamp(3.75rem, 7vw, 5.5rem) clamp(4rem, 7vw, 5.5rem);
    }}

    .report-section--sources h2 {{
      margin-bottom: 1.75rem;
      font-size: clamp(1.65rem, 2.4vw, 2.3rem);
    }}

    .report-secondary {{
      padding-top: clamp(2.5rem, 5vw, 4rem);
      border-top: 1px solid var(--line);
      color: color-mix(in oklch, var(--ink), var(--muted) 24%);
      font-size: 0.96em;
    }}

    .report-secondary .report-section {{ padding-bottom: 2.75rem; }}

    .report-secondary .report-section + .report-section {{
      padding-top: 2.75rem;
    }}

    .report-secondary .report-section h2 {{
      margin-bottom: 1.15rem;
      color: var(--muted);
      font-size: clamp(1.65rem, 2.4vw, 2.3rem);
      line-height: 1.08;
    }}

    .report-section--conflicting-evidence,
    .report-section--evidence-gaps,
    .report-section--uncertainty,
    .report-section--failed-operations {{
      margin-bottom: 3.5rem;
      padding: clamp(1.4rem, 3vw, 2rem);
      border: 1px solid color-mix(in oklch, var(--partial), transparent 58%);
      border-radius: 0.8rem;
      background: var(--partial-soft);
      color: var(--ink);
    }}

    ol, ul {{ padding-inline-start: 1.45rem; }}

    li {{ padding-inline-start: 0.35rem; margin-bottom: 0.7rem; }}

    blockquote {{
      margin: 1.5rem 0;
      padding: 1rem 1.2rem;
      border: 1px solid var(--line);
      border-radius: 0.6rem;
      background: var(--paper-raised);
    }}

    code {{
      padding: 0.12em 0.34em;
      border: 1px solid var(--line);
      border-radius: 0.3rem;
      background: var(--paper-raised);
      font: 0.88em/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
    }}

    pre {{
      max-width: 100%;
      overflow-x: auto;
      overflow-wrap: normal;
      padding: 1rem;
      border: 1px solid var(--line);
      border-radius: 0.6rem;
      background: var(--paper-raised);
    }}

    pre code {{ padding: 0; border: 0; background: transparent; }}

    .citation {{
      display: inline-grid;
      min-width: 1.45em;
      min-height: 1.45em;
      place-items: center;
      border-radius: 999px;
      background: var(--accent-soft);
      font: 720 0.72em/1 var(--sans);
      text-decoration: none;
      vertical-align: 0.12em;
    }}

    .source-list {{
      margin: 0;
      padding: 0;
      list-style: none;
      counter-reset: source;
    }}

    .source-list li {{
      counter-increment: source;
      margin: 0;
      padding: 0;
      border-top: 1px solid var(--line);
    }}

    .source-list li:last-child {{ border-bottom: 1px solid var(--line); }}

    .source-link,
    .source-static {{
      display: grid;
      grid-template-columns: 2.5rem minmax(0, 1fr) auto;
      gap: 1rem;
      align-items: center;
      padding: 1.35rem 0;
      color: var(--ink);
      font-family: var(--sans);
      text-decoration: none;
    }}

    .source-link::before,
    .source-static::before {{
      content: counter(source, decimal-leading-zero);
      display: grid;
      width: 2rem;
      height: 2rem;
      place-items: center;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.76rem;
      font-weight: 760;
    }}

    .source-title {{
      font-size: clamp(1rem, 0.97rem + 0.16vw, 1.1rem);
      font-weight: 720;
      line-height: 1.35;
    }}

    .source-domain {{
      display: block;
      margin-top: 0.25rem;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 520;
    }}

    .source-arrow {{ color: var(--muted); font-size: 1.1rem; }}

    .source-link:hover .source-title {{ color: var(--accent); }}

    @media (max-width: 760px) {{
      html {{ scroll-padding-top: 5rem; }}

      .report-header__inner,
      .report-shell {{ width: min(100% - 1.5rem, 48rem); }}

      .report-shell {{
        display: block;
        padding-top: 0;
      }}

      .report-nav {{
        z-index: 5;
        top: 0;
        margin-inline: -0.75rem;
        padding: 0.75rem;
        border-bottom: 1px solid var(--line);
        background: color-mix(in oklch, var(--paper), transparent 4%);
      }}

      .report-nav__title {{
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
      }}

      .report-nav ul {{
        display: flex;
        gap: 0.35rem;
        overflow-x: auto;
        scrollbar-width: thin;
        scrollbar-color: var(--line) transparent;
      }}

      .report-nav li {{ flex: 0 0 auto; margin: 0; padding: 0; }}

      .report-nav a {{
        display: flex;
        min-height: 2.75rem;
        align-items: center;
        padding: 0.48rem 0.72rem;
        border-radius: 999px;
        background: var(--paper-raised);
        font-size: 0.8rem;
      }}

      .report-content {{ padding-top: 3rem; }}

      .report-section--answer,
      .report-section--findings {{ padding: 1.4rem; }}

      .report-section--sources {{
        padding-block: 3.5rem 4rem;
      }}
    }}

    @media print {{
      :root {{ --paper: oklch(99% 0.003 83); --paper-raised: oklch(99% 0.003 83); }}
      body {{ font-size: 10.5pt; }}
      .skip-link, .report-nav {{ display: none; }}
      .report-header {{ background: transparent; }}
      .report-header__inner, .report-shell {{ width: 100%; }}
      .report-header__inner {{ padding: 0 0 2rem; }}
      .report-shell {{ display: block; padding: 2rem 0 0; }}
      .report-section {{ content-visibility: visible; break-inside: avoid; }}
      a {{ color: inherit; text-decoration: none; }}
    }}

    @media (prefers-reduced-motion: reduce) {{
      html {{ scroll-behavior: auto; }}
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">{skip_link}</a>
  <header class="report-header">
    <div class="report-header__inner">
      <p class="report-kicker">{report_kicker}</p>
      <h1>{escape(question)}</h1>
      <div class="report-meta" aria-label="{metadata_label}">
        <span class="status status--{outcome_value}">{outcome_label}</span>
        <span class="report-meta__source-count">{source_count}</span>
        <span class="report-meta__reason">{escape(reason)}</span>
      </div>
    </div>
  </header>
  <div class="report-shell">
    <nav class="report-nav" aria-label="{navigation_label}">
      <p class="report-nav__title">{contents_label}</p>
      <ul role="list">
        {''.join(navigation_items)}
      </ul>
    </nav>
    <main id="main-content" tabindex="-1">
      <article class="report-content">
        {content}
      </article>
    </main>
  </div>
</body>
</html>
"""


def _parse_sections(report: str) -> tuple[_Section, ...]:
    raw_sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in report.splitlines():
        heading = _HEADING_PATTERN.match(line)
        if heading and len(heading.group(1)) == 2:
            if current_title is not None:
                raw_sections.append((current_title, current_lines))
            current_title = heading.group(2).strip()
            current_lines = []
            continue
        if line.startswith("# "):
            continue
        if current_title is None:
            if line.strip():
                current_title = "Report"
                current_lines.append(line)
            continue
        current_lines.append(line)

    if current_title is not None:
        raw_sections.append((current_title, current_lines))

    slugs: dict[str, int] = {}
    sections: list[_Section] = []
    for title, lines in raw_sections:
        if title.casefold() in _OMITTED_SECTIONS:
            continue
        base_slug = _slugify(title)
        slugs[base_slug] = slugs.get(base_slug, 0) + 1
        suffix = f"-{slugs[base_slug]}" if slugs[base_slug] > 1 else ""
        sections.append(
            _Section(
                title=title,
                slug=f"{base_slug}{suffix}",
                lines=tuple(lines),
            )
        )

    if not sections:
        termination_lines = next(
            (
                lines
                for title, lines in raw_sections
                if title.casefold() == "termination reason"
            ),
            None,
        )
        sections.append(
            _Section(
                title="Report details",
                slug="report-details",
                lines=tuple(termination_lines or report.splitlines()),
            )
        )
    return tuple(sections)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "section"


def _section_title(title: str, simplified_chinese: bool) -> str:
    """Return the localized display title for a report section."""
    if not simplified_chinese:
        return title
    return _ZH_SECTION_TITLES.get(title.casefold(), title)


def _localize_body_text(text: str) -> str:
    """Translate report boilerplate while preserving sourced content."""
    if text in _ZH_BODY_TEXT:
        return _ZH_BODY_TEXT[text]
    if text in _ZH_TERMINATION_REASONS:
        return _ZH_TERMINATION_REASONS[text]

    research_ended_prefix = "Unverified gap: Research ended with status: "
    if text.startswith(research_ended_prefix):
        reason = text.removeprefix(research_ended_prefix).removesuffix(".")
        localized_reason = _ZH_TERMINATION_REASONS.get(reason, reason)
        return f"未验证的缺口：研究结束，原因：{localized_reason}。"

    source_read_prefix = "Source read for "
    if text.startswith(source_read_prefix):
        target, separator, _ = text.removeprefix(source_read_prefix).partition(": ")
        return f"读取来源 {target} 时失败。" if separator else "来源读取失败。"

    evidence_extraction_prefix = "Evidence extraction for "
    if text.startswith(evidence_extraction_prefix):
        target, separator, _ = text.removeprefix(
            evidence_extraction_prefix
        ).partition(": ")
        if separator:
            return f"从来源 {target} 提取证据时失败。"
        return "证据提取失败。"

    if text.startswith("search: "):
        return "搜索操作失败。"
    if text.startswith("Research synthesis: "):
        return "研究综合失败。"

    prefix_translations = (
        ("Unverified gap: ", "未验证的缺口："),
        ("Synthesis limitation: ", "综合分析限制："),
    )
    for prefix, localized_prefix in prefix_translations:
        if text.startswith(prefix):
            remainder = text.removeprefix(prefix)
            localized_remainder = _ZH_BODY_TEXT.get(remainder, remainder)
            return f"{localized_prefix}{localized_remainder}"
    return text


def _render_section(section: _Section, *, simplified_chinese: bool) -> str:
    section_class = re.sub(r"[^a-z0-9-]", "", section.slug)
    body = _render_blocks(section.lines, simplified_chinese=simplified_chinese)
    title = _section_title(section.title, simplified_chinese)
    return (
        f'<section class="report-section report-section--{section_class}" '
        f'id="{escape(section.slug, quote=True)}">\n'
        f"  <h2>{escape(title)}</h2>\n"
        f"  {body}\n"
        "</section>"
    )


def _render_blocks(lines: tuple[str, ...], *, simplified_chinese: bool) -> str:
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if line.startswith("```"):
            language = line[3:].strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            language_class = (
                f' class="language-{escape(language, quote=True)}"' if language else ""
            )
            blocks.append(
                f'<pre tabindex="0"><code{language_class}>'
                f"{escape(chr(10).join(code_lines))}</code></pre>"
            )
            continue

        heading = _HEADING_PATTERN.match(line)
        if heading and len(heading.group(1)) == 3:
            rendered_heading = _render_inline(
                heading.group(2), simplified_chinese=simplified_chinese
            )
            blocks.append(
                f"<h3>{rendered_heading}</h3>"
            )
            index += 1
            continue

        ordered = _ORDERED_ITEM_PATTERN.match(line)
        unordered = _UNORDERED_ITEM_PATTERN.match(line)
        if ordered or unordered:
            tag = "ol" if ordered else "ul"
            pattern = _ORDERED_ITEM_PATTERN if ordered else _UNORDERED_ITEM_PATTERN
            items: list[str] = []
            while index < len(lines):
                match = pattern.match(lines[index].strip())
                if not match:
                    break
                rendered_item = _render_inline(
                    (
                        _localize_body_text(match.group(1))
                        if simplified_chinese
                        else match.group(1)
                    ),
                    simplified_chinese=simplified_chinese,
                )
                items.append(
                    f"<li>{rendered_item}</li>"
                )
                index += 1
            blocks.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if line.startswith("> "):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("> "):
                quote_lines.append(lines[index].strip()[2:])
                index += 1
            rendered_quote = _render_inline(
                " ".join(quote_lines), simplified_chinese=simplified_chinese
            )
            blocks.append(
                "<blockquote><p>"
                f"{rendered_quote}"
                "</p></blockquote>"
            )
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index].strip()
            if (
                candidate.startswith("```")
                or _HEADING_PATTERN.match(candidate)
                or _ORDERED_ITEM_PATTERN.match(candidate)
                or _UNORDERED_ITEM_PATTERN.match(candidate)
                or candidate.startswith("> ")
            ):
                break
            paragraph_lines.append(candidate)
            index += 1
        paragraph = " ".join(paragraph_lines)
        if simplified_chinese:
            paragraph = _localize_body_text(paragraph)
        rendered_paragraph = _render_inline(
            paragraph, simplified_chinese=simplified_chinese
        )
        blocks.append(f"<p>{rendered_paragraph}</p>")

    return "\n  ".join(blocks)


def _render_inline(text: str, *, simplified_chinese: bool) -> str:
    rendered: list[str] = []
    position = 0
    for match in _CITATION_PATTERN.finditer(text):
        rendered.append(escape(text[position : match.start()]))
        if match.group(1) is not None:
            rendered.append(f"<code>{escape(match.group(1))}</code>")
        elif match.group(2) is not None and match.group(3) is not None:
            label = escape(match.group(2))
            url = match.group(3)
            if _is_safe_web_url(url):
                rendered.append(
                    f'<a href="{escape(url, quote=True)}" target="_blank" '
                    f'rel="noreferrer">{label}</a>'
                )
            else:
                rendered.append(label)
        else:
            citation = match.group(4)
            citation_label = "来源" if simplified_chinese else "Source"
            rendered.append(
                f'<a class="citation" href="#source-{citation}" '
                f'aria-label="{citation_label} {citation}">{citation}</a>'
            )
        position = match.end()
    rendered.append(escape(text[position:]))
    return "".join(rendered)


def _render_sources(
    sources: tuple[Source, ...], *, simplified_chinese: bool
) -> str:
    section_title = _section_title("Sources", simplified_chinese)
    if not sources:
        empty_message = (
            "未收集到可用来源。"
            if simplified_chinese
            else "No usable sources were collected."
        )
        return (
            '<section class="report-section report-section--sources" id="sources">\n'
            f"  <h2>{section_title}</h2>\n"
            f'  <p class="source-empty">{empty_message}</p>\n'
            "</section>"
        )

    items: list[str] = []
    for index, source in enumerate(sources, start=1):
        source_title = escape(source.title or source.url)
        domain = escape(urlsplit(source.url).hostname or source.url)
        if _is_safe_web_url(source.url):
            content = (
                f'<a class="source-link" href="{escape(source.url, quote=True)}" '
                'target="_blank" rel="noreferrer">'
                f'<span><span class="source-title">{source_title}</span>'
                f'<span class="source-domain">{domain}</span></span>'
                '<span class="source-arrow" aria-hidden="true">↗</span></a>'
            )
        else:
            content = (
                '<span class="source-static">'
                f'<span><span class="source-title">{source_title}</span>'
                f'<span class="source-domain">{domain}</span></span>'
                '<span class="source-arrow" aria-hidden="true"></span></span>'
            )
        items.append(f'<li id="source-{index}">{content}</li>')

    return (
        '<section class="report-section report-section--sources" id="sources">\n'
        f"  <h2>{section_title}</h2>\n"
        f'  <ol class="source-list" role="list">{"".join(items)}</ol>\n'
        "</section>"
    )


def _is_safe_web_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
