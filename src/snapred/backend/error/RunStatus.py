from enum import StrEnum

import mantid.api


class RunStatus(StrEnum):
    STOPPED = 'STOPPED'
    PAUSED = 'PAUSED'
    RUNNING = 'RUNNING'
    ERROR = 'ERROR'

    @classmethod
    def from_run(cls, run: mantid.api.Run) -> "RunStatus":
        """Factory method to determine the RunStatus from a Mantid Run object."""
        
        # 1. Retrieve the raw ICP event log
        icp_log = None
        if run.hasProperty("icp_event"):
            icp_log = run.getProperty("icp_event")
        elif run.hasProperty("icpevent"):
            icp_log = run.getProperty("icpevent")

        # 2. Check for an ERROR/ABORT state
        if icp_log is not None and len(icp_log.value) > 0:
            last_command = str(icp_log.value[-1]).strip()
            if "ABORT" in last_command:
                return cls.ERROR

        # 3. Check if currently RUNNING
        if run.hasProperty("running"):
            running_log = run.getProperty("running")
            if len(running_log.value) > 0:
                is_running = bool(running_log.value[-1])
                if is_running:
                    return cls.RUNNING

        # 4. Distinguish between STOPPED and PAUSED
        if run.hasProperty("end_time"):
            return cls.STOPPED
            
        if icp_log is not None and len(icp_log.value) > 0:
            last_command = str(icp_log.value[-1]).strip()
            if "PAUSE" in last_command:
                return cls.PAUSED
            elif "END" in last_command and "END_SE_WAIT" not in last_command:
                return cls.STOPPED

        # 5. Fallback
        return cls.PAUSED

# Usage:
# status = RunStatus.from_run(my_workspace.getRun())
