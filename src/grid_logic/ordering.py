from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
RANKS = [
    "iron", "bronze", "silver", "gold", "platinum",
    "emerald", "diamond", "master", "grandmaster", "challenger",
]
ORDINAL_WORDS = [
    "first", "second", "third", "fourth", "fifth",
    "sixth", "seventh", "eighth", "ninth", "tenth",
]

NUMBER_RE = re.compile(
    r"^(?P<pre>[^\d\-]*?)(?P<num>-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?P<suf>.*)$"
)
ORDINAL_SUFFIX_RE = re.compile(r"^(st|nd|rd|th)\b", re.IGNORECASE)
TIME_12H_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?$", re.IGNORECASE)
TIME_24H_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

SEQUENCE_KINDS = {"time", "weekday", "month"}


@dataclass
class Ordering:
    kind: str  # number, ordinal, time, weekday, month, or rank
    keys: list[Fraction]  # sort key for each value, in the category's value order
    prefix: str = ""
    suffix: str = ""

    @property
    def family(self) -> str:
        return "sequence" if self.kind in SEQUENCE_KINDS else "number"

    @property
    def supports_difference(self) -> bool:
        return self.kind != "rank"

    def with_unit(self, value: str, unit: tuple[str, str] | None, index: int) -> str:
        if self.kind != "number" or self.suffix.strip() or not unit:
            return value
        singular, plural = unit
        if self.keys[index] == 1:
            return f"{value} {singular}"
        return f"{value} {plural}"

    def difference_text(self, diff: Fraction, unit: tuple[str, str] | None = None) -> str:
        d = abs(diff)
        if self.kind == "number":
            number = f"{self.prefix}{_format_number(d)}"
            if self.suffix.strip():
                if d == 1:
                    return number + _singular(self.suffix)
                return number + self.suffix
            if unit:
                singular, plural = unit
                if d == 1:
                    return f"{number} {singular}"
                return f"{number} {plural}"
            return number
        if self.kind == "time":
            return _format_minutes(int(d))
        word = {"ordinal": "place", "weekday": "day", "month": "month"}[self.kind]
        if d != 1:
            word += "s"
        return f"{_format_number(d)} {word}"


def detect_ordering(values: list[str]) -> Ordering | None:
    for detector in (_numbers, _times, _weekdays, _months, _ranks, _ordinal_words):
        ordering = detector([v.strip() for v in values])
        if ordering and len(set(ordering.keys)) == len(values):
            return ordering
    return None


def _numbers(values: list[str]) -> Ordering | None:
    keys = []
    prefixes = set()
    suffixes = set()
    ordinals = set()
    raw_suffix = ""
    best = None
    for value in values:
        match = NUMBER_RE.match(value)
        if not match:
            return None
        suffix = match["suf"]
        ordinal = ORDINAL_SUFFIX_RE.match(suffix)
        if ordinal:
            suffix = suffix[ordinal.end():]
        key = Fraction(match["num"].replace(",", ""))
        keys.append(key)
        prefixes.add(match["pre"].strip().casefold())
        suffixes.add(suffix.strip().casefold().rstrip("s"))
        ordinals.add(bool(ordinal))
        if best is None or key > best:
            best = key
            raw_suffix = suffix
    if len(prefixes) > 1 or len(suffixes) > 1 or len(ordinals) > 1:
        return None
    kind = "ordinal" if ordinals.pop() else "number"
    prefix = NUMBER_RE.match(values[0])["pre"]
    return Ordering(kind, keys, prefix=prefix, suffix=raw_suffix)


def _times(values: list[str]) -> Ordering | None:
    keys = []
    for value in values:
        if match := TIME_12H_RE.match(value):
            hour = int(match[1])
            minute = int(match[2] or 0)
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12
            if match[3].lower() == "p":
                hour += 12
        elif match := TIME_24H_RE.match(value):
            hour = int(match[1])
            minute = int(match[2])
        else:
            return None
        if hour > 23 or minute > 59:
            return None
        keys.append(Fraction(hour * 60 + minute))
    return Ordering("time", keys)


def _named_sequence(values: list[str], names: list[str], kind: str, min_len: int = 3):
    keys = []
    for value in values:
        word = value.casefold().rstrip(".")
        found = []
        if len(word) >= min_len:
            for i, name in enumerate(names):
                if name.startswith(word):
                    found.append(i)
        if len(found) != 1:
            return None
        keys.append(Fraction(found[0]))
    return Ordering(kind, keys)


def _weekdays(values):
    return _named_sequence(values, WEEKDAYS, "weekday")


def _months(values):
    return _named_sequence(values, MONTHS, "month")


def _ranks(values):
    keys = []
    for value in values:
        word = value.casefold().replace(" ", "")
        if word not in RANKS:
            return None
        keys.append(Fraction(RANKS.index(word)))
    return Ordering("rank", keys)


def _ordinal_words(values):
    keys = []
    for value in values:
        words = value.casefold().split()
        word = words[0] if words else ""
        if word not in ORDINAL_WORDS:
            return None
        keys.append(Fraction(ORDINAL_WORDS.index(word) + 1))
    return Ordering("ordinal", keys)


def _format_number(value: Fraction) -> str:
    if value.denominator == 1:
        return f"{int(value):,}"
    text = f"{float(value):,.2f}"
    return text.rstrip("0").rstrip(".")


def _singular(suffix: str) -> str:
    if suffix.endswith("s") and not suffix.endswith("ss"):
        return suffix[:-1]
    return suffix


def _format_minutes(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours == 1:
        parts.append("1 hour")
    elif hours:
        parts.append(f"{hours} hours")
    if mins == 1:
        parts.append("1 minute")
    elif mins:
        parts.append(f"{mins} minutes")
    return " and ".join(parts)
