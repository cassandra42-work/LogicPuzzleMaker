from __future__ import annotations

import base64
import hashlib
import json
from html import escape
from pathlib import Path

from .model import Puzzle
from .style import MARK_COLORS, category_color

CSS = """
:root {
  --cell: 30px;
  --ink: #1f2328;
  --muted: #5f6368;
  --line: #9aa0a6;
  --thin: 1px solid var(--line);
  --thick: 2px solid var(--ink);
  --page: #f4f2ee;
  --paper: #ffffff;
  --hover: #e8f0fb;
  --x: __X_COLOR__;
  --o: __O_COLOR__;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 2000px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { text-align: center; margin: 0 0 8px; font-size: 1.8rem; }
.story { max-width: 70ch; margin: 0 auto 12px; line-height: 1.55; }
.help { text-align: center; color: var(--muted); margin: 0 0 12px; font-size: .9rem; }
/* Wide screens: notes | grid | clues. Medium: notes go under the clues.
   Narrow: everything stacks. */
.layout {
  display: grid; gap: 24px; justify-content: center; align-items: start;
  grid-template-columns: minmax(220px, 320px) minmax(0, max-content) minmax(280px, 440px);
  grid-template-areas: "notes sheet clues";
}
.layout > .sheet { grid-area: sheet; min-width: 0; }
.layout > .clues { grid-area: clues; }
.layout > .notes { grid-area: notes; }
@media (max-width: 1500px) {
  .layout {
    grid-template-columns: minmax(0, max-content) minmax(280px, 440px);
    grid-template-areas: "sheet clues" "sheet notes";
  }
}
@media (max-width: 900px) {
  .layout { grid-template-columns: minmax(0, 1fr); grid-template-areas: "sheet" "clues" "notes"; }
}
.clues, .notes {
  background: var(--paper); padding: 16px 20px;
  border-radius: 8px; box-shadow: 0 1px 3px rgba(0, 0, 0, .12);
}
.clues h2, .notes h2 { margin: 0 0 8px; font-size: 1.15rem; }
.notes-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.notes-head h2 { margin: 0; }
.notes-head button {
  font: inherit; font-size: .8rem; padding: 3px 10px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--ink);
}
.notes-head button:hover { background: var(--hover); }
.notes textarea {
  display: block; width: 100%; height: 14rem; min-height: 4rem; resize: vertical; overflow: auto;
  font: inherit; line-height: 1.45; padding: 8px 10px; color: var(--ink); background: var(--paper);
  border: 1px solid var(--line); border-radius: 6px;
}
.notes.expanded textarea { height: 40rem; }
.answers-title { text-align: center; font-size: 1.05rem; margin: 24px 0 8px; }
table.answers { border-collapse: collapse; margin: 0 auto; border: var(--thick); font-size: .9rem; }
table.answers th, table.answers td { border: var(--thin); padding: 4px 8px; text-align: left; }
table.answers thead th { border-bottom: var(--thick); -webkit-print-color-adjust: exact; print-color-adjust: exact; }
table.answers td { padding: 2px 4px; }
table.answers select {
  font: inherit; width: 100%; min-width: 7.5em; padding: 2px; color: var(--ink);
  background: transparent; border: none; cursor: pointer;
}
.clues ol { margin: 0; padding-left: 1.6em; }
.clues li { margin: 0 0 8px; line-height: 1.45; cursor: pointer; }
.clues li:hover { color: #0b57d0; }
.clues li.done { text-decoration: line-through; color: var(--muted); }
.clues .clue-help { color: var(--muted); font-size: .8rem; margin: 10px 0 0; }
.toolbar { display: flex; gap: 8px; justify-content: center; margin-bottom: 16px; }
.toolbar button {
  font: inherit; font-size: .9rem; padding: 6px 14px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--ink);
}
.toolbar button:hover { background: var(--hover); }
.sheet {
  overflow-x: auto; background: var(--paper); padding: 16px;
  border-radius: 8px; box-shadow: 0 1px 3px rgba(0, 0, 0, .12);
}
table.grid { border-collapse: collapse; margin: 0 auto; }
.grid th, .grid td { padding: 0; border: var(--thin); }
.grid .corner { border: none; }
.grid th { font-weight: 500; font-size: .85rem; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.grid .band { font-weight: 700; padding: 4px 6px; text-align: center; }
.grid .band-top .fit { width: 0; min-width: 100%; overflow-wrap: anywhere; }
.grid .top-label { vertical-align: bottom; padding: 6px 0; }
.grid .vertical { writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; display: inline-block; }
.grid .band-left .vertical { white-space: normal; }
.grid .left-label { text-align: right; padding: 0 8px; white-space: nowrap; height: var(--cell); }
.grid td.cell {
  width: var(--cell); min-width: var(--cell); height: var(--cell);
  text-align: center; vertical-align: middle; cursor: pointer; user-select: none;
  font-weight: 700; font-size: calc(var(--cell) * .6); line-height: 1; background: var(--paper);
  touch-action: none;
}
.grid td.cell:hover, .grid td.cell:focus-visible { background: var(--hover); outline: none; }
.grid td.cell.wrong { background: #fdecea; box-shadow: inset 0 0 0 2px var(--x); }
.toolbar button:disabled { opacity: .5; cursor: not-allowed; }
.toolbar button:disabled:hover { background: var(--paper); }
.result { text-align: center; min-height: 1.4em; margin: 0 0 12px; font-weight: 600; }
.result.good { color: var(--o); }
.result.bad { color: var(--x); }
.grid td.cell[data-mark="X"]::after { content: "X"; color: var(--x); }
.grid td.cell[data-mark="O"]::after { content: "O"; color: var(--o); }
.grid .bl { border-left: var(--thick); }
.grid .br { border-right: var(--thick); }
.grid .bt { border-top: var(--thick); }
.grid .bb { border-bottom: var(--thick); }
@media print {
  body { background: #fff; }
  .help, .toolbar, .clue-help, .result, .notes { display: none; }
  .grid td.cell.wrong { background: #fff; box-shadow: none; }
  .sheet, .clues { box-shadow: none; padding: 0; overflow: visible; }
  table.answers select { appearance: none; -webkit-appearance: none; }
  .clues li.done { text-decoration: none; color: var(--ink); }
  .grid td.cell:hover { background: #fff; }
}
"""
CSS = CSS.replace("__X_COLOR__", MARK_COLORS["X"])
CSS = CSS.replace("__O_COLOR__", MARK_COLORS["O"])

