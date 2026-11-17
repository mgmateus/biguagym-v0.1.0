Status: aprovado

# sensores-goto — Design

## Arquivos afetados
| Arquivo | Mudança |
|---|---|
| `biguagym/config/goto_sensores.json` (novo) | sensores do `v1` (câmeras embarcadas) e do `v2` (LiDAR e sonar) |
| `biguagym/core/goto.py` | `GotoPixelEnv(_PixelObsMixin, GotoEnv)` e `GotoRangeEnv(GotoEnv)` |
| `biguagym/register.py` | `HydroneGoto{Pilares,Dique}-v1/-v2` |
| `tests/test_sensores_goto.py` (novo) | testes sem simulador |

## Solução proposta
**Sensores** (`goto_sensores.json`), sem socket (o Hydrone não documenta sockets de câmera/sonar; um nome inválido derruba o
spawn), presos ao corpo:
- `v1`: `RGBCamera` e `DepthCamera` (`Debug: true`, entrega `depth_map` em metros), 256×256, `location [0.35, 0, 0.05]`,
  `rotation [0, 0, 0]` (frente). Os nomes `RGBCamera`/`DepthCamera` são os que o `_PixelObsMixin` lê.
- `v2`: `RangeFinderSensor` "Lidar" (`LaserCount 160`, `LaserMaxDistance 10`, `LaserAngle 0`, socket `IMUSocket`, como o
  `range.json`) e `ProfilingSonar` "Sonar" (`Azimuth 90`, `Elevation 15`, `RangeMin 0.5`, `RangeMax 20`, `AzimuthBins 20`,
  `RangeBins 100`, `MultiPath false`, ruído do `range.json` sem multipath, `location [0.25, 0, -0.05]`).

**`GotoPixelEnv`**: `_pixel_channels = ['rgb', 'depth']`, `frame_stack 3`, `frame_size (100, 100)`, `include_state True`.
`_build_params` chama `GotoEnv._build_params` (pula o do mixin, que leria o `pixels.json`) e acrescenta os sensores `v1`.
O estado é só a pose de 9 (`_obs_dim = 9`, `_wrap_state` do `GotoEnv` sem ações), que o mixin coloca em `state`.

**`GotoRangeEnv`**:
```python
LIDAR_IDX = [(3 + 6 * j) % 160 for j in range(-10, 10)]     # ±6,75° … ±128,25°, de 13,5° em 13,5° (20 leituras)

def _lidar20(self, raw):   # (160,) → (20,), inválidas → 10 m
def _sonar20(self, raw):   # (RangeBins, AzimuthBins) → por feixe: RangeMin + (argmax + 0,5)·Δr; sem retorno → 20 m
def _wrap_state(self, state):
    dist = self._lidar20(...) if z ≥ água else self._sonar20(...)
    return concat(dist, ações anteriores, [d, heading, heading_z])         # 26
```
O índice 0 do RangeFinder é a frente (doc do BiguaSim: "1 laser → frente"); o sentido de giro (horário ou anti-horário) só
inverte a ordem das 20 leituras, que é simétrica — a conferir no lab com `explorar_mapa.py`.

## Alternativas consideradas
- **Usar `pixels.json`/`range.json`** — descartado: câmera em terceira pessoa, 1280×720, sonar com multipath (lento) e
  RangeFinder de 10 lasers; mudar esses arquivos mudaria os `-v1/-v2` dos outros veículos.
- **`RaycastLidar`** — descartado: marcado como "WIP" no BiguaSim e devolve nuvem de pontos de tamanho variável.
- **Concatenar LiDAR e sonar sempre (40 valores)** — descartado: o Ricardo usa um sensor por meio, com 20 valores.

## Riscos
- Sonar lento (1,4–1,7 s/passo nos `-v2` antigos, com multipath) → sem multipath e 100 × 20 bins; medir passos/s no lab;
  se ainda for lento, reduzir `RangeBins`/usar `ticks_per_capture`.
- Sensores sem socket podem ficar em posição/orientação inesperada → conferir com `explorar_mapa.py` e nos quadros do smoke.
- Memória do buffer do CUPRL com 100×100 (≈ 0,54 MB/transição; 10 000 → ~5,4 GB) → conferir a RAM da máquina de treino.
- Sem retorno do sonar a intensidade pode não ser exatamente 0 (ruído) → limiar pequeno (`SONAR_LIMIAR`), ajustável.

## Plano de verificação
| Requisito | Como verificar |
|---|---|
| R1 | parâmetros do `_build_params` e espaços com simulador falso |
| R2, R5 | `_lidar20`/`_sonar20` com dados sintéticos |
| R3, R4 | `_wrap_state` acima e abaixo da água |
| R6 | `gym.spec` dos ids |
| R1–R4 | ⏱ smokes no lab |
