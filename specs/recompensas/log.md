# recompensas — Log de execução

## 2026-10-06 — T1: branches
- Usuário: "aprovado, faça da T1 à T10 de uma vez" → `tasks.md` em `Status: aprovado`.
- `git submodule update --init` no worktree (submódulo do fork `ttszin/biguagym` em `32698e5`) e
  `git -C biguagym checkout -b spec/recompensas`.
- Verificação: `git branch --show-current` = `spec/recompensas`; `git -C biguagym branch --show-current` =
  `spec/recompensas`; checkout da fila (`~/biguagym-v0.1.0/biguagym`) continua em `32698e5`. ✅

## 2026-10-06 — T2: referência da recompensa original
- Novos: `tests/recompensas_util.py` (ambiente sem simulador via `object.__new__` + `FakeSim`; 31 casos fixos de
  Hover/Nav/Land/Dock/Trajectory) e `tests/gerar_referencia_v0.py`, que grava `tests/dados/recompensa_v0.json`.
- Rodado no código original (`32698e5`): `cd tests && python gerar_referencia_v0.py` → "31 casos, 637 passos", sem NaN.
  Duas execuções deram o mesmo arquivo. ✅
- Correção no próprio teste: na primeira versão, o caso da Trajectory usava os limites ±10 m do Hover e terminava "fora
  da área" no passo 51. Agora os limites vêm da trajetória (margem de 5 m, como no `TrajectoryEnv.__init__`).
- Números do v0 que confirmam o diagnóstico da Trajectory: `traj_parado` +2,5 por passo (125 em 50 passos);
  `traj_avanca` (percurso completo) 755 em 297 passos. Ficar parado os 600 passos renderia ~1500.
- **Achado (bug do código original):** em `HoverEnv._step`, `LandEnv._step` e `DockEnv._step`, o `terminated` é
  calculado antes de `self._reward()`, que é quem atualiza `_on_target`.
  - Por isso o sucesso só termina o episódio **um passo depois** de atingir o alvo: nos casos `*_sucesso`, o passo no
    alvo sai com `terminated=False`.
  - No Hover, o bônus `3·|r|` também cai no passo seguinte. A condição usa o `_on_target` antigo, e o passo seguinte
    termina e recebe o bônus mesmo que o veículo tenha saído do alvo.
  - O `v0` precisa reproduzir isso (R5). O design não previa essa correção no `v1`: ver "Emenda" no `design.md`.

## 2026-10-06 — T3: parâmetro `reward_version`
- `biguagym/core/environments.py`:
  - `reward_version: str = "v1"` no fim da assinatura dos **13 construtores** (o `HoverEnv` e 12 subclasses; o design
    dizia "13 subclasses", mas são 13 construtores no total) e repassado no `super().__init__(...)`;
  - o `HoverEnv` valida o valor (`ValueError` se não for `v0`/`v1`) e o guarda em `self._reward_version`.
  - A edição foi feita com um script restrito a cada construtor. O diff tem só o repasse e a validação.
- Novos: `tests/test_recompensas.py` e `tests/conftest.py` (path de `tests/` e `biguagym/`).
- Verificação: `python -m pytest tests/ -q` → **3 passed**:
  - `test_versao_em_todos_os_construtores` (13 classes, padrão `v1`);
  - `test_versao_invalida` (`ValueError`);
  - `test_v0_identico_ao_original` (31 casos iguais à referência; o comportamento ainda não mudou). ✅
- Avisos: 758 `DeprecationWarning` do `np.cross` com vetores 2D em `TrajectoryEnv._frenet_errors` (código original).
  Sem efeito.
- Commit do submódulo local; o push para o fork é a T8.

## 2026-10-06 — T9: `env_kwargs` chega ao ambiente (harness)
- `run.py` (`Experiment.train`): `gym.make(cfg.env.name, **OmegaConf.to_container(cfg.env.kwargs, resolve=True))`.
- `workspace.py`: `import OmegaConf`; `self.eval_env_kwargs` em `__init__` (os mesmos kwargs do treino) e
  `gym.make(self.eval_env, render_mode="rgb_array", **self.eval_env_kwargs)` em `_build_eval_env`.
