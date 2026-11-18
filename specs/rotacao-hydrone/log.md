# rotacao-hydrone — Log

## 2026-11-17 — Aprovação e diagnóstico
- Pedido do usuário: "Resolva isso do giro" (depois do relatório do lab que mostrou o Hydrone sem guinada no BiguaSim 1.1.0).
  Tratado como aprovação de requisitos, design e tarefas, como nas specs anteriores do Goto.
- Leitura do BiguaSim 1.1.0 (`~/biguasim-treino`, sem alterar): `BiguaSim.step` faz `tick()` → `modelo.step(estado)` →
  `agente.act([v̇, ω̇])`; Hydrone e DjiMatrice usam o mesmo esquema de controle (1); `hauv.step` devolve ω̇ no mundo, já
  integrada em subpassos; o upstream (hydrone-furg) não tem commits depois da v1.1.0 (`git fetch upstream`).
- `tools/diag_rotacao_hydrone.py` no lab (`~/diag_rotacao.log`, `~/diag_rotacao2.log`; commits `ec9dc76`, `d866f04`),
  agente a 2 m do chão, partindo do repouso:

  | Teste | Hydrone | DjiMatrice |
  |---|---|---|
  | `accel` ω̇ 1 rad/s² em x / y / z, 20 ticks | 0,06° / 0,06° / 0,05° | 0,11° / 0,11° / 0,11° |
  | `accel` ω̇z 3,35 / 10 rad/s², 20 ticks | 0,06° / 0,06° | 64,7° (ω 2,05) / gira (ω 6,18) |
  | `accel` linear 1 m/s² em x, 20 ticks | 0,34 m | 0,34 m |
  | `set_physics_state` ωz = 30°/s uma vez, 20 ticks | 18,9°, ω cai a 0,192 rad/s | igual |
  | `set_physics_state` ωz = 30°/s a cada tick, 20 ticks | 29,2°, ω = 0,498 rad/s | igual |
  | teleporte para yaw 45° | 45° | igual |
  | `cmd_vel_yaw` 20°, 30 ticks | 0,08° (dinâmica manda ω̇z = 3,14 constante) | 46,3° (manda 1,01 → 0,51) |
  | as mesmas acelerações reenviadas em `accel` | 0,08° | 0,11° |

- Conclusões:
  - O motor não aplica a aceleração angular ao Hydrone (nenhum eixo, até 10 rad/s²); a linear, sim. Sem rotação ele
    também não inclina, então no ar não acelera na horizontal.
  - No DJI o motor aplica às vezes: as mesmas acelerações giram ou não conforme o histórico (como um corpo dormindo na
    física, que só acorda em certas condições). Fica registrado para os autores; o DJI não é usado no Goto.
  - A velocidade angular imposta por `set_physics_state` é sempre respeitada; o motor a amortece a ≈ 1 s⁻¹
    (0,524 → 0,192 rad/s em 1 s = e⁻¹; 0,524 → 0,498 em um tick de 0,05 s = e^(−0,05)).

## 2026-11-17 — T1–T4
- T1: branches `spec/rotacao-hydrone` (principal e submódulo) a partir da `spec/sensores-goto`.
- T2 (submódulo `7ceeb25`, `biguagym/core/goto.py`): `AMORTECIMENTO_ANGULAR_MOTOR = 1.0`; `integrar_rotacao=True` no
  construtor (recusa `batch_size` > 1); `_instalar_integrador` (envolve o `step` da dinâmica: guarda ω̇ e zera a parte
  angular enviada ao motor; reinstalar não empilha), `_impor_rotacao` (`set_physics_state` com posição, RPY em graus e
  velocidade do `RPYDynamicsSensor` e ω = (ω medido + ω̇·dt)·e^(c·dt) em graus/s), `_passo_sim` (tick a tick com a
  integração; sem ela, o `step` com `action_repeat` de antes); `_reset` zera ω̇ e instala; `_step` usa `_passo_sim`.
  Motivo: o motor não integra a aceleração angular do Hydrone; a integração vem para o biguagym, com a dinâmica dos autores.
