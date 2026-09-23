import uuid

import pytest

from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


class TestTenantMemberSQLAlchemyRepository:
    """
    Testes de integração para TenantMemberSQLAlchemyRepository.

    Validam que as queries funcionam contra o PostgreSQL real e que o
    isolamento multi-tenant está garantido nos filtros.

    TenantMember possui FKs para `users.id` e `tenants.id`, portanto cada
    teste que precisar de membership precisa criar primeiro o Tenant e o User.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        """Inicializa o repositório com a sessão de teste injetada."""
        self.repository = TenantMemberSQLAlchemyRepository(session=session)
        self.session = session

    # ─── find_by_tenant_and_user ─────────────────────────────────────────────

    async def test_find_by_tenant_and_user_returns_member_when_exists(self) -> None:
        """Membership existente → retorna TenantMember com os dados corretos."""
        tenant = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)
        await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user.id
        )

        result = await self.repository.find_by_tenant_and_user(
            tenant_id=tenant.id, user_id=user.id
        )

        assert result is not None
        assert result.tenant_id == tenant.id
        assert result.user_id == user.id

    async def test_find_by_tenant_and_user_returns_none_when_not_member(self) -> None:
        """Usuário não é membro de nenhuma tenant → retorna None."""
        tenant = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)
        # Nenhuma membership criada

        result = await self.repository.find_by_tenant_and_user(
            tenant_id=tenant.id, user_id=user.id
        )

        assert result is None

    async def test_find_by_tenant_and_user_returns_none_for_wrong_tenant(
        self,
    ) -> None:
        """
        MULTI-TENANT: Usuário é membro da tenant A, não da tenant B.
        Buscar na tenant B deve retornar None — sem vazamento de dados entre tenants.
        """
        tenant_a = await TenantFactory.create(self.session)
        tenant_b = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        # Usuário só tem membership na tenant A
        await TenantFactory.create_member(
            self.session, tenant_id=tenant_a.id, user_id=user.id
        )

        # Busca na tenant B deve retornar None
        result = await self.repository.find_by_tenant_and_user(
            tenant_id=tenant_b.id, user_id=user.id
        )

        assert result is None

    # ─── find_by_user_id ─────────────────────────────────────────────────────

    async def test_find_by_user_id_returns_all_memberships(self) -> None:
        """Usuário membro de 2 tenants → find_by_user_id retorna lista com 2 elementos."""
        tenant_1 = await TenantFactory.create(self.session)
        tenant_2 = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        await TenantFactory.create_member(
            self.session, tenant_id=tenant_1.id, user_id=user.id
        )
        await TenantFactory.create_member(
            self.session, tenant_id=tenant_2.id, user_id=user.id
        )

        result = await self.repository.find_by_user_id(user.id)

        assert len(result) == 2
        tenant_ids = {m.tenant_id for m in result}
        assert tenant_1.id in tenant_ids
        assert tenant_2.id in tenant_ids

    async def test_find_by_user_id_returns_empty_when_no_memberships(self) -> None:
        """Usuário sem nenhuma membership → retorna lista vazia."""
        user = await UserFactory.create(self.session)

        result = await self.repository.find_by_user_id(user.id)

        assert result == []

    # ─── find_by_tenant_id_paginated ─────────────────────────────────────────

    async def test_find_by_tenant_id_paginated_returns_members(self) -> None:
        """Tenant com 2 membros → find_by_tenant_id_paginated retorna itens paginados."""
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(self.session)
        user_1 = await UserFactory.create(self.session)
        user_2 = await UserFactory.create(self.session)

        await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user_1.id
        )
        await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user_2.id
        )

        page = await self.repository.find_by_tenant_id_paginated(
            tenant.id, pagination=PaginationParams(page=1, page_size=10)
        )

        assert page.total == 2
        assert len(page.items) == 2
        user_ids = {m.user_id for m in page.items}
        assert user_1.id in user_ids
        assert user_2.id in user_ids

    async def test_find_by_tenant_id_paginated_does_not_return_members_of_other_tenants(
        self,
    ) -> None:
        """
        MULTI-TENANT: Busca por tenant_id não deve retornar membros de outras tenants.
        """
        from shared.pagination import PaginationParams

        tenant_a = await TenantFactory.create(self.session)
        tenant_b = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        # Usuário só é membro da tenant B
        await TenantFactory.create_member(
            self.session, tenant_id=tenant_b.id, user_id=user.id
        )

        # Busca na tenant A não deve retornar nada
        page = await self.repository.find_by_tenant_id_paginated(
            tenant_a.id, pagination=PaginationParams(page=1, page_size=10)
        )

        assert page.total == 0
        assert page.items == []

    async def test_find_by_tenant_id_paginated_filters_by_role(self) -> None:
        """find_by_tenant_id_paginated com parâmetro role deve filtrar apenas membros com o papel especificado."""
        from shared.enums.user_role import UserRole
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(self.session)
        user_1 = await UserFactory.create(self.session)
        user_2 = await UserFactory.create(self.session)

        await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user_1.id, role=UserRole.ADMIN
        )
        await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user_2.id, role=UserRole.ALUNO
        )

        page = await self.repository.find_by_tenant_id_paginated(
            tenant.id, pagination=PaginationParams(page=1, page_size=10), role=UserRole.ALUNO
        )

        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].user_id == user_2.id

    async def test_find_by_tenant_id_paginated_filters_by_search_and_subject_class(self) -> None:
        """find_by_tenant_id_paginated com search e subject_class_id deve filtrar os resultados corretamente."""
        from modules.enrollment.domain.entities.enrollment import Enrollment
        from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
            EnrollmentSQLAlchemyRepository,
        )
        from modules.subject_class.domain.entities.subject_class import SubjectClass
        from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
            SubjectClassSQLAlchemyRepository,
        )
        from shared.enums.user_role import UserRole
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(self.session)
        user_carlos = await UserFactory.create(self.session, name="Carlos Eduardo", email="carlos@gmail.com")
        user_ana = await UserFactory.create(self.session, name="Ana Paula", email="ana@gmail.com")

        m_carlos = await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user_carlos.id, role=UserRole.ALUNO
        )
        await TenantFactory.create_member(
            self.session, tenant_id=tenant.id, user_id=user_ana.id, role=UserRole.ALUNO
        )

        sc = await SubjectClassSQLAlchemyRepository(self.session).save(
            SubjectClass(tenant_id=tenant.id, name="Matemática", discipline_name="Matemática")
        )
        await EnrollmentSQLAlchemyRepository(self.session).save(
            Enrollment(subject_class_id=sc.id, tenant_member_id=m_carlos.id)
        )

        # 1. Filtro por search (nome/email)
        by_search = await self.repository.find_by_tenant_id_paginated(
            tenant.id, pagination=PaginationParams(page=1, page_size=10), search="carlos"
        )
        assert by_search.total == 1
        assert len(by_search.items) == 1
        assert by_search.items[0].user_id == user_carlos.id

        # 2. Filtro por turma (subject_class_id)
        by_class = await self.repository.find_by_tenant_id_paginated(
            tenant.id, pagination=PaginationParams(page=1, page_size=10), subject_class_id=sc.id
        )
        assert by_class.total == 1
        assert len(by_class.items) == 1
        assert by_class.items[0].user_id == user_carlos.id

    async def test_find_by_tenant_id_paginated(self) -> None:
        """find_by_tenant_id_paginated deve aplicar offset, limit e calcular o total corretamente."""
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(self.session)
        user_1 = await UserFactory.create(self.session)
        user_2 = await UserFactory.create(self.session)
        user_3 = await UserFactory.create(self.session)

        await TenantFactory.create_member(self.session, tenant_id=tenant.id, user_id=user_1.id)
        await TenantFactory.create_member(self.session, tenant_id=tenant.id, user_id=user_2.id)
        await TenantFactory.create_member(self.session, tenant_id=tenant.id, user_id=user_3.id)

        # Página 1 com page_size=2
        page1 = await self.repository.find_by_tenant_id_paginated(
            tenant.id, pagination=PaginationParams(page=1, page_size=2)
        )
        assert page1.total == 3
        assert len(page1.items) == 2
        assert page1.pages == 2

        # Página 2 com page_size=2
        page2 = await self.repository.find_by_tenant_id_paginated(
            tenant.id, pagination=PaginationParams(page=2, page_size=2)
        )
        assert page2.total == 3
        assert len(page2.items) == 1

    # ─── save ────────────────────────────────────────────────────────────────

    async def test_save_persists_member_and_returns_entity(self) -> None:
        """save() persiste a membership e retorna a entidade com os dados corretos."""
        from modules.tenant.domain.entities.tenant_member import TenantMember

        tenant = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        member = TenantMember(
            tenant_id=tenant.id,
            user_id=user.id,
            role=UserRole.ADMIN,
        )

        saved = await self.repository.save(member)

        assert saved.id == member.id
        assert saved.tenant_id == tenant.id
        assert saved.user_id == user.id
        assert saved.role == UserRole.ADMIN

        # Confirma que está no banco
        found = await self.repository.find_by_tenant_and_user(
            tenant_id=tenant.id, user_id=user.id
        )
        assert found is not None
        assert found.role == UserRole.ADMIN
