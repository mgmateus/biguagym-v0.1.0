# ajuste-ambientes — Log de execução

## 2026-10-19 — T1: branches
- Usuário: "aprovado, pode fazer da T1 à T12" → `tasks.md` em `Status: aprovado` (inclui autorização das T9–T11 ⏱).
- Repositório principal: branch `spec/ajuste-ambientes` (worktree `.claude/worktrees/ajuste-ambientes`, já com o merge
  da `testes-ambientes`). Submódulo do worktree: `git -C biguagym checkout -b spec/ajuste-ambientes fcf4358`.
- Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` = `spec/ajuste-ambientes`;
  `git -C biguagym rev-parse HEAD` = `fcf4358`; checkout principal (`~/biguagym-v0.1.0/biguagym`) continua em `fcf4358`. ✅

## 2026-10-19 — T2: parâmetro `env_version`
- `biguagym/core/environments.py`: `env_version: str = "v1"` depois do `reward_version` nas 13 assinaturas e
  `env_version=env_version` nos 12 repasses ao `super().__init__`; `HoverEnv.__init__` valida (`ValueError`) e guarda
  `self._env_version` antes do `_build_params` (os limites dependem dele).
- `tests/recompensas_util.py`: os ambientes falsos ganham `_env_version = "v0"` (os casos da spec `recompensas` usam o
  limite de 15° para provocar o término por inclinação).
- Novo `tests/test_ajuste_ambientes.py`: `test_versao_em_todos_os_construtores`, `test_versao_invalida`.
- Verificação: `pytest -k versao tests/test_ajuste_ambientes.py` → 2 passed; `pytest tests/` → 37 passed (35 + 2). ✅

## 2026-10-19 — T3: spawn e limites em z
- `HoverEnv`: constantes `UNDERWATER_SPAWN_Z = -1.5` e `AIR_CEILING_ABOVE_SPAWN = 5.0`; método de classe
  `_spawn_location(agent_type, location, env_version)` (subaquático na v1 → z = −1,5), chamado no `__init__` antes do
  `_build_params` (separado num método para poder ser testado sem simulador).
- `HoverEnv._build_params` (Hover/Land): teto v1 = z do spawn + 5 (v0: `max(z_spawn, 2·piso)` = spawn).
- `DockEnv._build_params`: teto v1 = −0,1 (v0: `min(z_spawn, −0,2)` = spawn); fundo −10 nas duas.
- Nav e Trajectory não mudam no código: com o spawn em −1,5 o teto −0,1 passa a ter 1,4 m de folga.
- Testes: `test_limites_folga_v1` (5 casos: Land, Hover, Nav aéreo, Dock, Nav subaquático) e
  `test_limites_v0_iguais_aos_de_hoje` (mesmos 5, com os valores medidos no diagnóstico de 2026-10-16).
- Verificação: `pytest -k limites` → 10 passed; `pytest tests/` → 47 passed. ✅

## 2026-10-19 — T4: limite de inclinação por domínio
- `HoverEnv.TILT_LIMIT_DEG = {'aereo': 60, 'multi-domain': 60, 'underwater': 60, 'surface': 15}` e `_tilt_limit()`
  (v0 → 15° para todos). Os 6 `np.radians(15)` fixos (HoverEnv/Nav, LandEnv, DockEnv, TrajectoryEnv e LandCoopPixelEnv)
  passam a chamar `self._tilt_limit()`; o único `np.radians(15)` que sobra é o do caminho v0 dentro do método.
- Testes: a 30° drone (Hover, Land) e ROV (Dock, Nav) não terminam na v1 e terminam por `tilt` na v0; a 70° terminam na
  v1; barco: 20° termina e 10° não (15° mantido).
- Verificação: `pytest -k inclinacao` → 9 passed; `grep -c "np.radians(15)"` → 1 (em `_tilt_limit`); `pytest tests/` →
  56 passed. ✅ Trajectory e LandCoop sem teste unitário de inclinação: cobertos pelo smoke (T9) e `diag_termino` (T10).

## 2026-10-19 — T5: alvo do barco na superfície
- `HoverEnv._reset` (Nav herda): na v1, para `DOMAIN['surface']`, `self._target[2] = z do spawn` (0) depois do sorteio;
  x, y continuam sorteados em ±10 m. Land e Dock têm `_reset` próprio e não mudam.
- Testes (sem simulador, `_reset` com simulador falso e `rng` com seed 0): 1000 alvos do BlueBoat v1 com z = 0 e x, y
  em [90; 110]; v0 continua sorteando z em [−1; 0,1]; BlueROV2 v1 continua com z sorteado.
- Verificação: `pytest -k alvo` → 3 passed; `pytest tests/` → 59 passed. ✅

## 2026-10-19 — T6: alvo relativo na observação
- `HoverEnv._HAS_TARGET = True`, `TrajectoryEnv._HAS_TARGET = False`; `_target_in_obs()` = v1 e `_HAS_TARGET`.
- `HoverEnv._init_spaces`: `total_dim += 3` quando `_target_in_obs()`. `HoverEnv._wrap_state`: acrescenta
  `alvo − posição` (float32; zeros se ainda não houver alvo ou dinâmica). Variantes v1 (pixels) e v2 (range/sonar)
  leem o tamanho e chamam `super()._wrap_state`, então herdam sem mudança.
- Testes: dimensão 19 → 22 na v1 (Land, Hover, Nav aéreo, Dock, Nav subaquático) e 19 na v0; Trajectory 19 nas duas
  (antes do caminho); `_wrap_state` com posição (101, 98, −2) e alvo (105, 95, −7) → últimos 3 = (4, −3, −5).
- Verificação: `pytest -k observacao` → 7 passed; `pytest tests/` → 66 passed. ✅

## 2026-10-19 — T7: v0 idêntico ao de hoje
- Cobertura do caminho `env_version="v0"` nos testes: limites e spawn (`test_limites_v0_iguais_aos_de_hoje`, valores
  medidos em 2026-10-16), inclinação de 15° (`test_inclinacao_30_graus_...`, parte v0), alvo do barco em todo o volume
  (`test_alvo_barco_v0_...`), observação com 19 valores (`test_observacao_tem_mais_3_na_v1`, parte v0) e os testes da
  spec `recompensas` (ambientes falsos com `_env_version="v0"`), inclusive `test_v0_identico_ao_original` contra
  `tests/dados/recompensa_v0.json`.
- Revisão do diff do submódulo (`git -C biguagym diff fcf4358`): 92 inserções e 22 remoções; as 22 linhas removidas são
  repasses de parâmetro, os 6 `np.radians(15)` trocados por `_tilt_limit()` (15° na v0) e as 3 expressões originais
  (spawn, teto do Hover/Land, teto do Dock), que continuam no ramo v0. Nenhuma lógica original perdida.
- Verificação: `pytest tests/` → 66 passed (35 da spec `recompensas` + 31 novos). ✅

## 2026-10-19 — T8: fork, ponteiro do submódulo e `diag_termino.py`
- Submódulo: `git -C biguagym push git@github.com:ttszin/biguagym.git spec/ajuste-ambientes` (5 commits sobre `fcf4358`:
  `df0296a` T2, `fecdd64` T3, `9b431b6` T4, `9cfaae4` T5, `ff452dc` T6).
- Ponteiro do submódulo na `spec/ajuste-ambientes` do repositório principal → `ff452dc`.
- `tools/diag_termino.py`: 3º argumento opcional `env_version` (padrão v1), passado ao `gym.make`; a saída inclui
  `env_version` e `z_spawn`.
- Verificação: `git ls-remote https://github.com/ttszin/biguagym.git spec/ajuste-ambientes` → `ff452dcf…` = HEAD do
  submódulo do worktree. ✅

