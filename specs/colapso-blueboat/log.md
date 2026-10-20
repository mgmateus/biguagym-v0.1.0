# colapso-blueboat — Log

## 2026-10-20 — Fase 1: requisitos (rascunho)
- Pedido do usuário: "escreve a spec do colapso do BlueBoatNav" (`/spec-requisitos colapso-blueboat Corrigir o colapso do TD3 no BlueBoatNav-v0`).
- Branch `spec/colapso-blueboat` a partir da `testes-ambientes` (`aafb960`), worktree `.claude/worktrees/colapso-blueboat`.
- Leitura (sem alterar código): `HoverEnv._reward`/`_step`/`_init_spaces`, `NavEnv._build_params` (`biguagym/core/environments.py`),
  `src/agents/td3.py`, `src/agents/runner.py` (truncamento não é terminal), `config/agent/td3.yaml`, registros do TESTES.md
  (linha de base 100k, `diag_politica.py`, piloto T11 da `ajuste-ambientes`).
- Ponto novo em relação ao diagnóstico anterior: o BlueBoatTrajectoryFollower aprende com o mesmo TD3 e os mesmos motores,
  então a causa não é só o TD3; os requisitos começam por um diagnóstico da ordem das recompensas (R1, R2).
- Arquivo criado: `specs/colapso-blueboat/requirements.md` (`Status: rascunho`).

## 2026-10-20 — Requisitos aprovados
- Usuário: "aprovado, segue suas sugestões nas perguntas em aberto".
- `requirements.md`: `Status: aprovado`; seção "Perguntas em aberto" trocada por "Decisões (2026-10-20)" (ambiente primeiro,
  TD3 só se necessário e opcional; sucesso = não colapsar e se aproximar; piloto de 15k; BlueBoatNav continua nos 250k).

## 2026-10-20 — Fase 2: design (rascunho)
- `/spec-design colapso-blueboat`. Leitura (sem alterar código): `~/biguasim-treino/src/biguasim/dynamics/{usv,agents}.py`
  (`53ad1f9d`, o biguasim do `venv-biguagym` e do PC do lab; o `~/biguasim` na `sitl-test` não tem as correções do giro),
  `HoverEnv._reset/_reward/_step/_init_spaces`, `NavEnv._build_params`, `src/agents/td3.py`, `tools/diag_politica.py`.
- Achados: empuxo de ~300 N por motor (`k_eta` 3,55e-3); com os motores opostos no limite a guinada equilibra em ~2,9 rad/s
  (= a taxa da política colapsada); alvo sorteado até a borda da área (que é o limite de saída); raio de sucesso de 0,15 m;
  crítico do TD3 recebe a ação crua (±290).
- Proposta: diagnóstico com 4 políticas de referência (`tools/diag_referencia.py`); `env_version="v2"` (padrão novo, igual à
  v1 exceto no BlueBoatNav): alvo a ≥ 3 m da borda, raio de sucesso de 1 m na superfície, ação normalizada em [−1, 1];
  piloto TD3 de 15k; TD3 só numa etapa condicional com nova aprovação.
- Arquivo criado: `specs/colapso-blueboat/design.md` (`Status: rascunho`).

## 2026-10-20 — Design aprovado
- Usuário: "aprovado, pode seguir para as tarefas". `design.md`: `Status: aprovado`.

## 2026-10-20 — Fase 3: tarefas (rascunho)
- `/spec-tarefas colapso-blueboat`: `specs/colapso-blueboat/tasks.md` criado (`Status: rascunho`), T1–T14; T3, T12 e T13 com ⏱ (T13 = piloto de 15k, pede autorização). Aviso: não fazer `git pull` no PC do lab até os 250k terminarem.

## 2026-10-20 — Tarefas aprovadas; execução T1–T12
- Usuário: "aprovado, pode fazer da T1 à T12". `tasks.md`: `Status: aprovado`.

### T1 — branches
- `git submodule update --init biguagym` no worktree (`ff452dc`); `git -C biguagym checkout -b spec/colapso-blueboat`.
- Verificação: as duas branches em `spec/colapso-blueboat`; submódulo em `ff452dc`. ✅

### T2 — `tools/diag_referencia.py`
- Novo script: 4 políticas (parado, girar = [máx, mín], aleatória, controlador "aponta e acelera"); `u.rng` refeito com a
  semente `1000 + episódio` antes de cada reset (o `reset(seed=)` não reinicia o rng do alvo), então as 4 veem os mesmos alvos;
  converte rad/s para [−1, 1] quando o espaço de ação é normalizado (v2). Função `controlador` pura, testável.
- Novo `tests/test_colapso_blueboat.py` (4 testes do controlador: alvo à frente, à esquerda → boreste > bombordo, atrás → gira
  sem avançar, limites).
- Verificação: `py_compile` ok; `pytest tests/test_colapso_blueboat.py` → 4 passed. ✅

### T4–T8 — `env_version="v2"` e testes (submódulo `9558348`)
- `biguagym/core/environments.py`:
  - validação aceita `v0`/`v1`/`v2`; padrão `"v2"` nos 13 construtores; as checagens `== "v1"` (spawn subaquático,
    alvo na observação, alvo do barco na superfície) viraram `!= "v0"`, então a v2 herda toda a geometria da v1;
  - `_boat_nav_v2()`: v2, domínio superfície e `_HAS_TARGET` (falso na Trajectory) → só o BlueBoatNav (v0/v1/v2 de id);
  - T5: `TARGET_MARGIN_SURFACE = 3.0`; no `HoverEnv._reset` o alvo do BlueBoatNav v2 é sorteado em ±7 m (x, y) do spawn,
    com uma única chamada `rng.uniform` (sequência de sorteios dos outros ambientes inalterada);
  - T6: `SUCCESS_RADIUS = 0.15`, `SUCCESS_RADIUS_SURFACE = 1.0`; `HoverEnv._reward` usa 1 m no BlueBoatNav v2;
  - T7: `_init_spaces` guarda `_motor_lo`/`_motor_hi` e, no BlueBoatNav v2, `Box(-1, 1, (2,))`; `_to_motor_speeds`
    (0 → 0, +1 → 288,08, −1 → −295,75, satura fora do Box) chamado no `HoverEnv._step` antes do simulador.
- `tests/test_colapso_blueboat.py`: +20 testes (versão padrão/inválida; `_boat_nav_v2` só no BlueBoatNav; v2 = v1 em limites,
  spawn, inclinação, observação e sequência de alvos de drone/ROV; margem do alvo; raio; espaço de ação; conversão; `_step`
  envia rad/s ao simulador na v2 e a ação crua na v1).
- `tests/test_ajuste_ambientes.py`: `test_versao_em_todos_os_construtores` passa a esperar o padrão `'v2'` (motivo: padrão novo
  desta spec; previsto no design).
- Verificação: `pytest tests/` → **90 passed** (66 de antes + 24 novos); `grep -c '== "v1"'` → 0. ✅
- Obs.: as edições foram feitas com a T3 já rodando; o módulo já estava importado (simulador aberto), então a T3 usa o código v1.
