Status: aprovado

> Aprovação: pedido do usuário em 2026-11-17 ("Resolva isso do giro"), depois do relatório do lab que mostrou o Hydrone sem
> guinada. Ver `log.md`.

# rotacao-hydrone — Requisitos

## Contexto
No PC do lab (BiguaSim 1.1.0), o Hydrone dos `HydroneGoto*` não gira: a dinâmica (`dynamics/hauv.py`) devolve a aceleração
angular certa (3,14 rad/s² com `cmd_vel_yaw` de 20°, 14 rad/s² com `cmd_pos_yaw` de 90°), mas o `DynamicsSensor` mede
ω = 0 e o yaw anda 0,17° em 60 ticks. `tools/diag_rotacao_hydrone.py` (2026-11-17, `~/diag_rotacao2.log` no lab) isolou a
causa no motor (Unreal):

| Teste (20–30 ticks, a 2 m do chão, parado) | Hydrone | DjiMatrice |
|---|---|---|
| `accel`: ω̇ de 1 rad/s² em x, y ou z | 0,05–0,06° | 0,11° |
| `accel`: ω̇z de 3,35 / 10 rad/s² | 0,06° / 0,06° | 64,7° / gira a 6,2 rad/s |
| `cmd_vel_yaw` 20° (o que a dinâmica manda) | 0,08° (manda 3,14 rad/s²) | 46° (manda 1,01 → 0,51) |
| as mesmas acelerações do `cmd_vel_yaw` reenviadas em `accel` | 0,08° | 0,11° |
| `accel`: aceleração linear de 1 m/s² em x | 0,34 m | 0,34 m |
| `set_physics_state` com ωz = 30°/s uma vez | 18,9° (ω cai a 0,19 rad/s: amortecimento ≈ 1 s⁻¹) | igual |
| `set_physics_state` com ωz = 30°/s a cada tick | 29,2° (ω = 0,498 rad/s) | igual |
| teleporte para yaw 45° | 45° | igual |

Ou seja: o motor aplica a aceleração linear, mas **não aplica a aceleração angular ao Hydrone** (em nenhum eixo, até
10 rad/s²) e só às vezes ao DJI (as mesmas acelerações giram ou não conforme o histórico, como um corpo "dormindo" na
física). Imposta por `set_physics_state`, a velocidade angular é respeitada sempre, com amortecimento de ≈ 1 s⁻¹ do motor.
Sem rotação, o Hydrone não aponta para o alvo nem inclina (então também não acelera na horizontal no ar).

O BiguaSim não pode ser alterado (`~/biguasim` do lab e `~/biguasim-treino` do notebook são os clones da 1.1.0 dos autores);
o problema também vai para os autores.

## Objetivo
Fazer o Hydrone dos `HydroneGoto*` girar como manda a dinâmica do BiguaSim, integrando no biguagym a aceleração angular que o
motor ignora.

## Fora de escopo
- Alterar o BiguaSim (cliente ou motor) ou os parâmetros da dinâmica do Hydrone.
- Os outros ambientes do biguagym (DjiMatrice, BlueBoat, BlueROV2, TorpedoAUV, Hydrone*Hover etc.).
- `batch_size` > 1 no Goto.

## Requisitos
- **R1** — QUANDO o `GotoEnv` (e `-v1`/`-v2`) avançar um tick do simulador, O SISTEMA DEVE pegar a aceleração angular ω̇ que a
  dinâmica do BiguaSim calculou nesse tick, enviar ao motor só a aceleração linear e impor ao agente, com
  `set_physics_state`, a velocidade angular ω + ω̇·dt (no referencial do mundo), compensada pelo amortecimento do motor,
  mantendo a posição, a atitude e a velocidade linear atuais.
- **R2** — QUANDO a integração estiver ligada, O SISTEMA DEVE fazer o `action_repeat` tick a tick (um `step` do BiguaSim por
  tick), para impor a velocidade angular em todos os ticks.
- **R3** — O SISTEMA DEVE permitir desligar a integração (`integrar_rotacao=False`), voltando ao comportamento anterior.
- **R4** — QUANDO o Hydrone receber guinada no Goto, O SISTEMA DEVE fazê-lo girar no simulador: com `cmd_vel_yaw` de 20° a
  partir do repouso, a guinada deve passar de 15° em 60 ticks (antes: 0,17°), e o yaw medido deve acompanhar a referência
  integrada pelo `GotoEnv` (ação de guinada constante → yaw crescendo).
- **R5** — QUANDO a integração estiver ligada, O SISTEMA NÃO DEVE piorar o resto: subida e avanço continuam funcionando,
  sem NaN, e os smokes `HydroneGotoPilares-v0/-v1/-v2` continuam ok.

- **R6** (extensão aprovada em 2026-11-17: "pode seguir sim") — QUANDO a integração estiver ligada, O SISTEMA DEVE integrar
  também a aceleração linear da dinâmica (impor v + v̇·dt, compensada pelo amortecimento linear do motor) e mandar
  aceleração zero ao motor, para que acelerações pequenas (que o motor descarta) não se percam. Com avanço máximo a partir
  do repouso no ar, o Hydrone deve andar o que a dinâmica dos autores dá sozinha (~0,4 m em 5 s, `tools/avanco_offline_hydrone.py`).

## Critérios de aceitação
- R1, R2, R3: `pytest tests/test_rotacao_hydrone.py` → passa (simulador falso: ω̇ capturado, parte angular zerada no
  motor, `set_physics_state` com ω certo, um `step` por tick, integração desligada não chama `set_physics_state`).
- R4: `python tools/diag_goto.py HydroneGotoPilares-v0 5` no lab → guinada + e − com |Δyaw| > 15° (antes ≈ 0) e o "direto"
  de 20° girando; `python tools/diag_rotacao_hydrone.py` com o modo Goto → idem.
- R6: `pytest tests/test_rotacao_hydrone.py` (motor recebe zeros; v imposta) e, no lab, `diag_rotacao_hydrone.py goto` com
  v_x medido/previsto ≈ 1 e `diag_goto.py ... avanco` andando ~0,4 m em 5 s a partir do repouso.
- R5: `bash tools/testar_goto_lab.sh` no lab → pytest ok, os 3 smokes ok, sem NaN, 0 processos órfãos; no `diag_goto`, a
  subida continua (> 0,5 m) e o avanço move o Hydrone na direção do nariz.

## Impacto nos experimentos
Muda o comportamento dos `HydroneGoto*` (ainda não treinados): o Hydrone passa a girar e inclinar. A rotação continua sendo a
da dinâmica dos autores; só a integração angular sai do motor e vem para o biguagym. Ambientes já treinados não mudam.

## Perguntas em aberto
- O amortecimento angular do motor (≈ 1 s⁻¹, medido no ar) é o mesmo debaixo d'água? Verificar no lab (ω medido × previsto).