SCRIPT = """
(() => {
  // Keyed by title and seed: a later puzzle that reuses a title gets a fresh start.
  const KEY = "grid-logic:" + PUZZLE_ID;
  const ORDER = ["", "X", "O"];
  const grid = document.getElementById("grid");
  const cells = Array.from(grid.querySelectorAll("td.cell"));
  const clues = Array.from(document.querySelectorAll("#clues li"));
  const picks = Array.from(document.querySelectorAll("#answers select"));
  const notes = document.getElementById("notes");
  const notesBox = document.querySelector(".notes");
  const notesToggle = document.getElementById("notes-toggle");
  const checkButton = document.getElementById("check");
  const result = document.getElementById("result");

  // Where each square sits: left-side category row r, block b, row i, column j.
  const pos = new Map(cells.map((c) => {
    const [, r, b, i, j] = c.id.split("_").map(Number);
    return [c, { r, b, i, j }];
  }));
  const at = (r, b, i, j) => document.getElementById(`cell_${r}_${b}_${i}_${j}`);

  // Each row and column of each block, for finishing a line with its O.
  const lines = new Map();
  const lineKeys = (p) => [`${p.r}_${p.b}_row${p.i}`, `${p.r}_${p.b}_col${p.j}`];
  for (const c of cells) {
    for (const key of lineKeys(pos.get(c))) {
      if (!lines.has(key)) lines.set(key, []);
      lines.get(key).push(c);
    }
  }
  // After an X is placed: if its row or column is all X's but one blank
  // square, that square must be the O. Only placing an X triggers this, so
  // turning the O back to blank sticks.
  function finishLines(cell) {
    for (const key of lineKeys(pos.get(cell))) {
      const line = lines.get(key);
      const blanks = line.filter((c) => !c.dataset.mark);
      const xs = line.filter((c) => c.dataset.mark === "X");
      if (blanks.length === 1 && xs.length === line.length - 1) setMark(blanks[0], "O");
    }
  }

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; }
  }
  function save() {
    const state = {
      cells: {}, clues: [], answers: {},
      notes: notes.value, notesBig: notesBox.classList.contains("expanded"),
    };
    for (const c of cells) if (c.dataset.mark) state.cells[c.id] = c.dataset.mark;
    clues.forEach((li, i) => { if (li.classList.contains("done")) state.clues.push(i); });
    for (const p of picks) if (p.value) state.answers[p.dataset.key] = p.value;
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
    refresh();
  }
  function refresh() {
    const full = cells.every((c) => c.dataset.mark);
    checkButton.disabled = !full;
    checkButton.title = full ? "" : "Fill in every square to check your answers";
  }
  function setMark(cell, mark) {
    if (mark) cell.dataset.mark = mark; else delete cell.dataset.mark;
    cell.setAttribute("aria-label", cell.title + (mark ? ": " + mark : ": blank"));
    cell.classList.remove("wrong");
    result.textContent = "";
    result.className = "result";
  }
  function step(cell, dir) {
    const i = ORDER.indexOf(cell.dataset.mark || "");
    setMark(cell, ORDER[(i + dir + ORDER.length) % ORDER.length]);
    if (cell.dataset.mark === "X") finishLines(cell);
    save();
  }

  const saved = load();
  const savedCells = saved.cells || {};
  for (const c of cells) setMark(c, savedCells[c.id] || "");
  for (const i of saved.clues || []) if (clues[i]) clues[i].classList.add("done");
  const savedAnswers = saved.answers || {};
  for (const p of picks) p.value = savedAnswers[p.dataset.key] || "";
  notes.value = saved.notes || "";
  function sizeNotes(big) {
    notesBox.classList.toggle("expanded", big);
    notes.style.height = "";  // drop any size set by dragging the corner
    notesToggle.textContent = big ? "Shrink" : "Expand";
    notesToggle.setAttribute("aria-expanded", String(big));
  }
  sizeNotes(Boolean(saved.notesBig));
  refresh();

  for (const li of clues) {
    li.addEventListener("click", () => { li.classList.toggle("done"); save(); });
  }
  for (const p of picks) p.addEventListener("change", save);
  notes.addEventListener("input", save);
  notesToggle.addEventListener("click", () => {
    sizeNotes(!notesBox.classList.contains("expanded"));
    save();
  });

  // Click cycles a square. Pressing on a square and dragging along its row or
  // column copies that square to the squares passed over, inside its block:
  // from an X it fills X's (leaving O's alone); from a blank it clears X's
  // and O's. Dragging from an O does nothing, since a row holds only one O.
  let drag = null;
  const cellUnder = (e) => {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    return el && el.closest ? el.closest("td.cell") : null;
  };
  grid.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const c = e.target.closest("td.cell");
    if (!c) return;
    e.preventDefault();
    drag = { start: c, from: c.dataset.mark || "", axis: null };
  });
  grid.addEventListener("pointermove", (e) => {
    if (!drag || drag.from === "O") return;
    const c = cellUnder(e);
    if (!c || c === drag.start) return;
    const s = pos.get(drag.start), t = pos.get(c);
    if (t.r !== s.r || t.b !== s.b) return;
    if (!drag.axis) {
      if (t.i === s.i) drag.axis = "row";
      else if (t.j === s.j) drag.axis = "col";
      else return;
    }
    const fill = drag.from === "X"
      ? (cell) => { if (cell.dataset.mark !== "O") setMark(cell, "X"); }
      : (cell) => { if (cell.dataset.mark) setMark(cell, ""); };
    const passed = [];
    if (drag.axis === "row") {
      for (let j = Math.min(s.j, t.j); j <= Math.max(s.j, t.j); j++) passed.push(at(s.r, s.b, s.i, j));
    } else {
      for (let i = Math.min(s.i, t.i); i <= Math.max(s.i, t.i); i++) passed.push(at(s.r, s.b, i, s.j));
    }
    passed.forEach(fill);
    if (drag.from === "X") passed.forEach((c) => { if (c.dataset.mark === "X") finishLines(c); });
    save();
  });
  window.addEventListener("pointerup", (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.axis && cellUnder(e) === d.start) step(d.start, 1);
  });
  window.addEventListener("pointercancel", () => { drag = null; });

  grid.addEventListener("contextmenu", (e) => {
    const c = e.target.closest("td.cell");
    if (c) { e.preventDefault(); step(c, -1); }
  });
  grid.addEventListener("keydown", (e) => {
    const c = e.target.closest("td.cell");
    if (!c) return;
    const key = e.key.toLowerCase();
    if (key === "enter" || key === " ") step(c, 1);
    else if (key === "x" || key === "o") {
      setMark(c, key.toUpperCase());
      if (key === "x") finishLines(c);
      save();
    }
    else if (key === "backspace" || key === "delete") { setMark(c, ""); save(); }
    else return;
    e.preventDefault();
  });

  document.getElementById("clear").addEventListener("click", () => {
    if (!confirm("Clear every mark, crossed-off clue, and answer table entry? Your notes are kept.")) return;
    for (const c of cells) setMark(c, "");
    for (const li of clues) li.classList.remove("done");
    for (const p of picks) p.value = "";
    save();
  });
  document.getElementById("print").addEventListener("click", () => window.print());

  // The answer is stored scrambled so it isn't readable in the page source.
  const bytes = (b64) => Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
  const key = bytes(ANSWER_KEY), data = bytes(ANSWER_DATA);
  const answer = [];
  data.forEach((byte, n) => {
    const v = byte ^ key[n % key.length];
    for (let bit = 7; bit >= 0; bit--) answer.push((v >> bit) & 1 ? "O" : "X");
  });
  checkButton.addEventListener("click", () => {
    let wrong = 0;
    cells.forEach((c, n) => {
      const bad = c.dataset.mark !== answer[n];
      c.classList.toggle("wrong", bad);
      if (bad) wrong++;
    });
    if (wrong) {
      result.textContent = `Not quite: ${wrong} square${wrong === 1 ? " is" : "s are"} wrong (outlined in red).`;
      result.className = "result bad";
    } else {
      result.textContent = "Solved! Every square is correct.";
      result.className = "result good";
    }
  });
})();
"""


