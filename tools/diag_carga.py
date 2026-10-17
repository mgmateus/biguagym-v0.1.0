"""Diagnóstico: quanto tempo o simulador leva para sinalizar que carregou, quando iniciado pelo biguasim.

O biguasim espera só 30 s pelo semáforo de carga (environments.__linux_start_process__) e manda a saída do Unreal
para /dev/null. Aqui, só dentro deste processo (nada é alterado no biguasim instalado):
  - a espera pelo semáforo vira ESPERA_S (padrão 300 s) e o tempo real é impresso;
  - biguasim.make roda com verbose=True (a saída do Unreal aparece junto).
Depois faz reset + 20 passos e fecha. Um alarme encerra tudo em ESPERA_S + 120 s (o atexit do biguasim fecha o simulador).

Uso: python tools/diag_carga.py [env_id=DjiMatriceLand-v0] > ~/diag_carga.log 2>&1; grep DIAG ~/diag_carga.log
"""
import os
import signal
import sys
import time
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'biguagym'))
ESPERA_S = int(os.environ.get('ESPERA_S', '300'))
env_id = sys.argv[1] if len(sys.argv) > 1 else 'DjiMatriceLand-v0'


def diag(msg):
    print(f'DIAG {time.strftime("%H:%M:%S")} {msg}', flush=True)


def alarme(*_):
    diag(f'ALARME: passou de {ESPERA_S + 120} s; saindo (o atexit fecha o simulador)')
    sys.exit(3)


signal.signal(signal.SIGALRM, alarme)
signal.alarm(ESPERA_S + 120)

import posix_ipc  # noqa: E402
import biguasim  # noqa: E402
import biguasim.environments as be  # noqa: E402


class _Semaforo:
    def __init__(self, *a, **k):
        self._s = posix_ipc.Semaphore(*a, **k)

    def acquire(self, timeout=None):
        t0 = time.time()
        diag(f'esperando o semáforo de carga (até {ESPERA_S} s; o biguasim espera {timeout} s)')
        try:
            self._s.acquire(ESPERA_S)
        except posix_ipc.BusyError:
            diag(f'semáforo NÃO liberado em {time.time() - t0:.1f} s')
            raise
        diag(f'semáforo liberado em {time.time() - t0:.1f} s')

    def __getattr__(self, nome):
        return getattr(self._s, nome)


# O biguasim faz `import posix_ipc` dentro de __linux_start_process__: troca o módulo em sys.modules, mas só o
# semáforo de carga (HOLODECK_LOADING_SEM...) é envolvido; os semáforos de cada passo continuam os originais.
modulo = types.ModuleType('posix_ipc')
modulo.__dict__.update({k: getattr(posix_ipc, k) for k in dir(posix_ipc) if not k.startswith('__')})
modulo.Semaphore = lambda nome, *a, **k: (_Semaforo(nome, *a, **k) if 'LOADING' in str(nome)
                                          else posix_ipc.Semaphore(nome, *a, **k))
sys.modules['posix_ipc'] = modulo
be.posix_ipc = modulo

_make = biguasim.make
biguasim.make = lambda *a, **k: _make(*a, **{**k, 'verbose': True})

import gymnasium as gym  # noqa: E402
import register  # noqa: E402,F401

diag(f'gym.make({env_id})')
t0 = time.time()
env = gym.make(env_id)
diag(f'gym.make ok em {time.time() - t0:.1f} s')
t0 = time.time()
env.reset(seed=0)
diag(f'reset ok em {time.time() - t0:.1f} s')
t0 = time.time()
for _ in range(20):
    env.step(env.action_space.sample())
diag(f'20 passos em {time.time() - t0:.1f} s')
env.close()
diag('fim ok')
