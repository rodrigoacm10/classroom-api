import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROFESSOR = "professor"
    ALUNO = "aluno"
    COORDENADOR = "coordenador"
