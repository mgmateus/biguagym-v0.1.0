import os
import sys

# tests/ (recompensas_util) e biguagym/ (pacote core) no path
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))