- Testes: `tests/test_rotacao_hydrone.py` (7 testes, simulador falso que imita o `BiguaSim.step`); `montar()` de
  `test_hydrone_goto.py` e `preparar()` de `test_sensores_goto.py` desligam a integração (os simuladores falsos deles não
  têm dinâmica). Um teste pegou que o `_set_dynamics` converte o RPY do estado no lugar (o agente falso agora copia, como o
  `np.copyto` do BiguaSim). `pytest tests` → 169 passed (162 + 7).
- T4 (`2d2228a`): `diag_goto.py` com a fase "avanço" (deslocamento na direção do nariz) e a "direto" pela `_passo_sim`;
  `diag_rotacao_hydrone.py goto` (ω medido × previsto, guinada no ar e na água); `testar_goto_lab.sh` roda o modo goto e
  só testa os extras do `explorar_mapa` com `SO_EXTRAS=1` (já resolvido).

## 2026-11-17 — T5 no lab (parcial) e achado novo: acelerações lineares pequenas também são descartadas
Lab em `spec/rotacao-hydrone` (`2d2228a`/`7ceeb25`; depois `b470983`, `9ef3ad2`, `e285652` só com ferramentas). O treino
`teste_5m_rotft_1` de outra sessão (TCC, `biguasim_gold`, mundo 1.0.0) rodava ao mesmo tempo: passos/s abaixo do normal.

`bash tools/testar_goto_lab.sh` (`~/testar_rotacao.log`, 20:52–20:57):

| Critério | Resultado |
|---|---|
| pytest | 169 passed |
| ω medido / previsto (`diag_rotacao_hydrone.py goto`) | mediana 1,000 (min 1,000, max 1,000) no ar e na água: integração e amortecimento de 1 s⁻¹ certos nos dois meios |
| R4 guinada pelo `GotoEnv` (`diag_goto`, ω = ±0,3 rad/s, 5 s) | **+1,514 rad e −1,527 rad** (esperado ±1,50; antes 0,003); yaw segue a referência com desvio < 3° |
| R4 `cmd_vel_yaw` com desvio fixo de 20° | gira (2,8 rad em 100 ticks), mas a 3 rad/s e o Hydrone sobe até 7 m: entrada fora do uso (o `GotoEnv` manda 1–3°); o controlador dos autores satura |
| R5 subida (vz = 0,3 m/s, 5 s) | +1,11 m (igual a antes) |
| R5 avanço (0,31 m/s, 5 s) | **+0,175 m** (esperado 1,55) no `diag_goto`; **0 m** a partir do reset (`diag_goto.py ... avanco`), com a integração ligada **ou desligada** |
| smokes `-v0/-v1/-v2` | ok, 7,65 / 6,43 / 7,51 passos/s (antes 12,1 / 9,6 / 11,8, sem o treino concorrente), sem NaN, obs no espaço |
| processos | só os 4 do treino da outra sessão; 0 órfãos meus |

Investigação do avanço:
- `diag_rotacao_hydrone.py Hydrone` (G): ω imposta em x e y → roll/pitch de 29,2° em 20 ticks; teleporte para roll/pitch
  de 10° → 10°. O motor não trava nenhum eixo; a integração angular vale nos três.
- Dinâmica dos autores integrada só em Python (`tools/avanco_offline_hydrone.py`, sem o motor): o controlador de velocidade
  no ar inclina só 0,2° (lento, mas anda: 0,44 m e 0,16 m/s em 5 s). No motor, o mesmo pitch de 0,2° e deslocamento 0.
- `diag_rotacao_hydrone.py linear` (H, accel, parado a 2 m): aceleração linear de 0,035 m/s² e de 0,2 m/s² em x por 100
  ticks → **0 m** (esperado 0,43 e 2,45 m); v_x de 0,3 m/s imposta uma vez → 0,285 / 0,182 / 0,110 m/s nos ticks 0 / 9 / 19
  = 0,3·e^(−t): **amortecimento linear de 1 s⁻¹**, como o angular. O A de 1 m/s² (0,34 m) bate exatamente com 1 s⁻¹.
