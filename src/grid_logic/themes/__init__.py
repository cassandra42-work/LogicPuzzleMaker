from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

THEME_DIR = Path(__file__).parent

NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
]
COMPARE_KEYS = ("more", "less", "more_by", "less_by", "most", "least")


@dataclass
class Role:
    id: str
    label: str
    category: str
    hint: str
    keywords: list[str]
    samples: list[str]
    sample_run: bool
    person: bool
    unit: tuple[str, str] | None
    np: list[str]
    vp: list[str]
    vp_neg: list[str]
    compare: dict[str, list[str]]

    @classmethod
    def from_dict(cls, role_id: str, data: dict, common: dict) -> "Role":
        samples = data.get("samples", [])
        if samples == "@people_names":
            samples = common["people_names"]
        return cls(
            id=role_id,
            label=data.get("label", role_id.replace("_", " ").title()),
            category=data.get("category", data.get("label", role_id.title())),
            hint=data.get("hint", ""),
            keywords=[k.casefold() for k in data.get("keywords", [])],
            samples=list(samples),
            sample_run=bool(data.get("sample_run")),
            person=bool(data.get("person")),
            unit=tuple(data["unit"]) if data.get("unit") else None,
            np=data.get("np") or ["the {entity} with {v}"],
            vp=data.get("vp") or ["is {np}"],
            vp_neg=data.get("vp_neg") or ["is not {np}"],
            compare={key: data[key] for key in COMPARE_KEYS if data.get(key)},
        )

    def sample_values(self, count: int, rng: random.Random) -> list[str]:
        if len(self.samples) < count:
            return []
        if self.sample_run:
            start = rng.randrange(len(self.samples) - count + 1)
            return self.samples[start : start + count]
        return rng.sample(self.samples, count)


@dataclass
class ThemeOption:
    key: str
    prompt: str
    kind: str  # "text" or "choice"
    choices: list[str]
    default: str


def _merge(base: dict, extra: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@lru_cache(maxsize=1)
def _common() -> dict:
    return json.loads((THEME_DIR / "common.json").read_text(encoding="utf-8"))


class Theme:
    def __init__(self, data: dict):
        self.data = data
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.blurb: str = data.get("blurb", "")
        self.options = [
            ThemeOption(
                key=o["key"],
                prompt=o["prompt"],
                kind=o.get("type", "text"),
                choices=o.get("choices", []),
                default=o.get("default", ""),
            )
            for o in data.get("options", [])
        ]

    def resolve(self, answers: dict[str, str], rng: random.Random) -> "ResolvedTheme":
        common = _common()
        data = _merge({"roles": common["roles"]}, self.data)
        for option in self.options:
            if option.kind == "choice":
                variant = data.get("variants", {}).get(answers.get(option.key, ""))
                if variant:
                    data = _merge(data, variant)
        return ResolvedTheme(self, data, dict(answers), rng)


class ResolvedTheme:
    def __init__(self, theme: Theme, data: dict, answers: dict[str, str], rng):
        common = _common()
        self.entity, self.entities = data.get("entity", ["person", "people"])
        self.vars: dict[str, str] = {}
        for key, choices in data.get("flavor", {}).items():
            self.vars[key] = rng.choice(choices)
        self.vars.update(data.get("vars", {}))
        self.vars.update(answers)
        self.titles: list[str] = data.get("titles", [theme.name])
        # A story is a template, or {"text": ..., "needs": [role ids]} when it
        # mentions categories that must be in the puzzle for it to make sense.
        self.stories: list[tuple[str, frozenset[str]]] = []
        for story in data.get("stories", []):
            if isinstance(story, str):
                self.stories.append((story, frozenset()))
            else:
                needs = frozenset(story.get("needs", []))
                self.stories.append((story["text"], needs))
        self.wrappers: list[str] = data.get("wrappers", [])
        self.tasks: list[str] = common["tasks"]
        self.ordered_generic: dict = common["ordered_generic"]
        self.clue_templates: dict[str, list[str]] = {
            kind: list(templates) for kind, templates in common["clues"].items()
        }
        for kind, templates in data.get("clues", {}).items():
            self.clue_templates.setdefault(kind, []).extend(templates)
        self.roles = {
            role_id: Role.from_dict(role_id, role, common)
            for role_id, role in data["roles"].items()
        }
        order = list(data.get("default_roles", ["name"]))
        first = [r for r in order if r in self.roles]
        rest = [r for r in self.roles if r not in order and r != "other"]
        self.role_order = first + rest + ["other"]

    def role(self, role_id: str) -> Role:
        return self.roles.get(role_id) or self.roles["other"]

    def match_role(self, category_name: str, used: list[str]) -> Role | None:
        name = category_name.casefold().strip()
        best, best_score = None, 0
        for role_id in self.role_order:
            role = self.roles[role_id]
            words = set(role.keywords) | {role.category.casefold(), role.label.casefold()}
            score = 0
            for word in words:
                if not word:
                    continue
                exact = word == name
                whole_word = word in name.split()
                inside = len(word) > 3 and word in name
                if exact or whole_word or inside:
                    word_score = len(word)
                    if exact:
                        word_score += 10
                    score = max(score, word_score)
            if role_id in used:
                score -= 1
            if score > best_score:
                best, best_score = role, score
        return best

    def context(self, count: int) -> dict[str, str]:
        if count < len(NUMBER_WORDS):
            n = NUMBER_WORDS[count]
        else:
            n = str(count)
        return {
            "n": n,
            "n_cap": n[:1].upper() + n[1:],
            "N": str(count),
            "entity": self.entity,
            "entities": self.entities,
            **self.vars,
        }

    def fill(self, template: str, count: int, **extra: str) -> str:
        return template.format_map({**self.context(count), **extra})


@lru_cache(maxsize=1)
def load_themes() -> tuple[Theme, ...]:
    themes = []
    for path in THEME_DIR.glob("*.json"):
        if path.name == "common.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        themes.append((data.get("order", 99), Theme(data)))
    themes.sort(key=lambda t: (t[0], t[1].name))
    return tuple(theme for _, theme in themes)