def _edge_classes(i: int, j: int, k: int) -> str:
    classes = []
    if j == 0:
        classes.append("bl")
    if j == k - 1:
        classes.append("br")
    if i == 0:
        classes.append("bt")
    if i == k - 1:
        classes.append("bb")
    return " ".join(classes)


def _grid_table(puzzle: Puzzle) -> str:
    k = puzzle.size
    top = puzzle.top_categories
    rows: list[str] = []

    # Top Categories
    head = ['<td class="corner" colspan="2" rowspan="2"></td>']
    for cat in top:
        color = category_color(puzzle.color_index(cat))
        head.append(
            f'<th class="band band-top bl br bt" colspan="{k}" style="background:{color}">'
            f'<div class="fit">{escape(cat.name)}</div></th>'
        )
    rows.append("<tr>" + "".join(head) + "</tr>")

    labels = []
    for cat in top:
        color = category_color(puzzle.color_index(cat))
        for j, value in enumerate(cat.values):
            cls = _edge_classes(k - 1, j, k)  # thick sides and bottom
            labels.append(
                f'<th class="top-label {cls}" style="background:{color}" scope="col">'
                f'<span class="vertical">{escape(value)}</span></th>'
            )
    rows.append("<tr>" + "".join(labels) + "</tr>")

    # Left Categories
    for r, left in enumerate(puzzle.left_categories):
        color = category_color(puzzle.color_index(left))
        for i, row_value in enumerate(left.values):
            parts = []
            if i == 0:
                parts.append(
                    f'<th class="band band-left bl bt bb" rowspan="{k}" style="background:{color}">'
                    f'<span class="vertical">{escape(left.name)}</span></th>'
                )
            parts.append(
                f'<th class="left-label {_edge_classes(i, k - 1, k)}" '
                f'style="background:{color}" scope="row">{escape(row_value)}</th>'
            )
            for c in range(puzzle.blocks_in_row(r)):
                for j, col_value in enumerate(top[c].values):
                    label = escape(f"{row_value} / {col_value}", quote=True)
                    parts.append(
                        f'<td class="cell {_edge_classes(i, j, k)}" id="cell_{r}_{c}_{i}_{j}" '
                        f'tabindex="0" role="button" title="{label}"></td>'
                    )
            rows.append("<tr>" + "".join(parts) + "</tr>")

    return '<table class="grid" id="grid">\n' + "\n".join(rows) + "\n</table>"


