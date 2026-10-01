from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DayAttendanceMetricResponse(BaseModel):
    date: str = Field(..., description="Data no formato AAAA-MM-DD")
    day_of_week: int = Field(..., description="Índice do dia da semana: 0 (DOM) a 6 (SAB)")
    day_label: str = Field(..., description="Rótulo do dia: DOM, SEG, TER, QUA, QUI, SEX, SAB")
    attendance_rate: float = Field(
        ..., description="Taxa de frequência agregada do dia (0.0 a 1.0)"
    )
    total_sessions: int = Field(..., description="Quantidade de chamadas realizadas no dia")
    total_expected: int = Field(
        ..., description="Total de presenças esperadas de alunos matriculados"
    )
    total_presents: int = Field(..., description="Total de presenças confirmadas")

    model_config = ConfigDict(from_attributes=True)


class AtRiskStudentResponse(BaseModel):
    enrollment_id: UUID = Field(..., description="ID da matrícula do aluno na turma")
    student_name: str = Field(..., description="Nome do aluno")
    class_name: str = Field(..., description="Nome da turma")
    total_sessions: int = Field(..., description="Total de aulas realizadas na turma")
    absences: int = Field(..., description="Total de faltas acumuladas na turma")
    attendance_rate: float = Field(
        ..., description="Taxa de presença acumulada na turma (0.0 a 1.0)"
    )
    critical: bool = Field(
        ...,
        description="Indica se está na faixa crítica (<= 71%) vs zona de aviso (72-74%)",
    )

    model_config = ConfigDict(from_attributes=True)


class DashboardMetricsResponse(BaseModel):
    total_classes: int = Field(
        ..., description="Contagem total de turmas conforme o filtro aplicado"
    )
    total_unique_students: int = Field(
        ..., description="Contagem de alunos únicos com matrícula ativa"
    )
    average_attendance_rate: float = Field(
        ..., description="Frequência média geral dos últimos 30 dias (0.0 a 1.0)"
    )
    total_students_at_risk: int = Field(
        ..., description="Total de matrículas em risco de reprovação por falta (< 75% de presença)"
    )
    week_frequency: list[DayAttendanceMetricResponse] = Field(
        default_factory=list,
        description="Frequência diária agregada de Domingo a Sábado da semana atual",
    )
    at_risk_students: list[AtRiskStudentResponse] = Field(
        default_factory=list,
        description="Top 10 matrículas em situação mais crítica de falta (< 75% de frequência)",
    )

    model_config = ConfigDict(from_attributes=True)
