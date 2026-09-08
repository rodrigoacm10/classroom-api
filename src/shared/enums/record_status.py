from enum import Enum


class RecordStatus(str, Enum):
    REGULAR = "regular"
    IRREGULAR = "irregular"
    APPROVED = "approved"
    REJECTED = "rejected"
