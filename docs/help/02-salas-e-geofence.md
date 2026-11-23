---
topic: "Salas físicas e configuração de geofence"
routes:
  - "/dashboard/salas"
  - "/dashboard/salas/nova"
allowed_roles:
  - "admin"
  - "coordenador"
  - "professor"
---

# Salas Físicas e Geofence

## O que é uma sala no Locus

No Locus, cada **sala** representa um espaço físico real definido por um ponto geográfico no mapa (coordenadas WGS84 de **latitude** e **longitude**) e um **raio de tolerância** em metros (geofence). Esse perímetro é usado para validar automaticamente se o aluno estava fisicamente próximo à sala ao confirmar a chamada.

## Como cadastrar uma nova sala

A criação de salas é permitida para os papéis **Administrador (`admin`)** e **Professor (`professor`)**.

1. No menu lateral, clique em **Salas** (`/dashboard/salas`).
2. Clique no botão **Nova sala** para abrir `/dashboard/salas/nova`.
3. Informe o **nome da sala** (entre 1 e 255 caracteres, por exemplo: *"Laboratório de Informática 03"* ou *"Bloco B - Sala 204"*).
4. Defina a localização geográfica no mapa interativo:
   - Clique diretamente no mapa para posicionar o marcador; ou
   - Use o botão de **GPS do navegador** para capturar sua localização atual (útil se você estiver dentro da própria sala); ou
   - Digite manualmente a **latitude** (-90 a 90) e **longitude** (-180 a 180).
5. Ajuste o **raio de tolerância** entre **5 e 500 metros** (o valor padrão recomendado é **50 metros**). O círculo azul no mapa mostra em tempo real a área exata de cobertura.
6. Salve o cadastro. A sala ficará imediatamente disponível para ser vinculada a turmas ou selecionada em chamadas avulsas.

## Como escolher o raio de tolerância ideal

- **15 a 30 metros**: salas pequenas ou laboratórios em prédios com bom sinal de GPS (janelas amplas ou térreo).
- **50 metros (padrão)**: equilíbrio ideal para a maioria das salas de aula universitárias, compensando variações normais do GPS interno de celulares.
- **80 a 150 metros**: auditórios grandes, prédios com paredes espessas ou áreas cobertas onde o GPS sofre atenuação.

Raio muito pequeno pode gerar falsos alertas de presença irregular; raio muito grande reduz a precisão contra fraudes à distância.

## Como visualizar ou editar uma sala existente

1. Acesse **Salas** (`/dashboard/salas`) para ver os cards de todas as salas cadastradas, com badges de precisão e cálculo do raio médio.
2. Clique em uma sala para abrir os detalhes (`/dashboard/salas/[id]`).
3. Para ajustar nome, coordenadas ou raio de geofence, clique em **Editar** (`/dashboard/salas/[id]/editar`) e salve as alterações.
