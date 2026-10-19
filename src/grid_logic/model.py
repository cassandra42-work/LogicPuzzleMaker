from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .logic import Clue

MIN_CATEGORIES = 2
MAX_CATEGORIES = 6
MIN_VALUES = 2
MAX_VALUES = 10


SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "in",
    "nor", "of", "on", "or", "per", "the", "to", "vs", "with",
}


def title_case(name: str) -> str:
    words = name.split()
    if " ".join(words).isupper():
        return " ".join(words)
    result = []
    for n, word in enumerate(words):
        if len(word) > 1 and word.isupper():
            result.append(word)
        elif 0 < n < len(words) - 1 and word.lower() in SMALL_WORDS:
            result.append(word.lower())
        else:
            parts = []
            for part in word.split("-"):
                parts.append(part[:1].upper() + part[1:].lower())
            result.append("-".join(parts))
    return " ".join(result)


@dataclass
class Category:
    name: str
    values: list[str]
    role: str = "other"  # theme role id: how clues describe these values

    def __post_init__(self) -> None:
        self.name = title_case(self.name)


@dataclass
class Puzzle:
    title: str
    categories: list[Category]
    story: str = ""
    clues: list["Clue"] = field(default_factory=list)
    solution: list[list[int]] | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        if not MIN_CATEGORIES <= len(self.categories) <= MAX_CATEGORIES:
            raise ValueError(
                f"A puzzle needs {MIN_CATEGORIES}-{MAX_CATEGORIES} categories."
            )
        sizes = {len(c.values) for c in self.categories}
        if len(sizes) != 1:
            raise ValueError("Every category must have the same number of values.")

    @property
    def size(self) -> int:
        return len(self.categories[0].values)

    @property
    def top_categories(self) -> list[Category]:
        return self.categories[1:]

    @property
    def left_categories(self) -> list[Category]:
        first = self.categories[0]
        others = list(reversed(self.categories[2:]))
        return [first] + others

    def blocks_in_row(self, row: int) -> int:
        return len(self.categories) - 1 - row

    def color_index(self, category: Category) -> int:
        for i, c in enumerate(self.categories):
            if c is category:
                return i
        raise ValueError(f"{category.name} is not in this puzzle")

    def matches(self, cat_a: int, val_a: int, cat_b: int, val_b: int) -> bool:
        return any(
            row[cat_a] == val_a and row[cat_b] == val_b for row in self.solution
        )


def parse_value_list(text: str) -> list[str]:
    values = []
    for part in text.split(","):
        part = part.strip()
        if part:
            values.append(part)
    return values


def check_values(values: list[str], expected_count: int | None) -> str | None:
    if expected_count is not None and len(values) != expected_count:
        return (
            f"Every category must have the same number of values. "
            f"Expected {expected_count}, got {len(values)}."
        )
    if not MIN_VALUES <= len(values) <= MAX_VALUES:
        return f"Enter between {MIN_VALUES} and {MAX_VALUES} values."
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            return f'"{value}" appears more than once.'
        seen.add(key)
    return None
