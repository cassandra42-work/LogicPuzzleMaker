from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations


@dataclass(frozen=True)
class Ref:
    cat: int
    val: int


@dataclass
class Clue:
    kind: str
    refs: tuple[Ref, ...]
    order_cat: int | None = None
    diff: Fraction | None = None
    text: str = field(default="", compare=False)


class Contradiction(Exception):
    pass


class Grid:
    def __init__(self, n: int, k: int):
        full = (1 << k) - 1
        self.n = n
        self.k = k
        self.p = []
        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(None)
                else:
                    row.append([full] * k)
            self.p.append(row)
        self.changed = False

    def copy(self) -> "Grid":
        other = Grid.__new__(Grid)
        other.n = self.n
        other.k = self.k
        other.changed = False
        other.p = []
        for rows in self.p:
            copied = []
            for row in rows:
                copied.append(None if row is None else row[:])
            other.p.append(copied)
        return other

    def can(self, x: Ref, y: Ref) -> bool:
        if x.cat == y.cat:
            return x.val == y.val
        possible = self.p[x.cat][y.cat][x.val]
        return bool(possible >> y.val & 1)

    def sure(self, x: Ref, y: Ref) -> bool:
        if x.cat == y.cat:
            return x.val == y.val
        possible = self.p[x.cat][y.cat][x.val]
        return possible == 1 << y.val

    def remove(self, x: Ref, y: Ref) -> None:
        if x.cat == y.cat:
            if x.val == y.val:
                raise Contradiction
            return
        row = self.p[x.cat][y.cat]
        if row[x.val] >> y.val & 1:
            row[x.val] &= ~(1 << y.val)
            col = self.p[y.cat][x.cat]
            col[y.val] &= ~(1 << x.val)
            if not row[x.val] or not col[y.val]:
                raise Contradiction
            self.changed = True

    def join(self, x: Ref, y: Ref) -> None:
        if x.cat == y.cat:
            if x.val != y.val:
                raise Contradiction
            return
        for v in range(self.k):
            if v != y.val:
                self.remove(x, Ref(y.cat, v))
            if v != x.val:
                self.remove(Ref(x.cat, v), y)

    def solved(self) -> bool:
        for j in range(1, self.n):
            for row in self.p[0][j]:
                if row & (row - 1):
                    return False
        return True


def _apply_rules(g: Grid) -> None:
    n, k = g.n, g.k

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            rows = g.p[i][j]
            for a in range(k):
                row = rows[a]
                if row & (row - 1) == 0:
                    b = row.bit_length() - 1
                    for other in range(k):
                        if other != a and rows[other] >> b & 1:
                            g.remove(Ref(i, other), Ref(j, b))

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            pij = g.p[i][j]
            for l in range(n):
                if l == i or l == j:
                    continue
                pil, pjl = g.p[i][l], g.p[j][l]
                for a in range(k):
                    row, b = pij[a], 0
                    while row:
                        if row & 1 and not pil[a] & pjl[b]:
                            g.remove(Ref(i, a), Ref(j, b))
                        row >>= 1
                        b += 1


def _exclude_unless_any(g: Grid, x: Ref, options: tuple[Ref, ...]) -> None:
    for cat in range(g.n):
        if cat == x.cat:
            continue
        for v in range(g.k):
            y = Ref(cat, v)
            if g.can(x, y) and not any(g.can(o, y) for o in options):
                g.remove(x, y)


def _apply_clue(g: Grid, clue: Clue, keys: dict[int, list[Fraction]]) -> None:
    r = clue.refs
    kind = clue.kind
    if kind == "same":
        g.join(r[0], r[1])
    elif kind == "different":
        g.remove(r[0], r[1])
    elif kind == "neither":
        g.remove(r[0], r[2])
        g.remove(r[1], r[2])
    elif kind == "distinct":
        for x, y in combinations(r, 2):
            g.remove(x, y)
    elif kind == "either":
        a, b, c = r
        g.remove(b, c)
        if not g.can(a, b):
            g.join(a, c)
        elif not g.can(a, c):
            g.join(a, b)
        elif g.sure(a, b):
            g.remove(a, c)
        elif g.sure(a, c):
            g.remove(a, b)
        _exclude_unless_any(g, a, (b, c))
    elif kind == "pair":
        a, b, c, d = r
        g.remove(a, b)
        g.remove(c, d)
        #if a can't be c, it has to be d, etc
        if not g.can(a, c):
            g.join(a, d)
        if not g.can(a, d):
            g.join(a, c)
        if not g.can(b, c):
            g.join(b, d)
        if not g.can(b, d):
            g.join(b, c)
        if g.sure(a, c):
            g.join(b, d)
        if g.sure(a, d):
            g.join(b, c)
        _exclude_unless_any(g, a, (c, d))
        _exclude_unless_any(g, b, (c, d))
        _exclude_unless_any(g, c, (a, b))
        _exclude_unless_any(g, d, (a, b))
    elif kind == "greater":
        a, b = r
        o = clue.order_cat
        kk = keys[o]
        g.remove(a, b)

        def fits(high: int, low: int) -> bool:
            if high == low:
                return False
            if clue.diff is not None:
                return kk[high] - kk[low] == clue.diff
            return kk[high] > kk[low]

        for v in range(g.k):
            x = Ref(o, v)
            # a can only have v if b can still have a lower value
            if g.can(a, x):
                b_fits = any(fits(v, w) and g.can(b, Ref(o, w)) for w in range(g.k))
                if not b_fits:
                    g.remove(a, x)
            # b can only have v if a can still have a higher value
            if g.can(b, x):
                a_fits = any(fits(w, v) and g.can(a, Ref(o, w)) for w in range(g.k))
                if not a_fits:
                    g.remove(b, x)
    else:
        raise ValueError(f"Unknown clue kind: {kind}")


def propagate(g: Grid, clues: list[Clue], keys: dict[int, list[Fraction]]) -> Grid:
    while True:
        g.changed = False
        for clue in clues:
            _apply_clue(g, clue, keys)
        _apply_rules(g)
        if not g.changed:
            return g


def solve(n: int, k: int, clues: list[Clue], keys: dict[int, list[Fraction]]) -> Grid:
    return propagate(Grid(n, k), clues, keys)
