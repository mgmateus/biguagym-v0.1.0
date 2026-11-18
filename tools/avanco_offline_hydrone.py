"""Dinâmica do Hydrone (BiguaSim 1.1.0) integrada em Python, sem o motor (spec rotacao-hydrone): avanço no ar.

Uso: python tools/avanco_offline_hydrone.py [abstracao] [cmd separado por vírgulas]   (padrão: cmd_vel_yaw 0.31,0,0,0)
"""
import sys, numpy as np, torch, roma
from biguasim.dynamics.agents import Hydrone

dt = 0.05
abst = sys.argv[1] if len(sys.argv) > 1 else 'cmd_vel_yaw'
cmd = [float(c) for c in sys.argv[2].split(',')] if len(sys.argv) > 2 else [0.31, 0, 0, 0]
params = Hydrone._params.copy(); params['water_level'] = 0.0
m = Hydrone(batch_size=1, device='cpu', control_abstraction=abst, params=params)
m.dt = dt
x = np.array([0., 0., 2.]); v = np.zeros(3); w = np.zeros(3); q = np.array([0., 0., 0., 1.])
for k in range(101):
    dyn = np.zeros(19); dyn[3:6], dyn[6:9], dyn[12:15], dyn[15:19] = v, x, w, q
    a = np.asarray(m.step([dyn.tolist()], [cmd]), dtype=float).ravel()
    v = v + a[:3] * dt; x = x + v * dt; w = w + a[3:] * dt
    q = roma.quat_product(roma.rotvec_to_unitquat(torch.tensor(w * dt)), torch.tensor(q)).numpy(); q /= np.linalg.norm(q)
    if k % 20 == 0:
        rpy = roma.unitquat_to_euler('xyz', torch.tensor(q), degrees=True).numpy()
        print(f"t {k*dt:4.1f}s  pos {np.round(x,2)}  v {np.round(v,2)}  rpy {np.round(rpy,1)}  w {np.round(w,2)}")
