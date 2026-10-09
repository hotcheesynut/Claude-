# School Lunch → Cal AI

`lunch.py` gets today's Essex High School menu from MealViewer, lets you pick what you ate, and prints a total you can type into Cal AI.

## One-time setup

1. Install Python 3. On a Mac it's usually already installed. Open **Terminal** and type `python3 --version`. If you see a version number, you're done. If not, download it from <https://www.python.org/downloads/>. On Windows, tick **"Add Python to PATH"** when you install it.
2. Download this folder (on GitHub: green **Code** button → **Download ZIP**, then unzip it).
3. In Terminal, go into the folder. Type `cd `, then drag the folder onto the Terminal window and press Enter.

No other installs are needed. It only uses what comes with Python.

## Running it

| You want | Type |
|---|---|
| Today's lunch | `python3 lunch.py` |
| Today's breakfast | `python3 lunch.py breakfast` |
| Another day | `python3 lunch.py 10-14-2026` (or `tomorrow`, `yesterday`, `10/14`) |
| Another day's breakfast | `python3 lunch.py 10-14-2026 breakfast` |

(On Windows, use `python` or `py` instead of `python3` if `python3` doesn't work.)

Then:

1. You'll see a numbered menu. Lines like `== LOCAL BURGER ==` are just section names, not food.
2. Type the numbers of what you ate, with spaces between them, e.g. `2 5 7`. To count something twice, type its number twice (`5 5`) or write `5x2`.
3. Add extras such as `garlic aioli 1 tbsp`, one per line. Press Enter on an empty line when you're done.
4. Copy the **TOTAL FOR CAL AI** block into Cal AI.

A `!` next to an item means the school's numbers don't add up. Protein×4 + carbs×4 + fat×9 should be close to the calories, and for that item it's far off. Their data probably has a typo, so check that item before you log it.

## Adding your own extras

Open `custom_foods.txt` in any text editor (TextEdit, Notepad) and add a line:

```
name | serving | calories | protein | carbs | fat
garlic aioli | 1 tbsp | 95 | 0 | 1 | 10
ranch | 2 tbsp | 130 | 0 | 2 | 13
```

When the tool asks for extras, you can type `ranch` (1 serving), `ranch 2` (2 servings), or `ranch 4 tbsp` (4 tbsp, which works out to 2 servings here).

## Shortcuts (optional)

```
python3 lunch.py --pick "2 5 5" --extra "garlic aioli 1 tbsp"
```

This skips the questions. `--file saved.json` reads a menu you saved earlier instead of downloading it.

## Tests

`python3 -m unittest discover -s tests` runs the tool against `tests/sample_menu.json`, which is a **made-up** sample menu.
