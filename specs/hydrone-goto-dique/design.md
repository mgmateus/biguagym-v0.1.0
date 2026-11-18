Status: aprovado

# hydrone-goto-dique — Design

## Arquivos afetados
| Arquivo | Mudança |
|---|---|
| `biguagym/core/goto.py` (novo) | `GotoEnv(HoverEnv)`: cenário, pilares, alvos, conversão da ação, colisão, recompensa, observação `-v0` |
| `biguagym/config/goto_dique.json` (novo) | cenários `pilares` e `dique` (provisórios) |
| `biguagym/register.py` | `HydroneGotoPilares-v0`, `HydroneGotoDique-v0` (`cmd_vel_yaw`) |
| `tests/test_hydrone_goto.py` (novo) | testes sem simulador (simulador falso) |
| `tools/diag_goto.py` (novo) | diagnóstico no lab: guinada com ω constante e um passeio pelos alvos |

## Solução proposta
`GotoEnv` herda o `HoverEnv` só pela infraestrutura (`_unwrap_state`, `_set_dynamics`, `rng`, `draw_point`) e substitui
`_build_params`, `_init_spaces`, `_reset`, `_step` e `_wrap_state`.

**Cenário** (`goto_dique.json`), coordenadas do mundo em metros; z dos limites, pilares e alvos relativos à água:
```json
"pilares": {"provisorio": true, "nivel_agua": 0.0, "origem": [100, 100],
            "area": [[95, 95], [105, 105]], "z_limites": [-1.1, 4.8],
            "spawn": [103.6, 97.4, 2.0], "spawn_yaw_deg": 0,
            "pilares": [{"xy": [97.5, 97.5], "raio": 0.5, "base_z": -3.0, "altura": 8.0}, ...],
            "exclusao": [], "alvo_z_ar": [0.5, 3.0], "alvo_z_agua": [-0.7, -0.3], "p_alvo_agua": 0.5,
            "folga_alvo": 1.0, "dist_min_alvo": 2.0}
```
O spawn vem do paper (3,6; −2,6; 2,0 em relação ao centro do tanque). O cenário `dique` começa como cópia sem pilares e
com área maior; os dois recebem as coordenadas reais quando o usuário as trouxer.

**Pilares:** a cada `_reset`, depois do `self._env.reset()`:
`spawn_prop('cylinder', [x, y, água + base + altura/2], [0, 0, 0], [2r, 2r, altura], material='steel', tag='Pilar', name=f'pilar{i}')`
(o cilindro básico do Unreal tem o pivô no centro; os nomes podem se repetir porque o reset limpa `_props`).

**Ação** (R1, R2):
```python
v  = (a[0] + 1) / 2 * V_MAX + V_OFFSET        # 0,01 … 0,31 m/s (Dranaju: action_unnormalized + 0,01)
w  = a[1] * W_MAX                              # ±0,3 rad/s
vz = a[2] * VZ_MAX                             # ±0,3 m/s
psi = dyn[17]
self._yaw_ref = wrap(self._yaw_ref + w * self._action_repeat / TICKS_POR_S)
desvio = wrap(self._yaw_ref - psi)
if abs(desvio) > YAW_DESVIO_MAX:               # 45°
    desvio = copysign(YAW_DESVIO_MAX, desvio); self._yaw_ref = wrap(psi + desvio)
cmd = [v * cos(psi), v * sin(psi), vz, degrees(desvio)]
```
O `cmd_vel_yaw` do `hauv` usa vx, vy no referencial do mundo (ar e água) e põe o alvo de guinada em ψ + desvio a cada tick;
com a referência integrada, o desvio fecha a malha e a guinada segue ω. ψ é a guinada do `RPYDynamicsSensor`
(anti-horária a partir de +x, a mesma do controlador de referência validado na `colapso-blueboat`).

**Colisão** (R7), na ordem: `CollisionSensor` (sensor adicionado ao agente) → "contato"; distância < 0,625 m da borda da
área → "parede"; z fora de `z_limites` → "altura"; distância horizontal à superfície de um pilar < 0,625 m (com z na altura
do pilar) → "pilar"; distância a uma caixa de exclusão < 0,625 m → "obstaculo". Geometria em vez de um laser escondido:
mesma regra do Dranaju (laser < 0,625 m) para os obstáculos conhecidos, igual nos `-v0/-v1/-v2`; o `CollisionSensor`
cobre o que não está modelado (chão, cais).

