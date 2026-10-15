import dataclasses
import datetime
import enum
import typing

from apps.journal.models import Journal


class Half(enum.StrEnum):
    FULL = "full"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"
    UNKNOWN = "half_unknown"


LEAVE_TYPE_BY_HALF: dict[Half, Journal.LeaveType] = {
    Half.FULL: Journal.LeaveType.FULL,
    Half.FIRST_HALF: Journal.LeaveType.FIRST_HALF,
    Half.SECOND_HALF: Journal.LeaveType.SECOND_HALF,
}

WFH_TYPE_BY_HALF: dict[Half, Journal.WorkFromHomeType] = {
    Half.FULL: Journal.WorkFromHomeType.FULL,
    Half.FIRST_HALF: Journal.WorkFromHomeType.FIRST_HALF,
    Half.SECOND_HALF: Journal.WorkFromHomeType.SECOND_HALF,
}

HALF_LABEL = {
    1: "full",
    2: "first half",
    3: "second half",
}


@dataclasses.dataclass(frozen=True)
class DayState:
    """
    Leave/WFH values of a Journal for a single date
    """

    leave_type: int | None = None
    wfh_type: int | None = None

    @property
    def is_empty(self) -> bool:
        return self.leave_type is None and self.wfh_type is None

    @property
    def is_valid(self) -> bool:
        if self.leave_type is None or self.wfh_type is None:
            return True
        return (self.leave_type, self.wfh_type) in Journal.VALID_LEAVE_WFH_COMBINATION

    @property
    def blocks_first_half(self) -> bool:
        """
        Same rule used to exclude users from standup conductor selection
        """
        return self.leave_type in (Journal.LeaveType.FULL, Journal.LeaveType.FIRST_HALF) or self.wfh_type in (
            Journal.WorkFromHomeType.FULL,
            Journal.WorkFromHomeType.FIRST_HALF,
        )

    @property
    def label(self) -> str:
        parts = []
        if self.leave_type is not None:
            parts.append(f"Leave ({HALF_LABEL[self.leave_type]})")
        if self.wfh_type is not None:
            parts.append(f"WFH ({HALF_LABEL[self.wfh_type]})")
        return " + ".join(parts) or "No leave/WFH"

    def as_dict(self) -> dict[str, int | None]:
        return {"leave_type": self.leave_type, "wfh_type": self.wfh_type}

    @classmethod
    def from_journal(cls, journal: Journal) -> typing.Self:
        return cls(leave_type=journal.leave_type, wfh_type=journal.wfh_type)


EMPTY_DAY_STATE = DayState()


@dataclasses.dataclass(frozen=True)
class AvailabilityRange:
    """
    Inclusive date range of leave/WFH extracted from a thread
    """

    start_date: datetime.date
    end_date: datetime.date
    leave: Half | None = None
    wfh: Half | None = None
    source_phrase: str = ""
    """Words in the thread the range was read from"""
    open_end: bool = False
    """The absence has no end date yet; the range is its start day"""

    @property
    def has_unknown_half(self) -> bool:
        return Half.UNKNOWN in (self.leave, self.wfh)

    def as_day_state(self) -> DayState:
        return DayState(
            leave_type=LEAVE_TYPE_BY_HALF[self.leave] if self.leave else None,
            wfh_type=WFH_TYPE_BY_HALF[self.wfh] if self.wfh else None,
        )


class MissingDetail(enum.StrEnum):
    """
    What an unclear part of a thread leaves out
    """

    END_DATE = "end_date"
    DATES = "dates"
    TYPE = "type"
    DATES_AND_TYPE = "dates_and_type"


@dataclasses.dataclass(frozen=True)
class UnclearPart:
    phrase: str
    """Words in the thread that could not be written as a range"""
    missing: MissingDetail = MissingDetail.DATES_AND_TYPE

    def as_dict(self) -> dict[str, str]:
        return {"phrase": self.phrase, "missing": self.missing.value}


@dataclasses.dataclass(frozen=True)
class ThreadMessage:
    ts: str
    posted_at: datetime.datetime
    text: str


@dataclasses.dataclass
class ParseResult:
    is_about_availability: bool
    """False when the thread is not about the poster's own leave/WFH"""
    ranges: list[AvailabilityRange]
    unclear: list[UnclearPart]
    """Parts of a decided absence the parser could not write as ranges"""
    confidence: float
    raw: dict
    prompt: str = ""
    """Input text the parser sent for the thread"""
    model: str = ""
    """Name of the model that produced the result"""
    needs_care: bool = False
    """The author mentions illness, a hospital visit, a bereavement or another hard situation"""
