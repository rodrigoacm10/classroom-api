---
topic: "Auditoria de presença: registros irregulares, validação e rejeição"
routes:
  - "/dashboard/chamadas"
allowed_roles:
  - "admin"
  - "coordenador"
  - "professor"
---

# Auditoria de Presença e Registros Irregulares

## Por que o Locus não bloqueia o aluno na hora

Sinal de GPS fraco em salas fechadas ou imprecisão do aparelho podem acontecer com alunos que realmente estão na sala. Por isso, o Locus **não bloqueia** o registro quando a localização está fora do raio da sala ou apresenta algum indício suspeito: em vez disso, a confirmação é registrada com status **Irregular** para revisão do professor.

## Estados de um registro de presença

Cada confirmação em uma chamada possui um status claro:

- **Confirmada / Validada**: o aluno confirmou dentro do perímetro da sala (ou o professor validou manualmente um registro irregular). Conta como **presença**.
- **Irregular**: a confirmação foi recebida, mas houve alerta de geolocalização (por exemplo, distância acima do raio de tolerância da sala ou sinal suspeito). Aguarda revisão do professor.
- **Rejeitada**: o professor revisou um registro irregular e decidiu rejeitá-lo. **Presença rejeitada conta como falta** no cálculo de frequência.
- **Ausente / Falta**: o aluno não enviou confirmação durante a janela da chamada.

## Como auditar e revisar presenças irregulares

1. Acesse **Chamadas** (`/dashboard/chamadas`) e abra a sessão desejada (`/dashboard/chamadas/[subjectClassId]/[sessionId]`).
2. Na lista de presença (roster) e no **mapa de auditoria**, visualize os registros marcados como **Irregulares**, a distância calculada até a sala (fórmula de Haversine) e, quando disponível, a foto de evidência enviada pelo aluno.
3. Para cada registro irregular, o professor (ou administrador) pode escolher:
   - **Validar presença**: confirma que o aluno estava presente (ex.: falha temporária de GPS); o registro passa a contar como presença válida.
   - **Rejeitar presença**: invalida o registro suspeito; ele passa a contar como **falta** nos relatórios de frequência.
