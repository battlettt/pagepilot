"""Executor: run a plan in a real browser with gates, retries, and audit.

Playwright is imported only inside open_browser(), so this module (and its
tests with a fake page) works without Playwright installed.
"""

import contextlib
import time

from . import gates, locators

CAPTCHA_SELECTOR = (
    'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], '
    '.g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey], #captcha'
)


class StepFailed(Exception):
    pass


class Executor:
    def __init__(self, page, audit, approve, captcha_prompt=None, timeout_ms=10000,
                 step_delay=0.5, max_retries=3, backoff=1.0, sleep=time.sleep, out=print):
        self.page = page
        self.audit = audit
        self.approve = approve              # approve(prompt_text) -> bool
        self.captcha_prompt = captcha_prompt  # captcha_prompt(prompt_text) -> bool, or None to stop
        self.timeout_ms = timeout_ms
        self.step_delay = step_delay
        self.max_retries = max_retries
        self.backoff = backoff
        self.sleep = sleep
        self.out = out

    def run(self, plan):
        """Run every step in order. Returns (log, report)."""
        steps = plan.steps
        for number, step in enumerate(steps, 1):
            if number > 1:
                self.sleep(self.step_delay)  # rate limit: never hammer a site
            if not self._captcha_clear():
                self.audit.record(number, step, "stopped_captcha",
                                  error="CAPTCHA on page; PagePilot does not solve CAPTCHAs")
                self._skip_rest(steps, number)
                return self.audit.finish("stopped_captcha", f"Stopped at step {number}: CAPTCHA was not cleared by you.")
            if gates.needs_approval(step):
                if not self.approve(gates.approval_prompt(step, number)):
                    self.audit.record(number, step, "stopped_at_gate",
                                      error="You declined this irreversible step")
                    self._skip_rest(steps, number)
                    self.out(f"Stopped before step {number}. Nothing from that step onward ran.")
                    return self.audit.finish(
                        "stopped_at_gate",
                        f"Stopped at the gate before step {number} ({gates.irreversible_kind(step)}). "
                        "You declined, so that step and all later steps did not run.")
            self.out(f"[{number}/{len(steps)}] {step.description}")
            try:
                strategy, retries, text = self._run_with_retries(step)
            except StepFailed as e:
                retries, error = e.args
                shot = self._screenshot(number)
                self.audit.record(number, step, "failed", retries=retries, screenshot=shot, error=error)
                self._skip_rest(steps, number)
                return self.audit.finish("failed", f"Step {number} failed after {retries} retries: {error}")
            shot = self._screenshot(number, full_page=step.action == "screenshot")
            self.audit.record(number, step, "success", strategy=strategy, retries=retries,
                              screenshot=shot, text=text)
        return self.audit.finish("completed", f"All {len(steps)} steps ran.")

    def _skip_rest(self, steps, number):
        for later in range(number + 1, len(steps) + 1):
            self.audit.record(later, steps[later - 1], "skipped")

    def _run_with_retries(self, step):
        irreversible = gates.needs_approval(step)
        retries = 0
        while True:
            acted = False
            try:
                resolution = None
                if step.action not in ("goto", "screenshot"):
                    resolution = locators.resolve(self.page, step, timeout_ms=self.timeout_ms)
                acted = True
                text = self._act(step, resolution)
                return (resolution.strategy if resolution else None), retries, text
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                # Never repeat an irreversible action that may already have happened.
                if (irreversible and acted) or retries >= self.max_retries:
                    raise StepFailed(retries, error)
                retries += 1
                delay = self.backoff * (2 ** (retries - 1))
                self.out(f"  retry {retries}/{self.max_retries} in {delay:.1f}s ({error})")
                self.sleep(delay)

    def _act(self, step, resolution):
        t = self.timeout_ms
        if step.action == "goto":
            self.page.goto(step.target, timeout=t)
        elif step.action == "click":
            resolution.locator.click(timeout=t)
        elif step.action == "fill":
            resolution.locator.fill(step.value, timeout=t)
        elif step.action == "select":
            resolution.locator.select_option(label=step.value, timeout=t)
        elif step.action == "extract_text":
            return resolution.locator.inner_text(timeout=t).strip()
        elif step.action in ("wait_for", "screenshot"):
            pass  # wait_for is the resolve() wait; screenshot is taken after every step
        else:
            raise ValueError(f"Unknown action '{step.action}'")
        return None

    def _screenshot(self, number, full_page=False):
        path = self.audit.screenshot_path(number)
        try:
            self.page.screenshot(path=path, full_page=full_page)
            return path
        except Exception as e:
            self.out(f"  (screenshot failed: {e})")
            return None

    def _captcha_clear(self):
        if not has_captcha(self.page):
            return True
        msg = ("\nCAPTCHA detected. PagePilot does not solve CAPTCHAs.\n"
               "Solve it yourself in the browser window, then type 'yes' to continue, "
               "or anything else to stop: ")
        if self.captcha_prompt is None or not self.captcha_prompt(msg):
            return False
        return not has_captcha(self.page)


def has_captcha(page):
    try:
        return page.locator(CAPTCHA_SELECTOR).count() > 0
    except Exception:
        return False


@contextlib.contextmanager
def open_browser(headless=False, profile_dir=None):
    """Yield a Playwright page. Fresh context unless profile_dir is opted into."""
    from playwright.sync_api import sync_playwright  # the one real dependency

    with sync_playwright() as pw:
        if profile_dir:
            context = pw.chromium.launch_persistent_context(profile_dir, headless=headless)
            browser = None
        else:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context()
        try:
            yield context.pages[0] if context.pages else context.new_page()
        finally:
            context.close()
            if browser:
                browser.close()