**Recompensa** (R6), função pura `recompensa_dranaju(d_ant, d, z_rel, colisao, chegou)`, na ordem do código do Dranaju
(colisão e depois chegada; se as duas acontecem, fica +1 e o episódio termina).

**Observação `-v0`** (R9): `pose9 = [heading, heading_z, d, x−ox, y−oy, z−água, gx−ox, gy−oy, gz−água]` + 3 ações
anteriores (em [−1, 1]). Posições relativas à origem do cenário (o Dranaju usava as do tanque, perto de 0).

**Passo:** desenha o alvo, converte a ação, `self._env.step(cmd, action_repeat)`, atualiza a dinâmica, testa colisão,
calcula a recompensa, sorteia o alvo novo se chegou, monta a observação; `truncated` em 1000 passos.
`info = {reached_goals, termination_reason ("contato"/"parede"/"altura"/"pilar"/"obstaculo"/"timeout"/None), reward_terms}`.

## Alternativas consideradas
- **Mudar o `cmd_vel_yaw` no BiguaSim para receber ω** — descartada: muda o simulador (regra de não alterar o BiguaSim
  do TCC; o clone de treino teria de divergir da 1.1.0) e afeta quem já usa o `cmd_vel_yaw`.
- **Usar `cmd_vel` e girar pelo vy** — descartado: o `cmd_vel` segura a guinada atual; não haveria como virar a câmera.
- **Colisão por um RangeFinder escondido (como o laser do Dranaju)** — descartada como regra principal: um anel de lasers
  só vê o plano horizontal e custa um sensor a mais; a geometria é exata para os pilares e o `CollisionSensor` cobre o resto.
- **Herdar `NavEnv`** — descartado: recompensa, término, limites e alvo são todos diferentes; só a infraestrutura é reaproveitada.

## Riscos
- Sinal ou escala da guinada do `hauv` diferente da do `RPYDynamicsSensor` → ⏱ teste com ω constante no lab antes de treinar.
- Pivô ou escala do cilindro diferente do esperado → conferir nos quadros do smoke; ajustar `base_z`/`altura` no JSON.
- O nível da água do dique pode não ser z = 0 (o mundo não tem o bloco de superfície; a dinâmica usa 0) → o usuário confere ao
  explorar; `nivel_agua` fica no JSON e é passado à física em `agents[robot].dynamics.water_level` (aceito pelo
  `biguasim.make` da 1.1.0; mudança de 2026-11-17 durante a execução, ver `log.md`).
- Coordenadas provisórias → o cenário marca `provisorio: true` e o ambiente avisa (`warnings.warn`) ao ser criado.
- Velocidade máxima de 0,31 m/s com 1000 passos (50 s) → ~15 m por episódio; suficiente para o tanque, talvez não para o dique
  inteiro → revisar no cenário `dique`.

## Plano de verificação
| Requisito | Como verificar |
|---|---|
| R1, R2 | testes da conversão (ψ = 0 e ψ = 90°, ω positivo e negativo, saturação de 45°) |
| R3, R5 | testes de leitura do JSON e de 1000 sorteios |
| R4 | simulador falso registrando `spawn_prop` a cada reset |
| R6–R8 | testes da função de recompensa e do `_step` com simulador falso (cada motivo de colisão, chegada, truncamento) |
| R9, R10 | forma e conteúdo da observação; `gym.spec` dos ids; campos do `info` |
| R1, R4, R7 | ⏱ lab: `tools/diag_goto.py` (ω constante) e smoke de 200 passos |

---

## Mudança aprovada — obstáculos feitos de agentes (pilares 2 × 2 e vigas)

> Aprovação: usuário em 2026-11-18 ("Prefiro pilares mais grossos, pode colocar, e também, adicione mais obstácuos").
> Substitui os pilares por `spawn_prop` (o mundo SkyDive recusa `SpawnProp`; ver log.md).

**Por quê** (detalhes no log.md, 2026-11-18): o mundo SkyDive recusa `SpawnProp`, então os pilares do `_spawn_pilares` nunca
apareceram. O `DebugDraw` aparece só na câmera RGB e o Pier-Harbor não tem pilares em água aberta. No lab
(`tools/pilares_agentes.py`), colunas de TorpedoAUV em pé, em `accel` e com a posição reimposta a cada tick, ficaram
paradas, apareceram na câmera RGB e o LiDAR as mediu onde estavam (17,96 passos/s com 12 agentes extras).

