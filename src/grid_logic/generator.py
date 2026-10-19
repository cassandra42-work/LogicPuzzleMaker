from __future__ import annotations

import random
import re

from .logic import Clue, Grid, Ref, propagate, solve
from .model import Category, Puzzle
from .ordering import Ordering, detect_ordering
from .phrasing import Phraser, category_word, natural_join
from .themes import ResolvedTheme

# how often each kind of clue is drawn. 
CLUE_WEIGHTS = {
    "same": 1.0,
    "different": 3.0,
    "either": 2.0,
    "neither": 1.5,
    "pair": 1.5,
    "distinct": 1.0,
    "greater": 3.0,
    "greater_by": 2.0,
}
MAX_DRAWS = 3000


def orderings_for(categories: list[Category]) -> dict[int, Ordering]:
    result = {}
    for index, category in enumerate(categories):
        ordering = detect_ordering(category.values)
        if ordering:
            result[index] = ordering
    return result


class _Sampler:
    def __init__(self, n: int, k: int, assign, orderings: dict[int, Ordering], rng):
        self.n = n
        self.k = k
        self.assign = assign
        self.rng = rng
        self.orderings = orderings
        self.keys = {cat: o.keys for cat, o in orderings.items()}
        kinds = dict(CLUE_WEIGHTS)
        if k < 3:
            kinds.pop("neither")
            kinds.pop("distinct")
        if not orderings:
            kinds.pop("greater")
        if not any(o.supports_difference for o in orderings.values()):
            kinds.pop("greater_by")
        self.kinds = list(kinds)
        self.weights = [kinds[kind] for kind in self.kinds]

    def ref(self, cat: int, entity: int) -> Ref:
        return Ref(cat, self.assign[cat][entity])

    def draw(self) -> Clue | None:
        kind = self.rng.choices(self.kinds, self.weights)[0]
        return getattr(self, "_" + kind)()

    def _same(self):
        e = self.rng.randrange(self.k)
        i, j = self.rng.sample(range(self.n), 2)
        return Clue("same", (self.ref(i, e), self.ref(j, e)))

    def _different(self):
        e1, e2 = self.rng.sample(range(self.k), 2)
        i, j = self.rng.sample(range(self.n), 2)
        return Clue("different", (self.ref(i, e1), self.ref(j, e2)))

    def _either(self):
        e1, e2 = self.rng.sample(range(self.k), 2)
        i = self.rng.randrange(self.n)
        others = [c for c in range(self.n) if c != i]
        b = self.ref(self.rng.choice(others), e1)
        c = self.ref(self.rng.choice(others), e2)
        if self.rng.random() < 0.5:
            b, c = c, b
        return Clue("either", (self.ref(i, e1), b, c))

    def _neither(self):
        e1, e2, e3 = self.rng.sample(range(self.k), 3)
        j = self.rng.randrange(self.n)
        others = [c for c in range(self.n) if c != j]
        a = self.ref(self.rng.choice(others), e1)
        b = self.ref(self.rng.choice(others), e2)
        return Clue("neither", (a, b, self.ref(j, e3)))

    def _pair(self):
        e1, e2 = self.rng.sample(range(self.k), 2)
        i = self.rng.randrange(self.n)
        i2 = i
        if self.rng.random() >= 0.5:
            i2 = self.rng.randrange(self.n)
        rest = [c for c in range(self.n) if c not in (i, i2)]
        if not rest:
            return None
        j = self.rng.choice(rest)
        j2 = j
        if self.rng.random() >= 0.5:
            j2 = self.rng.choice(rest)
        c, d = self.ref(j, e1), self.ref(j2, e2)
        if self.rng.random() < 0.5:
            c, d = d, c
        return Clue("pair", (self.ref(i, e1), self.ref(i2, e2), c, d))

    def _distinct(self):
        size = min(self.k, self.rng.choice([3, 3, 4]))
        entities = self.rng.sample(range(self.k), size)
        if self.n >= size:
            cats = self.rng.sample(range(self.n), size)
        else:
            cats = [self.rng.randrange(self.n) for _ in entities]
        if len(set(cats)) == 1:
            return None
        refs = []
        for c, e in zip(cats, entities):
            refs.append(self.ref(c, e))
        return Clue("distinct", tuple(refs))

    def _greater(self, exact: bool = False):
        choices = []
        for cat, ordering in self.orderings.items():
            if ordering.supports_difference or not exact:
                choices.append(cat)
        o = self.rng.choice(choices)
        keys = self.keys[o]
        e1, e2 = self.rng.sample(range(self.k), 2)
        if keys[self.assign[o][e1]] < keys[self.assign[o][e2]]:
            e1, e2 = e2, e1
        others = [c for c in range(self.n) if c != o]
        a = self.ref(self.rng.choice(others), e1)
        b = self.ref(self.rng.choice(others), e2)
        diff = None
        if exact:
            diff = keys[self.assign[o][e1]] - keys[self.assign[o][e2]]
        return Clue("greater", (a, b), order_cat=o, diff=diff)

    def _greater_by(self):
        return self._greater(exact=True)


