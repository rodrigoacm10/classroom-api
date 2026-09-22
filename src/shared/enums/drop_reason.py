from enum import Enum


class DropReason(str, Enum):
    ADMIN_CANCELLATION = "admin_cancellation"
    ROLE_CHANGE = "role_change"
