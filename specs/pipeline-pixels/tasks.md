Status: aprovado

# pipeline-pixels — Tarefas

Só a T6 usa o simulador (no PC do lab, depois da `hydrone-goto-dique`).

- [x] T1 — Branch `spec/pipeline-pixels` a partir da `spec/colapso-blueboat` (repositório principal e submódulo, worktree `.claude/worktrees/goto`)
  - Verificação: `git branch --show-current` e `git -C biguagym branch --show-current` → `spec/pipeline-pixels`
- [x] T2 — `PixelStack.append` com `cv2.resize` + `transpose` (R1)
  - Verificação: `pytest tests/test_pipeline_pixels.py -k stack` → passa
- [x] T3 — Profundidade em escala fixa de 5 m e `frame_size` padrão 100×100 (R2, R3)
  - Verificação: `pytest tests/test_pipeline_pixels.py -k "depth or frame"` → passa
- [x] T4 — `random_crop` sem recorte com tamanho igual; `image_size: 100` no CUPRL (R4, R5)
  - Verificação: `pytest tests/test_pipeline_pixels.py -k "crop or cuprl"` → passa
- [x] T5 — Suíte inteira sem regressão
  - Verificação: `pytest tests` → 93 anteriores + novos passando
- [ ] T6 — ⏱ Smoke de pixel no lab e critérios de aceitação
  - Verificação: tabela de critérios preenchida no log.md
