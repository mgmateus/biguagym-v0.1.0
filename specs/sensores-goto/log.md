# sensores-goto — Log

## 2026-11-17 — Fases 1 a 3
- Pedido do usuário: "verifique nessas mensagens que te mandei se os sensores do v2 precisam ser iguais aos que o Ricardo
  utilizou. então aplique (...) a configuração dos sensores" (tratado como aprovação).
- Resposta à pergunta: as mensagens do coorientador **não exigem** sensores iguais aos do Ricardo; pedem "lidar e sonar",
  a mesma tarefa e "setar os parâmetros". Decisão registrada: reproduzir a configuração do paper do Ricardo
  (arXiv 2209.06332: LiDAR UST-10LX, 20 leituras a cada 13,5° em 270°, 10 m; FLS 90° × 15°, 20 feixes, 20 m; estado de 26).
- Leitura: `sensors.py` da 1.1.0 (`RangeFinderSensor`: lasers distribuídos em 360°, o 1º para a frente; `ProfilingSonar`
  /`ImagingSonar`: `raw` com forma (RangeBins, AzimuthBins); `DepthCamera`: metros, `depth_map` com `Debug`);
  `_PixelObsMixin`/`_RangeObsMixin`; `TESTES.md` (sonar com multipath: 1,4–1,7 s/passo).

## 2026-11-17 — T1 a T5
- T1: `spec/sensores-goto` a partir da `spec/hydrone-goto-dique` (principal e submódulo).
- T2–T4 (um commit no submódulo; mesmo arquivo `core/goto.py`):
  - `config/goto_sensores.json`: `v1` = `RGBCamera` + `DepthCamera` 256×256 presas ao corpo, para a frente (sem socket);
    `v2` = RangeFinder "Lidar" (160 lasers, 10 m) e ProfilingSonar "Sonar" (90° × 15°, 0,5–20 m, 100 × 20 bins, sem multipath).
  - `GotoPixelEnv(_PixelObsMixin, GotoEnv)`: `rgb`/`depth` (9, 100, 100) e `state` = pose de 9; sensores do `goto_sensores.json`
    (não do `pixels.json`).
  - `GotoRangeEnv(GotoEnv)`: 20 leituras do LiDAR (índices 3 + 6j, ±6,75° … ±128,25°) acima da água ou 20 do sonar (bin de
    maior intensidade por feixe; sem retorno → 20 m) abaixo; + 3 ações + [d, heading, heading_z] = 26.
  - `register.py`: `HydroneGoto{Pilares,Dique}-v1/-v2` (60 ids no total).
- Ajuste: `_pixel_channels` virou atributo da classe `GotoPixelEnv` (canais fixos).
- Testes: `tests/test_sensores_goto.py` (12). `pytest tests` → **157 passed**.
- Observação: `smoke_test.py --list/--all` só mostra ids de `core.environments`; `--env HydroneGoto...` funciona (não alterei o
  `smoke_test.py`, que é arquivo de apoio).
- Pendente: T6 (⏱ lab).

## 2026-11-17 — T6 no PC do lab (parcial)
- Smokes de 200 passos: `HydroneGotoPilares-v1` ok (9,6 passos/s; rgb/depth 9×100×100 + state 9) e `-v2` ok (11,8 passos/s;
  26 valores; o sonar sem multipath não deixou o passo lento). 0 processos órfãos. Falta: conferir os quadros das câmeras e as
  leituras perto dos pilares (os pilares aparecem? o LiDAR os vê?) — depende da guinada do Hydrone (ver hydrone-goto-dique).
