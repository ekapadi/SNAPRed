# Test-related imports go last:
import pytest

from snapred.backend.error.LiveDataState import LiveDataState


def test_LiveDataState():
    # all properties are initialized correctly
    state = LiveDataState("message", LiveDataState.Type.RUN_START, "12345", "0")
    assert state.message == "message"
    assert state.transition == LiveDataState.Type.RUN_START
    assert state.endRunNumber == "12345"
    assert state.startRunNumber == "0"


def test_LiveDataState_runStateTransition_start():
    # a transition from "no run" state is recognized as a start of run
    state = LiveDataState.runStateTransition("12345", "0")
    assert state.message.startswith("start of run")
    assert "12345" in state.message
    assert "0" not in state.message


def test_LiveDataState_runStateTransition_end():
    # a transition to a "no run" state is recognized as an end of run
    state = LiveDataState.runStateTransition("0", "12345")
    assert state.message.startswith("end of run")
    assert "12345" in state.message
    assert "0" not in state.message


def test_LiveDataState_runStateTransition_gap():
    # a gap in run-number values, without an intervening "no run" state, is recognized
    state = LiveDataState.runStateTransition("12346", "12345")
    assert state.message.startswith("run-number gap:")
    assert "12346" in state.message
    assert "12345" in state.message


def test_LiveDataState_runStateTransition_unexpected():
    # all run numbers must be greater than zero
    with pytest.raises(ValueError, match=r"unexpected run-state transition:.*"):
        LiveDataState.runStateTransition("-1", "-2")


def test_LiveDataState_runStateTransition_no_transition():
    # start and end run numbers cannot be the same
    with pytest.raises(ValueError, match=r"Not a valid run-state transition:.*"):
        LiveDataState.runStateTransition("12345", "12345")


def test_LiveDataState_runStateTransition_invalid_transition():
    # run numbers cannot decrease, except to zero
    with pytest.raises(ValueError, match=r"Not a valid run-state transition:.*"):
        LiveDataState.runStateTransition("12344", "12345")


def test_LiveDataState_model_defaults():
    # Model can be constructed with all defaults.
    model = LiveDataState.Model()
    assert model.message == "unset"
    assert model.transition == LiveDataState.Type.UNSET
    assert model.endRunNumber == "0"
    assert model.startRunNumber == "0"


def test_LiveDataState_type_is_non_transition_state_true():
    # UNSET, NOT_RUNNING, RUNNING, and DEAD_TIME are non-transition states.
    for t in (
        LiveDataState.Type.UNSET,
        LiveDataState.Type.NOT_RUNNING,
        LiveDataState.Type.RUNNING,
        LiveDataState.Type.DEAD_TIME,
    ):
        assert t.is_non_transition_state is True


def test_LiveDataState_type_is_non_transition_state_false():
    # RUN_START, RUN_END, and RUN_GAP are transition states.
    for t in (LiveDataState.Type.RUN_START, LiveDataState.Type.RUN_END, LiveDataState.Type.RUN_GAP):
        assert t.is_non_transition_state is False


def test_LiveDataState_non_transition_state_mismatched_run_numbers_raises():
    # A non-transition Model with mismatched run numbers must raise ValueError.
    with pytest.raises(ValueError, match=r"a non-transition.*"):
        LiveDataState.Model(
            transition=LiveDataState.Type.RUNNING,
            endRunNumber="12345",
            startRunNumber="0",
        )


def test_LiveDataState_running():
    # running() creates a RUNNING state with the given run number.
    state = LiveDataState.running("12345")
    assert state.transition == LiveDataState.Type.RUNNING
    assert state.message == "running"
    assert state.endRunNumber == "12345"
    assert state.startRunNumber == "12345"


def test_LiveDataState_running_accepts_int():
    # running() converts an integer run number to string.
    state = LiveDataState.running(12345)
    assert state.endRunNumber == "12345"
    assert state.startRunNumber == "12345"


def test_LiveDataState_notRunning():
    # notRunning() creates a NOT_RUNNING state with run number 0.
    state = LiveDataState.notRunning()
    assert state.transition == LiveDataState.Type.NOT_RUNNING
    assert state.message == "not running"
    assert state.endRunNumber == "0"
    assert state.startRunNumber == "0"


def test_LiveDataState_deadTimeInterval():
    # deadTimeInterval() creates a DEAD_TIME state with the given run number.
    state = LiveDataState.deadTimeInterval("12345")
    assert state.transition == LiveDataState.Type.DEAD_TIME
    assert state.message == "dead-time interval"
    assert state.endRunNumber == "12345"
    assert state.startRunNumber == "12345"


def test_LiveDataState_deadTimeInterval_accepts_int():
    # deadTimeInterval() converts an integer run number to string.
    state = LiveDataState.deadTimeInterval(12345)
    assert state.endRunNumber == "12345"


def test_LiveDataState_parse_raw():
    # parse_raw() reconstructs a LiveDataState from its JSON model representation.
    original = LiveDataState.running("12345")
    json_str = original.model.model_dump_json()
    parsed = LiveDataState.parse_raw(json_str)
    assert parsed.transition == original.transition
    assert parsed.endRunNumber == original.endRunNumber
    assert parsed.startRunNumber == original.startRunNumber
    assert parsed.message == original.message
