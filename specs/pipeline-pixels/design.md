Status: aprovado

# pipeline-pixels — Design

## Arquivos afetados
| Arquivo | Mudança |
|---|---|
| `biguagym/core/base_env.py` | `PixelStack.append`: `cv2.resize` + `transpose(2, 0, 1)` no lugar de `np.resize` |
| `biguagym/core/environments.py` | `_PixelObsMixin`: `DEPTH_MAX_M = 5.0` e `_depth_to_gray()` (escala fixa); espaço da profundidade [0, 255]; `frame_size` padrão (100, 100) nas 6 classes `*PixelEnv` |
| `replay_buffer.py` | `random_crop`: sem recorte quando `output_size >= tamanho da imagem` |
| `config/agent/cuprl.yaml` | `image_size: 100` |
| `tests/test_pipeline_pixels.py` | testes novos (sem simulador) |

## Solução proposta
```python
# base_env.py — PixelStack.append
h, w = self._pre_aug
for k in self._dtype:
    img = np.asarray(raw[k])
    if img.ndim == 2:                       # cinza → 3 canais
        img = np.repeat(img[..., None], 3, axis=-1)
    img = cv2.resize(img[..., :3].astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)  # (H, W, 3)
    img = img.transpose(2, 0, 1)            # (3, H, W)
    if k in ("rgb", "segmentation"):
        img = np.clip(img, 0, 255).astype(np.uint8)
    else:
        img = img.astype(np.float32)
```
O `cv2.resize` recebe `(largura, altura)`. Converter para float32 antes evita o `cv2` recusar float64 ou uint8 com 4
canais. O `import cv2` fica dentro do módulo, porque o `cv2` já é dependência do harness.

```python
# environments.py — _PixelObsMixin
DEPTH_MAX_M = 5.0   # Depth-CUPRL: profundidade normalizada por 5 m (255 = 5 m ou mais)

@classmethod
def _depth_to_gray(cls, depth_map):
    d = np.asarray(depth_map, dtype=np.float32)
    d = np.where(np.isfinite(d), d, cls.DEPTH_MAX_M)
    return np.clip(d, 0.0, cls.DEPTH_MAX_M) * (255.0 / cls.DEPTH_MAX_M)
```
`_wrap_state` passa a usar `_depth_to_gray` e empilha em 3 canais, como hoje. O espaço do canal de profundidade vira
`Box(0, 255, float32)`.

```python
# replay_buffer.py — random_crop
crop_max = img_size - output_size
if crop_max <= 0:          # sem recorte (ex.: 100×100 com image_size 100, como o Depth-CUPRL)
    return imgs
```

## Alternativas consideradas
- **Recortar 84 de 100 (CURL original)** — descartada: o Depth-CUPRL não recorta (o `random_crop` está comentado) e o
  usuário pediu 100×100.
- **Manter o min–max por quadro na profundidade** — descartado: a escala muda a cada quadro; o Dranaju usa escala fixa.
- **Converter a profundidade para uint8** — descartado: o buffer já guarda a profundidade em float32; quantizar não ajuda.

## Riscos
- Muda a observação de todos os `-v1` → registrado no impacto; nenhuma run de pixel está nos resultados atuais.
- Imagem 1280×720 → 100×100 achata a proporção (16:9 → 1:1), como no Dranaju → a câmera do Goto é ajustada na
  `sensores-goto`.
- Memória do buffer do CUPRL: (9, 100, 100) uint8 + float32 por transição ≈ 0,45 MB × 2 (obs e próxima) → com
  `buffer_size: 10000`, ~9 GB → **verificar a RAM antes do treino** (a spec `sensores-goto` ajusta o `buffer_size`).

## Plano de verificação
| Requisito | Como verificar |
|---|---|
| R1 | teste com imagem sintética (metades de cores diferentes) e empilhamento de 3 quadros |
| R2 | teste lendo a assinatura (`inspect.signature`) dos `*PixelEnv` |
| R3 | teste de `_depth_to_gray` com NaN, inf, 0, 2,5 e 10 m |
| R4 | teste do `random_crop` com tamanho igual e menor |
| R5 | leitura do `cuprl.yaml` no teste |
| R1–R3 | ⏱ smoke no lab do `HydroneGotoDique-v1`, comparando `cam_*` e `obs_rgb_*` |
