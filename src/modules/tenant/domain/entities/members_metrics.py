from dataclasses import dataclass


@dataclass
class MembersMetrics:
    total_members: int
    professors_count: int
    coordinators_count: int
    admins_count: int
    management_count: int
    assigned_classes_count: int

