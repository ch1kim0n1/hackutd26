"""OPS-38 demo runner tests — transcript honesty + structure."""
import json

from demo import FULL_DEMO_90S, WINSTEAD_3M, run_demo, write_transcript


def test_full_demo_structure():
    rep = run_demo(FULL_DEMO_90S)
    assert rep["steps"] == 7 and rep["mode"] == "SIMULATED"
    assert "SIMULATED" in rep["disclaimer"]
    actors = {s["actor"] for s in rep["transcript"]}
    assert {"operator", "system", "nemotron", "commander",
            "executor", "team"} <= actors


def test_winstead_demo_covers_adversarial():
    rep = run_demo(WINSTEAD_3M)
    assert rep["steps"] == 11
    actions = " ".join(s["action"] + " " + s["expected"]
                       for s in rep["transcript"])
    assert "denied" in actions and "revoke" in actions


def test_transcript_written(tmp_path):
    rep = run_demo(FULL_DEMO_90S)
    p = write_transcript(rep, tmp_path / "t.json")
    assert json.loads(p.read_text())["steps"] == 7


def test_mode_never_ambiguous():
    for s in FULL_DEMO_90S + WINSTEAD_3M:
        assert s.mode in ("SIMULATED", "LIVE")
    # default is SIMULATED — live must be explicit opt-in
    assert all(s.mode == "SIMULATED" for s in FULL_DEMO_90S)
