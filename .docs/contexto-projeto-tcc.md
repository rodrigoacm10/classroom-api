# Sistema de Chamada Acadêmica com Validação por Geolocalização
## Documento de Contexto do Projeto (TCC — Fábrica de Software + Tópicos Avançados)

---

## 1. Sobre a disciplina e o trabalho

- **Disciplina**: Fábrica de Software (Profª Pryscilla Gonçalves) — UNINASSAU
- **Projeto integrado com**: Tópicos Avançados (Prof. Antenor Parnaíba)
- **Formato**: um único sistema desenvolvido ao longo do semestre, atendendo aos requisitos das duas disciplinas simultaneamente — não são dois projetos separados.
- **Entrega final**: 05/12
- **Equipe**: 3 a 5 integrantes, sem trocas após o prazo estabelecido (salvo exceção autorizada), participação individual avaliada.

---

## 2. Requisitos obrigatórios do projeto

### 2.1 O sistema precisa possuir
- [ ] Interface (frontend)
- [ ] Backend
- [ ] Banco de dados
- [ ] Regras de negócio reais (não apenas salvar/ler dados)
- [ ] Controle/autenticação de usuários
- [ ] Diferentes perfis de usuários (pelo menos 2)
- [ ] Integração entre módulos
- [ ] Persistência de dados
- [ ] Funcionalidades completas (não protótipo parcial)
- [ ] Documentação
- [ ] Testes

### 2.2 Componente computacional obrigatório (Tópicos Avançados)
O projeto deve conter, obrigatoriamente, pelo menos um dos itens abaixo:
- Inteligência Artificial, **e/ou**
- Otimização de processamento / processamento paralelo / computação de alto desempenho (HPC) / uso de GPU quando aplicável

**Importante**: o "e/ou" é literal — é válido optar apenas pela via de otimização/processamento paralelo, **sem IA**, desde que seja robusto, genuíno e não decorativo. Esse componente precisa ser:
- Relevante para o problema escolhido
- Desenvolvido pela própria equipe (não vale só consumir uma API externa pronta, ex: só chamar API do ChatGPT)
- Demonstrável tecnicamente (a equipe precisa saber explicar como funciona por dentro)
- Integrado ao sistema principal (não um módulo desconectado)

### 2.3 O que NÃO é aceito como projeto final
- Página institucional / landing page / site estático
- Portfólio pessoal
- Loja apenas em HTML
- Apenas frontend
- Apenas dashboard sem funcionalidades reais
- CRUD simples (sem regra de negócio por trás)
- Sistema copiado de tutorial
- Template comprado ou pronto

---

## 3. Ideia escolhida: Sistema de Chamada Acadêmica com Validação por Geolocalização

### 3.1 Problema
Controle de presença em sala de aula de forma confiável, evitando fraude (colega confirmando presença por outro), com validação dupla: código do dia + geolocalização (o aluno precisa estar fisicamente perto do local da aula no momento da chamada).

### 3.2 Por que não é um "CRUD disfarçado"
O núcleo técnico do projeto **não é** salvar presença no banco — é resolver três desafios reais:
1. **Concorrência real**: quando o professor abre a chamada, dezenas de alunos confirmam presença quase simultaneamente, numa janela curta de tempo. Isso exige controle de concorrência no banco (evitar duplicidade, race conditions), testável e mensurável (teste de carga: X requisições simultâneas, comparação com/sem otimização).
2. **Validação geoespacial**: cálculo de distância entre a localização do aluno e a localização cadastrada da sala, com raio de tolerância configurável (via PostGIS).
3. **Camadas de segurança/anti-fraude**: código do dia com expiração curta, geolocalização, evidência fotográfica opcional para auditoria manual.

Esse é o "gancho" técnico para Tópicos Avançados **sem depender de IA**.

### 3.3 Perfis de usuário
- **Admin**: gerencia usuários e perfis, configura regras institucionais (% máximo de faltas, raio padrão de tolerância)
- **Professor**: cria/gerencia turmas e disciplinas, cadastra local da sala (coordenadas + raio), abre janela de chamada, gera código do dia, acompanha presença em tempo real, audita evidências, gera relatórios
- **Aluno**: recebe notificação quando a chamada abre, insere/escaneia código do dia, tem localização capturada no momento da confirmação, visualiza histórico pessoal de presença/faltas e alertas de risco
- **(Opcional) Coordenador**: relatórios agregados entre turmas/disciplinas