- Conclusão: o motor do BiguaSim 1.1.0 descarta acelerações pequenas (lineares e angulares; o limiar fica entre 0,2 e
  1 m/s² no linear; a angular do Hydrone nunca é aplicada) e amortece a 1 s⁻¹ o que aplica. A correção da rotação resolve o
  giro (R4), mas o avanço lento do controlador dos autores fica abaixo do limiar e é descartado.
- **Proposta (fora do design aprovado, aguardando aprovação):** estender a integração à parte linear — impor também
  v + a·dt (compensada por e^(dt)) no mesmo `set_physics_state` e mandar aceleração zero ao motor, que fica só com a
  cinemática e as colisões. Ver "Extensão proposta" no `design.md`.

## 2026-11-17 — T6: integração linear (extensão aprovada)
- Usuário: "pode seguir sim" (aprovação da extensão proposta no design.md).
- `biguagym/core/goto.py`: o envoltório guarda as 6 acelerações em `_acc` e manda **zero** ao motor; `_impor_rotacao` →
  `_impor_estado`, que impõe v = (v + v̇·dt)·e^(dt) (v do `DynamicsSensor`, a mesma que a dinâmica lê) e ω como antes;
  `AMORTECIMENTO_LINEAR_MOTOR = 1.0` (medido: 0,3 → 0,285 m/s em um tick); `integrar_rotacao` → `integrar_dinamica`.
  Motivo: o motor descarta acelerações lineares pequenas (0,2 m/s² por 5 s → 0 m), e o avanço do controlador dos autores
  pede ~0,03 m/s².
- Testes: `test_rotacao_hydrone.py` cobre motor recebendo zeros e v imposta a partir do `DynamicsSensor`; fixtures antigas
  com os nomes novos. `pytest tests` → 169 passed.
- `diag_rotacao_hydrone.py goto`: cmd_vel_yaw [0,3, 0, 0, 5°], razão medido/previsto de v_x e de ω_z, no ar e na água.

## 2026-11-17 — T7 no lab: integração linear (`~/testar_linear.log`, 21:49–21:56)
Lab em `16b1f71`/`f27fe79`; treino de outra sessão rodando junto.

| Critério | Resultado |
|---|---|
| pytest | 169 passed |
| v_x e ω_z medidos / previstos (`diag_rotacao_hydrone.py goto`, ar e água) | mediana 1,000 / 1,000 nos dois meios |
| água, cmd_vel_yaw [0,3, 0, 0, 5°], 60 ticks | anda 0,36 m e gira 16,7°, estável |
| ar, mesmo comando | anda e gira, mas o desvio **fixo** de 5° (alvo sempre 5° à frente) acelera a guinada até divergir (ω_z −25 rad/s, sobe a 6 m em 3 s); o `GotoEnv` não manda isso: a referência de guinada é integrada e limitada a 0,3 rad/s |
| R4 guinada pelo `GotoEnv` | +1,514 / −1,527 rad |
| R5 subida | **+1,485 m** (esperado 1,5; só com a rotação: 1,11) |
| R6 avanço no `diag_goto` (depois da subida, em movimento) | **+0,509 m** (só com a rotação: 0,175) |
| R6 avanço a partir do reset (`diag_goto.py ... avanco`) | **0 m** com a integração ligada ou desligada (pitch 0,2°, v medido 0) |
| smokes `-v0/-v1/-v2` | ok, 4,91 / 4,58 / 5,11 passos/s (treino concorrente), sem NaN, obs no espaço |
| processos | só os 4 do treino da outra sessão |

Diagnóstico do avanço a partir do repouso: com o Hydrone em movimento a velocidade imposta é respeitada 1:1, mas parado
(depois do reset) o corpo fica "dormindo" na física do motor: a velocidade imposta a partir da **medida** (0 + 0,03·0,05 =
0,0017 m/s por tick) não o acorda, o motor devolve v = 0 e a integração recomeça do zero a cada tick. É o mesmo efeito
que descartou as acelerações pequenas.

**Ajuste proposto ao design (aguardando aprovação):** integrar v e ω no próprio `GotoEnv` (estado do integrador, zerado no
reset e reposto pelo valor medido quando o motor mudar a velocidade, por exemplo numa colisão) em vez de partir da medida a
cada tick, e entregar à dinâmica esse v/ω. Assim a velocidade acumula mesmo enquanto o corpo dorme e, ao passar do limiar,
o motor passa a mover o Hydrone.

