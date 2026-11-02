"""Audit trail: per-step log, screenshots dir, and a final Markdown report.

Pure module. No browser, no Playwright. Everything is written under the run
directory (runs/<run_id>/ by default), which is gitignored runtime data.
"""

import json
import os
import re
from datetime import datetime, timezone

from . import gates

READ_ONLY = ("goto", "wait_for", "screenshot", "extract_text")
STATUSES = ("success", "failed", "skipped", "stopped_at_gate", "stopped_captcha")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_id(task, when=None):
    when = when or datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "-", (task or "run").lower()).strip("-")[:40] or "run"
    return when.strftime("%Y%m%d-%H%M%S") + "-" + slug


class AuditLog:
    def __init__(self, plan, run_dir, run_id=None, clock=now_iso):
        self.plan = plan
        self.run_dir = run_dir
        self.run_id = run_id or os.path.basename(run_dir.rstrip("/"))
        self.clock = clock
        self.started_at = clock()
        self.outcomes = []
        os.makedirs(run_dir, exist_ok=True)

    def screenshot_path(self, number):
        return os.path.join(self.run_dir, f"step-{number:02d}.png")

    def record(self, number, step, status, strategy=None, retries=0,
               screenshot=None, text=None, error=None):
        assert status in STATUSES, status
        value = step.value
        if value and gates.is_sensitive(step.target):
            value = "[redacted]"
        self.outcomes.append({
            "step": number,
            "action": step.action,
            "target": step.target,
            "value": value,
            "description": step.description,
            "classification": gates.classify(step),
            "status": status,
            "strategy": strategy,
            "retries": retries,
            "screenshot": os.path.basename(screenshot) if screenshot else None,
            "text": text,
            "error": error,
        })

    def changes(self):
        changed = []
        for o, step in self._done():
            if o["action"] in READ_ONLY:
                continue
            if o["classification"] == gates.IRREVERSIBLE:
                changed.append(f"IRREVERSIBLE ({gates.irreversible_kind(step)}), approved by you: {o['description']}")
            elif o["action"] in ("fill", "select"):
                changed.append(f"Entered '{o['value']}' into '{o['target']}' (in the page form only)")
            else:
                changed.append(f"Clicked '{o['target']}' (may change what the page shows)")
        return changed

    def _done(self):
        for o in self.outcomes:
            if o["status"] == "success":
                yield o, self.plan.steps[o["step"] - 1]

    def to_dict(self, final_status, message):
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.clock(),
            "task": self.plan.task,
            "source": self.plan.source,
            "final_status": final_status,
            "message": message,
            "planned": [
                dict(s.to_dict(), step=i, classification=gates.classify(s))
                for i, s in enumerate(self.plan.steps, 1)
            ],
            "outcomes": self.outcomes,
            "changes": self.changes(),
        }

    def finish(self, final_status, message):
        """Write log.json and report.md. Returns (log_dict, report_text)."""
        log = self.to_dict(final_status, message)
        report = render_report(log)
        with open(os.path.join(self.run_dir, "log.json"), "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2)
            f.write("\n")
        with open(os.path.join(self.run_dir, "report.md"), "w", encoding="utf-8") as f:
            f.write(report)
        return log, report


def render_report(log):
    """Render a run log as a Markdown report."""
    lines = [
        f"# PagePilot run report: {log['run_id']}",
        "",
        f"- Task: {log['task']}",
        f"- Source: {log['source']}",
        f"- Started: {log['started_at']}",
        f"- Finished: {log['finished_at']}",
        f"- Result: **{log['final_status']}**. {log['message']}",
        "",
        "## Planned steps",
        "",
    ]
    for s in log["planned"]:
        lines.append(f"{s['step']}. {s['description']} ({s['action']}, {s['classification']})")
    lines += ["", "## Step outcomes", "",
              "| # | Action | Status | Strategy | Retries | Screenshot | Notes |",
              "|---|--------|--------|----------|---------|------------|-------|"]
    for o in log["outcomes"]:
        note = o["error"] or (f"text: {o['text']}" if o["text"] else "")
        note = note.replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {o['step']} | {o['action']} | {o['status']} | {o['strategy'] or '-'} | "
            f"{o['retries']} | {o['screenshot'] or '-'} | {note} |"
        )
    lines += ["", "## What actually changed", ""]
    if log["changes"]:
        lines += [f"- {c}" for c in log["changes"]]
    else:
        lines.append("Nothing changed. The run only opened pages, waited, read text, and took screenshots.")
    lines.append("")
    return "\n".join(lines)
