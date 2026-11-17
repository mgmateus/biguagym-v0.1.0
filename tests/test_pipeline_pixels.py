"""Spec pipeline-pixels: redimensionamento das imagens, profundidade em escala fixa e recorte do CUPRL (sem simulador)."""
import inspect
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(AQUI)
sys.path.insert(0, REPO)

import core.environments as E  # noqa: E402
from core.base_env import PixelStack  # noqa: E402
from replay_buffer import random_crop  # noqa: E402

VERMELHO, AZUL = (255, 0, 0), (0, 0, 255)


def imagem_metades(h=720, w=1280):
    """(H, W, 3) uint8: metade esquerda vermelha, metade direita azul."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 2] = VERMELHO
    img[:, w // 2:] = AZUL
    return img


# --- R1: imagem inteira, redimensionada e transposta ----------------------------------------------------------
def test_stack_rgb_redimensiona_imagem_inteira():
    ps = PixelStack(['rgb'], [100, 100], 3)
    ps.append((imagem_metades(), None, None, None), is_reset=True)
    rgb = ps.built_stack()['rgb']
    assert rgb.shape == (9, 100, 100) and rgb.dtype == np.uint8
    q = rgb[:3]
    assert np.all(q[:, :, :50] == np.array(VERMELHO, dtype=np.uint8)[:, None, None])
    assert np.all(q[:, :, 50:] == np.array(AZUL, dtype=np.uint8)[:, None, None])


def test_stack_rgba_descarta_alfa_e_aceita_cinza():
    rgba = np.concatenate([imagem_metades(72, 128), np.full((72, 128, 1), 7, np.uint8)], axis=-1)
    ps = PixelStack(['rgb', 'depth'], [100, 100], 1)
    ps.append((rgba, np.full((72, 128), 127.5, np.float32), None, None), is_reset=True)
    st = ps.built_stack()
    assert st['rgb'].shape == (3, 100, 100) and st['rgb'][0, 0, 0] == 255
    assert st['depth'].shape == (3, 100, 100) and st['depth'].dtype == np.float32
    assert np.allclose(st['depth'], 127.5)


def test_stack_empilha_quadros_na_ordem_e_reinicia():
    ps = PixelStack(['rgb'], [100, 100], 3)
    cores = [np.full((50, 80, 3), c, np.uint8) for c in (10, 20, 30)]
    ps.append((cores[0], None, None, None), is_reset=True)
    assert np.all(ps.built_stack()['rgb'] == 10)              # 1º quadro replicado nos 3
    ps.append((cores[1], None, None, None), is_reset=False)
    ps.append((cores[2], None, None, None), is_reset=False)
    st = ps.built_stack()['rgb']
    assert [int(st[3 * i, 0, 0]) for i in range(3)] == [10, 20, 30]
    ps.append((cores[2], None, None, None), is_reset=True)
    assert np.all(ps.built_stack()['rgb'] == 30)


# --- R2: 100×100 por padrão ---------------------------------------------------------------------------------
@pytest.mark.parametrize('cls', [c for c in vars(E).values()
                                 if inspect.isclass(c) and c.__name__.endswith('PixelEnv')])
def test_frame_size_padrao_100(cls):
    assert inspect.signature(cls.__init__).parameters['frame_size'].default == (100, 100)


# --- R3: profundidade em escala fixa de 5 m ---------------------------------------------------------------------
def test_depth_escala_fixa_5m():
    d = np.array([np.nan, np.inf, 0.0, 2.5, 10.0], dtype=np.float32)
    assert np.allclose(E._PixelObsMixin._depth_to_gray(d), [255, 255, 0, 127.5, 255])


def test_depth_nao_depende_do_quadro():
    a = E._PixelObsMixin._depth_to_gray(np.array([1.0, 2.0]))
    b = E._PixelObsMixin._depth_to_gray(np.array([1.0, 4.0]))
    assert a[0] == b[0] == pytest.approx(51.0)


# --- R4/R5: recorte do CUPRL ------------------------------------------------------------------------------------
def test_crop_tamanho_igual_devolve_imagem():
    x = np.random.rand(4, 9, 100, 100).astype(np.float32)
    assert random_crop(x, 100) is x


def test_crop_menor_continua_recortando():
    x = np.random.rand(4, 9, 100, 100).astype(np.float32)
    assert random_crop(x, 84).shape == (4, 9, 84, 84)


def test_cuprl_image_size_100():
    with open(os.path.join(REPO, 'config', 'agent', 'cuprl.yaml')) as f:
        linhas = [ln for ln in f if ln.startswith('image_size:')]
    assert linhas and linhas[0].split()[1] == '100'


@pytest.mark.parametrize('lado,camadas', [(100, 4), (84, 4), (64, 4), (84, 2), (84, 6)])
def test_encoder_cuprl_aceita_o_tamanho(lado, camadas):
    import torch
    from src.agents.cuprl import PixelEncoder
    enc = PixelEncoder((9, lado, lado), feature_dim=50, num_layers=camadas, num_filters=32, output_logits=False)
    assert enc(torch.zeros(2, 9, lado, lado)).shape == (2, 50)
