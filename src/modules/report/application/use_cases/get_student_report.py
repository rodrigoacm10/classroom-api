from dataclasses import dataclass
from uuid import UUID

from modules.report.domain.entities.student_report import StudentReport
from modules.report.domain.services.student_calculator import calculate_student_report
from modules.report.infra.repositories.report_data_repository import ReportDataRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetStudentReportInput:
    tenant_id: UUID
    subject_class_id: UUID
    tenant_member_id: UUID


class GetStudentReportUseCase:
    def __init__(
        self,
        report_data_repo: ReportDataRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.report_data_repo = report_data_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: GetStudentReportInput) -> StudentReport:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        students_data = await self.report_data_repo.load_class_data(
            data.tenant_id, data.subject_class_id
        )
        student_data = next(
            (s for s in students_data if s.tenant_member_id == data.tenant_member_id),
            None,
        )
        if student_data is None:
            raise ResourceNotFoundException("Aluno não encontrado nesta turma.")

        return calculate_student_report(student_data)
