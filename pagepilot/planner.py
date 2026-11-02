"""Planner: turn a plain-English task into an explicit, ordered step plan.

Pure module. No browser, no Playwright. An unknown task produces a plan
with no steps and a clarify message, never a guessed action list.
"""

import re
from dataclasses import asdict, dataclass, field

from . import gates, recipes as recipes_mod

ACTIONS = ("goto", "click", "fill", "select", "wait_for", "screenshot", "extract_text")

EXAMPLES = (
    'go to https://example.com then click "More information" then take a screenshot',
    'open example.com then fill "lamps" into Search then click Search then extract text of Results',
)


@dataclass
class Step:
    action: str
    target: str = ""
    value: str = ""
    description: str = ""
    selector: str = ""
    kind: str = ""
    irreversible: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class Plan:
    task: str
    steps: list = field(default_factory=list)
    clarify: str = ""
    source: str = "task"

    @property
    def ok(self):
        return bool(self.steps) and not self.clarify

    def to_dict(self):
        return {
            "task": self.task,
            "source": self.source,
            "clarify": self.clarify,
            "steps": [s.to_dict() for s in self.steps],
        }


class PlanError(Exception):
    pass


def _unquote(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _url(text):
    text = _unquote(text)
    if re.match(r"^(https?|file)://\S+$", text):
        return text
    if re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", text):
        return "https://" + text
    raise PlanError(f"'{text}' is not a URL")


def _click(target, kind="", what=None):
    target = _unquote(target)
    return Step("click", target, description=f"Click '{target}'" + (f" ({what})" if what else ""), kind=kind)


# (pattern, builder). Order matters: gated verbs come before plain click.
_RULES = [
    (r"(?:go to|goto|open|visit|navigate to)\s+(\S+)",
     lambda m: Step("goto", _url(m[1]), description=f"Open {_url(m[1])}")),
    (r"(?:sign in|log in|login|signin)(?:\s+.*)?",
     lambda m: _click("Log in" if "log" in m[0].lower() else "Sign in", "signin", "sign in with your existing browser session")),
    (r"(?:submit)(?:\s+(?:the\s+)?(.+?))?",
     lambda m: _click("Submit", "submit", f"submit {_unquote(m[1])}" if m[1] else "submit the form")),
    (r"(pay|place (?:the )?order|checkout|check out|buy|purchase)(?:\s+.*)?",
     lambda m: _click({"pay": "Pay", "buy": "Buy", "purchase": "Purchase", "checkout": "Checkout",
                       "check out": "Checkout"}.get(m[1].lower(), "Place order"), "payment", "payment")),
    (r"send(?:\s+(?:the\s+)?(.+?))?",
     lambda m: _click("Send", "send", f"send {_unquote(m[1])}" if m[1] else "send")),
    (r"(?:delete|remove)\s+(?:the\s+)?(.+?)",
     lambda m: _click("Delete", "delete", f"delete {_unquote(m[1])}")),
    (r"(?:click|press|tap)(?:\s+on)?(?:\s+the)?\s+(.+?)(?:\s+(?:button|link))?",
     lambda m: _click(m[1])),
    (r"(?:fill(?: in)?|type|enter)\s+(.+?)\s+(?:in|into)\s+(?:the\s+)?(.+?)(?:\s+(?:field|box))?",
     lambda m: _fill(m[2], m[1])),
    (r"fill(?: in)?\s+(?:the\s+)?(.+?)(?:\s+(?:field|box))?\s+with\s+(.+)",
     lambda m: _fill(m[1], m[2])),
    (r"(?:select|choose|pick)\s+(.+?)\s+(?:in|from)\s+(?:the\s+)?(.+?)(?:\s+(?:dropdown|menu|list))?",
     lambda m: Step("select", _unquote(m[2]), _unquote(m[1]),
                    f"Select '{_unquote(m[1])}' in '{_unquote(m[2])}'")),
    (r"wait (?:for|until)\s+(?:the\s+)?(.+?)(?:\s+(?:appears|is visible|to appear))?",
     lambda m: Step("wait_for", _unquote(m[1]), description=f"Wait for '{_unquote(m[1])}'")),
    (r"(?:take (?:a )?)?screenshot(?:\s+.*)?",
     lambda m: Step("screenshot", "page", description="Take a screenshot of the page")),
    (r"(?:extract|read|copy)\s+(?:the\s+)?(?:text\s+(?:of|from|in)\s+)?(?:the\s+)?(.+)",
     lambda m: Step("extract_text", _unquote(m[1]), description=f"Read the text of '{_unquote(m[1])}'")),
]


def _fill(target, value):
    target, value = _unquote(target), _unquote(value)
    if gates.is_sensitive(target):
        raise PlanError(
            f"PagePilot never enters credentials or payment secrets ('{target}'). "
            "Sign in yourself in the browser, or use --profile with your own saved session."
        )
    return Step("fill", target, value, f"Type '{value}' into '{target}'")


def _split(task):
    parts = re.split(r"\s*(?:,?\s*\band then\b|,?\s*\bthen\b|;|\n)\s*", task.strip(), flags=re.I)
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _parse_clause(clause):
    for pattern, build in _RULES:
        match = re.fullmatch(pattern, clause, flags=re.I)
        if match:
            return build(match)
    raise PlanError(f"I do not know how to do: '{clause}'")


def _clarify(task, reason):
    hint = "Try a task like:\n  " + "\n  ".join(EXAMPLES) + "\nor run a saved recipe (--list-recipes)."
    return Plan(task, [], clarify=f"{reason}\n{hint}")


def _match_recipe(task, recipes):
    norm = " ".join(task.lower().split())
    for recipe in (recipes or {}).values():
        for trigger in recipe.get("triggers", []):
            if norm == trigger or norm.startswith(trigger + " "):
                return recipe
    return None


def plan_recipe(recipe, params=None, task=None):
    """Build a plan from a recipe and parameter overrides."""
    steps = []
    for d in recipes_mod.fill_steps(recipe, params):
        step = Step(**d)
        if step.action not in ACTIONS:
            raise PlanError(f"Recipe '{recipe['name']}' uses unknown action '{step.action}'")
        if step.action == "fill" and gates.is_sensitive(step.target):
            raise PlanError(f"Recipe '{recipe['name']}' tries to fill a sensitive field '{step.target}'")
        if step.action == "goto":
            step.target = _url(step.target)
        if not step.description:
            step.description = f"{step.action} {step.target}".strip()
        steps.append(step)
    return Plan(task or f"recipe {recipe['name']}", steps, source=f"recipe:{recipe['name']}")


def plan_task(task, recipes=None):
    """Turn a task string into a Plan. Unknown tasks get a clarify plan."""
    if not task or not task.strip():
        return _clarify(task or "", "The task is empty.")
    recipe = _match_recipe(task, recipes)
    if recipe:
        params = {}
        url = re.search(r"(https?://\S+)", task)
        if url and "url" in recipe.get("params", {}):
            params["url"] = url.group(1)
        try:
            return plan_recipe(recipe, params, task=task)
        except (PlanError, recipes_mod.RecipeError) as e:
            return _clarify(task, str(e))
    try:
        steps = [_parse_clause(c) for c in _split(task)]
    except PlanError as e:
        return _clarify(task, str(e))
    if steps[0].action != "goto":
        return _clarify(task, "The plan must start by opening a page (for example 'go to https://example.com').")
    return Plan(task, steps)


def format_plan(plan):
    """Human-readable plan, with every gated step marked."""
    lines = [f"Task: {plan.task}", f"Source: {plan.source}"]
    if not plan.ok:
        lines.append("No plan. " + plan.clarify)
        return "\n".join(lines)
    lines.append(f"Plan ({len(plan.steps)} steps):")
    for i, step in enumerate(plan.steps, 1):
        gate = "  [IRREVERSIBLE, needs your approval]" if gates.needs_approval(step) else ""
        detail = f"{step.action} target={step.target!r}"
        if step.value:
            detail += f" value={step.value!r}"
        lines.append(f"  {i}. {step.description}{gate}")
        lines.append(f"     ({detail})")
    gated = sum(1 for s in plan.steps if gates.needs_approval(s))
    lines.append(f"{gated} step(s) will stop and ask for approval before running.")
    return "\n".join(lines)
