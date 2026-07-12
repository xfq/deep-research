---
name: Deep Research Agent
description: A rigorous, elegant reading system for evidence-backed AI research reports.
colors:
  reading-paper: "oklch(97.4% 0.009 83)"
  raised-paper: "oklch(99.1% 0.006 83)"
  primary-ink: "oklch(24% 0.025 252)"
  secondary-ink: "oklch(51% 0.025 252)"
  quiet-rule: "oklch(87% 0.018 83)"
  index-blue: "oklch(52% 0.13 252)"
  index-blue-soft: "oklch(93% 0.025 252)"
  verified-green: "oklch(49% 0.105 154)"
  verified-green-soft: "oklch(93% 0.035 154)"
  caution-amber: "oklch(53% 0.125 71)"
  caution-amber-soft: "oklch(94% 0.045 82)"
  failure-red: "oklch(50% 0.15 27)"
  failure-red-soft: "oklch(94% 0.035 27)"
typography:
  display:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "clamp(2.35rem, 6vw, 5.5rem)"
    fontWeight: 760
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "clamp(1.65rem, 2.4vw, 2.3rem)"
    fontWeight: 760
    lineHeight: 1.08
    letterSpacing: "-0.035em"
  body:
    fontFamily: "ui-serif, Iowan Old Style, Palatino Linotype, Noto Serif CJK SC, Songti SC, serif"
    fontSize: "clamp(1rem, 0.96rem + 0.18vw, 1.12rem)"
    fontWeight: 400
    lineHeight: 1.78
  label:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.82rem"
    fontWeight: 720
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  focus: "0.2rem"
  code: "0.3rem"
  inset: "0.6rem"
  callout: "0.8rem"
  pill: "999px"
spacing:
  xs: "0.35rem"
  sm: "0.7rem"
  md: "1rem"
  lg: "1.5rem"
  section: "3.5rem"
components:
  status-complete:
    backgroundColor: "{colors.verified-green-soft}"
    textColor: "{colors.verified-green}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.45rem 0.75rem"
  status-partial:
    backgroundColor: "{colors.caution-amber-soft}"
    textColor: "{colors.caution-amber}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.45rem 0.75rem"
  citation:
    backgroundColor: "{colors.index-blue-soft}"
    textColor: "{colors.index-blue}"
    rounded: "{rounded.pill}"
    size: "1.45em"
  caution-panel:
    backgroundColor: "{colors.caution-amber-soft}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.callout}"
    padding: "clamp(1.4rem, 3vw, 2rem)"
---

# Design System: Deep Research Agent

## Overview

**Creative North Star: "The Annotated Reading Room"**

An expert opens the report on a large monitor in a bright, quiet room, settles in for sustained reading, then prints or cites the result. That physical scene requires a light, paper-like surface, disciplined navigation, restrained status color, and typography that remains comfortable across long passages. The interface should feel measured, lucid, and archival.

The system makes rigor visible through structure rather than decoration. Sources, citations, outcomes, conflicts, and uncertainty each receive clear but quiet treatment. It rejects generic SaaS dashboards, decorative AI imagery, neon-on-black futurism, chat-interface mimicry, glassmorphism, template-like card grids, sterile corporate minimalism, and ornamental editorial design that competes with the Research Report.

**Key Characteristics:**

- Warm reading surfaces with cool blue indexing and links
- Serif prose paired with compact sans-serif structure
- Strong typographic hierarchy without magazine affectation
- Flat surfaces separated by rules, spacing, and tonal shifts
- Responsive section navigation and first-class print behavior

## Colors

The palette is restrained: warm paper and blue-tinted ink carry nearly the whole report, while green, amber, and red appear only when research state requires them.

### Primary

- **Index Blue:** The navigational voice for links, citations, source numbers, and short structural accents.
- **Index Blue Soft:** A quiet backing for citation markers and other compact references.

### Secondary

- **Verified Green:** Communicates a complete outcome together with a textual label.
- **Caution Amber:** Marks partial outcomes, conflicting Evidence, Evidence gaps, uncertainty, and failed operations.
- **Failure Red:** Communicates failed outcomes together with a textual label.

### Neutral

- **Reading Paper:** The dominant page surface for sustained reading.
- **Raised Paper:** Separates headers, quotations, code, and compact navigation without relying on shadows.
- **Primary Ink:** The main text and title color, tinted toward the same cool family as Index Blue.
- **Secondary Ink:** Metadata, domains, navigation, and supporting labels.
- **Quiet Rule:** Dividers and full borders that clarify structure without becoming ornament.

### Named Rules

**The Evidence Color Rule.** Green, amber, and red are semantic research-state colors. Never use them as decoration.

