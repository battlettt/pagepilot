"""Gate logic: decide which steps are irreversible and need human approval.

Pure module. No browser, no Playwright.
"""

import re

REVERSIBLE = "REVERSIBLE"
IRREVERSIBLE = "IRREVERSIBLE"

# Step kinds that are always irreversible.
IRREVERSIBLE_KINDS = ("signin", "payment", "submit", "send", "delete")

# Words in a click target or description that mark an irreversible action.
_KEYWORDS = {
    "signin": ["sign in", "signin", "log in", "login", "sign on"],
    "payment": ["pay", "payment", "place order", "purchase", "buy", "checkout", "check out"],
    "submit": ["submit", "confirm", "apply", "register", "sign up"],
    "send": ["send", "post", "publish", "reply"],
    "delete": ["delete", "remove", "erase", "cancel order", "close account"],
}

# Field names PagePilot refuses to fill. Credentials and payment data never
# pass through the tool.
SENSITIVE_WORDS = [
    "password", "passwd", "passcode", "pin", "otp", "one-time code",
    "card number", "credit card", "cvv", "cvc", "security code", "ssn",
    "social security", "secret", "token", "api key",
]

# Actions whose target or value is scanned for irreversible keywords.
_SCANNED = ("click", "select")


def _has_word(text, word):
    return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text) is not None


def is_sensitive(text):
    """True if a field name looks like a credential or payment secret."""
    text = (text or "").lower()
    return any(_has_word(text, w) for w in SENSITIVE_WORDS)


def irreversible_kind(step):
    """Return the irreversible kind for a step, or None if it is reversible."""
    if step.kind in IRREVERSIBLE_KINDS:
        return step.kind
    if step.irreversible:
        return step.kind or "marked"
    if step.action not in _SCANNED:
        return None
    text = " ".join([step.target or "", step.value or ""]).lower()
    for kind, words in _KEYWORDS.items():
        if any(_has_word(text, w) for w in words):
            return kind
    return None


def classify(step):
    """Return REVERSIBLE or IRREVERSIBLE."""
    return IRREVERSIBLE if irreversible_kind(step) else REVERSIBLE


def needs_approval(step):
    """Does this step need explicit human approval before it runs?"""
    return classify(step) == IRREVERSIBLE


def approval_prompt(step, number):
    kind = irreversible_kind(step)
    return (
        f"\nGATE: step {number} is IRREVERSIBLE ({kind}).\n"
        f"  {step.description}\n"
        "Type 'yes' to allow this step, anything else stops the run: "
    )


def is_yes(answer):
    return (answer or "").strip().lower() in ("y", "yes")
