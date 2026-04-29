"""
mantid_memory_fragmentation.py
==============================

Purpose
-------
This script investigates Mantid memory fragmentation in isolation by exercising
the same internal Mantid code paths that ``live_data_memory_leak_v2.py`` exercises
*after* it has obtained a live-data chunk -- but **without** invoking any live-data
listener, ``LoadLiveData``, ``hasLiveDataConnection``, ``readLiveMetadata``, or
related machinery.

It is therefore runnable on any developer workstation (no ``bl3-daq1`` connection
required).

Live-data analog
----------------
See ``tests/cis_tests/live_data_memory_leak_v2.py`` for the equivalent script that
drives the same Mantid code paths via the live-data stack.

Memory footprint
----------------
* A one-time circular buffer of ``~5 GB`` of ``float64`` values is allocated before
  the loop.
* Each loop iteration creates a SNAP-sized ``EventWorkspace`` of ``~2.5 GB`` of
  ``TofEvent`` objects (16 bytes each), which is then converted to a ``Workspace2D``
  via ``ConvertToMatrixWorkspace`` (matching the ``PreserveEvents=False`` branch of
  ``LoadLiveData::exec`` in ``Framework/LiveData/src/LoadLiveData.cpp`` ~L488-535).
  ``events_per_pixel`` is rounded down to the nearest power of two so that each
  ``EventList``'s underlying ``std::vector<TofEvent>`` capacity equals its size --
  otherwise vector growth (powers of two) would inflate resident memory by up to
  ~2x across all ~1.18 M spectra.
* The event workspace is created with a single-bin X-axis (``BinWidth == XMax``)
  so the resulting histogram is small (~28 MB) -- this matches the typical
  live-data chunk shape.  Multi-bin event workspaces (e.g. ``BinWidth=1.0`` over
  ``[0, 1000]`` us) would yield a ~28 GB Workspace2D after conversion, which is
  not representative of the live-data path and would OOM the workstation.
* Peak RSS during the conversion step is therefore **>= ~5 GB** (buffer + event WS
  resident simultaneously).

What this script does NOT use
------------------------------
* ``LoadLiveData``
* ``hasLiveDataConnection``
* ``readLiveMetadata`` / ``_readLiveData`` / ``_liveMetadataFromRun``
* ``RunMetadata`` / ``DetectorState``
* ``socket`` / ``urlparse`` / any SNS live-data listener machinery
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import os
import time
import tracemalloc

import numpy as np
import pydantic  # noqa: F401 -- kept for structural parity with the live-data script

from mantid.simpleapi import *  # noqa: F401,F403
from mantid.kernel import ConfigService

import snapred
SNAPRed_module_root = Path(snapred.__file__).parent.parent

from snapred.meta.Config import Config, datasearch_directories  # noqa: F401

# Test helper utility routines (structural parity with live_data_memory_leak_v2.py):
import sys
sys.path.insert(0, str(Path(SNAPRed_module_root).parent / "tests"))
from util.script_as_test import not_a_test, pause  # noqa: F401
from util.IPTS_override import IPTS_override

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mantid_memory_fragmentation")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_pid_rss_kb(pid: int):
    """
    Retrieves the Resident Set Size (RSS) in KB for a given PID
    using the Linux /proc/[pid]/smaps_rollup file.
    """
    path = f"/proc/{pid}/smaps_rollup"
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith("Rss:"):
                    # Format is usually: "Rss:                1234 kB"
                    parts = line.split()
                    return int(parts[1])
    except FileNotFoundError:
        return f"Error: {path} not found. (Requires Linux kernel 4.14+)"
    except PermissionError:
        return f"Error: Permission denied accessing {path}."
    except Exception as e:  # noqa: BLE001
        return f"Error: {str(e)}"


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

N_TESTS = 100                              # number of loop iterations
DT_SLEEP = 0.0                             # seconds between iterations (default: no throttling)
EVENT_WS_TARGET_BYTES = int(2.5 * 1024**3)  # ~2.5 GB per-iteration event workspace
BUFFER_TARGET_BYTES   = int(5.0 * 1024**3)  # ~5 GB circular buffer of float64 doubles
TOF_MAX_US = 1000.0                         # physical TOF range upper bound (microseconds)
RSS_PRINT_INTERVAL_S = 10.0                 # throttle RSS printing

# TofEvent is 16 bytes in Mantid (double TOF + 8-byte pulse-time):
EVENTS_PER_ITER = EVENT_WS_TARGET_BYTES // 16   # ~167 M events for 2.5 GB
BUFFER_LEN      = BUFFER_TARGET_BYTES // 8      # ~671 M float64 values for 5 GB

# Number of log values drawn from the buffer per iteration per log name:
N_LOG_VALUES = 10

# ---------------------------------------------------------------------------
# Always set the facility (structural parity with live_data_memory_leak_v2.py)
# ---------------------------------------------------------------------------
ConfigService.setFacility(Config["liveData.facility.name"])

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
with IPTS_override():

    # ------------------------------------------------------------------
    # One-time setup
    # ------------------------------------------------------------------

    # 1. Allocate the circular buffer
    buffer = np.random.default_rng(seed=12345).uniform(0.0, TOF_MAX_US, size=BUFFER_LEN)
    print(f"Circular buffer allocated: {buffer.nbytes / 1024**3:.2f} GB")

    # 2. Workspace names
    ev_ws_name   = "frag_event_ws"
    hist_ws_name = "frag_hist_ws"

    # 3. Empty logs dict
    logs: dict = {}

    # 4. Probe SNAP geometry
    LoadEmptyInstrument(InstrumentName="SNAP", OutputWorkspace="__snap_probe")
    num_hist = mtd["__snap_probe"].getNumberHistograms()
    logger.debug(f"SNAP num histograms: {num_hist}")
    DeleteWorkspace(Workspace="__snap_probe")

    # SNAP has 18 banks of 256x256 pixels = 1,179,648 spectra.
    #
    # Round `events_per_pixel` DOWN to the nearest power of 2.  Each Mantid
    # `EventList` is backed by a `std::vector<TofEvent>` that is filled via
    # `push_back`; its capacity therefore grows in powers of two.  If
    # `events_per_pixel` is e.g. 142, the per-spectrum capacity rounds up to
    # 256 -- nearly doubling resident memory across ~1.18 M spectra (an extra
    # ~2 GB) and pushing first-iteration RSS well above the intended
    # `BUFFER_TARGET_BYTES + EVENT_WS_TARGET_BYTES`.
    raw_events_per_pixel = max(1, EVENTS_PER_ITER // num_hist)
    events_per_pixel = 1 << (raw_events_per_pixel.bit_length() - 1)
    actual_events = events_per_pixel * num_hist
    logger.debug(
        f"events_per_pixel={events_per_pixel} (raw={raw_events_per_pixel}, rounded down to power of 2), "
        f"actual total events per iter={actual_events} "
        f"(~{actual_events * 16 / 1024**3:.2f} GB)"
    )

    # 5. Buffer cursor, RSS throttle, and perf timer
    offset = 0
    last_print = 0.0   # so iteration 0 always prints
    start_perf = time.perf_counter()

    # 6. Start tracemalloc
    tracemalloc.start()

    # ------------------------------------------------------------------
    # Per-iteration loop
    # ------------------------------------------------------------------
    for n_test in range(N_TESTS):

        # 1. Create the event workspace with SNAP geometry.
        #    BinWidth == (XMax - XMin) gives a single-bin X-axis.  This matches the
        #    typical live-data chunk shape and -- critically -- keeps the size of the
        #    histogram produced by `ConvertToMatrixWorkspace` below modest.  With
        #    e.g. `BinWidth=1.0` and `XMax=1000.0`, the resulting Workspace2D would
        #    carry 1000 bins x 1,179,648 spectra x 24 B (X+Y+E) ~ 28 GB, which is
        #    not what the live-data `PreserveEvents=False` path produces and would
        #    blow up RSS well past the ~5 GB target on the first iteration.
        CreateSampleWorkspace(
            OutputWorkspace=ev_ws_name,
            WorkspaceType="Event",
            NumBanks=18,
            BankPixelWidth=256,
            NumEvents=events_per_pixel,
            XMin=0.0,
            XMax=TOF_MAX_US,
            BinWidth=TOF_MAX_US,
            Random=True,
        )
        LoadInstrument(
            Workspace=ev_ws_name,
            InstrumentName="SNAP",
            RewriteSpectraMap=True,
        )

        # 2. Per-iteration TOF shift from the circular buffer
        #    offset_shift: cursor for the bin-offset value (advances by EVENTS_PER_ITER)
        #    offset_logs:  cursor for the log-value slice (advances by N_LOG_VALUES)
        shift_us = float(buffer[offset]) * 0.01   # 0–10 µs shift
        ChangeBinOffset(
            InputWorkspace=ev_ws_name,
            OutputWorkspace=ev_ws_name,
            Offset=shift_us,
        )
        offset_logs = (offset + EVENTS_PER_ITER) % BUFFER_LEN
        offset = offset_logs   # advance main cursor past the shift-value region

        log_end = offset_logs + N_LOG_VALUES
        if log_end <= BUFFER_LEN:
            log_values = buffer[offset_logs:log_end]
        else:
            # wrap around
            log_values = np.concatenate([buffer[offset_logs:], buffer[: log_end - BUFFER_LEN]])
        offset = (offset_logs + N_LOG_VALUES) % BUFFER_LEN

        # 3. Add random time-series logs and scalar sample logs
        base_time = datetime.now(timezone.utc).replace(microsecond=0)
        for log_name in ("proton_charge", "frequency", "temperature"):
            for i, val in enumerate(log_values):
                iso_ts = (base_time + timedelta(seconds=i)).isoformat()
                AddTimeSeriesLog(
                    Workspace=ev_ws_name,
                    Name=log_name,
                    Time=iso_ts,
                    Value=float(val),
                    Type="double",
                )

        AddSampleLog(
            Workspace=ev_ws_name,
            LogName="run_number",
            LogText=str(46342 + n_test),
            LogType="Number",
        )
        AddSampleLog(
            Workspace=ev_ws_name,
            LogName="run_title",
            LogText=f"fragmentation_test_iter_{n_test}",
            LogType="String",
        )

        # 4. Convert to Workspace2D (matches PreserveEvents=False branch of LoadLiveData)
        ConvertToMatrixWorkspace(
            InputWorkspace=ev_ws_name,
            OutputWorkspace=hist_ws_name,
        )

        # 5. Delete the event workspace
        DeleteWorkspace(Workspace=ev_ws_name)

        # 6. Transfer logs from the histogram workspace to the logs dict
        logs.clear()
        run = mtd[hist_ws_name].getRun()
        for prop in run.getProperties():
            logs[prop.name] = prop.value

        # 7. Throttled RSS reporting (~every 10 s, always on iteration 0)
        now = time.perf_counter()
        if n_test == 0 or (now - last_print) >= RSS_PRINT_INTERVAL_S:
            elapsed = now - start_perf
            rss = get_pid_rss_kb(os.getpid())
            print(
                f"iter {n_test}: {elapsed:.4f} s elapsed, RSS {rss} kB, "
                f"events ~{events_per_pixel * num_hist}, logs entries: {len(logs)}"
            )
            last_print = now

        # 8. Optional sleep
        if DT_SLEEP > 0.0:
            time.sleep(DT_SLEEP)

    # ------------------------------------------------------------------
    # Post-loop: tracemalloc report
    # ------------------------------------------------------------------
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")

    print("-----------------------------------------------------------")
    print("--------------- Memory-allocation traces ------------------")
    print("-----------------------------------------------------------")
    print("[ Top 10 ]")
    for stat in top_stats[:10]:
        print(stat)
    print("-----------------------------------------------------------")
