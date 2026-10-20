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
