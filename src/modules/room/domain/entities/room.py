import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class Room:
    tenant_id: UUID
    name: str
    latitude: float
    longitude: float
    tolerance_radius_meters: int = 50
    deleted: bool = False
    created_by: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_within_radius(self, latitude: float, longitude: float) -> bool:
        """
        Verificação aproximada em Python (Fórmula de Haversine em metros).
        Usado principalmente para testes unitários sem dependência de banco de dados.
        """
        R = 6_371_000  # Raio médio da Terra em metros

        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(latitude), math.radians(longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_meters = R * c

        return distance_meters <= self.tolerance_radius_meters
