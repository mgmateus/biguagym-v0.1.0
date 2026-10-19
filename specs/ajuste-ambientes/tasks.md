Status: aprovado

# ajuste-ambientes — Tarefas

T1–T8 não usam o simulador. T9–T11 usam o simulador do notebook (livre). Depois da T12, os 250k podem começar no
PC do lab.

- [x] T1 — Branch `spec/ajuste-ambientes` no repositório principal (já existe, worktree `.claude/worktrees/ajuste-ambientes`) e, no submódulo do worktree, branch `spec/ajuste-ambientes` a partir de `fcf4358`
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/ajuste-ambientes`; `git -C biguagym rev-parse HEAD` → `fcf4358…`
- [ ] T2 — Parâmetro `env_version` (`"v1"` padrão, `"v0"`; `ValueError` para outro valor) no `HoverEnv`, repassado nos 12 construtores das subclasses; `recompensas_util.make` fixa `_env_version = "v0"` (R5)
  - Verificação: `pytest tests/test_ajuste_ambientes.py -k versao` → passa; `pytest tests/test_recompensas.py` → 35 passam
- [ ] T3 — Spawn subaquático em −1,5 m (v1); teto do Hover/Land = spawn + 5 m; teto do Dock = −0,1 (R1)
  - Verificação: `pytest tests/test_ajuste_ambientes.py -k limites` → folga ≥ 1 m no v1 e valores de hoje no v0
- [ ] T4 — `_tilt_limit()` por domínio (60° aéreo/multi-domínio/subaquático, 15° superfície; 15° no v0) usado nos `_step` de Hover/Nav, Land, Dock, Trajectory e LandCoop (R2)
  - Verificação: `pytest tests/test_ajuste_ambientes.py -k inclinacao` → 30° não termina no drone/ROV v1 e termina no v0; `grep -c "np.radians(15)" biguagym/core/environments.py` → só dentro de `_tilt_limit`
- [ ] T5 — Alvo do barco (domínio superfície) com z = z do spawn no v1 (R3)
  - Verificação: `pytest tests/test_ajuste_ambientes.py -k alvo_barco` → 1000 sorteios com z = 0 e x, y em ±10 m
- [ ] T6 — Alvo − posição na observação (v1; `_HAS_TARGET`, falso na Trajectory): `_init_spaces` +3 e `_wrap_state` (R4)
  - Verificação: `pytest tests/test_ajuste_ambientes.py -k observacao` → dimensão +3 em Hover/Nav/Land/Dock, igual na Trajectory e no v0; últimos 3 valores = alvo − posição
- [ ] T7 — v0 idêntico ao de hoje: limites, spawn, inclinação, alvo e observação com `env_version="v0"`; suíte inteira (R5)
  - Verificação: `pytest tests/` → todos passam (35 da spec `recompensas` + os novos)
- [ ] T8 — Commit no submódulo, push da branch `spec/ajuste-ambientes` para o fork `ttszin/biguagym` e ponteiro do submódulo na `spec/ajuste-ambientes` do repositório principal; `tools/diag_termino.py` aceita `env_version`
  - Verificação: `git ls-remote https://github.com/ttszin/biguagym.git spec/ajuste-ambientes` → mesmo hash do submódulo do worktree
- [ ] T9 — ⏱ Smoke de 200 passos nos 24 ambientes da fila (v0/v1/v2) e `smoke_test.py --list` (R4, R6)
  - Verificação: 54 ids; 24/24 `ok`; dimensões +3 em relação à tabela de 2026-10-11 (exceto Trajectory); frames do BlueROV2 em −1,5 m sem colisão; 0 simuladores no fim
- [ ] T10 — ⏱ `tools/diag_termino.py` v0 × v1 nos 6 ambientes do diagnóstico de 2026-10-16 (R1, R2, R3)
  - Verificação: v1 com mediana ≥ 20 passos e `out_of_bounds` < 50% em BlueROV2Dock, DjiMatriceLand, BlueROV2Nav, BlueROV2TrajectoryFollower; DjiMatriceNav e DjiMatriceLand com mediana maior que 6 e 4; 0 simuladores no fim
- [ ] T11 — ⏱ Pilotos TD3 de 5000 passos (`learning_starts=1000`) em BlueROV2Dock-v0, DjiMatriceLand-v0 e BlueBoatNav-v0, um processo cada, em sequência (geral)
  - Verificação: `exit 0`; episódios do Dock e do Land mais longos que na linha de base no mesmo trecho; 0 simuladores no fim
- [ ] T12 — Verificar todos os critérios de aceitação do requirements.md; merge `spec/ajuste-ambientes` → `testes-ambientes` e push
  - Verificação: tabela de critérios preenchida no `log.md`; no checkout principal `pytest tests/` passa e `smoke_test.py --list` → 54 ids
