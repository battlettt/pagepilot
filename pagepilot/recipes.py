"""Recipes: saved, parameterized tasks stored as JSON under recipes/.

Pure module. No browser, no Playwright.
"""

import json
import os
import re

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recipes")

_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_STEP_FIELDS = ("action", "target", "value", "description", "selector", "kind", "irreversible")


class RecipeError(Exception):
    pass


def load_recipes(directory=DEFAULT_DIR):
    """Load every *.json recipe in a directory, keyed by name."""
    recipes = {}
    if not os.path.isdir(directory):
        return recipes
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(directory, filename)
        with open(path, encoding="utf-8") as f:
            recipe = json.load(f)
        validate(recipe, path)
        recipes[recipe["name"]] = recipe
    return recipes


def validate(recipe, where="recipe"):
    for key in ("name", "description", "steps"):
        if key not in recipe:
            raise RecipeError(f"{where}: missing '{key}'")
    if not isinstance(recipe["steps"], list) or not recipe["steps"]:
        raise RecipeError(f"{where}: 'steps' must be a non-empty list")
    for i, step in enumerate(recipe["steps"], 1):
        if "action" not in step:
            raise RecipeError(f"{where}: step {i} has no 'action'")


def get_recipe(recipes, name):
    if name not in recipes:
        known = ", ".join(sorted(recipes)) or "none"
        raise RecipeError(f"Unknown recipe '{name}'. Available recipes: {known}")
    return recipes[name]


def resolve_params(recipe, overrides=None):
    """Merge parameter defaults with user overrides. Rejects unknown names."""
    declared = recipe.get("params", {})
    overrides = overrides or {}
    for key in overrides:
        if key not in declared:
            known = ", ".join(sorted(declared)) or "none"
            raise RecipeError(f"Recipe '{recipe['name']}' has no parameter '{key}'. Parameters: {known}")
    values = {}
    for key, spec in declared.items():
        if key in overrides:
            values[key] = overrides[key]
        elif "default" in spec:
            values[key] = spec["default"]
        else:
            raise RecipeError(f"Recipe '{recipe['name']}' needs parameter '{key}' (use --param {key}=...)")
    return values


def _fill(text, values):
    def sub(match):
        key = match.group(1)
        if key not in values:
            raise RecipeError(f"Template uses undeclared parameter '{key}'")
        return str(values[key])
    return _PARAM.sub(sub, text)


def fill_steps(recipe, overrides=None):
    """Return the recipe's step template with parameters filled in, as dicts."""
    values = resolve_params(recipe, overrides)
    steps = []
    for template in recipe["steps"]:
        step = {}
        for key in _STEP_FIELDS:
            if key not in template:
                continue
            value = template[key]
            step[key] = _fill(value, values) if isinstance(value, str) else value
        steps.append(step)
    return steps


def parse_params(pairs):
    """Turn ['k=v', ...] into a dict."""
    params = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise RecipeError(f"Bad --param '{pair}', expected key=value")
        key, value = pair.split("=", 1)
        params[key.strip()] = value
    return params
