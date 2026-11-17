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
  explorar; `nivel_agua` fica no JSON, mas a física continua em 0 enquanto o mundo não exportar a superfície.
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
