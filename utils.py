import os
import contextlib
import subprocess

import pandas as pd


@contextlib.contextmanager
def eval_mode(*models):
    """Temporarily switch ``models`` to eval mode, restoring prior state on exit.

    Works for ``nn.Module`` and for the plain ``MUJEP`` agent (any object with a
    ``train(mode)`` method and a ``training`` flag).
    """
    states = [getattr(m, 'training', False) for m in models]
    for m in models:
        if hasattr(m, 'train'):
            m.train(False)
    try:
        yield
    finally:
        for m, state in zip(models, states):
            if hasattr(m, 'train'):
                m.train(state)


class NullRecorder:
    """No-op video recorder (placeholder for the eval-rollout capture API).

    ``Workspace.evaluate`` calls ``record(env, path)`` / ``stop(env)``; real video
    capture can replace this later without touching the train loop.
    """

    def record(self, env=None, path=None, **kwargs):
        pass

    def stop(self, env=None, **kwargs):
        pass


def gpu():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,nounits,noheader"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Parse the result to get total and free VRAM in MB
        vram_info = [
            int(free) * 100 / int(total) for total, free in 
            (line.split(",") for line in result.stdout.strip().split("\n"))
        ]
        vram_ordered = list(map(lambda idx, pct: (str(idx), pct), range(len(vram_info)), vram_info))
        return sorted(vram_ordered, key= lambda pct: pct[-1])[0][0]
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    

def get_dir(file : str = __file__, replace : str = ''):
    file_name = os.path.basename(file)
    return os.path.abspath(file).replace(file_name, replace)

def make_dir(dir_path, append=None) -> str:
    """Create directory if it does not already exist."""
    path= os.path.join(dir_path, append) if append else os.path.join(dir_path)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path

def store_csv(columns, file_path):
    df = pd.DataFrame(columns=columns).reset_index(drop=True)
    df.to_csv(file_path, index=False)




