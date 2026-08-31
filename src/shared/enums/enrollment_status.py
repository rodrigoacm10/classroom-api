from enum import Enum


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
