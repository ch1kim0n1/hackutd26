"""UX-32: stress-first incident ops UX composition contract.

Defines the layout regions (queue/docs/scope/chat/admin/approvals),
per-role visibility, the <=60s responder task path, and server-side
role enforcement hooks. UI consumes this; enforcement stays server-side
(#23 identity)."""
from __future__ import annotations


# regions every ops screen must compose
REGIONS = ["incident_queue", "incident_doc", "scope_matrix", "chat",
           "admin_panel", "approvals"]

# which roles see which regions (visibility != authorization —
# server still enforces on every API call)
VISIBILITY = {
    "admin": set(REGIONS),
    "commander": {"incident_queue", "incident_doc", "scope_matrix",
                  "chat", "approvals"},
    "responder": {"incident_queue", "incident_doc", "scope_matrix",
                  "chat"},
    "observer": {"incident_queue", "incident_doc", "scope_matrix",
                 "chat"},
    "agent": {"incident_queue", "chat"},
}

# the <=60s responder task: find incident -> open doc -> see scope ->
# join chat. Each step must be <=15s for an untrained operator.
RESPONDER_TASK_PATH = [
    ("incident_queue", "find incident by severity/time"),
    ("incident_doc", "open record, read summary+timeline"),
    ("scope_matrix", "see compromised-data statuses"),
    ("chat", "read team context, post if responder"),
]
TASK_STEP_BUDGET_S = 15.0
TASK_TOTAL_BUDGET_S = 60.0


def visible_regions(role: str) -> set[str]:
    return VISIBILITY.get(role, set())


def responder_path_complete(role: str) -> bool:
    """All task-path regions must be visible to the role."""
    vis = visible_regions(role)
    return all(r in vis for r, _ in RESPONDER_TASK_PATH)


def validate_layout(regions_present: list[str]) -> list[str]:
    """Returns missing required regions — layout incomplete if any."""
    return [r for r in REGIONS if r not in regions_present]


# accessibility contract (docs/07)
A11Y_REQUIREMENTS = [
    "keyboard_navigable", "focus_visible", "aria_labels_on_icons",
    "color_not_only_signal", "stale_data_text_not_just_color",
    "screen_reader_live_regions_for_chat",
]