def _missing_fact(g: Grid, sampler: _Sampler) -> Clue:
    for j in range(1, g.n):
        for a in range(g.k):
            row = g.p[0][j][a]
            if row & (row - 1):
                return Clue("same", (Ref(0, a), sampler.ref(j, a)))
    raise AssertionError("Grid is already solved.")


def build_clues(n, k, assign, orderings, rng) -> list[Clue]:
    sampler = _Sampler(n, k, assign, orderings, rng)
    keys = sampler.keys
    clues: list[Clue] = []
    grid = solve(n, k, clues, keys)
    draws = 0
    while not grid.solved():
        draws += 1
        if draws < MAX_DRAWS:
            clue = sampler.draw()
        else:
            clue = _missing_fact(grid, sampler)
        if clue is None or clue in clues:
            continue
        trial = propagate(grid.copy(), clues + [clue], keys)
        if trial.p == grid.p:
            continue  # tells the solver nothing new
        clues.append(clue)
        grid = trial

    #drop clues the puzzle doesn't need.
    order = sorted(clues, key=lambda c: (c.kind != "same", rng.random()))
    kept = list(clues)
    for clue in order:
        without = [c for c in kept if c is not clue]
        if solve(n, k, without, keys).solved():
            kept = without
    rng.shuffle(kept)
    return kept


def random_solution(n: int, k: int, rng: random.Random) -> list[list[int]]:
    assign = [list(range(k))]
    for _ in range(1, n):
        perm = list(range(k))
        rng.shuffle(perm)
        assign.append(perm)
    return assign


def write_story(theme: ResolvedTheme, categories: list[Category], rng) -> str:
    count = len(categories[0].values)
    roles = {c.role for c in categories}

    # Only stories whose needed categories are all in this puzzle.
    fitting = []
    for story_text, needs in theme.stories:
        if needs <= roles:
            fitting.append(story_text)
    story = ""
    if fitting:
        story = theme.fill(rng.choice(fitting), count)

    # The task lists the categories to match up, leaving out the people.
    named = []
    for c in categories:
        if not theme.role(c.role).person:
            named.append(c)
    if not named:
        named = categories
    cat_list = natural_join([category_word(c.name) for c in named])
    task = theme.fill(rng.choice(theme.tasks), count, cat_list=cat_list)

    text = f"{story} {task}".strip()
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m[1] + m[2].upper(), text)


def write_title(theme: ResolvedTheme, count: int, rng) -> str:
    return theme.fill(rng.choice(theme.titles), count)


def create_puzzle(
    categories: list[Category],
    theme: ResolvedTheme,
    seed: int,
    title: str | None = None,
) -> Puzzle:
    rng = random.Random(seed)
    n = len(categories)
    k = len(categories[0].values)
    orderings = orderings_for(categories)
    assign = random_solution(n, k, rng)
    clues = build_clues(n, k, assign, orderings, rng)

    phraser = Phraser(theme, categories, orderings, rng)
    for clue in clues:
        clue.text = phraser.text(clue)

    solution = []
    for e in range(k):
        solution.append([assign[cat][e] for cat in range(n)])

    return Puzzle(
        title=title or write_title(theme, k, rng),
        categories=categories,
        story=write_story(theme, categories, rng),
        clues=clues,
        solution=solution,
        seed=seed,
    )

