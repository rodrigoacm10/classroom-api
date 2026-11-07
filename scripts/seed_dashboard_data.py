"""
Script de Seed para o Classroom API e Dashboard Web.

Objetivo:
- Cria ou recupera uma Tenant padrão ("Escola Demo Classroom")
- Cria ou recupera os professores ("Ana Professora" e "Carlos Professor")
- Cria salas de aula físicas com geolocalização PostGIS
- Cria 5 alunos de teste com matrículas ativas
- Cria 4 turmas com métricas realistas (1 com 100%, 2 com < 75% e 1 com 90%)
- Cria histórico de chamadas nos últimos 30 dias e na semana atual
- Abre uma sessão de chamada AO VIVO no momento para testar o banner em tempo real

Uso:
    uv run python scripts/seed_dashboard_data.py
    ou
    PYTHONPATH=src .venv/bin/python scripts/seed_dashboard_data.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import select, text

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel, TenantModel
from infra.database.models.user import UserModel
from infra.database.session import AsyncSessionLocal
from security.password import hash_password
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole

DEFAULT_TENANT_NAME = "Escola Demo Classroom"
DEFAULT_TENANT_SLUG = "escola-demo-classroom"

SECONDARY_TENANT_NAME = "Faculdade de Tecnologia Alpha"
SECONDARY_TENANT_SLUG = "faculdade-alpha"


class ProfessorSeedData(TypedDict):
    name: str
    email: str
    role: UserRole


PROFESSORS_DATA: list[ProfessorSeedData] = [
    {
        "name": "Ana Professora",
        "email": "ana.professora@classroom.dev",
        "role": UserRole.ADMIN,
    },
    {
        "name": "Carlos Professor",
        "email": "carlos.professor@classroom.dev",
        "role": UserRole.PROFESSOR,
    },
]

STUDENTS_DATA = [
    {"name": "Lucas Mendes", "email": "lucas.mendes@classroom.dev"},
    {"name": "Camila Souza", "email": "camila.souza@classroom.dev"},
    {"name": "Rafael Alves", "email": "rafael.alves@classroom.dev"},
    {"name": "Joana Prado", "email": "joana.prado@classroom.dev"},
    {"name": "Beatriz Lima", "email": "beatriz.lima@classroom.dev"},
]

ROOMS_DATA = [
    {"name": "Lab 101"},
    {"name": "Lab 204"},
    {"name": "Sala 12"},
    {"name": "Sala 08"},
]


async def seed():
    async with AsyncSessionLocal() as session:
        print("=" * 65)
        print("🌱 INICIANDO SEED DE DADOS PARA AMBIENTE DE DESENVOLVIMENTO")
        print("=" * 65)

        # ── 1. Criar ou Recuperar Instituições (Tenants) ───────────────────────
        print("\n--> 1. Configurando Instituições (Tenants)...")

        # Tenant Principal
        stmt = select(TenantModel).where(TenantModel.slug == DEFAULT_TENANT_SLUG)
        tenant = (await session.execute(stmt)).scalar_one_or_none()
        if not tenant:
            tenant = TenantModel(
                name=DEFAULT_TENANT_NAME,
                slug=DEFAULT_TENANT_SLUG,
                active=True,
            )
            session.add(tenant)
            await session.flush()
            print(f"    [+] Tenant criada: {tenant.name} ({tenant.slug})")
        else:
            print(f"    [=] Tenant existente: {tenant.name} ({tenant.slug})")

        # Tenant Secundária (para teste de seleção de instituição)
        stmt_sec = select(TenantModel).where(TenantModel.slug == SECONDARY_TENANT_SLUG)
        sec_tenant = (await session.execute(stmt_sec)).scalar_one_or_none()
        if not sec_tenant:
            sec_tenant = TenantModel(
                name=SECONDARY_TENANT_NAME,
                slug=SECONDARY_TENANT_SLUG,
                active=True,
            )
            session.add(sec_tenant)
            await session.flush()
            print(f"    [+] Tenant secundária criada: {sec_tenant.name} ({sec_tenant.slug})")

        tenant_id = tenant.id

        # ── 2. Criar ou Recuperar Professores / Administradores ─────────────────
        print("\n--> 2. Configurando Usuários Professores...")
        prof_members = {}
        for p_data in PROFESSORS_DATA:
            u_stmt = select(UserModel).where(UserModel.email == p_data["email"])
            user = (await session.execute(u_stmt)).scalar_one_or_none()
            if not user:
                user = UserModel(
                    name=p_data["name"],
                    email=p_data["email"],
                    password_hash=hash_password("senha123"),
                )
                session.add(user)
                await session.flush()
                print(f"    [+] Usuário criado: {user.name} ({user.email})")
            else:
                print(f"    [=] Usuário existente: {user.name} ({user.email})")

            # Vínculo como membro do tenant
            m_stmt = select(TenantMemberModel).where(
                TenantMemberModel.tenant_id == tenant_id,
                TenantMemberModel.user_id == user.id,
            )
            member = (await session.execute(m_stmt)).scalar_one_or_none()
            if not member:
                member = TenantMemberModel(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role=p_data["role"],
                )
                session.add(member)
                await session.flush()
                print(f"    [+] Vínculo {p_data['role'].value} criado para {user.name}")
            prof_members[p_data["name"]] = member

        main_professor_member = prof_members["Ana Professora"]

        # ── 3. Criar ou Recuperar Salas Físicas (Rooms) ────────────────────────
        print("\n--> 3. Configurando Salas com Geofencing...")
        room_map = {}
        for r_data in ROOMS_DATA:
            r_stmt = select(RoomModel).where(
                RoomModel.tenant_id == tenant_id,
                RoomModel.name == r_data["name"],
                RoomModel.deleted.is_(False),
            )
            room = (await session.execute(r_stmt)).scalar_one_or_none()
            if not room:
                room = RoomModel(
                    tenant_id=tenant_id,
                    name=r_data["name"],
                    location="SRID=4326;POINT(-34.8813 -8.0578)",
                    tolerance_radius_meters=50,
                )
                session.add(room)
                await session.flush()
                print(f"    [+] Sala criada: {room.name} ({room.id})")
            else:
                print(f"    [=] Sala existente: {room.name} ({room.id})")
            room_map[r_data["name"]] = room

        # ── 4. Criar ou Recuperar os 5 Alunos de Teste ─────────────────────────
        print("\n--> 4. Configurando os 5 Alunos de Teste...")
        student_members = []
        for s_data in STUDENTS_DATA:
            u_stmt = select(UserModel).where(UserModel.email == s_data["email"])
            user = (await session.execute(u_stmt)).scalar_one_or_none()
            if not user:
                user = UserModel(
                    name=s_data["name"],
                    email=s_data["email"],
                    password_hash=hash_password("senha123"),
                )
                session.add(user)
                await session.flush()
                print(f"    [+] Aluno criado: {user.name} ({user.email})")

            # Vínculo como membro ALUNO
            m_stmt = select(TenantMemberModel).where(
                TenantMemberModel.tenant_id == tenant_id,
                TenantMemberModel.user_id == user.id,
            )
            member = (await session.execute(m_stmt)).scalar_one_or_none()
            if not member:
                member = TenantMemberModel(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role=UserRole.ALUNO,
                )
                session.add(member)
                await session.flush()
                print(f"    [+] Matrícula institucional criada para {user.name}")
            student_members.append(member)

        # ── 5. Limpar Turmas Anteriores para Garantir Idempotência ─────────────
        print("\n--> 5. Resetando turmas anteriores para o tenant...")
        await session.execute(
            text("DELETE FROM subject_classes WHERE tenant_id = :t_id"),
            {"t_id": tenant_id},
        )
        await session.flush()

        # ── 6. Criar as 4 Turmas ──────────────────────────────────────────────
        print("\n--> 6. Criando as 4 turmas ativas...")
        # Turma 1: Algoritmos e Estruturas de Dados (Meta: 100% de presença)
        t1 = SubjectClassModel(
            tenant_id=tenant_id,
            professor_id=main_professor_member.id,
            room_id=room_map["Lab 204"].id,
            name="T01",
            discipline_name="Algoritmos e Estruturas de Dados",
            active=True,
        )
        # Turma 2: Engenharia de Software (Meta: 65% de presença - < 75%)
        t2 = SubjectClassModel(
            tenant_id=tenant_id,
            professor_id=main_professor_member.id,
            room_id=room_map["Sala 08"].id,
            name="ES01",
            discipline_name="Engenharia de Software",
            active=True,
        )
        # Turma 3: Redes de Computadores (Meta: 68% de presença - < 75%)
        t3 = SubjectClassModel(
            tenant_id=tenant_id,
            professor_id=main_professor_member.id,
            room_id=room_map["Sala 12"].id,
            name="RC01",
            discipline_name="Redes de Computadores",
            active=True,
        )
        # Turma 4: Banco de Dados (Meta: 90% de presença)
        t4 = SubjectClassModel(
            tenant_id=tenant_id,
            professor_id=main_professor_member.id,
            room_id=room_map["Lab 101"].id,
            name="BD02",
            discipline_name="Banco de Dados",
            active=True,
        )
        session.add_all([t1, t2, t3, t4])
        await session.flush()

        print(
            f"    [+] Turma 1 (100%): {t1.discipline_name} ({t1.name}) - {room_map['Lab 204'].name}"
        )
        print(
            f"    [+] Turma 2 (<75%): {t2.discipline_name} ({t2.name}) - {room_map['Sala 08'].name}"
        )
        print(
            f"    [+] Turma 3 (<75%): {t3.discipline_name} ({t3.name}) - {room_map['Sala 12'].name}"
        )
        print(
            f"    [+] Turma 4 (90%):  {t4.discipline_name} ({t4.name}) - {room_map['Lab 101'].name}"
        )

        # ── 7. Matricular os 5 Alunos nas 4 Turmas ─────────────────────────────
        print("\n--> 7. Matriculando alunos nas 4 turmas...")
        for c in [t1, t2, t3, t4]:
            for m in student_members:
                enr = EnrollmentModel(
                    subject_class_id=c.id,
                    tenant_member_id=m.id,
                    status=EnrollmentStatus.ACTIVE,
                )
                session.add(enr)
        await session.flush()

        # ── 8. Criar Chamadas e Presenças ──────────────────────────────────────
        print("\n--> 8. Gerando histórico de chamadas e presenças...")
        now = datetime.now(timezone.utc)

        # ── Turma 1: 100% de Presença (3 fechadas + 1 aberta AO VIVO) ──────────
        t1_dates = [
            now - timedelta(days=3),  # SEG
            now - timedelta(days=1),  # QUA
            now - timedelta(hours=3),  # QUI
        ]
        for idx, s_date in enumerate(t1_dates, start=1):
            sess = AttendanceSessionModel(
                subject_class_id=t1.id,
                room_id=t1.room_id,
                day_code=f"100{idx}",
                opened_at=s_date,
                expires_at=s_date + timedelta(minutes=20),
                closed_at=s_date + timedelta(minutes=20),
                status=SessionStatus.CLOSED,
            )
            session.add(sess)
            await session.flush()

            # Todos os 5 presentes em todas as sessões fechadas
            for m in student_members:
                rec = AttendanceRecordModel(
                    session_id=sess.id,
                    tenant_member_id=m.id,
                    student_location="SRID=4326;POINT(-34.8813 -8.0578)",
                    distance_meters=4.5,
                    within_radius=True,
                    record_status=RecordStatus.REGULAR,
                )
                session.add(rec)
        await session.flush()

        # Sessão aberta AO VIVO agora para a Turma 1
        live_session = AttendanceSessionModel(
            subject_class_id=t1.id,
            room_id=t1.room_id,
            day_code="4821",
            opened_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=15),
            status=SessionStatus.OPEN,
        )
        session.add(live_session)
        await session.flush()

        # Todos os 5 presentes também na chamada ao vivo -> 20/20 (100.0%)
        for m in student_members:
            rec = AttendanceRecordModel(
                session_id=live_session.id,
                tenant_member_id=m.id,
                student_location="SRID=4326;POINT(-34.8813 -8.0578)",
                distance_meters=3.2,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
            session.add(rec)
        await session.flush()

        # ── Turma 2: 65% de Presença (< 75%) ──────────────────────────────────
        t2_dates = [
            now - timedelta(days=9),
            now - timedelta(days=7),
            now - timedelta(days=2),  # TER
            now - timedelta(hours=1),  # QUI
        ]
        t2_presence_map = {
            student_members[0].id: [True, False, True, False],  # Lucas: 2/4 (50%) -> Risco crítico
            student_members[1].id: [False, True, True, False],  # Camila: 2/4 (50%) -> Risco crítico
            student_members[2].id: [True, True, True, False],  # Rafael: 3/4 (75%)
            student_members[3].id: [True, False, True, True],  # Joana: 3/4 (75%)
            student_members[4].id: [False, True, True, True],  # Beatriz: 3/4 (75%)
        }
        for idx, s_date in enumerate(t2_dates, start=1):
            sess = AttendanceSessionModel(
                subject_class_id=t2.id,
                room_id=t2.room_id,
                day_code=f"200{idx}",
                opened_at=s_date,
                expires_at=s_date + timedelta(minutes=20),
                closed_at=s_date + timedelta(minutes=20),
                status=SessionStatus.CLOSED,
            )
            session.add(sess)
            await session.flush()

            for m in student_members:
                if t2_presence_map[m.id][idx - 1]:
                    rec = AttendanceRecordModel(
                        session_id=sess.id,
                        tenant_member_id=m.id,
                        student_location="SRID=4326;POINT(-34.8813 -8.0578)",
                        distance_meters=6.0,
                        within_radius=True,
                        record_status=RecordStatus.REGULAR,
                    )
                    session.add(rec)
        await session.flush()

        # ── Turma 3: 68% de Presença (< 75%) ──────────────────────────────────
        t3_dates = [
            now - timedelta(days=13),
            now - timedelta(days=8),
            now - timedelta(days=6),
            now - timedelta(days=3),  # SEG
            now - timedelta(days=1),  # QUA
        ]
        t3_presence_map = {
            student_members[0].id: [
                True,
                False,
                True,
                False,
                True,
            ],  # Lucas: 3/5 (60%) -> Risco crítico
            student_members[1].id: [
                False,
                True,
                False,
                True,
                True,
            ],  # Camila: 3/5 (60%) -> Risco crítico
            student_members[2].id: [
                True,
                True,
                False,
                False,
                True,
            ],  # Rafael: 3/5 (60%) -> Risco crítico
            student_members[3].id: [True, True, True, False, True],  # Joana: 4/5 (80%)
            student_members[4].id: [True, False, True, True, True],  # Beatriz: 4/5 (80%)
        }
        for idx, s_date in enumerate(t3_dates, start=1):
            sess = AttendanceSessionModel(
                subject_class_id=t3.id,
                room_id=t3.room_id,
                day_code=f"300{idx}",
                opened_at=s_date,
                expires_at=s_date + timedelta(minutes=20),
                closed_at=s_date + timedelta(minutes=20),
                status=SessionStatus.CLOSED,
            )
            session.add(sess)
            await session.flush()

            for m in student_members:
                if t3_presence_map[m.id][idx - 1]:
                    rec = AttendanceRecordModel(
                        session_id=sess.id,
                        tenant_member_id=m.id,
                        student_location="SRID=4326;POINT(-34.8813 -8.0578)",
                        distance_meters=5.1,
                        within_radius=True,
                        record_status=RecordStatus.REGULAR,
                    )
                    session.add(rec)
        await session.flush()

        # ── Turma 4: 90% de Presença ──────────────────────────────────────────
        t4_dates = [
            now - timedelta(days=16),
            now - timedelta(days=9),
            now - timedelta(days=2),  # TER
            now - timedelta(hours=2),  # QUI
        ]
        t4_presence_map = {
            student_members[0].id: [True, True, True, True],  # Lucas: 4/4 (100%)
            student_members[1].id: [True, False, True, True],  # Camila: 3/4 (75%)
            student_members[2].id: [True, True, True, True],  # Rafael: 4/4 (100%)
            student_members[3].id: [False, True, True, True],  # Joana: 3/4 (75%)
            student_members[4].id: [True, True, True, True],  # Beatriz: 4/4 (100%)
        }
        for idx, s_date in enumerate(t4_dates, start=1):
            sess = AttendanceSessionModel(
                subject_class_id=t4.id,
                room_id=t4.room_id,
                day_code=f"400{idx}",
                opened_at=s_date,
                expires_at=s_date + timedelta(minutes=20),
                closed_at=s_date + timedelta(minutes=20),
                status=SessionStatus.CLOSED,
            )
            session.add(sess)
            await session.flush()

            for m in student_members:
                if t4_presence_map[m.id][idx - 1]:
                    rec = AttendanceRecordModel(
                        session_id=sess.id,
                        tenant_member_id=m.id,
                        student_location="SRID=4326;POINT(-34.8813 -8.0578)",
                        distance_meters=7.3,
                        within_radius=True,
                        record_status=RecordStatus.REGULAR,
                    )
                    session.add(rec)
        await session.flush()

        await session.commit()

        print("\n" + "=" * 65)
        print("🎉 SEED CONCLUÍDO COM SUCESSO!")
        print("=" * 65)
        print("Credenciais de Acesso (Web / API):")
        print("  • E-mail: ana.professora@classroom.dev")
        print("  • Senha:  senha123")
        print(f"  • Tenant: {DEFAULT_TENANT_NAME} ({DEFAULT_TENANT_SLUG})")
        print("\nTurmas configuradas:")
        print("  1. Algoritmos e Estruturas de Dados (T01): 100.0%  (Chamada AO VIVO código 4821)")
        print("  2. Engenharia de Software (ES01):          65.0%  (Abaixo de 75%)")
        print("  3. Redes de Computadores (RC01):           68.0%  (Abaixo de 75%)")
        print("  4. Banco de Dados (BD02):                  90.0%  (Frequência normal)")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(seed())