def _clue_list(puzzle: Puzzle) -> str:
    items = "\n".join(f"<li>{escape(clue.text)}</li>" for clue in puzzle.clues)
    return (
        '<section class="clues">\n<h2>Clues</h2>\n'
        f'<ol id="clues">\n{items}\n</ol>\n'
        '<p class="clue-help">Click a clue to cross it off.</p>\n</section>'
    )


def _answer_table(puzzle: Puzzle) -> str:
    cats = puzzle.categories
    head = "".join(
        f'<th scope="col" style="background:{category_color(n)}">{escape(c.name)}</th>'
        for n, c in enumerate(cats)
    )
    rows = []
    for e, value in enumerate(cats[0].values):
        cells = [f'<th scope="row" style="background:{category_color(0)}">{escape(value)}</th>']
        for j, cat in enumerate(cats[1:], 1):
            options = ['<option value=""></option>']
            for v in cat.values:
                options.append(f'<option value="{escape(v, quote=True)}">{escape(v)}</option>')
            option_html = "".join(options)
            label = escape(f"{cat.name} for {value}", quote=True)
            cells.append(
                f'<td><select data-key="{e}_{j}" aria-label="{label}">{option_html}</select></td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<h2 class="answers-title">Answer Table</h2>\n'
        f'<table class="answers" id="answers">\n<thead><tr>{head}</tr></thead>\n'
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"
    )


