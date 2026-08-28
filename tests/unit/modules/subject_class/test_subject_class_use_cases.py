from uuid import uuid4

import pytest

from modules.room.domain.entities.room import Room
from modules.subject_class.application.use_cases.create_subject_class import (
    CreateSubjectClassInput,
    CreateSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.delete_subject_class import (
    DeleteSubjectClassInput,
    DeleteSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.get_subject_class import (
    GetSubjectClassInput,
    GetSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.list_subject_classes import (
    ListSubjectClassesInput,
    ListSubjectClassesUseCase,
)
from modules.subject_class.application.use_cases.update_subject_class import (
    UpdateSubjectClassInput,
    UpdateSubjectClassUseCase,
)
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException
from tests.unit.fakes.fake_room_repository import FakeRoomRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestSubjectClassUseCases:

    async def test_create_subject_class_success(self):
        """Deve criar uma turma de disciplina com sucesso vinculando a sala e o TenantMember do professor."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        room_repo = FakeRoomRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        room = Room(tenant_id=tenant.id, name="Lab 1", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        prof_user_id = uuid4()
        prof_member = TenantMember(tenant_id=tenant.id, user_id=prof_user_id, role=UserRole.PROFESSOR)
        await member_repo.save(prof_member)

        use_case = CreateSubjectClassUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            room_repo=room_repo,
            member_repo=member_repo,
        )

        input_data = CreateSubjectClassInput(
            tenant_id=tenant.id,
            professor_id=prof_user_id,
            room_id=room.id,
            name="Turma A",
            discipline_name="Algoritmos",
        )

        result = await use_case.execute(input_data)
        assert result.id is not None
        assert result.tenant_id == tenant.id
        assert result.professor_id == prof_member.id
        assert result.room_id == room.id
        assert result.name == "Turma A"
        assert result.discipline_name == "Algoritmos"
        assert result.deleted is False

    async def test_create_subject_class_tenant_not_found(self):
        """Deve lançar ResourceNotFoundException quando a instituição fornecida não for encontrada ou estiver deletada."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        room_repo = FakeRoomRepository()
        member_repo = FakeTenantMemberRepository()

        use_case = CreateSubjectClassUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            room_repo=room_repo,
            member_repo=member_repo,
        )

        input_data = CreateSubjectClassInput(
            tenant_id=uuid4(),
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Turma A",
            discipline_name="Algoritmos",
        )

        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada."):
            await use_case.execute(input_data)

    async def test_create_subject_class_room_not_found(self):
        """Deve lançar ResourceNotFoundException quando a sala indicada não existir na instituição."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        room_repo = FakeRoomRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        use_case = CreateSubjectClassUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            room_repo=room_repo,
            member_repo=member_repo,
        )

        input_data = CreateSubjectClassInput(
            tenant_id=tenant.id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Turma A",
            discipline_name="Algoritmos",
        )

        with pytest.raises(ResourceNotFoundException, match="Sala não encontrada."):
            await use_case.execute(input_data)

    async def test_create_subject_class_professor_not_found(self):
        """Deve lançar ResourceNotFoundException quando o professor indicado não for membro ativo da instituição."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        room_repo = FakeRoomRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        room = Room(tenant_id=tenant.id, name="Lab 1", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        use_case = CreateSubjectClassUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            room_repo=room_repo,
            member_repo=member_repo,
        )

        input_data = CreateSubjectClassInput(
            tenant_id=tenant.id,
            professor_id=uuid4(),
            room_id=room.id,
            name="Turma A",
            discipline_name="Algoritmos",
        )

        with pytest.raises(ResourceNotFoundException, match="Professor não encontrado nesta instituição."):
            await use_case.execute(input_data)

    async def test_create_subject_class_with_student_role_fails(self):
        """Deve lançar BusinessRuleException quando se tenta atribuir uma turma a um membro com o papel de ALUNO."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        room_repo = FakeRoomRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        room = Room(tenant_id=tenant.id, name="Lab 1", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        student_user_id = uuid4()
        student_member = TenantMember(tenant_id=tenant.id, user_id=student_user_id, role=UserRole.ALUNO)
        await member_repo.save(student_member)

        use_case = CreateSubjectClassUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            room_repo=room_repo,
            member_repo=member_repo,
        )

        input_data = CreateSubjectClassInput(
            tenant_id=tenant.id,
            professor_id=student_user_id,
            room_id=room.id,
            name="Turma A",
            discipline_name="Algoritmos",
        )

        with pytest.raises(BusinessRuleException, match="Apenas professores ou administradores podem ministrar turmas."):
            await use_case.execute(input_data)

    async def test_get_subject_class_success(self):
        """Deve retornar os detalhes de uma turma existente quando solicitada pelo ID e tenant."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_id = uuid4()
        sc = SubjectClass(
            tenant_id=tenant_id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Turma 101",
            discipline_name="Cálculo 1",
        )
        await subject_class_repo.save(sc)

        use_case = GetSubjectClassUseCase(subject_class_repo=subject_class_repo)
        result = await use_case.execute(GetSubjectClassInput(subject_class_id=sc.id, tenant_id=tenant_id))

        assert result.id == sc.id
        assert result.name == "Turma 101"

    async def test_get_subject_class_not_found_when_soft_deleted(self):
        """Deve lançar ResourceNotFoundException ao tentar buscar uma turma com status de soft delete (deleted=True)."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_id = uuid4()
        sc = SubjectClass(
            tenant_id=tenant_id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Turma Deletada",
            discipline_name="Física 1",
            deleted=True,
        )
        await subject_class_repo.save(sc)

        use_case = GetSubjectClassUseCase(subject_class_repo=subject_class_repo)
        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada."):
            await use_case.execute(GetSubjectClassInput(subject_class_id=sc.id, tenant_id=tenant_id))

    async def test_list_subject_classes_excludes_soft_deleted(self):
        """Deve listar apenas as turmas ativas de uma instituição, omitindo registros com soft delete."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        tenant = Tenant(name="UPE", slug="upe")
        await tenant_repo.save(tenant)

        sc1 = SubjectClass(tenant_id=tenant.id, professor_id=uuid4(), room_id=uuid4(), name="Ativa 1", discipline_name="D1")
        sc2 = SubjectClass(tenant_id=tenant.id, professor_id=uuid4(), room_id=uuid4(), name="Deletada", discipline_name="D2", deleted=True)
        sc3 = SubjectClass(tenant_id=tenant.id, professor_id=uuid4(), room_id=uuid4(), name="Ativa 2", discipline_name="D3")
        await subject_class_repo.save(sc1)
        await subject_class_repo.save(sc2)
        await subject_class_repo.save(sc3)

        use_case = ListSubjectClassesUseCase(subject_class_repo=subject_class_repo, tenant_repo=tenant_repo)
        result = await use_case.execute(ListSubjectClassesInput(tenant_id=tenant.id))

        assert len(result) == 2
        names = [r.name for r in result]
        assert "Ativa 1" in names
        assert "Ativa 2" in names
        assert "Deletada" not in names

    async def test_update_subject_class_success(self):
        """Deve atualizar nome, disciplina e sala da turma com sucesso."""
        subject_class_repo = FakeSubjectClassRepository()
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        room1 = Room(tenant_id=tenant_id, name="Sala 1", latitude=-8.0, longitude=-34.0)
        room2 = Room(tenant_id=tenant_id, name="Sala 2", latitude=-8.1, longitude=-34.1)
        await room_repo.save(room1)
        await room_repo.save(room2)

        sc = SubjectClass(
            tenant_id=tenant_id,
            professor_id=uuid4(),
            room_id=room1.id,
            name="Nome Antigo",
            discipline_name="Disciplina Antiga",
        )
        await subject_class_repo.save(sc)

        use_case = UpdateSubjectClassUseCase(subject_class_repo=subject_class_repo, room_repo=room_repo)
        updated = await use_case.execute(
            UpdateSubjectClassInput(
                subject_class_id=sc.id,
                tenant_id=tenant_id,
                name="Nome Novo",
                discipline_name="Disciplina Nova",
                room_id=room2.id,
            )
        )

        assert updated.name == "Nome Novo"
        assert updated.discipline_name == "Disciplina Nova"
        assert updated.room_id == room2.id

    async def test_update_subject_class_soft_deleted_fails(self):
        """Deve lançar ResourceNotFoundException ao tentar atualizar dados de uma turma que foi removida com soft delete."""
        subject_class_repo = FakeSubjectClassRepository()
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        sc = SubjectClass(
            tenant_id=tenant_id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Nome Antigo",
            discipline_name="D1",
            deleted=True,
        )
        await subject_class_repo.save(sc)

        use_case = UpdateSubjectClassUseCase(subject_class_repo=subject_class_repo, room_repo=room_repo)
        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada."):
            await use_case.execute(
                UpdateSubjectClassInput(
                    subject_class_id=sc.id,
                    tenant_id=tenant_id,
                    name="Tentativa Edição",
                )
            )

    async def test_delete_subject_class_success(self):
        """Deve marcar uma turma como deletada (deleted=True) via soft delete com sucesso."""
        subject_class_repo = FakeSubjectClassRepository()
        tenant_id = uuid4()
        sc = SubjectClass(
            tenant_id=tenant_id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Para Deletar",
            discipline_name="D1",
        )
        await subject_class_repo.save(sc)

        use_case = DeleteSubjectClassUseCase(subject_class_repo=subject_class_repo)
        await use_case.execute(DeleteSubjectClassInput(subject_class_id=sc.id, tenant_id=tenant_id))

        sc_in_repo = await subject_class_repo.find_by_id(sc.id, include_deleted=True)
        assert sc_in_repo is not None
        assert sc_in_repo.deleted is True

        sc_active = await subject_class_repo.find_by_id(sc.id, include_deleted=False)
        assert sc_active is None