## 2026-10-19 — T9: smoke dos 24 ambientes da fila (⏱)
- Laço (um ambiente por vez, sob `systemd-inhibit`, com trava: para se a bateria < 35% fora da tomada):
  `python smoke_test.py --env <id> --steps 200 --frame-every 100 --out smoke_results/t9_ajuste`, nos 24 ids do
  `treinos/cluster/runs.csv`, a partir do worktree (submódulo `ff452dc`). Começou na bateria (61%); o notebook foi ligado
  na tomada durante o laço (18:18). 18:15–18:39.
- Resultado: **24/24 `status ok`, `exit 0`, 0 simuladores depois de cada um.** `smoke_test.py --list` (T12) → 54 ids.

  | Ambiente | obs antes (2026-10-11) → agora | z do spawn | z do alvo |
  |---|---|---|---|
  | BlueBoatNav v0 / v2 | 19 → **22** / 129 → **132** | 0 | **0,0** (antes sorteado em [−1; 0,1]) |
  | BlueROV2Dock v0 | 19 → **22** | **−1,5** | −10 |
  | BlueROV2Nav v0 / v2 | 19 → **22** / 119 → **122** | **−1,5** | −2,9 |
  | DjiMatriceHover v0 | 19 → **22** | 5 | 8,6 (teto agora 10) |
  | DjiMatriceLand v0 | 19 → **22** | 5 | 0,1 |
  | DjiMatriceNav v0 / v2 | 19 → **22** / 29 → **32** | 5 | 12,9 |
  | Trajectory (Dji/BlueBoat/BlueROV2) v0 / v2 | 39 / 49, 149, 139 (iguais) | BlueROV2 **−1,5** | — |
  | todos os v1 | `rgb:9x84x84` (igual) | | |

- **Limitação encontrada:** os ambientes v1 têm `include_state=False` por padrão (observação só com a imagem), então o
  alvo relativo só entra neles com `include_state=True`. Por padrão, o agente v1 só "vê" o alvo pelo marcador desenhado
  na cena (e o bug do `np.resize` dos pixels continua aberto). O R4 previa a v1 "na parte de estado": atendido; registrado.