- Antes, todo `env_kwargs` era ignorado, inclusive os padrões do CUPRL em `_resolve_env` (rgb+depth, `include_state`,
  100×100).
- Novo `tests/test_env_kwargs.py` (monkeypatch do `gym.make`, sem simulador):
  - treino recebe `{'reward_version': 'v0'}`;
  - avaliação recebe `render_mode` + `{'reward_version': 'v0', 'frame_size': [100, 100]}`;
  - sem `env_kwargs` → `{}`.
- Verificação: `python -m pytest tests/ -q -p no:warnings` → **6 passed**. ✅
- Efeito colateral esperado (risco do design): os v1 com CUPRL passam a receber depth+state em 100×100.

## 2026-10-06 — T10: cluster com a recompensa nova
- `treinos/cluster/runs.csv`: os 8 seeds 0 do notebook voltaram para o bloco do seed 0 (**64 → 72**: 24 ambientes ×
  3 seeds, 24 por seed, sem duplicatas). A fila do notebook roda com a recompensa original (`v0`) e vira linha de base.
- `treinos/cluster/LEIAME.md`:
  - nova seção "Recompensa" (o cluster usa `v1`; o notebook é `v0`; os 8 seeds 0 voltaram; confira o
    `reward_version` no checkout antes de iniciar);
  - o passo 3 virou "(Não se aplica)";
  - a ressalva sobre a recompensa foi atualizada.
- `fila_cluster.sh` e `enviar_do_notebook.sh` sem mudança: a espera por curvas externas só age quando o seed anterior não
  está na lista, o que não acontece mais.
- Verificação: a fila com `run.py` falso sobre os 72 runs (`WORKERS=6`, tempos encurtados numa cópia do script) →
  `exit 0`, 72 inícios, 72 `.ok`, 0 exits ≠ 0, 0 linhas "esperando"/"NÃO rodado"/"bloqueados". ✅

## 2026-10-06 — Emenda aprovada; T4: Hover/Nav
- Usuário: "aprovado, pode seguir com as T4 a T8" → `design.md` em `Status: aprovado` (com a emenda).
- `HoverEnv` (o `NavEnv` herda):
  - `_reward` guarda `_last_terms` (`norm`, `smooth`, `stable`, `spin`), sem mudar o valor devolvido;
  - novas constantes `TERM_PENALTY = -10`, `SUCCESS_BONUS = 10`;
  - novos `_termination_reason(success, failures, truncated)` e `_terminal_reward(reason)` (0 no `v0` e em
    timeout/None);
  - `_step`:
    - `v0`: reproduz a ordem original (o término usa o `_on_target` antigo, e o bônus `3·|r|` vem atrasado);
    - `v1`: `_reward()` primeiro, e o sucesso termina e recebe +10 no próprio passo (emenda); tilt/out_of_bounds −10;
    - `info` com `termination_reason` e `reward_terms` (inclui `terminal`).
- Verificação: `pytest tests/ -k "hover or nav or v0 or versao"` → **15 passed**. Inclui:
  - sucesso no próprio passo com +10;
  - +10 também com shaping negativo (alvo atingido inclinado);
  - −10 por tilt e por out_of_bounds;
  - timeout sem penalidade;
  - tombar no passo 2 rende menos que 50 passos parado (com e sem γ = 0,99);
  - os 31 casos `v0` idênticos à referência. ✅

## 2026-10-06 — T5: Land/Dock
- `LandEnv`:
  - `SUCCESS_BONUS = 20` (o `DockEnv` herda);
  - `_reward` guarda `_last_terms` (com `impact` e `drift`);
  - novo `_land_like_reward(failures, hard_key, truncated)`, usado por `LandEnv._step` e `DockEnv._step`:
    - `v0`: ordem original (término com o `_on_target` anterior; `3·|r|` com o novo; dura → −5 fixo);
    - `v1`: sucesso termina no próprio passo com +20; dura, tilt e out_of_bounds somam −10 ao shaping;
  - `info` com `termination_reason` e `reward_terms`.
- Ajuste durante a tarefa: no `v0`, o `termination_reason` "success" usa o `_on_target` **anterior** (o que de fato
  termina o episódio no original), como no Hover. Assim, o motivo bate com o `terminated`.
