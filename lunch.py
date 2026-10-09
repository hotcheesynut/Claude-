#!/usr/bin/env python3
"""
School lunch -> Cal AI helper.

Pulls the day's menu from MealViewer, lets you pick what you ate,
adds any extras from custom_foods.txt, and prints totals to type into Cal AI.

Examples:
    python3 lunch.py                      today's lunch
    python3 lunch.py breakfast            today's breakfast
    python3 lunch.py 10-14-2026           lunch on a given date
    python3 lunch.py tomorrow breakfast   date and meal together
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

SCHOOL = "EssexHighSchool"
API_URL = "https://api.mealviewer.com/api/v4/school/{school}/{date}/{date}/"
CUSTOM_FOODS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_foods.txt")

# Nutrition fields we care about: our short name -> the name MealViewer uses.
NUTRIENTS = {
    "cal": "Calories",
    "protein": "Protein (g)",
    "carbs": "Total Carbs (g)",
    "fat": "Total Fat (g)",
}


# ---------------------------------------------------------------- dates / args

def parse_date(text):
    """Accept today, tomorrow, yesterday, MM-DD-YYYY, MM/DD/YYYY, YYYY-MM-DD, or MM-DD."""
    today = datetime.date.today()
    t = text.strip().lower()
    if t == "today":
        return today
    if t == "tomorrow":
        return today + datetime.timedelta(days=1)
    if t == "yesterday":
        return today - datetime.timedelta(days=1)
    t = t.replace("/", "-")
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m-%d-%y"):
        try:
            return datetime.datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    try:  # MM-DD with no year: assume this year
        return datetime.datetime.strptime(t, "%m-%d").date().replace(year=today.year)
    except ValueError:
        return None


# ---------------------------------------------------------------- fetching

def fetch_menu(date):
    url = API_URL.format(school=SCHOOL, date=date.strftime("%m-%d-%Y"))
    req = urllib.request.Request(url, headers={"User-Agent": "lunch-calai/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_nutrition(item):
    """Turn the item's 'nutritionals' list into {'cal': .., 'protein': .., 'carbs': .., 'fat': ..}."""
    found = {}
    for entry in item.get("nutritionals") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("nutrientName") or entry.get("label") or ""
        value = entry.get("value", entry.get("amount"))
        found[str(name).strip().lower()] = to_number(value)
    return {short: found.get(long.lower(), 0.0) for short, long in NUTRIENTS.items()}


def serving_size(item):
    size = item.get("portionSize", item.get("portionQuantity"))
    unit = (item.get("portionUnit") or "").strip()
    if size in (None, "", 0):
        return unit
    size = to_number(size)
    size = int(size) if size == int(size) else size
    return f"{size} {unit}".strip()


def calorie_mismatch(n):
    """True if protein*4 + carbs*4 + fat*9 is way off from the listed calories."""
    computed = n["protein"] * 4 + n["carbs"] * 4 + n["fat"] * 9
    diff = abs(computed - n["cal"])
    return diff > 50 and diff > 0.30 * max(n["cal"], computed)


def extract_rows(menu_json, meal):
    """
    Walk menuSchedules -> menuBlocks -> cafeteriaLineList.data -> foodItemList.data.
    Returns a list of rows, each either:
        {"type": "header", "name": ...}
        {"type": "food", "name": ..., "serving": ..., "nutrition": {...}, "suspect": bool}
    Duplicate items (same item_Id) are only kept once.
    """
    rows, seen = [], set()
    for schedule in menu_json.get("menuSchedules") or []:
        for block in schedule.get("menuBlocks") or []:
            if (block.get("blockName") or "").strip().lower() != meal:
                continue
            lines = (block.get("cafeteriaLineList") or {}).get("data") or []
            for line in lines:
                items = (line.get("foodItemList") or {}).get("data") or []
                for item in items:
                    key = item.get("item_Id") or item.get("item_Name")
                    if key in seen:
                        continue
                    seen.add(key)
                    name = (item.get("item_Name") or "?").strip()
                    n = get_nutrition(item)
                    if all(v == 0 for v in n.values()):
                        rows.append({"type": "header", "name": name})
                    else:
                        rows.append({
                            "type": "food",
                            "name": name,
                            "serving": serving_size(item),
                            "nutrition": n,
                            "suspect": calorie_mismatch(n),
                        })
    return rows


