Status: aprovado

> Aprovação: pedido do usuário em 2026-11-17 ("pode fazer o desenvolvimento para o cmd_vel_yaw receber uma velocidade e
> não um ângulo (...) vamos usar a recompensa do dranaju mesmo (...) então aplique o pipeline-pixels, o hydrone-goto-dique
> e a configuração dos sensores"). Ver `log.md`.

# hydrone-goto-dique — Requisitos

## Contexto
O artigo do biguagym tem 8 ambientes treinados; faltam os 2 do Hydrone. O coorientador pediu (mensagens de 2026-11-16):
- tarefa **Goto** com velocidades lineares e angulares, igual nos dois trabalhos; muda só o sensor (Dranaju: RGB + Depth;
  Ricardo: LiDAR + sonar) — os sensores ficam na spec `sensores-goto`;
- cenário: a parte do Pier-Harbor com o **dique inundado**, com **4 pilares** onde dê para navegar no ar e na água sem colidir
  com o barco que está lá (como a Fig. 6a do Depth-CUPRL, arXiv 2206.15211); depois, o dique inteiro com alvos aleatórios
  que não colidam com nada;
- recompensa dos autores; o usuário decidiu usar a do **Dranaju** (`environment_hydrone_image_depth.py`) nos dois.

Hoje:
- os ambientes do Hydrone (`HydroneNav-v*` etc., `biguagym/register.py`) usam `cmd_motor_speeds`, nascem em (100, 100, z)
  e usam a recompensa exp(−2d) + estabilidade do `HoverEnv._reward` (`biguagym/core/environments.py`);
- no BiguaSim 1.1.0 o Hydrone tem `cmd_vel_yaw` = [vx, vy, vz, desvio de guinada em graus] (`dynamics/hauv.py:573`):
  a cada tick o alvo de guinada vira "guinada atual + desvio", então o 4º valor é um ângulo, não uma velocidade;
- o `spawn_prop` cria cilindros (1 m de diâmetro e altura em escala 1), mas os objetos somem a cada `reset`;
- as coordenadas do dique ainda não são conhecidas: o usuário está explorando o mapa.

## Objetivo
Criar o ambiente Goto do Hydrone no dique (com 4 pilares e, depois, o dique inteiro), comandado por velocidade linear,
velocidade de guinada e velocidade vertical, com a recompensa e o término do Dranaju, e com o cenário num arquivo de
configuração para receber as coordenadas reais.

## Fora de escopo
- Alterar o BiguaSim: a conversão de velocidade de guinada fica no biguagym.
- Sensores da observação de imagem e de alcance (spec `sensores-goto`); aqui só a observação de estado (`-v0`).
- Escolher as coordenadas do dique e dos pilares (o usuário traz; até lá o cenário é provisório).
- Treinos (> 5k passos) e ajustes de hiperparâmetros.

## Requisitos
- **R1** — QUANDO o agente mandar a ação a ∈ [−1, 1]³, O SISTEMA DEVE convertê-la como o Dranaju: v = (a₀+1)/2·0,3 + 0,01 m/s
  para a frente, ω = 0,3·a₁ rad/s de guinada e v_z = 0,3·a₂ m/s; e enviar ao `cmd_vel_yaw` [v·cos ψ, v·sin ψ, v_z, desvio],
  em que o desvio (graus) leva a guinada até uma referência integrada ψ_ref ← ψ_ref + ω·Δt (Δt = 1/20 s por tick).
- **R2** — QUANDO o desvio |ψ_ref − ψ| passar de 45°, O SISTEMA DEVE limitá-lo e trazer ψ_ref junto (sem acumular erro).
- **R3** — QUANDO o ambiente for criado, O SISTEMA DEVE ler o cenário (`pilares` ou `dique`) de `config/goto_dique.json`:
  nível da água, área (x, y), limites de z, spawn, pilares (posição, raio, base, altura), caixas de exclusão (barco),
  faixas de z dos alvos no ar e na água, folga e distância mínima dos alvos.
- **R4** — QUANDO o episódio começar, O SISTEMA DEVE recriar os pilares no simulador (eles somem no reset).
- **R5** — QUANDO sortear um alvo, O SISTEMA DEVE escolher x, y na área e z no ar ou na água, rejeitando alvos a menos da
  folga de pilares e caixas de exclusão, ou perto demais do veículo.
- **R6** — QUANDO houver um passo, O SISTEMA DEVE calcular a recompensa do Dranaju (z relativo ao nível da água, d = distância
  3D ao alvo): r = 0,1·(d_ant − d); na faixa −0,23 < z < −0,05, ±0,01 no sentido de r; abaixo de −0,75, r = −0,1;
  colisão → r = −1 e término; d < 0,4 m → r = +1 e um alvo novo, sem terminar o episódio.
- **R7** — QUANDO o veículo encostar em algo (`CollisionSensor`), chegar a menos de 0,625 m de um pilar, de uma caixa de
  exclusão ou da borda da área, ou sair dos limites de z (−1,1 a 4,8 m em relação à água), O SISTEMA DEVE tratar como colisão.
- **R8** — QUANDO o episódio chegar a 1000 passos, O SISTEMA DEVE truncá-lo (Depth-CUPRL).
- **R9** — QUANDO o ambiente `-v0` for usado, A observação DEVE ser [heading, heading_z, d, posição (3), alvo (3)] relativos
  à origem do cenário (a "pose" de 9 valores do Dranaju) + as 3 ações anteriores (12 valores).
- **R10** — O SISTEMA DEVE registrar `HydroneGotoPilares-v0` e `HydroneGotoDique-v0` e informar em `info` os alvos
  atingidos, o motivo do término e os termos da recompensa.

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1, R2 | `pytest tests/test_hydrone_goto.py -k comando` | conversões de ação, integração de ψ_ref, desvio limitado a 45° |
| R3, R5 | `pytest tests/test_hydrone_goto.py -k "cenario or alvo"` | 2 cenários lidos; 1000 alvos sorteados fora dos pilares/caixas, na área e nas faixas de z |
| R4 | `pytest tests/test_hydrone_goto.py -k pilares` (simulador falso) | 4 `spawn_prop('cylinder', …)` a cada reset |
| R6, R7, R8 | `pytest tests/test_hydrone_goto.py -k "recompensa or colisao or trunca"` | cada caso da tabela de recompensa e de colisão |
| R9, R10 | `pytest tests/test_hydrone_goto.py -k "obs or registro"` | observação de 12 valores; ids registrados; `info` com os campos |
| R1 | ⏱ no lab: ω = +0,3 rad/s por 5 s (`tools/diag_goto.py`) | guinada sobe ~1,5 rad (sinal e taxa) |
| R4, R7 | ⏱ no lab: smoke de 200 passos de `HydroneGotoPilares-v0` | pilares aparecem nos quadros; sem exceção; sem processo órfão |
| — | `pytest tests` | testes anteriores continuam passando |

## Impacto nos experimentos
Ambientes novos; os 8 ambientes já treinados não mudam. Os resultados do Hydrone ficam na física da 1.1.0.
Registrar no artigo: recompensa, ação e término do Dranaju; cenário com as coordenadas finais do dique.

## Decisões
- Ação, recompensa e término do Dranaju nos dois trabalhos (decisão do usuário). O Ricardo usa ±0,25 e recompensa
  +100/−10; ficam registrados só como referência.
- Cenário com coordenadas **provisórias** (tanque de 10 × 10 m em torno de (100, 100), como o do paper) até o usuário
  trazer as do dique; o arquivo marca `"provisorio": true`.
- Alvos na água entre −0,7 e −0,3 m, por causa da penalidade abaixo de −0,75 m da recompensa do Dranaju.