- `LandCoopPixelEnv._step` não foi alterado (fora de escopo). Ele herda só o `_last_terms` do `LandEnv._reward`, sem
  efeito no valor. Para editar só o `LandEnv`, foi usada a 1ª ocorrência do bloco (antes de `class DockEnv`).
- Verificação: `pytest tests/ -q -p no:warnings` → **30 passed**. Inclui:
  - sucesso no próprio passo com +20;
  - tilt, out_of_bounds e pouso/docagem dura → shaping − 10;
  - tombar e pousar duro com o mesmo terminal (−10);
  - tombar rende menos que ficar parado;
  - `v0` idêntico. ✅

## 2026-10-06 — T6: Trajectory
- `TrajectoryEnv`:
  - `_reward`:
    - `v0` = `r_cte + r_align` todo passo (original);
    - `v1` = `(r_cte + r_align)·adv`, com `adv = max(_wp_idx − _best_wp, 0)` e `_best_wp` = máximo atingido;
    - guarda `_last_terms` (`cte`, `align`, `track`, `prog`, `stable`, `smooth`);
  - `_reset` zera `_best_wp`. O `_reset` do mixin de pixels chama `super()._reset()`, então vale para os v1;
  - `_step`: `BONUS_END` mantido (+10, nas duas versões); em `v1`, tilt/out_of_bounds somam −10;
    `termination_reason` ∈ {success, tilt, out_of_bounds, strayed, timeout, None}; `reward_terms` com `terminal`.
- Testes (2 ajustes nos próprios testes, sem mudar o código):
  - na queda, o auxiliar `_shaping` somava `cte` + `align` + `track` (dupla contagem) → o teste agora confere
    `terminal == −10` e que a recompensa é menor que no `v0`;
  - em ir e voltar, o `track` fica 0 depois da 1ª passagem, como no design. Mas o `r_prog` original
    (`W_PROG·Δprogresso`, que conta a partir do `_prev_progress`) volta a pagar ~0,01 por waypoint na 2ª ida. O design
    não muda esse termo, e ele é ~250× menor que o `track` da 1ª passagem: ir e voltar não compensa. O teste confere
    exatamente isso (ganho da volta + 2ª ida < 5% da 1ª ida).
- Verificação: `pytest tests/ -q -p no:warnings` → **35 passed**. Inclui:
  - parado: soma ≤ 0 e `track` = 0;
  - completo: termina com `success` e +10 de `BONUS_END`, soma > 0 e maior que parado e que ir e voltar;
  - no `v0`, ficar parado 600 passos > completar (confirma o diagnóstico);
  - queda e saída da área −10. ✅

## 2026-10-06 — T7: `v0` idêntico ao original
- `test_v0_identico_ao_original` compara os 31 casos (637 passos) com `reward_version="v0"` contra
  `tests/dados/recompensa_v0.json`, gerado na T2 com o código original (`32698e5`).
- Recompensa com tolerância 1e-9; `terminated`/`truncated` exatos.
- Verificação: `pytest tests/ -q -p no:warnings` → **35 passed** (suíte completa, depois das T4–T6). ✅

## 2026-10-06 — T8: push no fork e ponteiro do submódulo
- Submódulo: 4 commits sobre `32698e5` (`09b4fcf` T3, `c9eb818` T4, `cbd3f9f` T5, `fcf4358` T6). Diff total:
  `core/environments.py`, +145/−58.
- `git -C biguagym push git@github.com:ttszin/biguagym.git spec/recompensas`. O remoto do submódulo é HTTPS, sem
  credencial; o push foi por SSH, como os anteriores no fork.
- Verificação: `git ls-remote https://github.com/ttszin/biguagym.git spec/recompensas` = `fcf4358…` = HEAD do
  submódulo = ponteiro na branch `spec/recompensas` do repositório principal. ✅
- Checagens extras:
  - `python smoke_test.py --list` no worktree (código novo, sem simulador) → 54 ids registrados;
  - R7: o checkout da fila continua no `32698e5`, e o `DjiMatriceLand-v0_s0` segue avançando (passo 12.622).
- Próximas: T11–T13 (⏱, com simulador), depois que a fila do notebook terminar.
