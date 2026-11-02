"""Selector fallback with a fake page, no browser."""

from helpers import raises

from pagepilot import locators
from pagepilot.fakepage import FakePage
from pagepilot.planner import Step


def click(target, selector=""):
    return Step("click", target, selector=selector)


def strategy_of(lookup):
    return lookup.split(":")[0]


def test_role_strategy_first():
    page = FakePage({"role:button:Go": 1})
    r = locators.resolve(page, click("Go"), timeout_ms=0)
    assert r.strategy == "role"
    assert page.lookups[0] == "role:button:Go"


def test_falls_through_to_css():
    page = FakePage({"css:#go-btn": 1})
    r = locators.resolve(page, click("Go", selector="#go-btn"), timeout_ms=0)
    assert r.strategy == "css"
    # every role was tried before CSS
    roles = [k for k in page.lookups if k.startswith("role:")]
    assert len(roles) == len(locators.ROLES["click"])
    assert page.lookups.index("css:#go-btn") > page.lookups.index(roles[-1])


def test_falls_through_to_text_then_label_then_attribute():
    page = FakePage({"text:Go": 1})
    assert locators.resolve(page, click("Go"), timeout_ms=0).strategy == "text"
    page = FakePage({"label:Email": 1})
    assert locators.resolve(page, Step("fill", "Email", "x"), timeout_ms=0).strategy == "label"
    page = FakePage()
    page.matches['css:[aria-label*="Go" i], [placeholder*="Go" i], [name*="Go" i], [title*="Go" i]'] = 1
    assert locators.resolve(page, click("Go"), timeout_ms=0).strategy == "attribute"


def test_order_of_strategies():
    page = FakePage()
    raises(locators.SelectorError, locators.resolve, page, click("Go", selector="#go"), timeout_ms=0)
    seen = []
    for key in page.lookups:
        s = strategy_of(key)
        if key.startswith("css:[aria-label"):
            s = "attribute"
        if s not in seen:
            seen.append(s)
    assert seen == ["role", "css", "text", "label", "attribute"], seen


def test_hidden_match_falls_through():
    page = FakePage({"role:button:Go": 1, "text:Go": 1}, hidden={"role:button:Go"})
    r = locators.resolve(page, click("Go"), timeout_ms=0)
    assert r.strategy == "text"
    assert any("not visible" in t for t in r.tried)


def test_broken_selector_does_not_stop_fallback():
    page = FakePage({"css:###": ValueError("bad css"), "text:Go": 1})
    r = locators.resolve(page, click("Go", selector="###"), timeout_ms=0)
    assert r.strategy == "text"
    assert any("error: bad css" in t for t in r.tried)


def test_total_failure_lists_every_strategy():
    e = raises(locators.SelectorError, locators.resolve, FakePage(), click("Nowhere"), timeout_ms=0)
    msg = str(e)
    assert "Could not find 'Nowhere'" in msg
    for part in ("role=button", "role=link", "text=", "label=", "attribute~="):
        assert part in msg, part
    assert len(e.tried) == len(locators.ROLES["click"]) + 3  # roles + text + label + attribute


def test_polls_until_timeout():
    clock = [0.0]
    page = FakePage()
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock[0] += s
        if len(sleeps) == 3:
            page.matches["text:Late"] = 1  # element appears on the 4th pass

    r = locators.resolve(page, click("Late"), timeout_ms=5000, now=lambda: clock[0], sleep=sleep)
    assert r.strategy == "text" and len(sleeps) == 3


def test_css_looking_target_used_as_css():
    assert locators.looks_like_css("#id") and locators.looks_like_css("button.primary")
    assert not locators.looks_like_css("Sign in")