# ---------------------------------------------------------------- custom foods

def load_custom_foods(path=CUSTOM_FOODS_FILE):
    """
    Each non-comment line:  name | serving | calories | protein | carbs | fat
    e.g.                    garlic aioli | 1 tbsp | 95 | 0 | 1 | 10
    """
    foods = []
    if not os.path.exists(path):
        return foods
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 6:
                print(f"  (skipping line {lineno} of custom_foods.txt: expected 6 parts separated by |)")
                continue
            name, serving, cal, protein, carbs, fat = parts
            m = re.match(r"\s*([\d.]+)\s*(.*)", serving)
            amount, unit = (float(m.group(1)), m.group(2).strip()) if m else (1.0, serving)
            foods.append({
                "name": name,
                "serving": serving,
                "amount": amount or 1.0,
                "unit": unit,
                "nutrition": {"cal": to_number(cal), "protein": to_number(protein),
                              "carbs": to_number(carbs), "fat": to_number(fat)},
            })
    return foods


def parse_extra(text, foods):
    """
    'garlic aioli'          -> 1 serving
    'garlic aioli 2'        -> 2 servings
    'garlic aioli 2 tbsp'   -> 2 tbsp (= 2 servings if the serving is 1 tbsp)
    Returns (food, servings) or (None, error message).
    """
    t = text.strip().lower()
    # Longest name first so "aioli" doesn't steal "garlic aioli".
    for food in sorted(foods, key=lambda f: -len(f["name"])):
        if not t.startswith(food["name"].lower()):
            continue
        rest = t[len(food["name"]):].strip()
        if not rest:
            return food, 1.0
        m = re.match(r"^([\d.]+)\s*(.*)$", rest)
        if not m:
            return None, f"couldn't read the amount in '{text}'"
        qty, unit = float(m.group(1)), m.group(2).strip()
        if unit and food["unit"] and unit.rstrip("s") != food["unit"].lower().rstrip("s"):
            return None, f"'{food['name']}' is measured in {food['unit']}, not {unit}"
        return food, (qty / food["amount"]) if unit else qty
    names = ", ".join(f["name"] for f in foods) or "(none yet)"
    return None, f"'{text}' isn't in custom_foods.txt. Known extras: {names}"


# ---------------------------------------------------------------- output

def fmt(x):
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def print_menu(rows, meal, date):
    print(f"\n{meal.title()} for {date.strftime('%A %m/%d/%Y')}\n")
    print(f"  {'#':>3}  {'Item':<34} {'Serving':<12} {'Cal':>5} {'Prot':>5} {'Carb':>5} {'Fat':>5}")
    print("  " + "-" * 75)
    numbered, any_suspect = [], False
    for row in rows:
        if row["type"] == "header":
            print(f"\n  == {row['name']} ==")
            continue
        numbered.append(row)
        n = row["nutrition"]
        flag = " !" if row["suspect"] else ""
        any_suspect |= row["suspect"]
        print(f"  {len(numbered):>3}  {row['name'][:34]:<34} {row['serving'][:12]:<12} "
              f"{fmt(n['cal']):>5} {fmt(n['protein']):>5} {fmt(n['carbs']):>5} {fmt(n['fat']):>5}{flag}")
    if any_suspect:
        print("\n  ! = the school's numbers don't add up (protein*4 + carbs*4 + fat*9 is far from")
        print("      the listed calories). Probably a typo in their data - double-check before logging.")
    return numbered


def parse_picks(text, count):
    """'2 5 7', '2,5,7', '2 2' (twice) or '2x2' (twice). Returns list of indexes or raises ValueError."""
    picks = []
    for token in re.split(r"[\s,]+", text.strip()):
        if not token:
            continue
        m = re.fullmatch(r"(\d+)(?:[x*](\d+))?", token.lower())
        if not m:
            raise ValueError(f"'{token}' isn't a number")
        num, times = int(m.group(1)), int(m.group(2) or 1)
        if not 1 <= num <= count:
            raise ValueError(f"there's no item #{num} (pick 1-{count})")
        picks.extend([num] * times)
    return picks


