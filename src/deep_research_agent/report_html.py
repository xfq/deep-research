from dataclasses import dataclass
from html import escape
import re
from urllib.parse import urlsplit

from deep_research_agent.research import ResearchOutcome, Source, TerminationReason


_CITATION_PATTERN = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\((https?://[^\s)]+)\)|\[(\d+)\]")
_HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_HEADING_PATTERN = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_ORDERED_ITEM_PATTERN = re.compile(r"^\d+\.\s+(.+)$")
_UNORDERED_ITEM_PATTERN = re.compile(r"^[-*]\s+(.+)$")
_OMITTED_SECTIONS = {
    "research question",
    "outcome",
    "termination reason",
    "sources",
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
    sections = _parse_sections(report)
    source_section = _render_sources(sources)
    navigation_items = [
        f'<li><a href="#{escape(section.slug, quote=True)}">'
        f"{escape(section.title)}</a></li>"
        for section in sections
    ]
    navigation_items.append('<li><a href="#sources">Sources</a></li>')
    content = "\n".join(_render_section(section) for section in sections)
    language = "zh-CN" if _HAN_PATTERN.search(question + report) else "en"
    outcome_value = outcome.value
    outcome_label = {
        ResearchOutcome.COMPLETE: "Complete",
        ResearchOutcome.PARTIAL: "Partial",
        ResearchOutcome.FAILED: "Failed",
    }[outcome]
    reason = (
        termination_reason.value
        if isinstance(termination_reason, TerminationReason)
        else str(termination_reason)
    )
    source_label = "source" if len(sources) == 1 else "sources"

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>{escape(question)} | Deep Research</title>
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
      font-size: clamp(1rem, 0.96rem + 0.18vw, 1.12rem);
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
      padding-block: clamp(3.5rem, 8vw, 7.5rem) clamp(2.25rem, 5vw, 4rem);
    }}

    .report-kicker {{
      margin: 0 0 1.25rem;
      color: var(--accent);
      font: 720 0.82rem/1.2 var(--sans);
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
      margin-top: clamp(2rem, 5vw, 3.5rem);
      color: var(--muted);
      font: 560 0.88rem/1.45 var(--sans);
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
      grid-template-columns: minmax(11rem, 14rem) minmax(0, 48rem);
      gap: clamp(2.5rem, 7vw, 8rem);
      width: min(100% - 2.5rem, 76rem);
      margin-inline: auto;
      padding-block: clamp(2.5rem, 6vw, 6rem) 8rem;
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
      font-size: 0.88rem;
      font-weight: 600;
      line-height: 1.35;
      text-decoration: none;
    }}

    .report-nav a:hover {{ color: var(--accent); }}

    .report-content {{ min-width: 0; overflow-wrap: anywhere; }}

    .report-section {{
      padding-block: 0 3.5rem;
      content-visibility: auto;
      contain-intrinsic-size: auto 32rem;
    }}

    .report-section + .report-section {{
      padding-top: 3.5rem;
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

    .report-section--answer > p:first-of-type {{
      font-size: clamp(1.2rem, 1.5vw, 1.38rem);
      line-height: 1.72;
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
      grid-template-columns: 2.4rem minmax(0, 1fr) auto;
      gap: 0.8rem;
      align-items: center;
      padding: 1.15rem 0;
      color: var(--ink);
      font-family: var(--sans);
      text-decoration: none;
    }}

    .source-link::before,
    .source-static::before {{
      content: counter(source, decimal-leading-zero);
      color: var(--accent);
      font-size: 0.76rem;
      font-weight: 760;
    }}

    .source-title {{ font-weight: 680; line-height: 1.35; }}

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
  <a class="skip-link" href="#main-content">Skip to report</a>
  <header class="report-header">
    <div class="report-header__inner">
      <p class="report-kicker">Deep Research Report</p>
      <h1>{escape(question)}</h1>
      <div class="report-meta" aria-label="Report metadata">
        <span class="status status--{outcome_value}">{outcome_label}</span>
        <span>{len(sources)} {source_label}</span>
        <span>{escape(reason)}</span>
      </div>
    </div>
  </header>
  <div class="report-shell">
    <nav class="report-nav" aria-label="Report sections">
      <p class="report-nav__title">Contents</p>
      <ul role="list">
        {''.join(navigation_items)}
      </ul>
    </nav>
    <main id="main-content" tabindex="-1">
      <article class="report-content">
        {content}
        {source_section}
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


def _render_section(section: _Section) -> str:
    section_class = re.sub(r"[^a-z0-9-]", "", section.slug)
    body = _render_blocks(section.lines)
    return (
        f'<section class="report-section report-section--{section_class}" '
        f'id="{escape(section.slug, quote=True)}">\n'
        f"  <h2>{escape(section.title)}</h2>\n"
        f"  {body}\n"
        "</section>"
    )


def _render_blocks(lines: tuple[str, ...]) -> str:
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
            blocks.append(f"<h3>{_render_inline(heading.group(2))}</h3>")
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
                items.append(f"<li>{_render_inline(match.group(1))}</li>")
                index += 1
            blocks.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if line.startswith("> "):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("> "):
                quote_lines.append(lines[index].strip()[2:])
                index += 1
            blocks.append(
                f"<blockquote><p>{_render_inline(' '.join(quote_lines))}</p></blockquote>"
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
        blocks.append(f"<p>{_render_inline(' '.join(paragraph_lines))}</p>")

    return "\n  ".join(blocks)


def _render_inline(text: str) -> str:
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
            rendered.append(
                f'<a class="citation" href="#source-{citation}" '
                f'aria-label="Source {citation}">{citation}</a>'
            )
        position = match.end()
    rendered.append(escape(text[position:]))
    return "".join(rendered)


def _render_sources(sources: tuple[Source, ...]) -> str:
    if not sources:
        return (
            '<section class="report-section report-section--sources" id="sources">\n'
            "  <h2>Sources</h2>\n"
            '  <p class="source-empty">No usable sources were collected.</p>\n'
            "</section>"
        )

    items: list[str] = []
    for index, source in enumerate(sources, start=1):
        title = escape(source.title or source.url)
        domain = escape(urlsplit(source.url).hostname or source.url)
        if _is_safe_web_url(source.url):
            content = (
                f'<a class="source-link" href="{escape(source.url, quote=True)}" '
                'target="_blank" rel="noreferrer">'
                f'<span><span class="source-title">{title}</span>'
                f'<span class="source-domain">{domain}</span></span>'
                '<span class="source-arrow" aria-hidden="true">↗</span></a>'
            )
        else:
            content = (
                '<span class="source-static">'
                f'<span><span class="source-title">{title}</span>'
                f'<span class="source-domain">{domain}</span></span>'
                '<span class="source-arrow" aria-hidden="true"></span></span>'
            )
        items.append(f'<li id="source-{index}">{content}</li>')

    return (
        '<section class="report-section report-section--sources" id="sources">\n'
        "  <h2>Sources</h2>\n"
        f'  <ol class="source-list" role="list">{"".join(items)}</ol>\n'
        "</section>"
    )


def _is_safe_web_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
