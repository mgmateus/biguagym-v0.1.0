Status: aprovado

# colapso-blueboat — Tarefas

T2, T4–T10 não usam o simulador. T3, T11 e T12 usam o simulador do notebook por poucos minutos. A T13 é o piloto
TD3 de 15k (~25 min) e **pede autorização antes de rodar**. Nada aqui usa o PC do lab, que está com os 250k.

Atenção: depois do merge (T14), **não fazer `git pull` no PC do lab até a fila dos 250k terminar**. Cada run lê o
código do checkout ao começar, então o BlueBoatNav (7º da fila) passaria a rodar com o padrão novo `v2`.

- [x] T1 — Branch `spec/colapso-blueboat` no repositório principal (já existe, worktree `.claude/worktrees/colapso-blueboat`); no worktree, `git submodule update --init` (`ff452dc`) e, no submódulo, branch `spec/colapso-blueboat` a partir de `ff452dc`
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/colapso-blueboat`; `git -C biguagym rev-parse --short HEAD` → `ff452dc`
- [x] T2 — `tools/diag_referencia.py <env_id> [episodios=6] [env_version=v1]` (novo): políticas parado, girar, aleatória e controlador "aponta e acelera"; mesmas sementes de alvo para as 4; saída `REF {json}` com retorno médio, motivos, passos medianos e distância inicial/final média (R1)
  - Verificação: `python -m py_compile tools/diag_referencia.py` → sem erro; teste sem simulador do controlador (alvo à frente → os dois motores para frente; alvo à esquerda → motor de boreste > bombordo) → passa
- [ ] T3 — ⏱ (~8 min) Diagnóstico da recompensa de hoje: `python tools/diag_referencia.py BlueBoatNav-v0 6 v1` (R1)
  - Verificação: tabela das 4 políticas no `log.md`; sinal do giro do controlador conferido no 1º episódio; 0 simuladores no fim. Se o controlador não superar parado e girar, registrar e seguir (a T5/T6 atacam isso; a T12 confere)
- [x] T4 — `env_version="v2"` (padrão novo): validação aceita `v0`/`v1`/`v2`; as 5 checagens `== "v1"` viram `!= "v0"`; padrão `"v2"` no `HoverEnv` e nos 12 repasses; método `_boat_nav_v2()` (R5)
  - Verificação: `pytest tests/test_colapso_blueboat.py -k versao` → `"v3"` dá `ValueError`; v2 = v1 em limites, alvo, espaços e recompensa em Hover/Land/Dock/Nav (drone, ROV) e BlueBoatTrajectory; `_boat_nav_v2()` verdadeiro só no BlueBoatNav v2
- [x] T5 — Alvo do BlueBoatNav v2 a ≥ 3 m da borda (`TARGET_MARGIN_SURFACE = 3.0`, `HoverEnv._reset`) (R2)
  - Verificação: `pytest tests/test_colapso_blueboat.py -k margem` → 1000 sorteios com x, y em ±7 m do spawn e z = 0; v1 continua em ±10 m
- [x] T6 — Raio de sucesso de superfície de 1 m no BlueBoatNav v2 (`SUCCESS_RADIUS`, `_on_target` em `HoverEnv._reward`) (R2)
  - Verificação: `pytest tests/test_colapso_blueboat.py -k raio` → a 0,9 m do alvo: sucesso na v2, não na v1; drone/ROV v2 continuam em 0,15 m
- [x] T7 — Ação normalizada no BlueBoatNav v2: `action_space = Box(−1, 1, (2,))` em `_init_spaces` e `_to_motor_speeds` no `HoverEnv._step` (0 → 0; ±1 → limites reais) (R3)
  - Verificação: `pytest tests/test_colapso_blueboat.py -k acao` → `[1, −1]` → `[288,08; −295,75]`, `[0, 0]` → `[0, 0]`, `[0,5; −0,5]` → `[144,04; −147,875]`; espaço de ação do v1 e dos outros ambientes igual ao de hoje
- [x] T8 — Regressão sem simulador (R5)
  - Verificação: `pytest tests/` → os 66 de hoje + os novos passam; `grep -c '== "v1"' biguagym/core/environments.py` → 0
- [ ] T9 — `tools/diag_politica.py`: argumentos `reward_version` e `env_version` (padrões de hoje: `v0` e `v1`); métricas `frac_dois_motores_saturados` (os dois motores a ≥ 95% do limite) e `dist_ini_fim_media` (média por episódio) (R3, R4)
  - Verificação: `python -m py_compile tools/diag_politica.py` → sem erro; chamada sem os argumentos novos → mesmo comportamento de hoje (leitura do código)
- [ ] T10 — Commit no submódulo, push da `spec/colapso-blueboat` para o fork `ttszin/biguagym`, ponteiro do submódulo no repositório principal; linha no `treinos/cluster/LEIAME.md` sobre `+env_kwargs.env_version=v1` para os runs anteriores à spec
  - Verificação: `git ls-remote https://github.com/ttszin/biguagym.git spec/colapso-blueboat` → mesmo hash do submódulo do worktree
- [ ] T11 — Smoke de 200 passos em BlueBoatNav-v0/v1/v2 e `smoke_test.py --list` (~5 min) (R6)
  - Verificação: 54 ids; 3/3 `ok`; ação `[-1, 1]` no `summary.json`; 0 simuladores no fim
- [ ] T12 — ⏱ (~8 min) `python tools/diag_referencia.py BlueBoatNav-v0 6 v2` (R2)
  - Verificação: retorno(controlador) > retorno(parado) e > retorno(girar); 0 simuladores no fim
- [ ] T13 — ⏱ (~25 min, **pede autorização**) Piloto TD3 de 15k: `python run.py env=BlueBoatNav-v0 agent=td3 num_train_steps=15000 eval_freq=1000000 num_eval_episodes=1 runs=1 agent.learning_starts=1000` (padrão v2) e `python tools/diag_politica.py BlueBoatNav-v0 <actor_last.pt> 600 v1 v2` (R3, R4)
  - Verificação: retorno médio de treino em 5k–15k > em 0–1k; `frac_dois_motores_saturados` < 0,5; distância final média < inicial; comparação com o piloto T11 da `ajuste-ambientes` no `log.md`; 0 simuladores no fim. Se colapsar: parar, atualizar o design (etapa 4) e pedir aprovação
- [ ] T14 — Verificar todos os critérios de aceitação do requirements.md; merge `spec/colapso-blueboat` → `testes-ambientes` e push
  - Verificação: tabela de critérios preenchida no `log.md`; no checkout principal `pytest tests/` passa e `smoke_test.py --list` → 54 ids
