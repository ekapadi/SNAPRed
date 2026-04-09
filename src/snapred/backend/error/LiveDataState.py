from enum import Enum, auto

from pydantic import BaseModel, Field, model_validator

from snapred.backend.log.logger import snapredLogger

logger = snapredLogger.getLogger(__name__)


class LiveDataState(Exception):
    """
    Raised when a live-data run changes state.
    """

    class Type(Enum):
        UNSET = 0
        
        ## ====== NON-TRANSITION STATES: =========
        
        NOT_RUNNING = auto()
        
        RUNNING = auto()
        
        # <total events> == 0: run-number, timing, and logs information may not be reliable
        DEAD_TIME = auto()

        # ====== TRANSITION STATES: ==============
        
        # <run number> > 0 <- <run number> == 0
        RUN_START = auto()

        # <run number> == 0 <- <run number> > 0
        RUN_END = auto()

        # <run number>` != <run number>  <- <run number> > 0
        RUN_GAP = auto()

        @property
        def is_non_transition_state(self):
            # Checks if the current member is one of the specific non-transition types
            return self in {
                LiveDataState.Type.UNSET,
                LiveDataState.Type.NOT_RUNNING,
                LiveDataState.Type.RUNNING,
                LiveDataState.Type.DEAD_TIME
            }

    class Model(BaseModel):
        message: str = "unset"
        transition: "LiveDataState.Type" = Field(
            default_factory=lambda: LiveDataState.Type.UNSET
        )
        endRunNumber: str = "0"
        startRunNumber: str = "0"

        @model_validator(mode="after")
        def _validate_LiveDataState(self):
            if self.transition.is_non_transition_state:
                if self.endRunNumber != self.startRunNumber:
                    raise ValueError(
                        f"a non-transition live-data state must have a constant run-number value, not: {self.endRunNumber} <- {self.startRunNumber}"
                    )                
            else:
                is_same = self.endRunNumber == self.startRunNumber
                is_decreasing = (
                    int(self.endRunNumber) > 0 
                    and int(self.startRunNumber) > 0 
                    and int(self.endRunNumber) < int(self.startRunNumber)
                )

                if is_same or is_decreasing:
                    raise ValueError(
                        f"Not a valid run-state transition: "
                        f"{self.endRunNumber} <- {self.startRunNumber}"
                    )
            return self

    def __init__(self, message: str, transition: "Type", endRunNumber: str, startRunNumber: str):
        LiveDataState.Model.model_rebuild(force=True)
        self.model = LiveDataState.Model(
            message=message, transition=transition, endRunNumber=endRunNumber, startRunNumber=startRunNumber
        )
        super().__init__(message)
        
    @property
    def message(self):
        return self.model.message

    @property
    def transition(self):
        return self.model.transition

    @property
    def endRunNumber(self):
        return self.model.endRunNumber

    @property
    def startRunNumber(self):
        return self.model.startRunNumber

    @staticmethod
    def parse_raw(raw) -> "LiveDataState":
        raw = LiveDataState.Model.model_validate_json(raw)
        return LiveDataState(**raw.dict())

    @staticmethod
    def running(runNumber: str | int) -> "LiveDataState":
        return LiveDataState(
            message="running",
            transition=LiveDataState.Type.RUNNING,
            endRunNumber=str(runNumber),
            startRunNumber=str(runNumber)
        )

    @staticmethod
    def notRunning() -> "LiveDataState":
        runNumber = 0
        return LiveDataState(
            message="not running",
            transition=LiveDataState.Type.NOT_RUNNING,
            endRunNumber=str(runNumber),
            startRunNumber=str(runNumber)
        )

    @staticmethod
    def deadTimeInterval(runNumber: str | int) -> "LiveDataState":
        return LiveDataState(
            message="dead-time interval",
            transition=LiveDataState.Type.DEAD_TIME,
            endRunNumber=str(runNumber),
            startRunNumber=str(runNumber)
        )
    
    @staticmethod
    def runStateTransition(endRunNumber: str | int, startRunNumber: str | int) -> "LiveDataState":
        transition = LiveDataState.Type.UNSET
        message = "unknown state transition"
        if int(endRunNumber) > 0 and int(startRunNumber) == 0:
            transition = LiveDataState.Type.RUN_START
            message = f"start of run {endRunNumber}"
        elif int(endRunNumber) == 0 and int(startRunNumber) > 0:
            transition = LiveDataState.Type.RUN_END
            message = f"end of run {startRunNumber}"
        elif int(endRunNumber) > 0 and int(startRunNumber) > 0:
            transition = LiveDataState.Type.RUN_GAP
            message = f"run-number gap: {endRunNumber} <- {startRunNumber}"
        else:
            raise ValueError(f"unexpected run-state transition: {endRunNumber} <- {startRunNumber}")

        return LiveDataState(
            message, transition=transition, endRunNumber=str(endRunNumber), startRunNumber=str(startRunNumber)
        )
