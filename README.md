# Grid Logic Puzzle Maker
Generates custom grid logic puzzles, like those found in variety puzzle books. 

The user is prompted for a theme, category, category items and then the tool will generate a classic grid logic puzzle in both form-fillable pdf format and an interactive local web app.

## Background
My dad and I both really enjoy logic puzzles and subscribe to logic puzzle books. Years ago, I wanted to make him one for a gift but it was taking me forever to come up with all of the stories, clues and then test them all out, not to mention trying to make it look pretty. I gave up. 

Years later, I tried again to do similar for a good friend of mine, but again I gave up. A few years passed, and the idea came back up. This time I decided to try to make a program to help me out. Life got in the way, and I put the project aside. 

Until now. 

Most recently, I refreshed the project with AI assistance and set it up on GitHub. I put together a list of planned updates and bug fixes, found at the bottom under "Future Plans" and "Known Issues".  

## Setup
Requires Python 3.10 or newer.

### Installation
To install, run: `pipx install <file_path>`

To update, run: `pipx install --force <file_path>`

To uninstall, run: `pipx uninstall grid-logic-puzzle-maker`


## Usage
Currently, the puzzle generation UX is all within the CLI. 

From within the terminal, run: `grid-logic`

To specify where the puzzles are saved, use: `--output-dir PATH` (The default file path is within the user's Documents folder.) 

The user is prompted through a series of questions. The tool will generate the story and clues using stored templates. The puzzle outputs as a form-fillable .pdf that can also be printed along with the answer key in .pdf format. In addition, an .html file is generated to run the puzzle as an interactive local web app. 

The tool prompts the user with the following:
1. Select a theme from a provided list.
2. The number of categories to be included (2–6, default 4).
3. For each category, the user is prompted for the name and type, followed by a prompt for the list of category items in a comma-separated list. Currently, each category must have the same number of items. Pressing Enter will autofill with placeholder values. If category names are input in mixed or lower case, they are converted to Title Case. The user is then prompted to confirm the list of category items before moving to the next list.
4. A title for the puzzle. Leaving it blank will have one automatically generated based on the theme.

Once the puzzles are generated, their save path is linked within the terminal.


## Output
Each puzzle gets its own folder, named after its title:

```
Documents/Grid Logic Puzzles/
  Paws_About_Town/
    Paws_About_Town.pdf              a form-fillable and printable .pdf of the puzzle
    Paws_About_Town_Answer_Key.pdf   a printable .pdf of the puzzle answer key
    Paws_About_Town.html             an interactive local web app, run from a browser
```

### Form-fillable, interactive .pdf
- Clicking a square toggles between a red X → a green O → blank. This has been verified with Adobe Acrobat Reader only.
- If the grid and clues don't fit on one page at a comfortable size, the clues follow on the next page.
- An empty answer table is also included to accompany the puzzle grid.
- A notes page is included at the end for the user's convenience.

### Interactive local web app
- Clicking a square toggles between a red X → a green O → blank. Right-clicking will do the reverse.
- Clicking a blank square and dragging across the row or column in a subgrid will clear all entries.
- Clicking a square with an X and dragging across the row or column in a subgrid will mark all entries with a red X, ignoring any O markers.
- When placing an X leaves a block's row or column with X's in every square but one blank, that last square autofills with a green O automatically. 
- Clicking a clue on the list will cross it off.
- An empty answer table with drop-down options is also included to accompany the puzzle grid. 
- A notes textbox sits to the left of the grid (or under the clues for smaller viewports) that can be expanded or shrunk by pressing a UI button, or dragged from the corner.
- A check answers button is shown but disabled until all squares are filled in. When selecting, the user sees either a confirmation that the puzzle was solved correctly or a note that there are wrong answers, with wrong squares outlined in red.
- A start over button is available, and when selected, it clears all marks and crossed-out clues.
- A print button is available to print the puzzle as seen on the display, with or without marks. 
- Everything is remembered in that browser between visits.

## Puzzle generation
The `create_puzzle()` function found in `src/grid_logic/generator.py` is the runner. The `main()` function inside `cli.py` picks a random seed and every random choice after that (solution, clues, etc.) using `random.Random(seed)`. The seed is used again in `html_export.py`.

- Categories: The `orderings_for()` function in `generator.py` calls the `detect_ordering()` function from `ordering.py` for each category. Detectors are tried in order and stop with the first one that gives each value a distinct key.
- Solutions: The `random_solution(n, k, rng)` function in `generator.py` builds the value index each entity has in each category (`assign[cat][entity]`). 
- Clues: The `_Sampler.draw()` function in `generator.py` picks a clue kind and builds a `Clue` object from `logic.py`. The function `build_clues()` in `generator.py` loops through the list and stores any that change the grid. When `Grid.solved()` is true, the loop breaks.
- Puzzle Grid: The `Grid` class from `logic.py` stores the partners still possible. These are the blank squares of the grid. The function `propagate()` loops through until nothing new is changed.
- Wording: The `Phraser.text()` function found in `phrasing.py` calls the theme's .json templates to create sentences with the clues.
- Story: The function `write_story()` retrieves the story from the matching theme's templates. 
- Output: The `save_puzzle()` function found in `output.py` generates the two .pdfs and .html output files.

## Themes
I had several templates with clues generated for this tool based on themes I provided. Each theme defines the title, story, "wrapper" phrases for clues and the category kinds suggested in the CLI. Each category kind lists several examples. Clue sentences rotate through these to avoid redundancy. Each new theme is stored in its own .json file so nothing is hard-coded. Themes are stored in .json files in: src/grid_logic/themes.

- Champion Select: Each player's favorite champion in a video game; the user is prompted to give the name of the game
- Twice the Fun: Find the two hobbies each friend enjoys
- Tails on Tour: Where everyone took their pet
- Too Close to Call: Who won and who lost on election night
- Party Overload: Too many parties
- Secret Identities: Alter egos; the user is prompted to select from: superheroes, spies or criminal masterminds
- Between Gigs: Odd jobs people pick up while they're between jobs
- Favorites Roundup: Everyone's favorite things
- Top of the Queue: Which crowdwork project was the best

## Future plans

### Basic feature updates
- Add a difficulty tier option.
- Update CLI category item input to not be comma-separated input (too many bugs with this).
- Add a warning if a row or column has all X's and no O's, or more than one O.
- Add features to clear a row or column with hotkeys.
- Create a web app version of the puzzle creation UX to coexist with the CLI feature.
- Add support for some categories having a different number of values than others in the same puzzle.
- Add support for one value matching two values that are in the same block as each other (a different block from the first value).

### Story and clue generation updates
- Add an AI agent to dynamically generate stories and clues.
- Add an option to write custom stories and clues, then test the logic before generating the output files.

### Final output updates
- Improve the aesthetics of the web app version.
- Ensure the .pdf version looks and feels like those found in physical logic puzzle books.
- Add the ability to generate one printable .pdf of many existing puzzles, with a corresponding answer sheet .pdf.
- Add a feature to generate actual logic puzzle books that resemble existing puzzle books found in bookshops.
- Add the ability to share a local web app executable with a friend, that displays in its own app-style browser window.


## Known issues
- On the web app version, when dragging Xs, sometimes multiple Os appear instead.
- On the web app version, arrow keys don't work to navigate between squares.
