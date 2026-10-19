from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

from .generator import create_puzzle, write_title
from .model import (
    MAX_CATEGORIES,
    MIN_CATEGORIES,
    Category,
    check_values,
    parse_value_list,
    title_case,
)
from .ordering import detect_ordering
from .output import DEFAULT_OUTPUT_DIR, save_puzzle, unique_title
from .style import APP_NAME
from .themes import ResolvedTheme, Theme, load_themes

DEFAULT_CATEGORIES = 4
DEFAULT_VALUES = 5
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def use_color() -> bool:
    if "NO_COLOR" in os.environ or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")  # switches older Windows consoles into ANSI mode
    return True


def file_link(path: Path, color: bool, ansi: str = YELLOW) -> str:
    path = path.resolve()
    if not color:
        return str(path)
    return f"\033]8;;{path.as_uri()}\033\\{ansi}{path}{RESET}\033]8;;\033\\"


def ask(prompt: str) -> str:
    return input(prompt).strip()


def ask_int(prompt: str, low: int, high: int, default: int | None = None) -> int:
    hint = f" [{default}]" if default is not None else ""
    while True:
        answer = ask(f"{prompt}{hint}: ")
        if not answer and default is not None:
            return default
        if answer.isdigit() and low <= int(answer) <= high:
            return int(answer)
        print(f"  Please enter a whole number from {low} to {high}.")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        answer = ask(f"{prompt} {hint} ").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer y or n.")


def ask_choice(
    prompt: str, options: list[tuple[str, str]], default: int | None = None, indent: str = ""
) -> int:
    print(f"{indent}{prompt}")
    for number, (label, detail) in enumerate(options, 1):
        line = f"{indent}  {number}. {label}"
        if detail:
            line += f"  ({detail})"
        print(line)
    hint = f" [{default + 1}]" if default is not None else ""
    while True:
        answer = ask(f"{indent}Choose 1-{len(options)}{hint}: ")
        if not answer and default is not None:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1
        print(f"{indent}  Please enter a number from 1 to {len(options)}.")


def ask_theme() -> Theme:
    themes = load_themes()
    index = ask_choice("What theme would you like?", [(t.name, t.blurb) for t in themes])
    return themes[index]


def ask_theme_options(theme: Theme) -> dict[str, str]:
    answers = {}
    for option in theme.options:
        print()
        if option.kind == "choice":
            labels = [(choice.title(), "") for choice in option.choices]
            index = ask_choice(option.prompt, labels, 0)
            answers[option.key] = option.choices[index]
        else:
            hint = f" [{option.default}]" if option.default else ""
            while True:
                answer = ask(f"{option.prompt}{hint}: ") or option.default
                if answer:
                    break
                print("  Please enter an answer.")
            answers[option.key] = answer
    return answers


def ask_category(
    number: int,
    theme: ResolvedTheme,
    done: list[Category],
    rng: random.Random,
) -> Category:
    expected = len(done[0].values) if done else None
    used_roles = [c.role for c in done]
    taken = {c.name.casefold() for c in done}

    while True:
        print()
        name = title_case(ask(f"Category {number} name: "))
        if not name:
            print("  The category needs a name.")
            continue
        if name.casefold() in taken:
            print(f'  You already have a category called "{name}".')
            continue

        role_ids = theme.role_order
        guess = theme.match_role(name, used_roles) or theme.roles["other"]
        index = ask_choice(
            f"What kind of category is {name}? (this shapes how clues are worded)",
            [(theme.roles[r].label, theme.roles[r].hint) for r in role_ids],
            role_ids.index(guess.id),
            indent="  ",
        )
        role = theme.roles[role_ids[index]]

        sample = role.sample_values(expected or DEFAULT_VALUES, rng)
        count_hint = f", {expected} values" if expected else ""
        print(f"  Values for {name}, separated by commas{count_hint}")
        if sample:
            print(f"  Press Enter to use: {', '.join(sample)}")
        elif role.hint:
            print(f"  For example: {role.hint}")
        answer = ask("  > ")
        values = parse_value_list(answer) if answer else sample
        problem = check_values(values, expected)
        if problem:
            print(f"  {problem} Let's try this category again.")
            continue

        print(f"\n  {name} ({role.label.lower()}):")
        for i, value in enumerate(values, 1):
            print(f"    {i}. {value}")
        if detect_ordering(values):
            print("  These have a natural order, so clues can compare them.")
        if ask_yes_no("  Is this correct?"):
            return Category(name, values, role.id)
        print("  No problem, let's redo this category.")


def ask_title(output_dir: Path) -> str | None:
    print()
    print("Puzzle title")
    print("  Leave this blank and a title will be generated for you based on the theme.")
    while True:
        title = ask("  Title: ")
        title = " ".join(title.split())
        if not title:
            return None
        if not any(ch.isalnum() for ch in title):
            print("  That title has no letters or numbers to name the files with. Try another.")
            continue
        final = unique_title(title, output_dir)
        if final != title:
            print(f'  A puzzle called "{title}" already exists, so this one will be "{final}".')
        return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grid-logic", description=APP_NAME)
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"folder to save puzzles in (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args(argv)
    seed = random.randrange(1_000_000_000)
    rng = random.Random(seed)

    print(APP_NAME)
    print("=" * len(APP_NAME))
    try:
        theme = ask_theme()
        resolved = theme.resolve(ask_theme_options(theme), rng)
        print()
        count = ask_int(
            f"How many categories? ({MIN_CATEGORIES}-{MAX_CATEGORIES})",
            MIN_CATEGORIES,
            MAX_CATEGORIES,
            DEFAULT_CATEGORIES,
        )
        categories = []
        for number in range(1, count + 1):
            categories.append(ask_category(number, resolved, categories, rng))
        title = ask_title(args.output_dir)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing was saved.")
        return 1

    print("\nWriting the story and clues...")
    if title is None:
        title = write_title(resolved, len(categories[0].values), rng)
        title = unique_title(title, args.output_dir)
    puzzle = create_puzzle(categories, resolved, seed, title=title)
    saved = save_puzzle(puzzle, args.output_dir)

    color = use_color()
    print(f'\nSaved "{puzzle.title}" with {len(puzzle.clues)} clues')
    print(f"  Folder:     {file_link(saved.folder, color, GREEN)}")
    print(f"  Puzzle PDF: {file_link(saved.pdf, color)}")
    print(f"  Answer key: {file_link(saved.answer_key, color)}")
    print(f"  Web page:   {file_link(saved.html, color)}")
    return 0
