# pipeline-pixels — Log

## 2026-11-17 — Fases 1 a 3 (requisitos, design, tarefas)
- Pedido do usuário: "Normalize a imagem em 100x100 e resolva este bug da imagem (...) então aplique o pipeline-pixels, o
  hydrone-goto-dique e a configuração dos sensores". Tratado como aprovação das três specs; as fases foram escritas mesmo
  assim, para registro (`Status: aprovado` com a nota da aprovação).
- Leitura: `PixelStack` (`biguagym/core/base_env.py`), `_PixelObsMixin` (`environments.py`), `random_crop`/
  `PrioritizedReplayBuffer` (`replay_buffer.py`), `config/agent/cuprl.yaml`, `src/agents/{cuprl,runner}.py`; código do
  Dranaju (`dranaju/curl_navigation`: `environment_hydrone_image_depth.py`, `curl_prio_image_depth.py`): 100×100
  `INTER_AREA`, profundidade NaN → máximo e ×255/5, `image_size=100` sem recorte.
- Achado extra: `random_crop` levanta `ValueError` (`randint(0, 0)`) quando o recorte tem o tamanho da imagem.

## 2026-11-17 — T1 a T5
- T1: worktree `.claude/worktrees/goto`, branch `spec/pipeline-pixels` a partir da `spec/colapso-blueboat` (`049f259`);
  submódulo `spec/pipeline-pixels` a partir de `e73d85d`. Motivo da base: é o código que o lab roda e já contém as
  specs ajuste-ambientes, recompensas e colapso-blueboat.
- T2: `PixelStack.append` com `cv2.resize(INTER_AREA)` + `transpose(2, 0, 1)` (submódulo `5991da7`).
- T3: `_PixelObsMixin.DEPTH_MAX_M = 5.0` e `_depth_to_gray` (NaN/inf → 5 m, corte em [0, 5], ×51); espaço da
  profundidade `Box(0, 255)`; `frame_size` padrão (100, 100) nas 6 classes `*PixelEnv` (submódulo `6c995f9`).
- T4: `random_crop` devolve as imagens quando `output_size >= tamanho`; `cuprl.yaml` `image_size: 100`.
- Testes: `tests/test_pipeline_pixels.py` (14). Comando: `~/venv-biguagym/bin/python -m pytest -q tests` →
  **107 passed** (93 anteriores + 14).
- Pendente: T6 (⏱, simulador no lab), depois da `hydrone-goto-dique`.

## 2026-11-17 — Correção achada na sensores-goto: encoder do CUPRL em 100×100
- Problema: `PixelEncoder` (`src/agents/cuprl.py`) usava a tabela `OUT_DIM[4] = 35`, válida só para 84×84; com 100×100 a
  saída convolucional tem 43 de lado e a `nn.Linear` falharia no 1º passo do treino (o Dranaju trocou para 43 à mão no código dele).
- Correção (R5): `out_dim = (lado − 3)//2 + 1 − 2·(camadas − 1)` (84 → 35, 64 → 25, 100 → 43). As tabelas ficaram sem uso.
- Teste novo `test_encoder_cuprl_aceita_o_tamanho` (5 casos). `pytest tests` → 112 passed nesta branch.
