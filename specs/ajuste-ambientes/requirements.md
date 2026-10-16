Status: rascunho

# ajuste-ambientes — Requisitos

## Contexto
Pedido do usuário (2026-10-16): "verifique os treinos que não tiveram a curva de aprendizado subindo e melhore eles.
E vamos testar todos novamente, mas dessa vez com 250 mil steps".

Linha de base v0 (notebook, TD3, seed 0, 100k passos, `treinos/100k`, ver TESTES.md 2026-10-11 e 2026-10-13):

| Ambiente | Retorno médio (0–20k → 80–100k) | Passos/episódio | Curva |
|---|---|---|---|
| DjiMatriceNav-v0 | −2,7 → −1,7 | 8 → 3 | sobe só porque o episódio encurta |
| DjiMatriceLand-v0 | −4,6 → −0,8 | 6 → 2 | sobe só porque o episódio encurta |
| DjiMatriceTrajectoryFollower-v0 | 15,9 → 27,5 | 8 → 22 | sobe |
| BlueBoatNav-v0 | −26 → −230 | 400 (sempre timeout) | **piora** |
| BlueBoatTrajectoryFollower-v0 | 755 → 1439 | 487 → 589 | sobe, mas pelo "ficar parado" (já corrigido na v1 da spec `recompensas`) |
| BlueROV2Nav-v0 | −5,1 → −3,1 | 36 → 12 | **piora** na avaliação (−2,4 → −3,3) |
| BlueROV2Dock-v0 | −1,8 → −0,07 | 13 → 3 (mediana 2) | sobe só porque o episódio encurta |
| BlueROV2TrajectoryFollower-v0 | 82 → 27 | 36 → 12 | **piora** |

Diagnóstico com o simulador (`tools/diag_termino.py`, 300 passos com ação zero e 300 com ação aleatória por
ambiente, recompensa v1 para ter o `termination_reason`; 2026-10-16):

| Ambiente | Limites z | Ação zero | Ação aleatória |
|---|---|---|---|
| BlueROV2Dock-v0 | [−10; **−0,2**] | parado em −0,2; timeout (300) | 18/22 `out_of_bounds`, 4 `tilt`; **mediana 2 passos**; z final −0,198 |
| DjiMatriceLand-v0 | [0,1; **5,0**] | cai: 15 `hard_landing` (19 passos) | 19 `out_of_bounds`, 25 `tilt` (15,6°); mediana 4 passos |
| BlueROV2Nav-v0 | [−20; −0,1] | não termina em 300 | 5 `tilt`, 1 `out_of_bounds`; mediana 46 |
| BlueROV2TrajectoryFollower-v0 | [−5,2; −0,1] | não termina em 300 | 4 `tilt`, 2 `out_of_bounds`; mediana 34 |
| DjiMatriceNav-v0 | [0; 15] | cai: 11 `out_of_bounds` pelo chão (27 passos) | **39/39 `tilt`** (17,6°); mediana 6 |
| BlueBoatNav-v0 | [−1; 0,1] | não termina em 300 | não termina em 300 |

Causas no código (`biguagym/core/environments.py`, submódulo `fcf4358`):

1. **Teto da área igual à altura do spawn (Dock e Land).**
   - `DockEnv._build_params`: `self._bounds[0, 2] = min(loc_z - 10 + 10, -0.2)` → −0,2, e o BlueROV2 nasce em
     z = −0,2 (`register.py`). Subir 2 mm termina o episódio. (No Dock o índice 0 de z é o teto e o 1 é o fundo.)
   - `HoverEnv._build_params` (herdado pelo `LandEnv`): `self._bounds[1, 2] = max(loc_z, 2·z_min)` → 5,0, a
     altura do spawn do DjiMatrice. Qualquer subida termina o episódio.
2. **Folga de 10 cm até o teto (BlueROV2 Nav e Trajectory).** `NavEnv._build_params` e `TrajectoryEnv.__init__`
   usam teto −0,1 para o domínio subaquático, com spawn em −0,2.
