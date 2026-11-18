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
- [x] T5 — ⏱ Lab: `diag_rotacao_hydrone.py goto`, `diag_goto.py` e `testar_goto_lab.sh`; critérios R4 e R5
  - Verificação: tabela de critérios preenchida no log.md
  - Parcial (2026-11-17): R4 ok (guinada ±1,51 rad), smokes ok, 0 órfãos; R5 falha no avanço (0 m a partir do repouso)
    porque o motor descarta acelerações lineares pequenas. Extensão proposta no design.md (aguardando aprovação).
- [x] T6 — Integração linear no `GotoEnv` (`_impor_estado`, `_acc`, `integrar_dinamica`, `AMORTECIMENTO_LINEAR_MOTOR`) (R6)
  - Verificação: `pytest tests` → 169 passed
- [x] T7 — ⏱ Lab: `testar_goto_lab.sh` e `diag_goto.py ... avanco` com a integração linear; critérios R4, R5 e R6
  - Verificação: tabela de critérios preenchida no log.md
  - Parcial (2026-11-17): v/ω medido/previsto = 1,000; subida 1,485 m; avanço 0,509 m em movimento, mas 0 m a partir do
    repouso (corpo dormindo no motor). Ajuste do design proposto no log.md, aguardando aprovação.
- [x] T8 — Integrador com estado próprio no `GotoEnv` (`_v`, `_w`, `_conciliar`, dinâmica recebe o v/ω integrado) (R6)
  - Verificação: `pytest tests` → anteriores + novos passando
- [x] T9 — ⏱ Lab: `diag_goto.py ... avanco`, `testar_goto_lab.sh`; critérios R4, R5 e R6
  - Verificação: tabela de critérios preenchida no log.md
  - Concluída (2026-11-18): avanço a partir do repouso 0,44 m em 5 s; guinada, subida e smokes ok; 0 órfãos. T5 e T7
    fechadas pelo T9 (os critérios que faltavam nelas foram atendidos com o ajuste).
