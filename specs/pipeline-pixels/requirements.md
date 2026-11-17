Status: aprovado

> Aprovação: o usuário pediu em 2026-11-17 "Normalize a imagem em 100x100 e resolva este bug da imagem (...) então aplique o
> pipeline-pixels, o hydrone-goto-dique e a configuração dos sensores". O pedido foi tratado como aprovação das três specs,
> com cada fase escrita e registrada (ver `log.md`).

# pipeline-pixels — Requisitos

## Contexto
Etapa 6 do CLAUDE.md. Nos ambientes de pixel (`-v1`), `PixelStack.append` (`biguagym/core/base_env.py:142`) faz
`np.resize(raw[k], (3, H, W))`. O `np.resize` não interpola nem transpõe: pega os primeiros 3·H·W valores da imagem
(H, W, 3) e os repete ou corta. Com câmera de 1280×720 e quadro de 84×84, a rede recebe ~0,8% da imagem, e com os canais
embaralhados.

Além disso:
- a profundidade é normalizada por quadro (min–max) em `_PixelObsMixin._wrap_state` (`biguagym/core/environments.py`),
  então o mesmo cinza significa distâncias diferentes em quadros diferentes;
- o Depth-CUPRL (Dranaju, arXiv 2206.15211, código `dranaju/curl_navigation`) usa imagens 100×100 (`cv2.INTER_AREA`),
  profundidade com NaN → máximo e `×255/5` (5 m = branco) e nenhum recorte (`image_size=100`);
- o `random_crop` do buffer priorizado (`replay_buffer.py:616`) falha quando o recorte tem o tamanho da imagem
  (`np.random.randint(0, 0)` → `ValueError`), então não dá para usar 100×100 sem recorte.

## Objetivo
Entregar à rede a imagem inteira, redimensionada para 100×100 e com a profundidade numa escala fixa como no Depth-CUPRL,
e permitir treinar o CUPRL sem recorte.

## Fora de escopo
- Mudar a câmera (resolução, posição, campo de visão) no `pixels.json`: fica com a spec `sensores-goto`.
- Mudar o CUPRL além do `image_size`.
- Ambientes `-v0`/`-v2` (não usam imagem).

## Requisitos
- **R1** — QUANDO um quadro RGB, de segmentação ou de profundidade entrar no `PixelStack`, O SISTEMA DEVE redimensioná-lo
  com `cv2.resize(..., INTER_AREA)` para o tamanho do quadro e transpor de (H, W, 3) para (3, H, W), preservando a imagem
  inteira e a ordem dos canais.
- **R2** — QUANDO um ambiente de pixel for criado sem `frame_size`, O SISTEMA DEVE usar 100×100.
- **R3** — QUANDO a profundidade chegar do `DepthCamera` (metros), O SISTEMA DEVE trocar NaN/inf pelo máximo (5 m),
  cortar em [0, 5] m e escalar para [0, 255] (`×255/5`), como o Depth-CUPRL, em vez do min–max por quadro.
- **R4** — QUANDO o tamanho do recorte for igual ao da imagem, o `random_crop` DEVE devolver as imagens sem recorte.
- **R5** — QUANDO o CUPRL for usado, O SISTEMA DEVE trabalhar em 100×100 sem recorte (`image_size: 100`).

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1 | `pytest tests/test_pipeline_pixels.py` (imagem sintética 720×1280 metade vermelha / metade azul) | saída (3, 100, 100) com a metade esquerda vermelha e a direita azul; empilhamento (9, 100, 100) |
| R2 | idem (assinatura dos `*PixelEnv`) | `frame_size` padrão = (100, 100) em todas as classes de pixel |
| R3 | idem (mapa com NaN, inf, 0, 2,5 m e 10 m) | 255, 255, 0, 127,5 e 255 |
| R4 | idem | `random_crop(x, 100)` com x de 100×100 devolve x |
| R5 | `grep image_size config/agent/cuprl.yaml` | `image_size: 100` |
| R1–R3 | ⏱ no lab: `python smoke_test.py --env HydroneGotoDique-v1 --steps 100 --frame-every 25` (depois da `hydrone-goto-dique`) | `obs_rgb_*.png` mostra a mesma cena de `cam_*.png`, em 100×100 |
| — | `pytest tests` | os 93 testes anteriores continuam passando |

## Impacto nos experimentos
Muda a observação de **todos** os ambientes `-v1`: as runs antigas de pixel não são comparáveis (recebiam ~0,8% da
imagem). Os ambientes `-v0`/`-v2` e os 250k não mudam.

## Decisões
- 100×100 em todos os ambientes de pixel (pedido do usuário), não só no Hydrone.
- Profundidade em float32 na escala [0, 255] (o Dranaju converte para uint8; aqui fica sem quantizar).
