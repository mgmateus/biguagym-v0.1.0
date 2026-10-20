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