### 3.4 Funcionalidades principais

**Professor**
- Criar/gerenciar turmas e disciplinas
- Cadastrar local da sala (coordenadas de referência + raio de tolerância)
- Abrir janela de chamada (tempo de expiração configurável)
- Gerar código do dia (numérico ou QR code)
- Visualizar presença em tempo real durante a chamada
- Auditar evidências (fotos) em caso de suspeita de fraude
- Gerar relatórios de frequência por aluno/turma/período

**Aluno**
- Receber notificação push quando a chamada abre
- Inserir/escanear código do dia
- Capturar localização (GPS) no momento da confirmação
- Capturar foto de evidência (funcionalidade opcional)
- Ver histórico pessoal de presença/faltas
- Alertas de risco (ex: aproximando do limite de faltas permitido)

**Admin**
- Gerenciar usuários e perfis
- Configurar regras institucionais
- Relatórios gerenciais (frequência geral, turmas com mais faltas)

**Transversais (sistema)**
- Validação dupla: código do dia + geolocalização
- Controle de concorrência na confirmação de presença (ponto técnico central)
- Notificações push em lote
- Armazenamento seguro de evidências (imagens)
- Geração de relatórios em lote (processamento paralelo)
- Envio de e-mails (confirmação de cadastro, relatórios periódicos, alertas formais)

### 3.5 Onde está o "gancho" técnico para Tópicos Avançados
1. Concorrência controlada na confirmação de presença — com teste de carga demonstrando o ganho (métricas antes/depois)
2. Processamento geoespacial em escala com PostGIS (índice espacial GiST)
3. Broadcast paralelo/assíncrono de notificações (fila de tarefas)
4. Geração de relatórios em lote com processamento paralelo (multiprocessing)

Esses 4 pontos dão material concreto e mensurável para o vídeo horizontal (item "otimizações realizadas").

### 3.6 Ponto de atenção
Validar com o professor de Tópicos Avançados se "otimização de processamento + concorrência", **sem nenhum componente de IA**, é aceito na prática dele — o slide diz "e/ou", mas vale confirmar antes de fechar o escopo definitivamente.

---

## 4. Stack técnica definida

| Camada | Tecnologia | Observações |
|---|---|---|
| App mobile (aluno) | **React Native** | Equipe já tem experiência — produtividade > escolha "ideal". Suporta Android/iOS oficialmente; Web via `react-native-web`; Desktop via projetos da comunidade (`react-native-windows`/`macos`) |
| Painel web (professor/admin) | React (web) | Uso complementar de JS é aceito pelos slides para interface |
| Backend / API REST | **Python + FastAPI** | Linguagem prioritária nos slides; suporte nativo a `async`, facilita processamento paralelo e futura integração com IA se necessário |
| Banco de dados | **PostgreSQL + PostGIS** (hospedado no **Neon**) | PostGIS confirmado como suportado nativamente no Neon (inclusive free tier). Ativar com `CREATE EXTENSION postgis;` no SQL Editor do Neon |
| ORM / mapeamento geoespacial | GeoAlchemy2 (extensão do SQLAlchemy) | Para mapear tipos `GEOGRAPHY`/`GEOMETRY` nos models Python |
| Armazenamento de imagens | MinIO (self-hosted, compatível S3) ou AWS S3 | Separar arquivos binários do banco relacional |
| Fila / processamento assíncrono | Começar com `BackgroundTasks` do FastAPI (mais simples) → evoluir para **Celery + Redis** se sobrar tempo no cronograma | Celery processa tarefas em background; Redis é o broker (fila) que armazena as tarefas pendentes. Migrar de síncrono para fila assíncrona é, em si, uma "otimização" citável no vídeo |
| Notificações push | **Firebase Cloud Messaging (FCM)** via `@react-native-firebase/messaging` | Gratuito, ativo, bem documentado. iOS exige conta Apple Developer (paga) para configurar APNs — Android funciona sem essa barreira |
| E-mail | Resend, SendGrid ou Amazon SES | Confirmação de cadastro, relatórios periódicos, alertas formais |
| Versionamento | Git + GitHub | Obrigatório — repositório deve estar sempre atualizado, é avaliado no processo |

