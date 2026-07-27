"""Language-selection helpers shared by research and report rendering."""

import re


_HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_JAPANESE_PATTERN = re.compile(r"[\u3040-\u30ff\uff66-\uff9f]")
_SIMPLIFIED_MARKERS = re.compile(
    r"[这网网页标标准么个与为于从后发开关体学会问题实业东车马风书"
    r"长门"
    r"见还来时国华万无过里证据结论请绍场规几吗职责余]"
)
_TRADITIONAL_MARKERS = re.compile(
    r"[這網頁標準麼個與為於從後發開關體學會問題實業東車馬風書長門"
    r"見還"
    r"來時國華萬無過裡證據結論請紹場規幾嗎職責餘]"
)
_JAPANESE_KANJI_CUES = re.compile(r"人工知能|情報処理|株式会社|検索方法")


def should_use_simplified_chinese(question: str) -> bool:
    """Prefer Simplified Chinese unless a Han query is clearly another variant."""
    if not _HAN_PATTERN.search(question):
        return False
    if _JAPANESE_PATTERN.search(question) or _JAPANESE_KANJI_CUES.search(question):
        return False
    has_simplified_markers = bool(_SIMPLIFIED_MARKERS.search(question))
    has_traditional_markers = bool(_TRADITIONAL_MARKERS.search(question))
    if has_simplified_markers:
        return True
    if has_traditional_markers:
        return False
    return True
