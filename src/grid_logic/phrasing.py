from __future__ import annotations

import random
import re
from collections import Counter

from .logic import Clue, Ref
from .model import Category
from .ordering import Ordering
from .themes import NUMBER_WORDS, ResolvedTheme, Role

VALUE_START, VALUE_END = "\x01", "\x02"
NAMES_ONLY = "[names] "
WRAPPER_CHANCE = 0.18
SUPERLATIVE_CHANCE = 0.7


def finish_sentence(text: str) -> str:
    if text.startswith(VALUE_START):
        value = text[1:].split(VALUE_END, 1)[0]
        has_capital = any(ch.isupper() for ch in value)
        if value[:1].isalpha() and not has_capital:
            text = VALUE_START + value[0].upper() + text[2:]
    elif text[:1].isalpha():
        text = text[0].upper() + text[1:]
    text = text.replace(VALUE_START, "").replace(VALUE_END, "")
    return re.sub(r"\s+", " ", text).strip()


def natural_join(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def category_word(name: str) -> str:
    words = []
    for word in name.split():
        if len(word) > 1 and word.isupper():
            words.append(word)
        else:
            words.append(word.lower())
    return " ".join(words)


class _Lazy(dict):
    def __init__(self, makers):
        super().__init__()
        self.makers = makers

    def __missing__(self, key):
        value = self.makers[key]()
        self[key] = value
        return value


class Phraser:
    def __init__(
        self,
        theme: ResolvedTheme,
        categories: list[Category],
        orderings: dict[int, Ordering],
        rng: random.Random,
    ):
        self.theme = theme
        self.categories = categories
        self.orderings = orderings
        self.rng = rng
        self.count = len(categories[0].values)
        self.used: Counter[str] = Counter()

    def pick(self, options: list[str]) -> str:
        fewest = min(self.used[o] for o in options)
        least_used = [o for o in options if self.used[o] == fewest]
        choice = self.rng.choice(least_used)
        self.used[choice] += 1
        return choice

    def role(self, cat: int) -> Role:
        return self.theme.role(self.categories[cat].role)

    def _base(self, cat: int) -> dict[str, str]:
        return {
            **self.theme.context(self.count),
            "cat": category_word(self.categories[cat].name),
        }

    def _value(self, ref: Ref) -> dict[str, str]:
        value = self.categories[ref.cat].values[ref.val]
        ordering = self.orderings.get(ref.cat)
        with_unit = value
        if ordering:
            with_unit = ordering.with_unit(value, self.role(ref.cat).unit, ref.val)
        return {
            "v": f"{VALUE_START}{value}{VALUE_END}",
            "vu": f"{VALUE_START}{with_unit}{VALUE_END}",
        }

    def np(self, ref: Ref) -> str:
        template = self.pick(self.role(ref.cat).np)
        return template.format_map({**self._base(ref.cat), **self._value(ref)})

    def vp(self, ref: Ref, negative: bool = False) -> str:
        role = self.role(ref.cat)
        template = self.pick(role.vp_neg if negative else role.vp)
        context = {**self._base(ref.cat), **self._value(ref)}
        if "{np}" in template:
            context["np"] = self.np(ref)
        return template.format_map(context)

    def compare(self, cat: int, key: str, diff_text: str = "") -> str:
        role = self.role(cat)
        options = role.compare.get(key)
        if not options:
            family = self.orderings[cat].family
            options = self.theme.ordered_generic[family][key]
        context = {**self._base(cat), "d": f"{VALUE_START}{diff_text}{VALUE_END}"}
        return self.pick(options).format_map(context)

    def _extreme(self, ref: Ref) -> str | None:
        ordering = self.orderings.get(ref.cat)
        if not ordering:
            return None
        key = ordering.keys[ref.val]
        if key == max(ordering.keys):
            return "most"
        if key == min(ordering.keys):
            return "least"
        return None

    def text(self, clue: Clue) -> str:
        refs = list(clue.refs)
        kind = clue.kind
        templates = self.theme.clue_templates
        extra: dict = {}

        if kind in ("same", "different") and self.rng.random() < 0.75:
            if not self.role(refs[0].cat).person and self.role(refs[1].cat).person:
                refs.reverse()

        if kind == "same":
            for i in (1, 0):
                extreme = self._extreme(refs[i])
                if extreme and self.rng.random() < SUPERLATIVE_CHANCE:
                    other = refs[1 - i]
                    refs = [other, refs[i]]
                    kind = "superlative"
                    extra["sup"] = lambda c=refs[1].cat, e=extreme: self.compare(c, e)
                    break

        if kind == "greater":
            a, b = refs
            diff_text = ""
            if clue.diff is not None:
                diff_text = self.orderings[clue.order_cat].difference_text(
                    clue.diff, self.role(clue.order_cat).unit
                )
            suffix = "_by" if clue.diff is not None else ""
            if self.rng.random() < 0.5:
                refs = [a, b]
                key = "more" + suffix
            else:
                refs = [b, a]
                key = "less" + suffix
            extra["cmp"] = lambda: self.compare(clue.order_cat, key, diff_text)

        makers = {
            "entity": lambda: self.theme.entity,
            "entities": lambda: self.theme.entities,
            "count": lambda: NUMBER_WORDS[len(refs)],
            "list": lambda: natural_join([self.np(r) for r in refs]),
            **extra,
        }
        for letter, ref in zip("abcd", refs):
            makers[letter] = lambda r=ref: self.np(r)
            makers[f"vp_{letter}"] = lambda r=ref: self.vp(r)
            makers[f"vpn_{letter}"] = lambda r=ref: self.vp(r, negative=True)

        options = templates[kind]
        if kind == "either" and any(self.role(r.cat).person for r in refs[1:]):
            noun_forms = [t for t in options if "{vp_" not in t]
            if noun_forms:
                options = noun_forms
        if not all(self.role(r.cat).person for r in refs[:2]):
            general = [t for t in options if not t.startswith(NAMES_ONLY)]
            if general:
                options = general
        template = self.pick(options).removeprefix(NAMES_ONLY)
        sentence = template.format_map(_Lazy(makers))

        unused_wrappers = [w for w in self.theme.wrappers if not self.used[w]]
        if unused_wrappers and self.rng.random() < WRAPPER_CHANCE:
            wrapper = self.pick(unused_wrappers)
            context = self.theme.context(self.count)
            context["clue"] = sentence
            sentence = wrapper.format_map(context)
        return finish_sentence(sentence)
