# Salas (web)

**Quem:** professor, admin. **Objetivo:** cadastrar o ponto GPS e o raio da chamada.

## Regiões

- Título + “Nova sala”
- Tabela: `name`, raio (`tolerance_radius_meters` + “m”), coordenadas resumidas
- Form/dialog: nome, latitude, longitude, raio (5–500, default 50)
- Mapa estático ou preview do ponto — opcional no v1; se não houver mapa, inputs numéricos bastam

## Dados

- `GET/POST /tenants/{tenant_id}/rooms`
- `PATCH /tenants/{tenant_id}/rooms/{room_id}`
- `DELETE` só admin
- Schema: `src/modules/room/interface/schemas/room_schemas.py`

## Não mostrar

`created_by`, `tenant_id`.
