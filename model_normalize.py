from __future__ import annotations

import csv
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Tuple

_DASH_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2212\uFE58\uFE63\uFF0D"
_DASH_RE = re.compile(f"[{_DASH_CHARS}]")

# Strip trailing punctuation/brackets/quotes/spaces
_TRAIL_RE = re.compile(r"""[\s\.\,\;\:\!\?\)\]\}\>\"\'\u2019\u201D]+$""")

# Collapse multiple whitespace
_WS_RE = re.compile(r"\s+")

# Collapse patterns like "Q-150" or "Q 150" -> "Q150" (digits-only suffix)
_SINGLE_LETTER_DIGITS_DASH_RE = re.compile(r"\b([A-Za-z])\s*-\s*(\d{2,4})\b")
_SINGLE_LETTER_DIGITS_SPACE_RE = re.compile(r"\b([A-Za-z])\s+(\d{2,4})\b")

# Brand collapsing helper for matching text and keying
_BW_PHRASE_RE = re.compile(
    r"\b(bowers\s*(?:&|and)?\s*wilkins|bowers\s+wilkins)\b",
    re.IGNORECASE
)
_BW_RE = re.compile(r"\b(b\s*&\s*w|b\s+and\s+w|bw)\b", re.IGNORECASE)


@dataclass(frozen=True)
class AliasRecord:
    canonical_key: str
    display_name: str


class ModelNormalizer:
    """
    Two-track identity:
      - canonical_key: aggressive, deterministic grouping key (lowercase alnum only)
      - display_name: cleaned string for UI/output
    """

    def __init__(self, alias_csv: str = "data/reference/model_aliases.csv"):
        self.alias_csv = alias_csv
        self.alias_map: Dict[str, AliasRecord] = self._load_aliases(alias_csv)

    @staticmethod
    def _nfkc(s: str) -> str:
        return unicodedata.normalize("NFKC", s)

    @staticmethod
    def prepare_text_for_matching(text: str) -> str:
        """
        Normalizes source text BEFORE regex matching:
          - NFKC normalize
          - normalize unicode dashes
          - collapse 'Bowers & Wilkins' phrases to 'B&W' to help brand regex
        """
        s = ModelNormalizer._nfkc(text or "")
        s = _DASH_RE.sub("-", s)
        s = _BW_PHRASE_RE.sub("B&W", s)
        return s

    @staticmethod
    def _normalize_dashes(s: str) -> str:
        s = _DASH_RE.sub("-", s)
        s = re.sub(r"\s*-\s*", "-", s)
        return s

    @staticmethod
    def _strip_trailing_punct(s: str) -> str:
        return _TRAIL_RE.sub("", s)

    @staticmethod
    def _collapse_ws(s: str) -> str:
        return _WS_RE.sub(" ", s).strip()

    @staticmethod
    def normalize_display(raw: str) -> str:
        if raw is None:
            return ""
        s = str(raw)
        s = ModelNormalizer._nfkc(s)
        s = s.strip()

        s = ModelNormalizer._normalize_dashes(s)
        s = ModelNormalizer._strip_trailing_punct(s)
        s = ModelNormalizer._collapse_ws(s)

        # Collapse Q-150 / Q 150 -> Q150 (digits-only suffix)
        s = _SINGLE_LETTER_DIGITS_DASH_RE.sub(r"\1\2", s)
        s = _SINGLE_LETTER_DIGITS_SPACE_RE.sub(r"\1\2", s)

        return s

    @staticmethod
    def canonical_key(raw: str) -> str:
        if raw is None:
            return ""
        s = ModelNormalizer.normalize_display(raw)

        # Collapse B&W variants
        s = _BW_PHRASE_RE.sub("bw", s)
        s = _BW_RE.sub("bw", s)

        s = s.lower()
        s = re.sub(r"[^a-z0-9]+", "", s)
        return s

    def has_alias(self, raw: str) -> bool:
        k = self.canonical_key(raw)
        return bool(k) and k in self.alias_map

    def normalize(self, raw: str) -> Tuple[str, str]:
        """
        Returns (canonical_key, display_name), applying alias overrides when present.
        """
        display = self.normalize_display(raw)
        key = self.canonical_key(display)
        if not key:
            return "", display

        rec = self.alias_map.get(key)
        if rec:
            return rec.canonical_key, rec.display_name

        return key, display

    def _load_aliases(self, path: str) -> Dict[str, AliasRecord]:
        """
        CSV accepted columns (case-insensitive):
          - alias (required)
          - canonical OR canonical_model OR canonical_name (optional)
          - display_name (optional)
          - canonical_key (optional override)

        Mapping is done using canonical_key(alias).
        """
        if not path or not os.path.exists(path):
            return {}

        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

            alias_map: Dict[str, AliasRecord] = {}

            for row in reader:
                if not row:
                    continue
                alias = (row.get("alias") or "").strip()
                if not alias or alias.startswith("#"):
                    continue

                canonical = (row.get("canonical") or row.get("canonical_model") or row.get("canonical_name") or "").strip()
                display = (row.get("display_name") or "").strip()
                canonical_key_override = (row.get("canonical_key") or "").strip()

                alias_key = self.canonical_key(alias)
                if not alias_key:
                    continue

                if display:
                    display_name = self.normalize_display(display)
                elif canonical:
                    display_name = self.normalize_display(canonical)
                else:
                    display_name = self.normalize_display(alias)

                if canonical_key_override:
                    ck = self.canonical_key(canonical_key_override)
                else:
                    ck = self.canonical_key(display_name)

                if not ck:
                    ck = alias_key

                alias_map[alias_key] = AliasRecord(canonical_key=ck, display_name=display_name)

        return alias_map