def print_totals(chosen):
    """chosen: list of (label, servings, nutrition, suspect)"""
    total = {k: 0.0 for k in NUTRIENTS}
    print("\nYou picked:")
    for label, servings, n, suspect in chosen:
        for k in total:
            total[k] += n[k] * servings
        times = f" x{fmt(servings)}" if servings != 1 else ""
        warn = "   <- school data looks wrong, check this one" if suspect else ""
        print(f"  - {label}{times}  ({fmt(n['cal'] * servings)} cal){warn}")
    print("\n" + "=" * 28)
    print("  TOTAL FOR CAL AI")
    print("=" * 28)
    print(f"  Calories: {total['cal']:.0f}")
    print(f"  Protein:  {total['protein']:.0f} g")
    print(f"  Carbs:    {total['carbs']:.0f} g")
    print(f"  Fat:      {total['fat']:.0f} g")
    print("=" * 28)
    return total


# ---------------------------------------------------------------- main

def ask(prompt, preset):
    """Use a value given on the command line, otherwise ask the user."""
    if preset is not None:
        print(prompt + preset)
        return preset
    try:
        return input(prompt)
    except EOFError:
        return ""


def main(argv=None):
    p = argparse.ArgumentParser(description="Pull school lunch nutrition and total it for Cal AI.")
    p.add_argument("when", nargs="*", help="optional date (e.g. 10-14-2026, tomorrow) and/or 'breakfast'/'lunch'")
    p.add_argument("--pick", help="item numbers, skips the question (e.g. \"2 5 7\")")
    p.add_argument("--extra", action="append", help="an extra from custom_foods.txt (e.g. \"garlic aioli 1 tbsp\"); repeatable")
    p.add_argument("--file", help="read menu JSON from a saved file instead of the internet")
    args = p.parse_args(argv)

    meal, date = "lunch", datetime.date.today()
    for word in args.when:
        if word.lower() in ("breakfast", "lunch"):
            meal = word.lower()
        else:
            d = parse_date(word)
            if d is None:
                p.error(f"didn't understand '{word}'. Use a date like 10-14-2026, or 'breakfast'/'lunch'.")
            date = d

    try:
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                menu = json.load(f)
        else:
            menu = fetch_menu(date)
    except urllib.error.HTTPError as e:
        print(f"MealViewer returned an error ({e.code}). Try again later or check the date.")
        return 1
    except (urllib.error.URLError, OSError) as e:
        print(f"Couldn't reach MealViewer: {getattr(e, 'reason', e)}\nCheck your internet connection.")
        return 1
    except json.JSONDecodeError:
        print("MealViewer sent back something that isn't valid menu data.")
        return 1

    rows = extract_rows(menu, meal)
    if not any(r["type"] == "food" for r in rows):
        print(f"No {meal} menu found for {date.strftime('%m/%d/%Y')} (weekend, holiday, or not posted yet).")
        return 0

    numbered = print_menu(rows, meal, date)
    chosen = []

    preset = args.pick
    while True:
        text = ask("\nWhat did you eat? Type item numbers (e.g. 2 5 7; repeat a number to count it twice): ", preset)
        try:
            for num in parse_picks(text, len(numbered)):
                r = numbered[num - 1]
                chosen.append((r["name"], 1.0, r["nutrition"], r["suspect"]))
            break
        except ValueError as e:
            print(f"  Oops: {e}")
            if preset is not None:
                return 1

    foods = load_custom_foods()
    if args.extra is not None:
        for text in args.extra:
            food, result = parse_extra(text, foods)
            if food is None:
                print(f"  Oops: {result}")
                return 1
            print(f"Extra: {text}")
            chosen.append((food["name"], result, food["nutrition"], False))
    elif foods:
        print("\nExtras from custom_foods.txt: " + ", ".join(f"{f['name']} ({f['serving']})" for f in foods))
        while True:
            text = ask("Add an extra (e.g. 'garlic aioli 1 tbsp'), or press Enter when done: ", None)
            if not text.strip():
                break
            food, result = parse_extra(text, foods)
            if food is None:
                print(f"  Oops: {result}")
            else:
                chosen.append((food["name"], result, food["nutrition"], False))
                print(f"  Added {food['name']} x{fmt(result)}")

    if not chosen:
        print("\nNothing picked, nothing to total.")
        return 0
    print_totals(chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
