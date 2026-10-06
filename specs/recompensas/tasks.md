Status: aprovado

# recompensas — Tarefas

As tarefas T1–T10 não usam o simulador e podem ser feitas com a fila do notebook rodando: todo o trabalho fica no worktree
`.claude/worktrees/recompensas` (R7). As T11–T13 usam o simulador e esperam a fila do notebook terminar.

- [x] T1 — Branch `spec/recompensas` (repositório principal, a partir de `testes-ambientes`) e, no submódulo do worktree, a branch `spec/recompensas` a partir de `32698e5` (`testes-ambientes` do fork)
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/recompensas`; `git -C ~/biguagym-v0.1.0/biguagym rev-parse HEAD` → `32698e5…` (checkout da fila intacto)
- [x] T2 — Gerar a referência da recompensa original: script de casos fixos (Hover, Nav, Land, Dock, Trajectory; sucesso, tilt, out_of_bounds, pouso/docagem dura, passo normal) rodado no código atual → `tests/dados/recompensa_v0.json` (R5)
  - Verificação: `python tests/gerar_referencia_v0.py` → JSON com todos os casos e nenhum NaN; rodar de novo dá um arquivo idêntico
- [x] T3 — Parâmetro `reward_version` (`"v1"` padrão, `"v0"`) no `HoverEnv`, com `ValueError` para outro valor, repassado nos 13 construtores das subclasses (R5)
  - Verificação: `grep -c "reward_version" biguagym/core/environments.py` cobre todos os `__init__`; `pytest tests/test_recompensas.py -k versao` → passa
- [x] T4 — `HoverEnv._reward` guarda `_last_terms`; `HoverEnv._step` em `v1`: sucesso +10, tilt/out_of_bounds −10; `info` com `reward_terms` e `termination_reason` (R1, R2, R6)
  - Verificação: `pytest tests/test_recompensas.py -k "hover or nav"` → passa
- [x] T5 — `LandEnv` e `DockEnv` em `v1`: todas as falhas −10 (inclusive pouso/docagem dura, no lugar do −5); sucesso +20; `info` (R1, R2, R6)
  - Verificação: `pytest tests/test_recompensas.py -k "land or dock"` → passa
- [x] T6 — `TrajectoryEnv` em `v1`: `_best_wp`, `r_track = (r_cte + r_align)·adv`, −10 por tilt/out_of_bounds; `info` (R1, R3, R4, R6)
  - Verificação: `pytest tests/test_recompensas.py -k trajetoria` → passa (parado ≤ 0, para trás ≤ 0, completo > ambos, ir e voltar não paga de novo)
- [x] T7 — `v0` idêntico ao original: os casos da T2 com `reward_version="v0"` reproduzem `recompensa_v0.json` (R5)
  - Verificação: `pytest tests/test_recompensas.py` → todos passam
- [x] T8 — Commit no submódulo, push da branch `spec/recompensas` para o fork `ttszin/biguagym` e atualização do ponteiro do submódulo na branch `spec/recompensas` do repositório principal
  - Verificação: `git ls-remote https://github.com/ttszin/biguagym.git spec/recompensas` → mesmo hash do submódulo do worktree
- [x] T9 — Harness: `run.py` e `workspace.py` passam `**cfg.env.kwargs` ao `gym.make` do treino e da avaliação (correção do `env_kwargs` ignorado)
  - Verificação: teste unitário com `gym.make` falso (monkeypatch) → os kwargs chegam às duas chamadas; `pytest tests/` → passa
- [x] T10 — Cluster: os 8 seeds 0 do notebook voltam para o `treinos/cluster/runs.csv` (64 → 72); LEIAME explica que o cluster usa a recompensa v1 e que o `enviar_do_notebook.sh` não se aplica a ela
  - Verificação: `tail -n +2 treinos/cluster/runs.csv | wc -l` → 72; fila com `run.py` falso → nenhum run espera curva externa
- [ ] T11 — ⏱ (depois da fila do notebook) Smoke de todos os ids que rodam, com a recompensa nova: `python smoke_test.py --all --steps 200 --frame-every 0` (sem Hydrone, BlueROVHeavy e Torpedo) (R6, risco dos construtores)
  - Verificação: `smoke_results/resumo.csv` → os mesmos ids `ok` de antes; `info` com `reward_terms` e `termination_reason`; 0 processos do simulador no fim
- [ ] T12 — ⏱ (depois da fila do notebook) Políticas fixas com o simulador, `v0` contra `v1`: BlueBoatTrajectoryFollower-v0 parado × `--follow`; DjiMatriceHover-v0 motores em hover × máximo; piloto `run.py ... +env_kwargs.reward_version=v0 num_train_steps=300` (R1–R4, correção do `env_kwargs`)
  - Verificação: no `v1`, seguir > parado e hover > tombar; no `v0`, o oposto na trajetória (confirma o diagnóstico); o log do piloto mostra `v0` nos ambientes de treino e de avaliação
- [ ] T13 — ⏱ Verificar todos os critérios de aceitação do requirements.md e, com a fila do notebook terminada, fazer o merge de `spec/recompensas` na `testes-ambientes` (R7)
  - Verificação: tabela de critérios preenchida no `log.md`; `git -C biguagym rev-parse HEAD` no checkout principal → commit novo do fork
