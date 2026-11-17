Status: aprovado

# sensores-goto — Tarefas

T2–T5 não usam o simulador. T6 usa o simulador do PC do lab (depois da exploração do usuário).

- [ ] T1 — Branch `spec/sensores-goto` a partir da `spec/hydrone-goto-dique` (repositório principal e submódulo)
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/sensores-goto`
- [ ] T2 — `config/goto_sensores.json` e `GotoPixelEnv` (R1)
  - Verificação: `pytest tests/test_sensores_goto.py -k v1` → passa
- [ ] T3 — `GotoRangeEnv`: LiDAR 20, sonar 20, troca por meio, leituras inválidas (R2, R3, R5)
  - Verificação: `pytest tests/test_sensores_goto.py -k "lidar or sonar or meio or invalida"` → passa
- [ ] T4 — Observação de 26 e registro dos ids `-v1/-v2` (R4, R6)
  - Verificação: `pytest tests/test_sensores_goto.py -k "v2 or registro"` → passa
- [ ] T5 — Suíte inteira sem regressão
  - Verificação: `pytest tests` → anteriores + novos passando
- [ ] T6 — ⏱ Lab: smokes `HydroneGotoPilares-v1` e `-v2` e critérios de aceitação
  - Verificação: tabela de critérios preenchida no log.md
