# App mobile do aluno

Documento do aplicativo que o aluno usa para confirmar presença. Professor e administrador ficam no painel web. A API é o único ponto de entrada: o app não acessa banco, storage nem fila.

As regras de negócio (código do dia, GPS, flags, push) já existiam em outros documentos. Este arquivo junta o que é responsabilidade do app e a stack com a qual isso será feito.

---

## 1. Stack

Um único código gera o app de iOS e o de Android.

| Peça | Papel |
|---|---|
| **React Native** | Interface nativa. Já era a escolha do projeto. |
| **TypeScript** | Mesma linguagem do painel web. |
| **Expo** | Gera os binários e entrega GPS, câmera e armazenamento seguro. |
| **NativeWind** | Classes no estilo Tailwind em `View` e `Text`. O pacote `tailwindcss` do web não estiliza componente nativo. |
| **Expo development build** (`expo-dev-client`) | Build de desenvolvimento em que o Firebase Messaging roda. O Expo Go não carrega esse SDK. |

Bibliotecas que cobrem o que a API espera do aparelho:

| Necessidade | Biblioteca |
|---|---|
| UUID do aparelho no Keychain (iOS) e no Keystore (Android) | `expo-secure-store` |
| Latitude, longitude e precisão do GPS | `expo-location` |
| Leitura do QR do código do dia e foto de evidência | `expo-camera` (foto também pode ir por `expo-image-picker`) |
| Token de push e recebimento da notificação | `@react-native-firebase/messaging` |

TypeScript e NativeWind não participam de autenticação, GPS nem push. São linguagem e visual.

Android recebe push com a conta gratuita do Firebase. iOS exige conta Apple Developer paga para o APNs. Sem essa conta, a demonstração de push fica no Android.

---

## 2. O que o app faz

### Entrar e sair

- Login com e-mail e senha (`POST /auth/login`). A API devolve um JWT.
- Se o aluno pertence a mais de uma instituição, escolhe em qual entrar (`POST /auth/switch-tenant`). As chamadas seguintes usam o JWT dessa instituição, com papel `aluno`.
- Recuperação de senha em três passos: pedir o código por e-mail, validar o código, definir a senha nova. O fluxo está em [password-reset-flow.md](../.flows/password-reset-flow.md).
- No logout, remove o token de push daquele aparelho (`DELETE /fcm-tokens/{device_id}`), para o celular não continuar recebendo chamada depois da saída.

### Receber a chamada

Quando o professor abre a chamada, a API responde na hora e um worker avisa os alunos matriculados pelo Firebase. O app:

1. Na primeira abertura, gera um `device_id` (UUID) e guarda no cofre do sistema.
2. Pede ao Firebase o token de push daquele aparelho.
3. Envia os dois para `POST /fcm-tokens`. Se o Firebase trocar o token depois, o `device_id` continua o mesmo e a API só atualiza o token.
4. Mostra a notificação de chamada aberta. O evento de chamada encerrada também está previsto para chegar por push.

### Confirmar presença

O aluno confirma uma sessão aberta da turma em que está matriculado. O app junta os dados e envia `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/confirm`.

| Dado | Quem produz | Para que serve |
|---|---|---|
| Código do dia | O aluno digita ou a câmera lê o QR. É o mesmo código para a turma inteira, 6 caracteres, sem `0`, `O`, `I` e `1`. | Provar que ele viu o código que o professor exibiu. |
| Latitude, longitude e precisão | GPS do aparelho, no momento do envio. | A API calcula a distância até a sala. |
| `device_id` | UUID criado na instalação e guardado no cofre. | Detectar o mesmo aparelho confirmando dois alunos. |
| `device_info` | Plataforma, versão do sistema, modelo, versão do app, fuso. | Auditoria. A API guarda e não gera flag a partir disso. |
| Foto | Câmera, opcional. | Evidência visual para o professor revisar um caso irregular. |

O app não envia IP nem User-Agent. A API lê os dois do request HTTP. O cliente do React Native já se identifica como app (`okhttp` no Android, `CFNetwork` no iOS), que a API trata como mobile legítimo.

Quem decide o resultado é a API. O app mostra a resposta:

- Presença registrada como `REGULAR` quando nenhuma flag dispara.
- Presença registrada como `IRREGULAR` quando alguma flag dispara. O aluno não é bloqueado na hora. O professor revisa depois.
- Erro quando a chamada expirou, foi encerrada ou cancelada, o código não confere, o aluno não está matriculado ou ele já confirmou aquela sessão.