- Velocidade: v0 17,9–19,1 passos/s; v1 11–12; v2 com sonar 1,2–3,3 (em 2026-10-11 tinha dado 4,1–4,4; variação não
  investigada); v2 do drone 18,3–18,6.
- Drone com ação aleatória ainda termina (4–5 de 5 episódios em 200 passos): medido na T10.

## 2026-10-19 — T10: diagnóstico de término v0 × v1 (⏱)
- Laço: `python tools/diag_termino.py <env> 300 <v1|v0>` (300 passos com ação zero + 300 aleatórios, recompensa v1
  para ter o `termination_reason`), um processo por vez, `timeout -k 30 1200`, trava de bateria; na tomada. 0
  simuladores depois de cada um.

  | Ambiente | limites z v0 → v1 | Aleatória v0: mediana (motivos) | Aleatória v1: mediana (motivos) |
  |---|---|---|---|
  | BlueROV2Dock | [−10; −0,2] → [−10; −0,1], spawn −0,2 → −1,5 | **2** (17 out_of_bounds, 3 tilt) | **128** (2 tilt a ~60°) |
  | DjiMatriceLand | [0,1; 5] → [0,1; 10] | **6** (34 tilt, 8 out_of_bounds) | **35** (6 hard_landing, 2 tilt) |
  | BlueROV2Nav | [−20; −0,1], spawn −0,2 → −1,5 | **21** (5 tilt, 4 out_of_bounds) | **76** (3 tilt) |
  | BlueROV2TrajectoryFollower | [−5,2; −0,1] → [−6,5; −0,1] | **26** (5 tilt, 4 out_of_bounds) | **101** (2 tilt) |
  | DjiMatriceNav | [0; 15] (igual) | **7** (36 tilt) | **47** (3 out_of_bounds, 3 tilt) |
  | BlueBoatNav | [−1; 0,1] (igual) | não termina em 300 | não termina em 300 |

  Ação zero: igual nas duas versões (Dock e Nav do ROV parados até o timeout; drone cai → `hard_landing` no Land e
  `out_of_bounds` pelo chão no Nav), mas agora o ROV fica parado em −1,5.
- Critérios: mediana ≥ 20 e `out_of_bounds` < 50% em Dock (128; 0%), Land (35; 0%), BlueROV2Nav (76; 0%),
  BlueROV2TrajectoryFollower (101; 0%) ✅; DjiMatriceNav 47 > 6 e DjiMatriceLand 35 > 4 ✅.
- Observação: na v1 os episódios aleatórios ficaram tão longos que 300 passos dão só 2–8 episódios; as medianas são
  menos precisas, mas a diferença para a v0 (2–26) é grande.

## 2026-10-19 — T11: pilotos TD3 de 5000 passos (⏱)
- Laço, um por vez, na tomada, `systemd-inhibit`, pasta própria por piloto:
  `python run.py hydra/launcher=basic env=<id> agent=td3 num_train_steps=5000 runs=1 agent.learning_starts=1000
  eval_freq=1000000 num_eval_episodes=1 curves_path=... logs_path=...` (worktree, submódulo `ff452dc`, padrões v1/v1).
- Resultado: BlueROV2Dock-v0 `exit 0` em 14 min; DjiMatriceLand-v0 `exit 0` em 20 min; BlueBoatNav-v0 `exit 0` em 7 min;
  0 tracebacks; 0 simuladores depois de cada um.

  | Ambiente | Trecho | Linha de base: passos/ep (mediana) | Piloto v1: passos/ep (mediana) | Retorno médio do piloto |
  |---|---|---|---|---|
  | BlueROV2Dock | 0–1000 (aleatório) | 2 | **86** | −218 |
  | BlueROV2Dock | 1000–5000 | 3 | **28** | −27 |
  | DjiMatriceLand | 0–1000 (aleatório) | 4,5 | **39** | −199 |
  | DjiMatriceLand | 1000–5000 | 5 | **19** | −96 |
  | BlueBoatNav | 0–1000 / 1000–5000 | 400 / 400 | 400 / 400 | −30 / −211 |

- Critério (episódios do Dock e do Land mais longos que na linha de base no mesmo trecho): ✅.
- **Observações para os 250k (não bloqueiam a spec):**
  - BlueBoatNav: logo depois de começar a aprender (passo ~2400) o retorno cai para −231 por episódio, o mesmo valor do
    "gira parado" da linha de base. Ter o alvo na observação não evitou o colapso: o problema do BlueBoatNav é do TD3
    (ação travada nos extremos dos motores, ±290), fora do escopo desta spec (hiperparâmetros). Proposta: spec própria.
  - Dock e Land: com o TD3 aprendendo, os episódios encurtam (86 → 28, 39 → 19) enquanto o retorno melhora. Com o
    limite de 60°, o termo `stable` chega a −3 por passo acima de 35° e a queda custa −10 uma vez: terminar cedo pode
    voltar a compensar. 5000 passos não distinguem isso de aprendizado; acompanhar nas curvas dos 250k.