### 4.1 Notas técnicas importantes
- **PostGIS**: usado para cálculo de distância geodésica com precisão (`ST_DWithin`, `ST_Distance`) e índice espacial (GiST), permitindo consultas em lote otimizadas (ex: "quais alunos confirmaram dentro do raio" para uma turma inteira). Não é estritamente obrigatório para o caso de uso simples (1 aluno x 1 sala — daria para fazer com Haversine em Python puro), mas é um diferencial técnico defensável para a parte de otimização.
- **Neon**: scale-to-zero no free tier pode gerar pequena latência na primeira consulta após período de inatividade (compute "acorda") — não é um problema para o TCC, mas vale saber explicar se perguntado.
- **Celery vs Redis**: não são a mesma coisa. Celery é a biblioteca que processa tarefas em paralelo/background; Redis é o banco em memória usado como broker (fila) que armazena as tarefas pendentes até serem processadas pelos workers.
- **FCM**: API antiga ("legacy") foi descontinuada, hoje se usa a API HTTP V1 (OAuth 2.0) — mas isso é tratado automaticamente pelo Firebase Admin SDK no backend, não exige atenção manual da equipe.

---

## 5. Cronograma de Sprints (definido pela disciplina)

| Sprint | Entregas |
|---|---|
| Sprint 1 | Formação das equipes, escolha do tema, levantamento de requisitos |
| Sprint 2 | Casos de uso, banco de dados, protótipo |
| Sprint 3 | Arquitetura, GitHub, ambiente configurado |
| Sprint 4 | Login funcionando, banco funcionando |
| Sprint Final | Preparação para banca final |

Em cada orientação semanal, apresentar: repositório GitHub atualizado, funcionalidades desenvolvidas, dificuldades encontradas, planejamento da próxima Sprint. **Não são aceitas orientações baseadas apenas em slides ou ideias sem implementação prática.**

---

## 6. Entrega final (05/12)

- [ ] Sistema totalmente funcional
- [ ] Componente de IA/otimização integrado (não separado)
- [ ] Código-fonte no GitHub
- [ ] Documentação técnica
- [ ] Banco de dados + instruções de execução
- [ ] Vídeo horizontal (16:9, máx. 10 min, YouTube)
- [ ] Vídeo vertical (9:16, Instagram, marcando @pryscillabgoncalves e @antenorparnaiba)

### 6.1 Roteiro sugerido — Vídeo horizontal
1. O problema
2. A solução desenvolvida
3. Arquitetura
4. Tecnologias utilizadas
5. Demonstração do software funcionando (obrigatório mostrar funcionando, não só slides)
6. IA/processamento
7. CUDA/OpenCL, se usado (não se aplica a este projeto, salvo mudança de escopo)
8. Otimizações realizadas
9. Resultados alcançados
10. Considerações finais

### 6.2 Roteiro sugerido — Vídeo vertical
Estrutura tipo pitch de startup: Problema → "criamos uma solução para isso" → produto funcionando → IA/processamento → resultado → identidade do projeto.

---

## 7. Critérios de avaliação

| Categoria | Peso | O que avalia |
|---|---|---|
| Desenvolvimento do projeto | 60% | Funcionamento, regras de negócio, qualidade técnica, IA/processamento, integração, otimização, código, banco, documentação |
| Processo | 20% | Sprints, GitHub, evolução, participação, orientações |
| Apresentação final | 20% | Os 2 vídeos — clareza, criatividade, qualidade, demonstração técnica, comunicação, edição, síntese |

---

## 8. Pendências / decisões em aberto

- [ ] Confirmar com o Prof. Antenor Parnaíba se o componente "concorrência + geoprocessamento", sem IA, é aceito como componente de Tópicos Avançados
- [ ] Decidir se a funcionalidade de foto-evidência entra no escopo inicial ou fica como extensão futura
- [ ] Decidir se a migração para Celery + Redis entra no escopo ou fica como "otimização" de uma versão mais simples com `BackgroundTasks`
- [ ] Confirmar se haverá suporte a iOS (implica custo de conta Apple Developer) ou se o MVP focará em Android
- [ ] Definir papéis da equipe (Scrum Master, Product Owner, Dev Backend, Dev Frontend, Responsável por BD/Documentação)