Flags que a API pode marcar a partir do que o app enviou:

| Flag | Quando |
|---|---|
| `outside_radius` | O GPS está fora do raio da sala. |
| `low_gps_accuracy` | A precisão relatada é pior que o raio da sala. |
| `confirmed_near_expiry` | A confirmação caiu nos últimos 30 segundos da janela. |
| `shared_device` | O mesmo `device_id` já confirmou outro aluno nessa sessão. |
| `non_mobile_client` | O User-Agent não parece um app iOS/Android. |

### Ver a própria frequência

O contexto do produto prevê que o aluno consulte o histórico de presenças e faltas e veja alerta quando se aproxima do limite de faltas. Os números (`frequency_rate` e `at_risk`, abaixo de 75%) já nascem no módulo de relatório. Os endpoints atuais desse módulo são de professor e administrador. A tela do aluno lê só o próprio histórico, sem a listagem da turma.

---

## 3. Três identificadores, três papéis

| Nome | De quem é | Onde vive | Muda quando |
|---|---|---|---|
| Código do dia | Da sessão de chamada. Igual para todos os alunos daquela aula. | Gerado pela API quando o professor abre a chamada. | A cada nova chamada. |
| `device_id` | Da instalação do app naquele aparelho. | Keychain / Keystore, via `expo-secure-store`. | Reinstalar o app pode gerar outro. |
| Token FCM | Do Firebase, para entregar push naquele aparelho. | Tabela `user_fcm_tokens`, ligado ao `device_id`. | O Firebase rotaciona. O app reenvia no próximo login. |

O código do dia não identifica o celular. O `device_id` não é o token de notificação.

---

## 4. O que o app não faz

- Não abre chamada, não cadastra sala, não matrícula aluno e não revisa presença irregular. Isso é do painel web.
- Não calcula se o aluno está dentro do raio. Envia o GPS. O PostGIS calcula.
- Não decide `REGULAR` ou `IRREGULAR`.
- Não analisa o conteúdo da foto. Não há reconhecimento facial.
- Não bloqueia GPS falso nem mock location. A detecção de spoofing ficou para uma etapa futura de segurança. Hoje a precisão ruim vira a flag `low_gps_accuracy`.
- Não usa o IP para aceitar ou recusar presença. Na rede da instituição vários alunos saem pelo mesmo IP.

---

## 5. Limites já aceitos

- Reinstalar o app pode apagar o `device_id` e enfraquecer a flag `shared_device`. A documentação de validação estima que isso cobre a fraude amadora, não um ataque dedicado.
- User-Agent é uma pista, não uma trava. Um cliente que imite `okhttp` ou `CFNetwork` passa pela flag `non_mobile_client`. A presença irregular ainda depende do código do dia e do GPS.
- A foto é opcional. Sem câmera ou com rede lenta, a confirmação segue só com código e GPS.
- Push no iOS depende da conta Apple Developer.

---

## 6. Onde cada parte já estava descrita

| Assunto | Documento |
|---|---|
| Papel do aluno e stack original (React Native + FCM) | [contexto-projeto-tcc.md](./contexto-projeto-tcc.md) |
| Arquitetura e fluxo de confirmação | [documentacao-tecnica-tcc.md](./documentacao-tecnica-tcc.md) |
| Código do dia, GPS, `device_id`, flags | [.tasks/6-attendance.md](../.tasks/6-attendance.md) e [.tasks/7-attendance-confirm-validations.md](../.tasks/7-attendance-confirm-validations.md) |
| Registro do token e envio do push | [.tasks/8-fcm-push-notifications.md](../.tasks/8-fcm-push-notifications.md) |
| Push de chamada encerrada | [.tasks/9-application-event-bus.md](../.tasks/9-application-event-bus.md) |
| Foto de evidência | [.tasks/10-evidence-photo-upload.md](../.tasks/10-evidence-photo-upload.md) |
| Frequência e alerta de risco | [.tasks/11-frequency-report-parallelism.md](../.tasks/11-frequency-report-parallelism.md) |
| Login e instituição | [.tasks/1-auth-system.md](../.tasks/1-auth-system.md) |
| Recuperação de senha | [.flows/password-reset-flow.md](../.flows/password-reset-flow.md) |
