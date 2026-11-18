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
- [x] T9 — Obstáculos feitos de agentes no `GotoEnv` (design: "Mudança aprovada", 2026-11-18): `goto_dique.json` com
  `agente_obstaculo` e `obstaculos` (coordenadas reais), geometria em cápsulas, agente em lote, posicionamento no reset,
  reimposição a cada tick
  - Verificação: `pytest tests` → anteriores + novos passando
- [x] T10 — `tools/conferir_obstaculos.py` (posicionamento, calibração da origem, fotos, LiDAR, passos/s)
  - Verificação: `python -m py_compile tools/conferir_obstaculos.py` e teste da análise sem simulador
- [ ] T11 — ⏱ Lab: `conferir_obstaculos.py` nos cenários `pilares` e `dique`; smokes `-v0/-v1/-v2`
  - Verificação: tabela no log.md (torpedos no lugar, origem calibrada, fotos, LiDAR, passos/s, 0 órfãos)
