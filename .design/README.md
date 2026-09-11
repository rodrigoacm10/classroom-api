# Design — Locus

Esta pasta é o **brief das telas**: o que existe, quem usa, o que a API devolve. O desenho vive no **Paper**. O contrato de dados continua em `src/`.

Não sabe o que é o Locus ou por quê? Comece por `.design/geral/produto.md`.

Não copie JSON de response para cá. Aponte a rota e os campos que a tela usa.

Visual (cores, tipo, componentes) fica de fora de propósito — decide-se depois, no Paper, sem estes arquivos mandando paleta.

## O que é um artboard?

Um **artboard** é um quadro no canvas do Paper — uma “folha” com tamanho fixo (ex.: 1440×900 desktop, 390×844 iPhone).

Pense no Paper como uma mesa, e em cada artboard como uma folha em cima dela:

```text
  Paper (arquivo .paper aberto no Desktop)
  ┌─────────────────────────────────────────────────────────┐
  │  [Web / Shell]   [Web / Chamada]   [Mobile / Home]      │
  │   1440 × 900      1440 × 900        390 × 844           │
  └─────────────────────────────────────────────────────────┘
         ↑ cada retângulo acima é UM artboard
```

- **1 artboard = 1 tela**, não o projeto inteiro.
- O projeto completo é o **arquivo Paper** com vários artboards lado a lado.
- “1 artboard por vez” no chat do Cursor: peça *Chamada ao vivo* **ou** *Login mobile*, não “desenhe o sistema todo”.

## Papel de cada coisa

| Onde | Função |
|---|---|
| `.design/geral/produto.md` | O que é o Locus, objetivos, glossário |
| `.design/geral/ia.md` | Papéis, fluxos, sitemap |
| `.design/web/` e `.design/mobile/` | Shell (estrutura) + cartões de tela |
| Paper | Desenho |
| `src/modules/*/interface/` | Rotas e schemas |

## Como usar com o Cursor + Paper

1. Instale o [Paper Desktop](https://paper.design) e **deixe um arquivo aberto** (isso sobe o MCP).
2. No Cursor: `/add-plugin paper-desktop` (ou Marketplace → Paper).
3. Confirme em **Settings → Tools & MCP**. Teste: *“crie um retângulo vermelho no Paper”*.
4. Abra o Agent mode. Anexe **só** o necessário:

```text
@.design/web/shell.md
@.design/web/screens/attendance-live.md
```

5. Peça **um** artboard. Exemplo:

```text
No Paper, crie o artboard "Web / Chamada ao vivo" (1440×900)
seguindo o shell web e este cartão de tela.
Não escreva código neste repo.
```

## Ordem (depois que o Paper estiver ligado)

1. **Web / Shell** e **Mobile / Shell**
2. Telas, uma a uma, começando pelo núcleo: chamada ao vivo (web) e confirmar presença (mobile)

## Regra de ouro dos cartões

Cada arquivo em `screens/` é um cartão curto: quem usa, regiões, binding de rota, estados.  
Campo da API que não entra na UI fica em **Não mostrar**.
