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
