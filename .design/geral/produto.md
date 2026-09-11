# Locus

Sistema de chamada acadêmica com validação por geolocalização. O aluno confirma presença com um código do dia + a posição do GPS; o professor abre a chamada e vê quem está de fato na sala.

Sem tokens, cor ou tipografia aqui — isso é decidido depois, no Paper. Este arquivo é o "porquê" por trás das telas.

## Problema

Chamada tradicional (papel, ou app sem validação) permite um aluno confirmar presença por outro. Locus resolve isso com dupla validação: **código do dia** (expira, evita reuso) + **geolocalização** (o aluno precisa estar dentro do raio da sala).

## Quem usa

- **Professor** — abre a chamada, acompanha em tempo real, revisa casos irregulares, gera relatório.
- **Admin** — tudo do professor + gestão de instituição, membros e convites.
- **Coordenador** — relatórios agregados; sem ação operacional de chamada.
- **Aluno** — confirma presença (código + GPS), acompanha seu próprio histórico.

## Objetivos de design (o que a UI precisa garantir)

1. **Confiança no momento da chamada.** Professor precisa ver, sem ambiguidade, quem confirmou, se está dentro do raio, e o que exige revisão. Isso é o núcleo — as outras telas são suporte.
2. **Confirmar presença é rápido.** O aluno está em sala, com poucos segundos de janela mental. Código + GPS + um toque; sem fricção extra (login não conta, isso já aconteceu antes).
3. **Irregularidade é visível, não escondida.** `irregular`, fora do raio, revisão pendente — isso precisa se destacar da lista, não se misturar ao resto.
4. **Cadastro (turmas, salas, matrículas) é ferramenta, não vitrine.** Tabelas densas, sem hero, sem card bonito para dado operacional.
5. **O aluno nunca vê o que não é dele.** Sem lista de colegas, sem código do dia (esse é do professor), sem dado de auditoria (IP, device).

## Não-objetivos (por enquanto)

- Sem tempo real via socket — poll simples resolve para o escopo do TCC.
- Sem tela de configuração institucional avançada (% de falta, raio padrão) — mencionado no TCC, ainda não tem rota.
- Sem edição de perfil do usuário — não existe `PATCH /users` na API.

## Glossário (API → termo de UI)

| Termo da API | Como aparece na tela |
|---|---|
| `tenant` | Instituição |
| `subject_class` | Turma |
| `attendance_session` | Chamada / sessão de chamada |
| `day_code` | Código do dia |
| `attendance_record` | Confirmação de presença |
| `within_radius` | Dentro do raio |
| `record_status = irregular` | Pendente de revisão |
| `enrollment` | Matrícula |
| `tenant_member` | Membro da instituição (papel dentro dela) |

## Tom verbal

Português direto, verbo de ação nos botões ("Abrir chamada", "Confirmar presença"). Sem jargão de SaaS ("dashboard", "insights"). Vazio e erro em frase curta + próximo passo.
