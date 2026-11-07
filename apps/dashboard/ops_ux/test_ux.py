"""UX-32 ops composition contract tests."""
from ux_spec import (
    A11Y_REQUIREMENTS,
    REGIONS,
    RESPONDER_TASK_PATH,
    TASK_STEP_BUDGET_S,
    TASK_TOTAL_BUDGET_S,
    responder_path_complete,
    validate_layout,
    visible_regions,
)


def test_all_regions_defined():
    assert set(REGIONS) == {"incident_queue", "incident_doc",
                            "scope_matrix", "chat", "admin_panel",
                            "approvals"}


def test_role_visibility_matrix():
    assert "admin_panel" in visible_regions("admin")
    assert "admin_panel" not in visible_regions("commander")
    assert "approvals" in visible_regions("commander")
    assert "approvals" not in visible_regions("responder")
    assert "scope_matrix" in visible_regions("observer")
    assert "admin_panel" not in visible_regions("observer")
    assert visible_regions("device") == set()


def test_responder_60s_path():
    # responder must reach all 4 task regions
    assert responder_path_complete("responder")
    # observer lacks write regions but path is read-focused; verify
    # the critical doc+scope+chat are visible
    obs = visible_regions("observer")
    assert {"incident_doc", "scope_matrix", "chat"} <= obs
    # budgets sane: 4 steps x 15s = 60s
    assert len(RESPONDER_TASK_PATH) * TASK_STEP_BUDGET_S == \
        TASK_TOTAL_BUDGET_S


def test_layout_validation():
    assert validate_layout(["incident_queue", "incident_doc",
                            "scope_matrix", "chat", "admin_panel",
                            "approvals"]) == []
    missing = validate_layout(["incident_queue"])
    assert "chat" in missing and "admin_panel" in missing


def test_accessibility_contract():
    assert "stale_data_text_not_just_color" in A11Y_REQUIREMENTS
    assert "keyboard_navigable" in A11Y_REQUIREMENTS