3. **Inclinação máxima de 15° com controle direto dos motores** (`cmd_motor_speeds`), nos `_step` de
   Hover/Land/Dock/Trajectory. Com ação aleatória, o drone passa de 15° em ~6 passos e o BlueROV2 em ~40. Como o TD3
   começa com 25 000 passos aleatórios (`learning_starts`), quase toda a experiência inicial é de quedas de
   poucos passos.
4. **Alvo inalcançável no BlueBoatNav.** `HoverEnv._reset` sorteia o alvo em todo o volume da área; na superfície
   z ∈ [−1; 0,1], mas o barco fica em z ≈ 0. Com sucesso em `‖alvo − pos‖ ≤ 0,15`, a maior parte dos alvos nunca
   pode ser atingida.
5. **O alvo não está na observação (Hover, Nav, Land, Dock).** `HoverEnv._build_params` monta a observação só com
   os sensores de `observation_type` (padrão `"DynamicsSensor"`, 19 valores: aceleração, velocidade, posição,
   ângulos; `core/space.py`). O alvo é sorteado a cada `_reset` e não entra em `_wrap_state`. O agente não tem
   como saber para onde ir: o melhor que ele aprende é terminar rápido (Dock, Land, DjiMatriceNav) ou um
   comportamento fixo. Só os `TrajectoryEnv` acrescentam o caminho à observação (`_traj_obs`, 5 + 3·lookahead
   valores), e são justamente os únicos cuja curva sobe.
6. **BlueBoatNav piora.** A política treinada (`tools/diag_politica.py`, `actor_last.pt`, 400 passos) satura os dois
   motores em sentidos opostos (+288 e −296, desvio 0) e gira parado a 3,1 rad/s: termo `spin` −0,60 por passo,
   `norm` 0 (alvo a 5,6–9,4 m). Ficar parado renderia mais (≈0), então a ordem da recompensa está certa; é um
   ótimo local ruim do TD3, que sem o alvo na observação (causa 5) não tem gradiente útil para sair dele.

## Objetivo
Corrigir os limites, o término e o sorteio do alvo para que, nos ambientes acima, um episódio não termine por
causa da geometria da área antes de o agente poder agir, e que a curva de aprendizado reflita a tarefa e não o
encurtamento do episódio. Depois, retreinar os ambientes com 250 000 passos.

## Fora de escopo
- Vazamento do `close()` (spec `vazamento-simulador`). Os runs de 250k usam `eval_freq=250000` (avaliação só no
  passo 0 e no fim, 3 simuladores, como nos runs de 100k).
- Bug dos pixels (`np.resize`, spec `pipeline-pixels`) e o CUPRL nos v1.
- Hiperparâmetros dos agentes (`learning_starts`, ruído, rede).
- Hydrone, Torpedo, BlueROVHeavy.
- Trocar o `control_abstraction` padrão dos ambientes (ver Perguntas em aberto).

## Requisitos
- **R1** — QUANDO o veículo nasce na posição do `register.py`, O SISTEMA DEVE ter pelo menos 1 m de folga entre o
  spawn e cada limite da área em z (Dock, Land, Nav e Trajectory, nos domínios aéreo e subaquático), sem passar da
  superfície no subaquático (teto ≤ −0,1) nem do chão no aéreo (piso ≥ 0).
- **R2** — QUANDO o veículo inclina, O SISTEMA DEVE terminar por `tilt` só em perda de controle, com um limite por
  domínio (valor no design), e não no limite fixo de 15° atual.
- **R3** — QUANDO o ambiente sorteia o alvo de um veículo de superfície, O SISTEMA DEVE sortear z na altura da
  superfície (onde o barco consegue estar), de modo que todo alvo seja alcançável.
- **R4** — QUANDO o ambiente tem um alvo sorteado (Hover, Nav, Land, Dock), O SISTEMA DEVE incluir na observação a
  posição do alvo relativa ao veículo (alvo − posição, 3 valores), nas variantes v0, v1 (parte de estado) e v2.
