# Test-related imports go last:
from unittest import mock

import pytest

from snapred.backend.error.RunStatus import RunStatus


def _make_run(
    has_icp_event=False,
    icp_value=None,
    has_running=False,
    running_value=None,
    has_end_time=False,
):
    """Helper: build a mock mantid.api.Run with configurable log properties."""
    run = mock.Mock()

    # Properties present on this Run:
    present = set()
    if has_icp_event:
        present.add("icp_event")
    if has_running:
        present.add("running")
    if has_end_time:
        present.add("end_time")

    def _has_property(name):
        return name in present

    def _get_property(name):
        prop = mock.Mock()
        if name == "icp_event":
            prop.value = icp_value if icp_value is not None else []
        elif name == "running":
            prop.value = running_value if running_value is not None else []
        elif name == "end_time":
            prop.value = "2026-04-09T00:00:00"
        return prop

    run.hasProperty.side_effect = _has_property
    run.getProperty.side_effect = _get_property
    return run


# --- StrEnum basics ---

def test_RunStatus_enum_members():
    expected = {"STOPPED", "PAUSED", "RUNNING", "ERROR"}
    actual = {s.name for s in RunStatus}
    assert actual == expected


def test_RunStatus_string_values():
    assert str(RunStatus.RUNNING) == "RUNNING"
    assert str(RunStatus.STOPPED) == "STOPPED"
    assert str(RunStatus.PAUSED) == "PAUSED"
    assert str(RunStatus.ERROR) == "ERROR"


def test_RunStatus_from_string():
    assert RunStatus("RUNNING") == RunStatus.RUNNING
    assert RunStatus("STOPPED") == RunStatus.STOPPED
    assert RunStatus("PAUSED") == RunStatus.PAUSED
    assert RunStatus("ERROR") == RunStatus.ERROR


def test_RunStatus_invalid_string_raises():
    with pytest.raises(ValueError):
        RunStatus("UNKNOWN_STATUS")


# --- from_run factory ---

def test_from_run_error_on_abort_command():
    """ICP event log ending in ABORT → ERROR."""
    run = _make_run(has_icp_event=True, icp_value=["BEGIN RUN", "ABORT 12345"])
    assert RunStatus.from_run(run) == RunStatus.ERROR


def test_from_run_running_when_running_log_true():
    """'running' log with last value True → RUNNING."""
    run = _make_run(has_running=True, running_value=[True])
    assert RunStatus.from_run(run) == RunStatus.RUNNING


def test_from_run_not_running_when_running_log_false():
    """'running' log with last value False + end_time → STOPPED."""
    run = _make_run(has_running=True, running_value=[True, False], has_end_time=True)
    assert RunStatus.from_run(run) == RunStatus.STOPPED


def test_from_run_stopped_when_end_time_present():
    """Presence of 'end_time' log → STOPPED (if not still running)."""
    run = _make_run(has_end_time=True)
    assert RunStatus.from_run(run) == RunStatus.STOPPED


def test_from_run_paused_on_pause_command():
    """ICP event log ending in PAUSE (and no end_time) → PAUSED."""
    run = _make_run(has_icp_event=True, icp_value=["BEGIN RUN", "PAUSE"])
    assert RunStatus.from_run(run) == RunStatus.PAUSED


def test_from_run_stopped_on_end_command():
    """ICP event log ending in END (and no end_time) → STOPPED."""
    run = _make_run(has_icp_event=True, icp_value=["BEGIN RUN", "END RUN"])
    assert RunStatus.from_run(run) == RunStatus.STOPPED


def test_from_run_end_se_wait_not_treated_as_end():
    """END_SE_WAIT in ICP log should not be treated as a run END → falls through to PAUSED fallback."""
    run = _make_run(has_icp_event=True, icp_value=["BEGIN RUN", "END_SE_WAIT"])
    assert RunStatus.from_run(run) == RunStatus.PAUSED


def test_from_run_fallback_paused_when_no_relevant_logs():
    """No running log, no icp_event, no end_time → fallback PAUSED."""
    run = _make_run()
    assert RunStatus.from_run(run) == RunStatus.PAUSED


def test_from_run_abort_takes_priority_over_running_log():
    """ABORT in ICP log → ERROR even if 'running' log suggests running."""
    run = _make_run(
        has_icp_event=True,
        icp_value=["ABORT 12345"],
        has_running=True,
        running_value=[True],
    )
    assert RunStatus.from_run(run) == RunStatus.ERROR


def test_from_run_icpevent_alias():
    """Handles 'icpevent' as an alias for 'icp_event'."""
    run = mock.Mock()

    def _has(name):
        return name == "icpevent"

    def _get(name):
        prop = mock.Mock()
        prop.value = ["ABORT 12345"] if name == "icpevent" else []
        return prop

    run.hasProperty.side_effect = _has
    run.getProperty.side_effect = _get
    assert RunStatus.from_run(run) == RunStatus.ERROR
