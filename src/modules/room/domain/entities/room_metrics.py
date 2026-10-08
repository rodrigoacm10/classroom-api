from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoomMetrics:
    total_rooms: int
    avg_radius: int
    precisas_count: int
    amplas_count: int
