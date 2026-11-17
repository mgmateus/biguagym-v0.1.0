Status: aprovado

# hydrone-goto-dique — Tarefas

T2–T6 não usam o simulador. T7 e T8 usam o simulador do PC do lab por poucos minutos, depois que o usuário terminar de
explorar o mapa (não rodar ao mesmo tempo).

- [x] T1 — Branch `spec/hydrone-goto-dique` a partir da `spec/pipeline-pixels` (repositório principal e submódulo)
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/hydrone-goto-dique`
- [x] T2 — `config/goto_dique.json` e leitura do cenário (R3)
  - Verificação: `pytest tests/test_hydrone_goto.py -k cenario` → passa
- [x] T3 — Conversão da ação para `cmd_vel_yaw` com guinada integrada (R1, R2)
  - Verificação: `pytest tests/test_hydrone_goto.py -k comando` → passa
- [x] T4 — Pilares, sorteio de alvos, colisão e recompensa do Dranaju (R4–R8)
  - Verificação: `pytest tests/test_hydrone_goto.py -k "pilares or alvo or colisao or recompensa or trunca"` → passa
- [x] T5 — Observação `-v0` e registro dos ids (R9, R10)
  - Verificação: `pytest tests/test_hydrone_goto.py -k "obs or registro"` → passa
- [x] T6 — `tools/diag_goto.py` e suíte inteira sem regressão
  - Verificação: `pytest tests` → anteriores + novos passando
- [ ] T7 — ⏱ Lab: `python tools/diag_goto.py HydroneGotoPilares-v0` (guinada com ω constante) e smoke de 200 passos
  - Verificação: guinada ≈ +1,5 rad em 5 s; pilares nos quadros; 0 processos órfãos
- [ ] T8 — ⏱ Cenário real: coordenadas do usuário no JSON (`provisorio: false`) e critérios de aceitação
  - Verificação: tabela de critérios preenchida no log.md
