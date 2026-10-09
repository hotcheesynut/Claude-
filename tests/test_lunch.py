import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lunch

SAMPLE = os.path.join(os.path.dirname(__file__), "sample_menu.json")


class LunchTests(unittest.TestCase):
    def setUp(self):
        with open(SAMPLE) as f:
            self.menu = json.load(f)

    def test_dedupes_and_marks_headers(self):
        rows = lunch.extract_rows(self.menu, "lunch")
        self.assertEqual(rows[0], {"type": "header", "name": "LOCAL BURGER"})
        names = [r["name"] for r in rows if r["type"] == "food"]
        self.assertEqual(names.count("Cheeseburger on Bun"), 1)
        self.assertEqual(len(names), 5)

    def test_breakfast_block(self):
        rows = lunch.extract_rows(self.menu, "breakfast")
        self.assertEqual([r["name"] for r in rows], ["Breakfast Burrito"])

    def test_flags_marinara_typo_only(self):
        rows = lunch.extract_rows(self.menu, "lunch")
        suspect = [r["name"] for r in rows if r["type"] == "food" and r["suspect"]]
        self.assertEqual(suspect, ["Marinara Sauce"])

    def test_picks_allow_repeats(self):
        self.assertEqual(lunch.parse_picks("2 5 5", 6), [2, 5, 5])
        self.assertEqual(lunch.parse_picks("3x2, 1", 6), [3, 3, 1])
        with self.assertRaises(ValueError):
            lunch.parse_picks("9", 6)

    def test_custom_food_amounts(self):
        foods = lunch.load_custom_foods()
        for text, servings in [("garlic aioli", 1), ("garlic aioli 1 tbsp", 1),
                               ("Garlic Aioli 2 tbsp", 2), ("garlic aioli 0.5", 0.5)]:
            food, got = lunch.parse_extra(text, foods)
            self.assertEqual(food["name"], "garlic aioli")
            self.assertEqual(got, servings)
        self.assertIsNone(lunch.parse_extra("ranch", foods)[0])
        self.assertIsNone(lunch.parse_extra("garlic aioli 1 cup", foods)[0])

    def test_end_to_end_total(self):
        rows = [r for r in lunch.extract_rows(self.menu, "lunch") if r["type"] == "food"]
        chosen = [(r["name"], 1.0, r["nutrition"], r["suspect"]) for r in (rows[0], rows[1], rows[1])]
        food, s = lunch.parse_extra("garlic aioli 1 tbsp", lunch.load_custom_foods())
        chosen.append((food["name"], s, food["nutrition"], False))
        total = lunch.print_totals(chosen)
        self.assertEqual(total, {"cal": 380 + 320 + 95, "protein": 26, "carbs": 75, "fat": 43})


if __name__ == "__main__":
    unittest.main()