## 2026-11-18 — Ajuste aprovado e T8: integrador com v/ω próprios
- Usuário: "Sim" (aprovação do ajuste proposto no T7). Ajuste descrito no design.md ("Ajuste — integrador com estado
  próprio"); tarefas T8 e T9 acrescentadas ao tasks.md.
- `biguagym/core/goto.py` (submódulo `ac6ff26`): `_v`/`_w` (leitura esperada do `DynamicsSensor` no próximo tick, zeradas no
  reset e no construtor); `_conciliar` (com o motor medindo v = ω = 0 e o integrado abaixo de `VEL_DORMINDO = 0,1` m/s e
  `VEL_ANG_DORMINDO = 0,1` rad/s, valem os integrados; senão, os medidos); o envoltório entrega à dinâmica uma cópia do
  `DynamicsSensor` com esse v/ω; `_impor_estado` parte de `_v`/`_w`. Motivo: parado, o corpo dorme no motor e a integração
  a partir da medida recomeçava do zero a cada tick (avanço 0 m a partir do repouso).
- Testes (`53c5854`): 4 novos em `test_rotacao_hydrone.py` (parado: v imposta cresce a·dt por tick; a dinâmica recebe o
  integrado e o estado do motor não muda; acima do limiar vale a medida; motor medindo velocidade, vale a medida); o reset
  zera `_v`/`_w`. `~/venv-biguagym/bin/python -m pytest tests` → 173 passed.
  - Os 3 testes novos falharam na primeira versão por erro do próprio teste: o envoltório captura o `step` original na
    instalação, então trocar o `_step_original` depois não tinha efeito. A aceleração do modelo falso passou a ser um atributo.
- `tools/diag_goto.py ... avanco` imprime também o v integrado.

## 2026-11-18 — T9 no lab: integrador com v/ω próprios (`~/testar_dormindo.log`, 02:46–02:53)
Lab em `01ffa5d`/`ac6ff26`; a outra sessão (TCC) liberou o lab, e o treino `teste_5m_rotft_1` dela rodava junto.
Comando: `bash tools/testar_goto_lab.sh` seguido de `tools/diag_goto.py HydroneGotoPilares-v0 5 avanco`.

| Critério | Resultado |
|---|---|
| pytest | 173 passed |
| v_x e ω_z medidos / previstos (`diag_rotacao_hydrone.py goto`) | mediana 1,000 / 1,000 no ar e na água |
| água, cmd_vel_yaw [0,3, 0, 0, 5°], 60 ticks | anda 0,36 m e gira 16,7° (igual ao T7) |
| ar, mesmo comando | diverge como no T7 (desvio **fixo** de 5°, entrada fora do uso do `GotoEnv`) |
| R4 guinada pelo `GotoEnv` | +1,514 / −1,527 rad |
| R5 subida | +1,485 m |
| R6 avanço no `diag_goto` (em movimento) | +0,509 m |
| **R6 avanço a partir do reset** (`diag_goto.py ... avanco`, 100 passos) | **+0,44 m, v = 0,16 m/s** com a integração (o mesmo da dinâmica dos autores integrada em Python: 0,44 m e 0,16 m/s); sem ela, 0 m |
| smokes `-v0/-v1/-v2` | ok, 6,18 / 6,23 / 7,49 passos/s (treino concorrente), 0 passos com NaN |
| processos | só os 4 do treino da outra sessão (PIDs 456635, 456638, 456684, 456784); 0 órfãos meus |

Na fase `avanco` com a integração, a v medida pelo motor acompanha a integrada desde o passo 19 (0,03 / 0,036 m/s; 0,16 /
0,161 m/s no passo 99): o corpo acorda logo e o motor passa a respeitar a velocidade imposta. Todos os critérios (R1–R6)
estão atendidos. Para os autores: aceleração angular do Hydrone ignorada pelo motor; acelerações lineares pequenas
descartadas; amortecimento de 1 s⁻¹ em v e ω; corpo dormindo que não acorda com velocidades pequenas; controlador
`cmd_vel_yaw` que diverge no ar com desvio de guinada fixo.
