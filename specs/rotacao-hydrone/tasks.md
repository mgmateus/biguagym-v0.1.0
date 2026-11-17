Status: aprovado

> Aprovação: pedido do usuário em 2026-11-17 ("Resolva isso do giro"). Ver `log.md`.

# rotacao-hydrone — Tarefas

- [x] T1 — Branch `spec/rotacao-hydrone` a partir da `spec/sensores-goto` (repositório principal e submódulo)
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/rotacao-hydrone`
- [x] T2 — Integração angular no `GotoEnv` (`_instalar_integrador`, `_passo_sim`, `_impor_rotacao`, `integrar_rotacao`) (R1–R3)
  - Verificação: `pytest tests/test_rotacao_hydrone.py` → passa
- [x] T3 — Suíte inteira sem regressão
  - Verificação: `pytest tests` → anteriores + novos passando
- [x] T4 — `diag_goto.py` (direto pela integração, fase de avanço) e modo `goto` do `diag_rotacao_hydrone.py`
  - Verificação: `python -m py_compile tools/diag_goto.py tools/diag_rotacao_hydrone.py` → ok
- [ ] T5 — ⏱ Lab: `diag_rotacao_hydrone.py goto`, `diag_goto.py` e `testar_goto_lab.sh`; critérios R4 e R5
  - Verificação: tabela de critérios preenchida no log.md