- **R5** — QUANDO se passa a opção de versão original (nome no design, como o `reward_version` da spec
  `recompensas`), O SISTEMA DEVE reproduzir exatamente os limites, o término e o alvo de hoje, para a linha de base
  de 100k continuar reproduzível. O padrão é a versão nova.
- **R6** — QUANDO as mudanças estiverem feitas, O SISTEMA DEVE manter as variantes v1 (pixels) e v2 (range/sonar)
  com o mesmo comportamento das v0 (elas herdam os limites e o término) e os 54 ids registrados.

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1 | `pytest tests/` (teste novo, sem simulador, sobre `_bounds` de cada ambiente) | folga ≥ 1 m entre spawn e limites z; teto subaquático ≤ −0,1; piso aéreo ≥ 0 |
| R1, R2 | `python tools/diag_termino.py <env>` nos 6 ambientes da tabela | ação aleatória: mediana ≥ 20 passos por episódio no BlueROV2Dock, DjiMatriceLand, BlueROV2Nav e BlueROV2TrajectoryFollower; `out_of_bounds` < 50% dos términos |
| R2 | idem, DjiMatriceNav e DjiMatriceLand | ação aleatória: mediana maior que a atual (6 e 4); valor-alvo no design |
| R3 | `pytest tests/` (sorteio do alvo, sem simulador) | z do alvo do BlueBoat na superfície em 1000 sorteios |
| R4 | `pytest tests/` (sem simulador) e `smoke_test.py` | observação = sensores + 3; os 3 últimos valores = alvo − posição; dimensões dos v0/v1/v2 +3 em relação a hoje |
| R5 | `pytest tests/` | com a opção original, `_bounds`, término e alvo idênticos aos de hoje; `test_v0_identico_ao_original` continua passando |
| R6 | `python smoke_test.py --list`; smoke de 200 passos em v0/v1/v2 dos ambientes alterados | 54 ids; todos `ok` |
| Geral | piloto de 5000 passos (TD3) em BlueROV2Dock-v0, DjiMatriceLand-v0 e BlueBoatNav-v0 | roda sem erro; episódios do Dock e do Land mais longos que os da linha de base no mesmo trecho |

## Impacto nos experimentos
- A observação dos Hover/Nav/Land/Dock ganha 3 valores: modelos salvos da linha de base não carregam nos ambientes
  novos (só com a opção original, R5).
- Muda o comportamento de Dock, Land, Nav e Trajectory em todos os veículos afetados: os runs novos (250k) não são
  comparáveis com a linha de base de 100k. A linha de base continua reproduzível pela opção de versão original
  (R5) e fica registrada como "antes".
- Os ambientes de estado + sensor (v2) e pixels (v1) mudam junto (herança).
- Tempo dos 250k: os 8 runs de 100k somaram 77 h no notebook; 250k ≈ 2,5× → **~190 h (~8 dias) no notebook**,
  só a seed 0. Episódios mais longos devem reduzir o custo de reset e acelerar um pouco os ambientes que hoje
  terminam em 2–3 passos (o reset custa ~2 s).

## Perguntas em aberto
- **Drone com `cmd_motor_speeds`:** mesmo com um limite de inclinação maior, motores sorteados ao acaso derrubam o
  quadricóptero em poucos passos (é o esperado para controle direto de motores). Alternativas: (a) só aumentar o
  limite de inclinação (mínimo, mantém a tarefa); (b) ação relativa à rotação de hover (a ação 0 mantém o drone
  no ar); (c) usar `cmd_vel`/`cmd_pos_yaw` como padrão (o controlador interno estabiliza; testado no T12 da spec
  `recompensas`). Proposta: (a) nesta spec; (b)/(c) mudam a tarefa e ficam para decisão do usuário.
- **Quais ambientes nos 250k:** proposta: os 8 v0 da linha de base, seed 0, recompensa v1 (padrão). Incluir os v2
  depois, se houver máquina.
- **Onde rodar:** notebook (~8 dias só a seed 0) ou PC do lab/cluster2 (em paralelo).
