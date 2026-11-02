"""Recipes: parameter filling, listing, unknown-recipe error."""

import json
import os

from helpers import Recorder, raises, tempdir

from pagepilot import __main__ as cli
from pagepilot import gates, planner, recipes
from pagepilot.recipes import RecipeError

RECIPE = {
    "name": "demo",
    "description": "Demo recipe",
    "params": {"url": {"default": "https://example.com"}, "query": {"default": "lamps"}, "color": {}},
    "steps": [
        {"action": "goto", "target": "{url}/search", "description": "Open {url}"},
        {"action": "fill", "target": "Search", "value": "{query} in {color}"},
    ],
}


def test_defaults_and_overrides_fill_template():
    steps = recipes.fill_steps(RECIPE, {"color": "blue", "query": "chairs"})
    assert steps[0] == {"action": "goto", "target": "https://example.com/search",
                        "description": "Open https://example.com"}
    assert steps[1]["value"] == "chairs in blue"


def test_missing_required_param():
    e = raises(RecipeError, recipes.fill_steps, RECIPE, {})
    assert "needs parameter 'color'" in str(e)


def test_unknown_param_rejected():
    e = raises(RecipeError, recipes.fill_steps, RECIPE, {"color": "x", "colour": "y"})
    assert "no parameter 'colour'" in str(e)


def test_undeclared_template_param_rejected():
    bad = dict(RECIPE, steps=[{"action": "goto", "target": "{site}"}])
    raises(RecipeError, recipes.fill_steps, bad, {"color": "x"})


def test_parse_params():
    assert recipes.parse_params(["a=1", "b=x=y"]) == {"a": "1", "b": "x=y"}
    raises(RecipeError, recipes.parse_params, ["novalue"])


def test_unknown_recipe_error_lists_available():
    e = raises(RecipeError, recipes.get_recipe, recipes.load_recipes(), "nope")
    assert "Unknown recipe 'nope'" in str(e) and "order-status" in str(e)


def test_cli_unknown_recipe_exits_2():
    rec = Recorder()
    assert cli.main(["--recipe", "nope"], rec.input, rec.out) == 2
    assert "Unknown recipe 'nope'" in rec.text


def test_list_recipes_cli():
    rec = Recorder()
    assert cli.main(["--list-recipes"], rec.input, rec.out) == 0
    for name in ("contact-form", "order-status", "site-search"):
        assert name in rec.text
    assert "--param query=..." in rec.text


def test_load_from_custom_dir_and_validation():
    with tempdir() as d:
        with open(os.path.join(d, "demo.json"), "w") as f:
            json.dump(RECIPE, f)
        assert list(recipes.load_recipes(d)) == ["demo"]
        with open(os.path.join(d, "bad.json"), "w") as f:
            json.dump({"name": "bad", "description": "x", "steps": []}, f)
        raises(RecipeError, recipes.load_recipes, d)
    assert recipes.load_recipes("/nonexistent-dir") == {}


def test_recipe_plan_via_cli_params():
    rec = Recorder()
    code = cli.main(["--dry-run", "--recipe", "site-search", "--param", "query=desk lamp"], rec.input, rec.out)
    assert code == 0 and "Type 'desk lamp' into the search box" in rec.text


def test_recipe_cannot_fill_secret_fields():
    bad = {"name": "b", "description": "d", "steps": [
        {"action": "goto", "target": "https://example.com"},
        {"action": "fill", "target": "Password", "value": "x"}]}
    raises(planner.PlanError, planner.plan_recipe, bad)


def test_shipped_recipes_are_valid_and_clean():
    all_recipes = recipes.load_recipes()
    assert len(all_recipes) >= 3
    for name, r in all_recipes.items():
        plan = planner.plan_recipe(r)
        assert plan.ok and plan.steps[0].action == "goto", name
        for step in plan.steps:
            assert step.action in planner.ACTIONS
            assert not (step.action == "fill" and gates.is_sensitive(step.target))
        text = json.dumps(r).lower()
        assert "example.com" in text and "@" not in text and "password" not in text, name