**Cenário** (`config/goto_dique.json`):
- `agente_obstaculo` (comum aos cenários): `tipo` TorpedoAUV, `comprimento` 2,1 m, `diametro` 0,19 m, `folga` 0,15 m entre
  torpedos empilhados ou em fila (encostados, o motor os arremessa), `folga_feixe` 0,05 m entre os do feixe, `origem_eixo`
  (deslocamento da origem do ator ao longo do eixo do torpedo; 0 até calibrar no lab, onde se mediu 0,861 m sem sinal).
- Cada cenário troca `pilares` por `obstaculos`:
  - `{"tipo": "pilar", "xy": [x, y], "feixe": 2, "niveis": 3, "base_z": -1.2}`: feixe n × n de torpedos em pé (pitch 90°),
    `niveis` empilhados a partir de `base_z` (3 níveis: −1,2 a 5,4 m, cobre a faixa de voo −1,1 a 4,8 m mesmo com a origem
    deslocada 0,86 m); 2 × 2 = 0,43 m de lado.
  - `{"tipo": "viga", "de": [x, y, z], "ate": [x, y, z]}`: torpedos deitados em fila de `de` até `ate` (z igual; quantos
    couberem, centrados), guinada na direção da fila.
- Coordenadas reais (área conferida no lab em 2026-11-18: x 127–135, y −155 a −145, folga ≥ 1,8 m até parede e navio, 0
  colisões); `provisorio: false`:
  - `pilares` (Fig. 6a do Depth-CUPRL, pedido do coorientador): 4 pilares 2 × 2 em (129,4/132,6; −152/−148), 48 torpedos.
  - `dique` ("adicione mais obstáculos"): os 4 pilares + 1 pilar no centro (131; −150) + 2 vigas na linha d'água
    (z = −0,05, ao norte em y = −146,3 e ao sul em y = −153,7, de x = 127,9 a 132,25: o Hydrone passa por cima ou por baixo)
    + 2 travessas no ar entre pilares (x = 129,4, z = 2,5 e x = 132,6, z = 1,2, de y = −151 a −149): 66 torpedos.
  - Spawn nos dois: (133,88; −152,6; 2,0).
  O dique inteiro (bacia norte com o navio) fica para depois de mapear o navio de novo (`mapear_dique.py --mapa`).

**`GotoEnv`:**
- `_build_params`: acrescenta o agente em lote `obstaculo` (`batch_size` = nº de torpedos, `accel`, dois DynamicsSensor, nascendo
  30 m acima do spawn); sem obstáculos no cenário, nada muda.
- `_reset`: depois do `self._env.reset()`, `_posicionar_obstaculos()`: cada torpedo vai para um ponto de espera no alto, acima do
  seu lugar (níveis em alturas diferentes), e desce na vertical, um nível por tick, de baixo para cima (o teleporte varre o
  caminho); depois confere a posição de cada um (diferença para o ponto imposto igual à mediana dos outros, ±0,3 m) e repete
  subida e descida para os que não chegaram (até 3 vezes; senão `warnings.warn`).
- `_passo_sim`: um tick por vez quando há obstáculos, reimpondo posição e atitude de todos antes de cada tick; `cmds` vira
  `{'robot': cmd, 'obstaculo': [[0]*6]*n}`; `_unwrap_state` lê `state['robot']` e guarda `state['obstaculo']`.
- Colisão em Python: cada torpedo vira uma cápsula (eixo do torpedo, raio 0,095 m); `_dist_obstaculo(pos)` dá a menor
  distância e o tipo; motivos "pilar" ou "viga" (< 0,625 m), no lugar do antigo cilindro. Alvos sorteados a ≥ `folga_alvo` das
  cápsulas. `_spawn_pilares` (spawn_prop) sai.
- A recompensa e o resto do término não mudam.

**Riscos:** passos/s menores (66 torpedos; medir no lab; se ficar < ~12 passos/s, reduzir o `dique`); o Hydrone empurra um
torpedo num contato (o episódio termina na colisão e a posição é reimposta no tick seguinte); sinal do deslocamento da origem
do ator (calibrar no lab: varredura vertical do LiDAR junto a um pilar; com 3 níveis a faixa de voo fica coberta nos dois
sinais, mas as vigas deitadas deslocariam 0,86 m ao longo do eixo).

**Verificação:** testes sem simulador (geometria dos pilares e vigas, cápsulas, colisão, `cmds` em dicionário, reimposição a
cada tick, posicionamento com repetição); no lab (`tools/conferir_obstaculos.py`): todos os torpedos no lugar, calibração da
origem, fotos RGB e de profundidade, LiDAR nos obstáculos, passos/s dos `-v0/-v1/-v2` nos dois cenários e 0 órfãos.