NOTES_PANEL = """<section class="notes">
<div class="notes-head"><h2>Notes</h2>
<button type="button" id="notes-toggle" aria-controls="notes" aria-expanded="false">Expand</button></div>
<textarea id="notes" aria-label="Notes" placeholder="Jot down ideas, deductions, or anything else."></textarea>
</section>"""


def _scrambled_answer(puzzle: Puzzle) -> tuple[str, str]:
    bits = []
    for r, left in enumerate(puzzle.left_categories):
        li = puzzle.color_index(left)
        for i in range(puzzle.size):
            for c in range(puzzle.blocks_in_row(r)):
                ti = puzzle.color_index(puzzle.top_categories[c])
                for j in range(puzzle.size):
                    bits.append(puzzle.matches(li, i, ti, j))
    data = bytearray((len(bits) + 7) // 8)
    for n, bit in enumerate(bits):
        if bit:
            data[n // 8] |= 0x80 >> (n % 8)
    seed_text = f"{puzzle.title}|{puzzle.seed}"
    key = hashlib.sha256(seed_text.encode()).digest()[:16]
    scrambled = bytearray()
    for n, b in enumerate(data):
        scrambled.append(b ^ key[n % len(key)])
    key_text = base64.b64encode(key).decode()
    data_text = base64.b64encode(scrambled).decode()
    return key_text, data_text


def render_html(puzzle: Puzzle) -> str:
    title = escape(puzzle.title)
    puzzle_id = json.dumps(f"{puzzle.title}|{puzzle.seed}")
    puzzle_id = puzzle_id.replace("</", "<\\/")  # a title can't end the script tag early
    key, data = _scrambled_answer(puzzle)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p class="story">{escape(puzzle.story)}</p>
<p class="help">Click a square to cycle X &rarr; O &rarr; blank. Right-click to go back a step.<br>
Drag from an X along a row or column to fill in X's, or from a blank square to clear.<br>
When only one blank square is left in a row or column of X's, it becomes the O.</p>
<div class="toolbar">
<button type="button" id="check" disabled>Check answers</button>
<button type="button" id="clear">Start over</button>
<button type="button" id="print">Print</button>
</div>
<p id="result" class="result" role="status"></p>
<div class="layout">
{NOTES_PANEL}
<div class="sheet">
{_grid_table(puzzle)}
{_answer_table(puzzle)}
</div>
{_clue_list(puzzle)}
</div>
</main>
<script>
const PUZZLE_ID = {puzzle_id};
const ANSWER_KEY = "{key}";
const ANSWER_DATA = "{data}";
{SCRIPT}
</script>
</body>
</html>
"""


def write_html(puzzle: Puzzle, path: Path) -> Path:
    path.write_text(render_html(puzzle), encoding="utf-8")
    return path