**The Paper First Rule.** Reading Paper owns the surface. Index Blue should remain scarce enough to preserve its value as an index and action cue.

## Typography

**Display Font:** System sans-serif stack
**Body Font:** System serif stack with Iowan Old Style, Palatino Linotype, Noto Serif CJK SC, and Songti SC fallbacks
**Label/Mono Font:** System sans-serif labels; system monospace only for code

**Character:** The sans-serif voice is exact and structural. The serif voice is calm and literary enough for long reading, but avoids ornamental editorial mannerisms. Native stacks keep the self-contained report fast, private, and dependable across English and Chinese.

### Hierarchy

- **Display** (760, fluid 2.35rem to 5.5rem, 0.98): Research Question titles, capped near 22 characters per line.
- **Headline** (760, fluid 1.65rem to 2.3rem, 1.08): Major Research Report sections.
- **Title** (default bold, fluid 1.15rem to 1.35rem, 1.25): Subsections within Evidence and analysis.
- **Body** (400, fluid 1rem to 1.12rem, 1.78): Primary report prose in a reading column no wider than 48rem.
- **Label** (720, 0.76rem to 0.88rem, up to 0.08em tracking): Kicker, status, navigation, metadata, and source details.

### Named Rules

**The Two Voices Rule.** Serif explains; sans-serif organizes. Do not swap their responsibilities for novelty.

**The Reading Measure Rule.** Prose stays within the existing 48rem column. Never stretch body text across the full 76rem shell.

## Elevation

The system is flat by default and uses no box shadows. Depth comes from tonal layering, full borders, sticky positioning, and varied spacing. Raised Paper may sit over Reading Paper, but it must still feel like another sheet in the same reading environment, not a floating application card.

### Named Rules

**The No Shadow Rule.** If a surface needs a dark drop shadow to be understood, its structure is unresolved. Use a tonal shift, a full 1px rule, or clearer spacing.

## Components

### Status Indicators

- **Shape:** Compact pill with a circular leading marker.
- **Color:** Complete, Partial, and Failed use their semantic foreground and soft background pairs.
- **Accessibility:** Text labels always accompany color. The marker is redundant reinforcement, never the sole signal.

### Section Navigation

- **Desktop:** A sticky left index in muted sans-serif text, aligned beside the reading column.
- **Mobile:** A sticky horizontal list of compact Raised Paper pills with overflow scrolling.
- **State:** Hover changes text to Index Blue. Focus uses a visible three-pixel outline mixed from Index Blue.

### Citation Markers

- **Shape:** Small circular markers sized to at least 1.45em.
- **Color:** Index Blue on Index Blue Soft.
- **Behavior:** Each marker jumps directly to the corresponding numbered Source.

### Research-State Panels

- **Shape:** Gently curved full-border panel using the callout radius.
- **Color:** Caution Amber Soft with a restrained Caution Amber border.
- **Use:** Reserved for conflicting Evidence, Evidence gaps, uncertainty, and failed operations. These are not generic cards.

### Sources

- **Structure:** Number, title and domain, then an external-link arrow in a ruled list.
- **States:** Hover changes only the source title to Index Blue. Non-link Sources preserve the same reading structure without pretending to be interactive.
- **Rhythm:** Full-width rules and generous vertical padding make each Source independently scannable.

### Quotations and Code

- **Quotations:** Raised Paper, a full Quiet Rule border, and the inset radius.
- **Inline Code:** Compact Raised Paper capsule with a full Quiet Rule border.
- **Code Blocks:** Scrollable Raised Paper panels with no decorative syntax surface or fake window chrome.

## Do's and Don'ts

### Do:

- **Do** preserve the warm Reading Paper, cool Primary Ink, and scarce Index Blue relationship.
- **Do** make Sources, citations, uncertainty, and outcomes easy to inspect.
- **Do** use full one-pixel borders, tonal changes, and varied spacing to establish hierarchy.
- **Do** keep keyboard focus visible, outcome meaning color-independent, reduced motion respected, and print output legible.
- **Do** keep English and Chinese prose comfortable through the existing language-aware serif fallbacks.

### Don't:

- **Don't** turn the report into a generic SaaS dashboard or template-like card grid.
- **Don't** use decorative AI imagery, neon-on-black futurism, or chat-interface mimicry.
- **Don't** use glassmorphism, gradient text, colored side-stripe borders, or decorative drop shadows.
- **Don't** imitate academic authority while obscuring weak Evidence.
- **Don't** use sterile corporate minimalism or ornamental editorial design that competes with the Research Report.
- **Don't** use green, amber, or red without an explicit research-state meaning and a textual label.
