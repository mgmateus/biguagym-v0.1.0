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
