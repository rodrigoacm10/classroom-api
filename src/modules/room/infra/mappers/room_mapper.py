from typing import Any, cast

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from infra.database.models.room import RoomModel
from modules.room.domain.entities.room import Room


class RoomMapper:

    @staticmethod
    def to_domain(model: RoomModel) -> Room:
        point = cast(Point, to_shape(cast(Any, model.location)))
        return Room(
            id=model.id,
            tenant_id=model.tenant_id,
            created_by=model.created_by,
            name=model.name,
            latitude=point.y,
            longitude=point.x,
            tolerance_radius_meters=model.tolerance_radius_meters,
            deleted=model.deleted,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


    @staticmethod
    def to_model(entity: Room) -> RoomModel:
        wkt = WKTElement(f"POINT({entity.longitude} {entity.latitude})", srid=4326)
        return RoomModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            created_by=entity.created_by,
            name=entity.name,
            location=wkt,
            tolerance_radius_meters=entity.tolerance_radius_meters,
            deleted=entity.deleted,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
