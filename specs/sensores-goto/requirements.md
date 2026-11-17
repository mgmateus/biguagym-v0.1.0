Status: aprovado

> Aprovação: pedido do usuário em 2026-11-17 ("verifique nessas mensagens que te mandei se os sensores do v2 precisam ser
> iguais aos que o Ricardo utilizou. então aplique o pipeline-pixels, o hydrone-goto-dique e a configuração dos sensores").
> Ver `log.md`.

# sensores-goto — Requisitos

## Contexto
O Goto do Hydrone (`biguagym/core/goto.py`, spec `hydrone-goto-dique`) tem só a observação de estado (`-v0`). O coorientador
pediu (2026-11-16) dois treinos que "fazem exatamente a mesma coisa" com sensores diferentes:
- **Dranaju (Depth-CUPRL, arXiv 2206.15211):** "tem que usar RGB e Depth, dai tem que setar os parametros corretamente pra
  usar os dois da maneira correta". No código dele: câmera embarcada, RGB e profundidade 100×100, 3 quadros empilhados,
  profundidade normalizada por 5 m, pose de 9 valores; CUPRL com o RGB como âncora e a profundidade como positivo.
- **Ricardo (Grando et al., arXiv 2209.06332):** "tem que ser com lidar e sonar". No paper: LiDAR (UST-10LX) no ar com 20
  leituras a cada 13,5° num campo de 270° e alcance de 10 m; sonar frontal (FLS) debaixo d'água com 20 feixes em 90° × 15°
  e alcance de 20 m (o maior retorno de cada feixe); estado de 26 valores = 20 distâncias (LiDAR no ar, sonar na água)
  + 3 ações anteriores + distância e 2 ângulos até o alvo.

**As mensagens não exigem que os sensores do `-v2` sejam iguais aos do Ricardo:** pedem só "lidar e sonar" e que a tarefa seja
a mesma. A decisão aqui é reproduzir a configuração do paper do Ricardo (20 + 20 leituras), porque ela define o sensor de cada
meio e o tamanho do estado, e porque os dois trabalhos devem ser comparáveis entre si.

Hoje, no biguagym:
- `-v1` usa câmeras com socket `Viewport` (terceira pessoa, atrás e acima do veículo) em 1280×720 (`config/pixels.json`);
- `-v2` concatena um RangeFinder de 10 lasers e um ProfilingSonar 10×10 com multipath (`config/range.json`) — o sonar levou
  1,4–1,7 s por passo no BlueBoat/BlueROV2 (`TESTES.md`).

## Objetivo
Criar o `-v1` (RGB + profundidade, como o Dranaju) e o `-v2` (LiDAR no ar e sonar na água, como o Ricardo) do Goto do Hydrone,
com os parâmetros dos papers.

## Fora de escopo
- Mudar os `-v1`/`-v2` dos outros veículos (`pixels.json`/`range.json` ficam como estão).
- Estimar profundidade a partir do RGB (o Depth-CUPRL usa uma rede treinada no KITTI; aqui a profundidade vem do simulador).
- Redes recorrentes ou duplo crítico do Ricardo; hiperparâmetros de treino.

## Requisitos
- **R1** — QUANDO o `HydroneGoto*-v1` for criado, O SISTEMA DEVE usar uma câmera RGB e uma de profundidade **embarcadas**
  (presas ao corpo, apontando para a frente, quadradas), entregar `rgb` (9, 100, 100) uint8, `depth` (9, 100, 100) em [0, 255]
  (5 m) e `state` = a pose de 9 valores do Dranaju (sem ações anteriores, porque o CUPRL espera pose de 9).
- **R2** — QUANDO o `HydroneGoto*-v2` for criado, O SISTEMA DEVE usar um LiDAR horizontal (RangeFinder de 160 lasers, 10 m)
  do qual saem 20 leituras a cada 13,5° no setor frontal (±128,25°), e um sonar frontal (ProfilingSonar 90° × 15°, 0,5–20 m,
  20 feixes, sem multipath) do qual sai, por feixe, a distância do bin de maior intensidade (sem retorno → 20 m).
- **R3** — QUANDO o veículo estiver acima do nível da água, O SISTEMA DEVE usar as 20 leituras do LiDAR; abaixo, as 20 do sonar.
- **R4** — QUANDO o `-v2` for usado, A observação DEVE ter 26 valores: 20 distâncias + 3 ações anteriores + [distância,
  heading, heading_z].
- **R5** — QUANDO uma leitura vier inválida (NaN, inf, ≤ 0), O SISTEMA DEVE trocá-la pelo alcance máximo do sensor.
- **R6** — O SISTEMA DEVE registrar `HydroneGotoPilares-v1/-v2` e `HydroneGotoDique-v1/-v2` (mesmo `GotoEnv`, mesma recompensa).

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1 | `pytest tests/test_sensores_goto.py -k v1` | sensores embarcados; espaços `rgb`/`depth` (9,100,100), `state` (9,) |
| R2, R3, R5 | `pytest tests/test_sensores_goto.py -k "lidar or sonar or meio or invalida"` | índices dos 20 lasers; distância por feixe; troca de sensor no nível da água |
| R4, R6 | `pytest tests/test_sensores_goto.py -k "v2 or registro"` | observação (26,); 4 ids novos |
| R1 | ⏱ lab: `python smoke_test.py --env HydroneGotoPilares-v1 --steps 100 --frame-every 25` | `obs_rgb`/`obs_depth` mostram a vista da frente do veículo; ok; 0 órfãos |
| R2–R4 | ⏱ lab: `python smoke_test.py --env HydroneGotoPilares-v2 --steps 200` | ok; leituras < 10 m perto dos pilares; passos/s registrados (sonar) |
| — | `pytest tests` | testes anteriores continuam passando |

## Impacto nos experimentos
Ambientes novos (os 2 do Hydrone do artigo). Registrar no artigo a configuração de sensores de cada um e que a profundidade
vem do simulador (não de uma rede de estimação, como no Depth-CUPRL).

## Decisões
- Sensores do `-v2` como no paper do Ricardo (decisão minha, registrada; as mensagens só pedem "lidar e sonar").
- Distâncias em metros, sem normalizar (como nos dois trabalhos).
- Câmeras de 256×256 (padrão do BiguaSim), reduzidas para 100×100 pela `pipeline-pixels`.
