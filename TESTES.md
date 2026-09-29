# Testes dos ambientes biguagym no BiguaSim

Branch: `testes-ambientes` (repositório principal). Submódulo `biguagym` ainda na `main`, sem alterações.

---

## Etapa 1 — Ambiente de execução (2026-09-28)

### Submódulo `./biguagym`
- `git submodule status` → `a05e14b biguagym (heads/main)`, URL `https://github.com/hydrone-furg/biguagym.git`.
- Conteúdo presente: `register.py`, `__init__.py`, `core/` (`base_env.py`, `environments.py`, `space.py`),
  `config/` (`state.json`, `pixels.json`, `range.json`, `cooperation.json`). Não foi preciso rodar `submodule update`.

### Interpretador Python
- Comando: `which python; python --version`
- Resultado: `/home/teteu/venv-ardupilot/bin/python`, **Python 3.12.3**.
- O `environment.yml` pede um env conda `biguagym-v0.1.0` com **Python 3.10.20**
  (`prefix: /home/matheus/anaconda3/...`, de outra máquina). Não há conda instalado nesta máquina.

### Imports (script `check_imports.py` no scratchpad)
| Módulo | Status | Versão / origem |
|---|---|---|
| biguasim | OK | 1.0.0, instalado editável de `/home/teteu/biguasim/src` |
| gymnasium | OK | 1.2.1 (yml: 1.3.0) |
| torch | OK | 2.7.1+cu126, `cuda.is_available() = True` |
| hydra-core | OK | 1.3.2 (yml: 1.3.3) |
| cv2 | OK | 4.13.0 (não está no yml) |
| scipy | OK | 1.15.2 |
| **dm_env** | **FALTA** | usado em `biguagym/core/base_env.py:41` |
| **skimage** (scikit-image) | **FALTA** | usado em `replay_buffer.py:615` |
| **termcolor** | **FALTA** | usado em `logger.py:22` |

Impacto verificado:
- `python -c "import biguagym.core.base_env"` → `ModuleNotFoundError: No module named 'dm_env'`.
  O `import biguagym.register` funciona (os entry points são strings), então `--list` deve funcionar,
  mas qualquer `gym.make` vai falhar.
- `python -c "import logger"` → `ModuleNotFoundError: No module named 'termcolor'` → `run.py` não roda.

Comparação com o `environment.yml` (pip):
- Faltam 27 pacotes. Os relevantes são **`dm-env==1.6`** (+ a dependência `dm-tree==0.1.10`),
  **`scikit-image==0.25.2`** (+ `lazy-loader`) e **`termcolor==3.3.0`**.
  O resto são as libs CUDA 13 (`nvidia-*-cu13`, `cuda-toolkit`), que não fazem falta porque o torch
  instalado é cu126 e usa as libs `-cu12`, que estão presentes, além de backports que não se aplicam
  ao Python 3.12 (`exceptiongroup`, `tomli`) e dos pacotes auxiliares `charset-normalizer` e `tzdata`.
- Versões diferentes (18): numpy 2.4.4 (yml 2.2.6), pandas 3.0.2 (yml 2.3.3), gymnasium 1.2.1 (yml 1.3.0),
  hydra-core 1.3.2, omegaconf 2.3.0, wrapt 1.15.0 (yml 2.2.1), entre outras. **pandas 3.x e numpy 2.4**
  são saltos grandes e podem quebrar algo em `logger.py`; fica para observar nas próximas etapas.
- Nada foi instalado.

### Mundo do simulador
- `biguasim.packagemanager.installed_packages()` → `['SkyDive', 'Hydrone_test', 'SkyDive', 'Hydrone', 'SkyDive']`.
  O pacote **SkyDive está instalado** (aparece 3 vezes; possivelmente há instalações duplicadas).

### GPU
- `nvidia-smi` → **NVIDIA GeForce RTX 3050 6GB Laptop GPU**, driver 580.178.04, CUDA 13.0.
- VRAM: **6144 MiB total, 490 MiB usada (Xorg + plasmashell), 5316 MiB livre**.
- 6 GB é pouco para um simulador Unreal mais o treino; vários simuladores de avaliação abertos
  (hipótese da Etapa 5) esgotariam a VRAM rápido.

### Problema para a Etapa 2
- **`smoke_test.py` não existe** no repositório nem em nenhum outro lugar do disco
  (`find / -name smoke_test.py`). As Etapas 2 a 4 e 6 dependem dele.
  **Resolvido:** o script foi escrito (ver abaixo).

### Processos do simulador
- `ps aux | grep -i -E "biguasim|holodeck|unreal"` → nenhum processo aberto.

### Venv separado (2026-09-28)
- Decisão do usuário: criar um venv só para o projeto, sem mexer no `venv-ardupilot`.
- `requirements-venv.txt` (novo, na raiz) foi gerado a partir das versões do `environment.yml`, com três ajustes:
  sem as libs CUDA 13 (o torch 2.7.1 usa cu12) e os backports `exceptiongroup`/`tomli`;
  `networkx>=3.5`, porque o `biguasim` exige (o yml tem 3.4.2); e `opencv-python==4.13.0.92`
  adicionado, porque é usado em `base_env.py` e não está no yml.
- O Python 3.10 do yml não serve, porque o `biguasim` exige Python ≥ 3.11. Foi usado o Python 3.12.3 do sistema.
- Comandos:
  ```
  /usr/bin/python3 -m venv /home/teteu/venv-biguagym
  /home/teteu/venv-biguagym/bin/pip install -U pip
  /home/teteu/venv-biguagym/bin/pip install -r requirements-venv.txt
  /home/teteu/venv-biguagym/bin/pip install -e /home/teteu/biguasim --no-deps
  ```
- Resultado: instalação ok e `pip check` sem conflitos. Todos os imports passam (`dm_env` 1.6, `skimage` 0.25.2,
  `termcolor`, gymnasium 1.3.0, hydra 1.3.3, numpy 2.2.6, pandas 2.3.3, torch 2.7.1+cu126 com CUDA).
  `import logger` e `import core.environments` funcionam.
- Para ativar: `source /home/teteu/venv-biguagym/bin/activate`.
- Lock completo: `pip freeze > requirements-lock.txt` (246 linhas, na raiz).

### Instalação do biguasim usada (2026-09-28)
- `pip show biguasim` → **Version 1.0.0**, instalação **editável**:
  `Editable project location: /home/teteu/biguasim` (o `import biguasim` resolve para
  `/home/teteu/biguasim/src/biguasim/__init__.py`).
- Repositório: `https://github.com/hydrone-furg/biguasim.git`, **branch `sitl-test`** (não é a `main`),
  **commit `b0c6685e5dbcddc2aa59491b3c30385600519164`** (2026-09-24, "ardubridge: per-profile gyro yaw flip,
  BlueROV2/BlueBoat dynamics fixes, mt_z toggle"). Linha no lock:
  `-e git+https://github.com/hydrone-furg/biguasim.git@b0c6685e...#egg=biguasim`.
- Estado do working tree:
  - `M src/biguasim.egg-info/PKG-INFO` — **causado por este teste**: o `pip install -e` regenerou os
    metadados às 16:47 (muda só Home-page/Project-URL e a lista de Requires-Dist). O código não mudou.
  - `?? biguasim_docs/packages/SkyDive.zip` — já existia antes; não é deste teste.
- Mundos: `/home/teteu/.local/share/biguasim/1.0.0/worlds/`. Há 5 pacotes, **todos contêm o mundo `Pier-Harbor`**:

  | Pasta | `name` no config.json | Data |
  |---|---|---|
  | `SkyDive` | SkyDive | 2026-08-24 |
  | `SkyDive_test` | Hydrone_test | 2026-08-21 |
  | `SkyDive_broken_biguasim_repack` | SkyDive | 2026-08-21 |
  | `Hydrone` | Hydrone | — |
  | `SkyDive.backup_20260821_045522` | SkyDive | 2026-08-21 |

  - O binário vem de `get_binary_path_for_package("SkyDive")`, e hoje resolve para
    `worlds/SkyDive/Linux/Biguasim/Binaries/Linux/Holodeck` (o mais recente) ✅.
  - **Risco:** `packagemanager._iter_packages()` segue a ordem do `os.listdir` (não é alfabética) e
    devolve o primeiro `name == "SkyDive"`. Há três pastas com esse nome, incluindo uma marcada como
    "broken". A config do mundo (`get_package_config_for_scenario`) busca pelo nome do mundo, que
    existe nas cinco pastas. Se a ordem do diretório mudar (por exemplo, com uma reinstalação), outro
    pacote pode ser carregado sem aviso. Sugestão: mover as cópias backup/broken/test para fora de `worlds/`.

### `smoke_test.py` (novo, na raiz)
- Não existia, então foi escrito para esta validação. Não altera o código dos ambientes.
- Faz `gym.make` como o `run.py`, depois `reset` e N passos com ação aleatória. Mede o tempo por step,
  NaN/inf, `observation_space.contains`, posição inicial e final (`RPYDynamicsSensor[6:9]`) e VRAM.
  Salva frames das câmeras cruas (`cam_<sensor>_*.png`) e, nos ambientes v1, o último frame da pilha
  que a rede recebe (`obs_<canal>_*.png`).
- `hours_per_100k` usa o tempo de parede (steps + resets), sem o tempo gasto salvando PNG.
- Com `--all`, cada ambiente roda num processo filho com timeout, e o script gera `smoke_results/resumo.csv`.
- **Fechamento:** depois de `env.close()`, o script registra se o processo do simulador ainda está vivo
  (`sim_alive_after_env_close`) e então chama `__on_exit__()` do biguasim para não deixar órfão.
  Motivo: em `biguasim/environments.py:997` há `atexit.register(self.__on_exit__)`, que mantém uma
  referência ao ambiente, então o `del self._env` de `BiguaGymEnv.close()` não encerra o simulador
  (evidência preliminar para a Etapa 5).

---

## Etapa 2 — Registro dos ambientes (2026-09-28)
- Comando: `/home/teteu/venv-biguagym/bin/python smoke_test.py --list`
- Resultado: **54 ids** ✅ (20 v0, 20 v1, 14 v2).
- Observação: `register.py` diz que o v2 expõe só Nav e TrajectoryFollower (range/sonar), mas
  `DjiMatriceLand-v2` (linha 201) e `HydroneLand-v2` (linha 275) apontam para `LandCoopPixelEnv`,
  que é pouso cooperativo com pixels. Esses dois não seguem a convenção `-v2` e não devem ter as
  dimensões "+10/+110" esperadas na Etapa 4.
- Processos do simulador depois do teste: nenhum.
- Repetido depois de gerar o `requirements-lock.txt`: continua em **54 ids**, e nenhum processo do simulador ficou aberto.

---

## Decisão sobre a versão do simulador (2026-09-28)
- O usuário cogitou esperar a versão pública do BiguaSim. Ficou decidido: **nada de treino por enquanto**
  (a Etapa 5, que usa `run.py`, fica suspensa), mas os ambientes seguem sendo rodados com o `smoke_test.py`.
  Os problemas no código do `biguagym` valem para qualquer versão do simulador. Velocidade e sensores
  serão medidos de novo quando a versão pública sair.

## Etapa 3 — DjiMatriceLand-v0 (2026-09-28) — ❌ BLOQUEADA
- Comando: `/home/teteu/venv-biguagym/bin/python smoke_test.py --env DjiMatriceLand-v0 --steps 200` (sem viewer)
- Resultado: o simulador abre, mas `gym.make` falha em `_init_spaces`. Traceback completo:
  ```
  Traceback (most recent call last):
    File "/home/teteu/biguagym-v0.1.0/smoke_test.py", line 225, in run_one
      env = gym.make(env_id)
    File ".../gymnasium/envs/registration.py", line 735, in make
      env = env_creator(**env_spec_kwargs)
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/environments.py", line 268, in __init__
      super().__init__(seed, agent_type, control_abstraction, location, rotation, batch_size, observation_type,
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/environments.py", line 83, in __init__
      super().__init__(seed, env_params, obs_params, output_mode, show_viewer, None, render_mode)
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/base_env.py", line 516, in __init__
      self._init_spaces()
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/environments.py", line 165, in _init_spaces
      low=float(self._env.action_space.get_low()[0]),
    File "/home/teteu/biguasim/src/biguasim/environments.py", line 268, in action_space
      return self._agent.action_space
    File "/home/teteu/biguasim/src/biguasim/agents.py", line 182, in action_space
      return self.control_abstractions[self._current_control_abstraction][1]
  AttributeError: 'DjiMatrice' object has no attribute '_current_control_abstraction'. Did you mean: '_current_control_scheme'?
  ```
- Processos: logo depois do erro havia 1 processo do simulador vivo. O `atexit` do biguasim o encerrou quando
  o Python saiu, e depois do teste havia 0 processos. Nenhum órfão.

### Causa (no biguasim, não no biguagym)
- Em `biguasim/agents.py`, `set_control_scheme()` (linhas 78-81) foi reescrito para gravar
  `self._current_control_scheme`, e a linha antiga, que definia `_current_control_abstraction`, ficou comentada.
  A property `action_space` (linha 182) continua lendo `self._current_control_abstraction`, que nunca é definido.
- **Afeta todos os 54 ambientes**, porque todos chamam `self._env.action_space` em `_init_spaces`.
- O mesmo código está em **todas as branches do biguasim**: `sitl-test` local (`b0c6685e`),
  `origin/sitl-test` (`66a1b931`), `origin/v1.0.0` (`da9afad8`) e `origin/main` atualizada por
  `git fetch` (`dec40557`, 2026-08-28). Nenhuma versão disponível hoje funciona com o biguagym.

### Outros problemas encontrados na mesma investigação (sem rodar o simulador)
1. **Hydrone não tem modelo de dinâmica.** `biguasim/dynamics/agents.py::ModelsFactory._types` tem
   LandingPlatform, BlueBoat, BlueROV2, BlueROVHeavy, DjiMatrice e TorpedoAUV, mas não Hydrone
   (nenhuma branch tem). Os **13 ambientes Hydrone** devem falhar com `KeyError: 'Hydrone'` em
   `ModelsFactory.build_model`, antes mesmo do erro acima. A confirmar na Etapa 4.
2. **Espaço de ação suspeito para BlueBoat/BlueROV2/BlueROVHeavy, mesmo com a correção acima.**
   O `action_space` do biguasim devolve `control_abstractions[_scheme]` do agente Unreal, e o `_scheme`
   é fixo por modelo de dinâmica:

   | Veículo | `_scheme` | Espaço devolvido (Unreal) | Limites do `cmd_motor_speeds` na dinâmica |
   |---|---|---|---|
   | DjiMatrice | 1 | 4 thrusters, [0, 592.4] | rotor [0, 592.4] ✅ bate |
   | BlueBoat | 2 | `[vx, vy, vz]`, 3 dims, ±10 | rotor [-295.75, 288.08] ❓ |
   | BlueROV2 | 2 | `[vx, vy, vz]`, 3 dims, ±10 | rotor ±278.9 ❓ |
   | BlueROVHeavy | 2 | `[vx, vy, vz]`, 3 dims, ±10 | rotor ±278.9 ❓ |
   | TorpedoAUV | 1 | 5 dims (4 lemes + rpm), usa só `low[0]=-90`/`high[0]=90` | rpm ±1525 ❓ |

   O `_init_spaces` do biguagym ainda usa apenas `get_low()[0]`/`get_high()[0]` para todas as dimensões.
   No Torpedo, isso limitaria o rpm a ±90. Parece que o espaço de ação do RL deveria vir do modelo de
   dinâmica (o que `cmd_motor_speeds` espera), não do agente Unreal. **A confirmar rodando**, depois
   de corrigir o bug principal.
3. **Renomeação futura:** o `origin/main` do biguasim (`dec40557`) renomeia `BlueROVHeavy` para
   `BlueROV2Heavy`. Quando esse commit for usado, os 8 ambientes `BlueROVHeavy*` do `register.py`
   vão quebrar (`agent_type` desconhecido).

### Correção proposta (NÃO aplicada — aguardando decisão)
- **Opção A (no biguasim, 1 linha):** em `src/biguasim/agents.py:182`, trocar
  `self._current_control_abstraction` por `self._current_control_scheme`. É a correção certa e deveria ir
  para os mantenedores do biguasim, mas altera outro repositório.
- **Opção B (no biguagym, sem tocar no biguasim):** em `_init_spaces`, montar o `action_space` a partir
  do modelo de dinâmica (`rotor_speed_min`/`max` e número de motores de `self._env._dynamics_dict['robot']`).
  Resolve também o item 2, mas precisa de spec (`/spec-requisitos`) e de confirmar a interface da dinâmica.

### Etapa 3 — segunda tentativa, com a opção A aplicada (2026-09-28)
- Aprovado pelo usuário: branch **`testes-ambientes` criada no biguasim** a partir de `sitl-test` (`b0c6685e`).
  Alteração em `src/biguasim/agents.py:182`: `_current_control_abstraction` → `_current_control_scheme`.
  **Sem commit.**
- Comando: `/home/teteu/venv-biguagym/bin/python smoke_test.py --env DjiMatriceLand-v0 --steps 200`
- Resultado: `gym.make` **passou** (make em 7,64 s; obs `Box(19,)`, ação `Box(4,)` com [0, 592.4]).
  O teste falhou no `reset`:
  ```
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/base_env.py", line 271, in reset
      obs, info = self._reset()
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/environments.py", line 277, in _reset
      self._set_dynamics(state)
    File "/home/teteu/biguagym-v0.1.0/biguagym/core/environments.py", line 139, in _set_dynamics
      dynamics = np.asarray(state['RPYDynamicsSensor'], dtype=np.float64).ravel()
  KeyError: 'RPYDynamicsSensor'
  ```
- **Etapa 5 confirmada de passagem:** `sim_alive_after_env_close: true`. O processo do simulador continua
  vivo depois de `env.close()` e só morre com `__on_exit__()`. Depois do teste havia 0 processos.

### Causa: formato do `state` (diagnóstico com `diag_state.py` no scratchpad)
- O `reset()` do biguasim 1.0.0 devolve o estado **aninhado por agente e com batch**:
  `{'robot': [ {'DynamicsSensor': (19,), 'RPYDynamicsSensor': (18,), 'CameraView': (720,1280,4)} ], 't': float}`
  (`_get_single_state`, `environments.py:1083-1108`; o agente é renomeado para `robot-id0`).
- O biguagym espera o estado **plano**: `state['RPYDynamicsSensor']`, `state.get('CameraView')`, etc.
- Esse formato aninhado existe desde o **primeiro commit** do repositório público (`142b0082`, 2026-02-04,
  "Public sync from bs-client main") e está em todas as branches, inclusive na `v1.0.0`
  ("1.0.0: public version is done").

### Causa de fundo: o biguagym foi escrito para o biguasim 1.1.0
- Antes do commit `1d9bfed` (2026-06-18, "Biguasim removed from env"), o `environment.yml` pedia
  **`biguasim==1.1.0`**. O instalado aqui é o **1.0.0**.
- Não existe 1.1.0 disponível: todas as branches e tags do repositório público têm `version = "1.0.0"`
  (tag única `v1.0.0`), e o PyPI não tem o pacote (`pip download biguasim==1.1.0` → "from versions: none").
  O "bs-client" citado nos commits sugere que a 1.1.0 vem de um repositório privado.
- **Conclusão:** os ambientes não rodam com nenhuma versão pública do simulador. O usuário tinha razão
  ao sugerir esperar a versão pública (1.1.0), ou então é preciso pedir aos autores acesso à 1.1.0.
  Adaptar o biguagym ao 1.0.0 (formato do estado, espaço de ação, Hydrone sem dinâmica) seria
  retrabalho que a 1.1.0 provavelmente torna desnecessário.
- Etapas 3, 4 e 6 ficam **suspensas** até haver o biguasim 1.1.0.

### Resultados que continuam válidos (independem da versão)
- Registro dos 54 ids (Etapa 2); `DjiMatriceLand-v2` e `HydroneLand-v2` são `LandCoopPixelEnv`, fora da convenção.
- Vazamento do simulador em `BiguaGymEnv.close()` (Etapa 5), agora com evidência medida.
- `PixelStack.append` com `np.resize` (Etapa 6), que é código do biguagym.
- Bug `_current_control_abstraction` no biguasim 1.0.0 (todas as branches), a reportar aos mantenedores.
- `_init_spaces` usa só `get_low()[0]`/`get_high()[0]` para todas as dimensões da ação.

### Versão do TCC (`~/biguasim_tcc`) — avaliada, não serve (2026-09-28)
- Contexto: o usuário informou que os autores devem atualizar o simulador na **quarta-feira (2026-09-30)**
  e sugeriu usar a versão do TCC para testar enquanto isso.
- `~/biguasim_tcc` (repositório `ttszin/biguasim_tcc`, commit `f636d30`, 2026-09-20) é um fork do
  hydrone-furg/biguasim com `version = "1.0.0"`.
- Comparação do código (`diff -rq`, sem `ardubridge`) com o biguasim instalado (`sitl-test` + opção A):
  só dois arquivos diferem.
  - `agents.py:182`: o TCC tem o bug `_current_control_abstraction` (a diferença é só a correção da opção A);
  - `dynamics/uuv.py`: o público tem um toggle `BIGUA_MTZ_ORIG` para o sinal do `mt_z` do BlueROV2 (irrelevante aqui).
- Os três bloqueios estão iguais no TCC: `action_space` quebrado, estado aninhado
  (`environments.py:1105`) e `ModelsFactory` sem Hydrone.
- **Conclusão:** trocar para a versão do TCC não muda nenhum resultado, e ela não foi instalada.
  O TCC funciona porque o `biguasim_env/` dele tem wrappers próprios que tratam o estado aninhado.
  O biguagym espera outra API (a 1.1.0).
- Decisão: aguardar a atualização de quarta-feira para retomar as Etapas 3, 4 e 6.

### Reorganização das branches do biguasim (2026-09-28)
- Pedido do usuário: voltar o biguasim para a `sitl-test`, desfazer a correção e criar outra branch só
  com as correções, para testar o DjiMatrice e os barcos.
- `~/biguasim`: correção desfeita, `PKG-INFO` restaurado (tinha sido alterado pelo meu `pip install -e`) e
  volta para a `sitl-test` (`b0c6685e`, limpa). A branch vazia `testes-ambientes` foi apagada.
- **Nova branch `testes-biguagym`** (a partir de `sitl-test`), commit `8dc366a0`
  "fix: action_space lê _current_control_scheme" (`agents.py:182`).
- ⚠️ `~/biguasim` é instalação editável **também do `venv-ardupilot`**. Enquanto `testes-biguagym` estiver
  ativa, o ardubridge/SITL também usa essa branch. A correção só conserta uma property que dava crash,
  então não deveria afetar o SITL. Para voltar: `git -C ~/biguasim switch sitl-test`.
- `~/biguasim_tcc` não foi alterado.

### Correções que faltam para DjiMatrice e BlueBoat (propostas, NÃO aplicadas)
1. **Estado aninhado** (`KeyError: 'RPYDynamicsSensor'`). Não dá para corrigir dentro do biguasim, porque o
   `step()` dele usa `state[agent_name]` internamente para rodar a dinâmica (`environments.py:584-640`).
   Proposta no biguagym: um `_unwrap_state()` que devolve `state['robot'][0]` quando o formato é aninhado
   (e o próprio estado se já for plano, o que mantém compatibilidade com a 1.1.0), aplicado nas 8 chamadas
   `self._env.reset()/step()` das classes de um agente (`environments.py` linhas 144, 213, 276, 355, 437,
   462, 885, 904). As chamadas do `LandCoopPixelEnv` (1516-1573) são multiagente e ficam de fora.
2. **Espaço de ação do BlueBoat.** Mesmo com o `action_space` corrigido, o biguasim devolve o esquema
   Unreal `_scheme=2` = `[vx, vy, vz]`, 3 dims, ±10. Mas com `cmd_motor_speeds` a dinâmica
   (`usv.get_cmd_motor_speeds`) usa a ação direto como velocidade dos rotores: **2 rotores** (`rotor_pos`
   r1, r2), limites **[-295.75, 288.08]** rad/s. Proposta: em `_init_spaces`, quando
   `control_abstraction == 'cmd_motor_speeds'`, montar o `Box` a partir de
   `self._env._dynamics_dict['robot'].params` (`len(rotor_pos)`, `rotor_speed_min`/`max`).
   No DjiMatrice o resultado não muda (4 dims, [0, 592.4]).

### Patch temporário no biguagym (2026-09-28)
- Aprovado pelo usuário (sem spec, por ser temporário): branch **`testes-ambientes` no submódulo `biguagym`**,
  commit `32698e5` com as correções 1 (`_unwrap_state`) e 2 (`action_space` pela dinâmica) em `core/environments.py`.
  O repositório principal não foi commitado; o ponteiro do submódulo aparece como modificado.
- A correção 2 também cobre o BlueROV: BlueROV2 → 6 rotores, BlueROVHeavy → 8 rotores, ambos ±278.9
  (antes sairiam com 3 dims `[vx, vy, vz]`). TorpedoAUV não tem `rotor_pos` e continua no caminho antigo.

## Etapa 3 — DjiMatriceLand-v0 (2026-09-28) — ✅ OK (com biguasim `testes-biguagym` + patch biguagym)
- Comando: `/home/teteu/venv-biguagym/bin/python smoke_test.py --env DjiMatriceLand-v0 --steps 200` (sem viewer)
- Classe `LandEnv`, `max_episode_steps` 300, `ticks_per_sec`/`frames_per_sec` = 20.
- **Observação:** `Box(19,) float32`, (-inf, inf) = `DynamicsSensor`. **Ação:** `Box(4,) float32`, [0, 592.4] (velocidade dos 4 rotores).
- **Sensores:** `DynamicsSensor` (19), `RPYDynamicsSensor` (18), `CameraView` (RGB 1280×720×4 uint8).
- **Velocidade:** `steps_per_s` = **20.03** ✅ (bate com o limite de 20). Step: 49.9 ms em média, p95 57 ms, máx 132 ms.
  Tempos: make 7.3 s, **reset 2.2 s**.
- **Com ação aleatória, o reset domina o tempo:** foram 38 episódios em 200 steps, todos `terminated`
  (comprimento de 2 a 14 steps; a inclinação passa de 15° quase na hora). Por isso `steps_per_s_wall` = **2.16**
  e `hours_per_100k` = **12.9 h**. Esse número vale só para a política aleatória. Com episódios cheios
  (300 steps), o custo do reset cai para ~2.2 s a cada 15 s (≈ +15%), o que dá ~1.6 h por 100k.
  No começo do treino, com episódios curtos, deve ficar bem mais lento que isso.
- **NaN/inf:** 0 na observação, 0 na recompensa. `obs_in_space`: **true** em todos os steps.
- Recompensa: mín -4.56, máx 1.4e-5, média -0.66.
- **Posição:** inicial [100, 100, 5], final [100.007, 100.014, 4.78] (o drone quase não sai do lugar entre resets).
  Alvo sorteado: [105.48, 98.78, 0.1].
- **VRAM:** 492 MB antes → 2226 MB com o simulador aberto (~1.7 GB) → 659 MB depois de fechar.
- **Vazamento (Etapa 5):** `sim_alive_after_env_close: true`, `sim_alive_after_on_exit: false`. Depois do
  teste havia 0 processos.
- **Frames** (`frames/cam_CameraView_00000/00100/00200.png`): câmera em terceira pessoa (socket `Viewport`),
  atrás e acima do drone. Aparecem o DJI Matrice (cores corretas, cinza), a sombra dele na água e o mar azul
  até o horizonte; no step 100 dá para ver uma rocha/costa no canto superior direito. O píer e o porto do
  `Pier-Harbor` não aparecem (o spawn em [100, 100] fica em mar aberto). **O landing pad (`draw_box`) não
  aparece em nenhum frame.** Pode estar fora do campo de visão (alvo ~5.6 m ao lado, na altura da água)
  ou as primitivas de debug podem não ser renderizadas com `-RenderOffScreen`. A confirmar com o viewer.
- Processos do simulador depois do teste: 0.

---

## Alterações no `smoke_test.py` depois da primeira versão (registro, regra 8)
- **2026-09-28, antes da regra 6 existir, sem autorização explícita** (fica registrado):
  - `--show-viewer`: passa `show_viewer=True` ao `gym.make` para abrir a janela do simulador.
    Motivo: o usuário pediu para ver o simulador durante a Etapa 4.
  - `--filter` repetível: vírgula = OU, repetir o argumento = E (ex.: `--filter v0 --filter DjiMatrice,BlueBoat,BlueROV`).
    Motivo: rodar só os v0 de DjiMatrice, BlueBoat e BlueROV, a pedido do usuário.
  - `summary.json` passou a registrar `show_viewer`.
- **2026-09-28, `--action` (autorizado pelo usuário):** ver a seção "BlueBoat com ação constante" abaixo.

## Etapa 4 (parcial) — v0 de DjiMatrice, BlueBoat e BlueROV, com viewer (2026-09-28)
- Comando: `/home/teteu/venv-biguagym/bin/python smoke_test.py --all --filter v0 --filter DjiMatrice,BlueBoat,BlueROV --steps 200 --frame-every 100 --show-viewer --timeout 900`
  (log em `smoke_results/etapa4_v0.log`). São 12 ids.
- Contexto: biguasim na branch `testes-biguagym` (`8dc366a0`) e biguagym na `testes-ambientes` (`32698e5`).
- **Interrompida no 6/12** (ver BlueROVHeavy abaixo). Resultados de `smoke_results/resumo.csv`:

| Ambiente | Status | steps/s | steps/s (parede) | h/100k | Obs | Ação | NaN/inf | obs_in_space | Episódios |
|---|---|---|---|---|---|---|---|---|---|
| BlueBoatNav-v0 | ok | 20.04 | 19.98 | 1.39 | 19 | 2 [-295.75, 288.08] | 0 | true | 1 (200 steps) |
| BlueBoatTrajectoryFollower-v0 | ok | 20.07 | 20.03 | 1.39 | 39 | 2 | 0 | true | 1 |
| BlueROV2Dock-v0 | ok | 19.44 | 5.36 | 5.19 | 19 | 6 [±278.9] | 0 | true | 13 (12 term.) |
| BlueROV2Nav-v0 | ok | 19.81 | 10.41 | 2.67 | 19 | 6 | 0 | true | 5 (4 term.) |
| BlueROV2TrajectoryFollower-v0 | ok | 19.82 | 10.53 | 2.64 | 39 | 6 | 0 | true | 5 (4 term.) |
| BlueROVHeavyDock-v0 | **crash do Unreal** | — | — | — | — | — | — | — | — |
| BlueROVHeavyNav/TrajectoryFollower-v0, DjiMatrice Hover/Nav/Trajectory-v0 | não rodados | | | | | | | | |

- O patch do `action_space` funcionou: BlueBoat com 2 dims, BlueROV2 com 6. Com o viewer, o steps/s continua ~20.
- TrajectoryFollower: obs 39 = 19 + 5 (Frenet/progresso) + 3×5 (lookahead) ✅.
- Reset em ~2.2 s em todos os ambientes. O vazamento (`sim_alive_after_env_close: true`) se repete em todos.
- **Determinismo:** BlueBoatNav e BlueBoatTrajectoryFollower (mesma seed 0, mesmas ações) terminaram exatamente
  na mesma posição [104.481, 100.226, -0.113]. O mesmo vale para BlueROV2Nav/Trajectory, que tiveram os mesmos
  comprimentos de episódio. A simulação parece determinística para a mesma sequência de ações.
- BlueBoat: spawn em z = 0.0 e fim em z = -0.113. Com ação aleatória de média ~0, andou ~4.5 m em +x (ver investigação abaixo).
- BlueROV2: começa em z = -0.2; Dock tem alvo em z = -10. Episódios curtos no Dock (2 a 52 steps) com ação aleatória.

### BlueROVHeavy — crash do Unreal ao criar o agente
- O processo `Holodeck` virou `<defunct>` ~7 s depois de iniciar. O Python ficou bloqueado esperando o primeiro
  tick (o biguasim espera até 900 s, commit `2c10e46a`), sem detectar que o simulador morreu.
- `~/.local/share/biguasim/1.0.0/worlds/SkyDive/Linux/Biguasim/Saved/Logs/HolodeckLog.txt`:
  ```
  LogCore: Error: appError called: Assertion failed: SpawnedAgent [File:/home/lh/Documents/bs-engine/Source/Holodeck/ClientCommands/Private/SpawnAgentCommand.cpp] [Line: 33]
  LogCore: === Critical error: ===
  Unhandled Exception: SIGSEGV: invalid attempt to write memory at address 0x0000000000000003
  ```
- Causa provável: o binário do mundo não conhece o agente `BlueROVHeavy`, coerente com a renomeação para
  `BlueROV2Heavy` na `origin/main` do biguasim (`dec40557`). **Os 8 ambientes BlueROVHeavy não rodam com este binário.**
- Ação tomada: a bateria foi interrompida (`kill` nos processos iniciados por mim: o pai `smoke_test --all` e o
  filho) para não perder 2×15 min nos outros BlueROVHeavy. Depois disso havia 0 processos do simulador.
- Mesmo log, sem relação com o crash: `M_TabuaCorSolida` (material do BlueBoat do patch `_P`) falha ao
  compilar para VULKAN_SM6 ("Missing shader resource") e usa o material padrão.

### Relato do usuário sobre o BlueBoat e investigação (2026-09-28)
- Relato: vendo o viewer, o BlueBoat "trava e volta a se movimentar", fica numa altura ruim, e parece
  haver uma gambiarra para ele não flutuar. É o mesmo bug que o usuário corrigiu na versão dele, onde o BlueROV anda liso.
- Verificado:
  - A dinâmica em uso **já tem as correções do usuário**. `~/biguasim` na `testes-biguagym` deriva da
    `sitl-test`, que tem os commits do ttszin (buoyancy do HexaCopterFiveDoF, `motor_signs` do BlueROV2, timeout
    do 1º step, buffer de ação) e os "PATCH LOCAL" de 2026-08-24 em `dynamics/usv.py` (`k_eta` 10x,
    `BUOYANCY_VOLUME_SCALE = 0.09`, redução de ½ do `dumping_hack` desligada, máscara de empuxo submerso).
    O `usv.py` é idêntico ao do `biguasim_tcc`.
  - O patch de mundo do BlueBoat (`Biguasim-Linux_P.{pak,ucas,utoc}`) instalado no SkyDive é **idêntico,
    byte a byte,** ao `worlds_patch/BlueBoat_P` do TCC.
  - No TCC, o BlueBoat anda com um controlador P próprio (`biguasim_env/core/agent.py::_advance_platform`),
    que gera comandos de motor suaves. O smoke test sorteia comandos aleatórios independentes a cada 50 ms
    em toda a faixa de [-295, 288] rad/s, o que provavelmente causa o "trava e volta".
  - Altura: o `register.py` faz o spawn do BlueBoat em z = 0. O código do TCC registra o equilíbrio medido
    em z ≈ -0.42 ("sem teleport, física livre"), então o barco pode estar começando fora do equilíbrio.
  - "Gambiarra": em `usv.py:28` existe `dumping_hack` ("a hack to generate a nice buoyancy behavior").
    Pedi ao usuário para confirmar se é esse; não foi achada gambiarra de altura no biguagym.
  - Observação a investigar: com ação aleatória de média ≈ -3.8 rad/s (levemente para trás), o barco
    andou ~4.5 m para +x.
- Decisão: testar o BlueBoat com ação constante para separar "simulador" de "política aleatória".

## BlueBoat com ação constante — os 4 modos de controle, com viewer (2026-09-28)

### Alteração no `smoke_test.py` (autorizada pelo usuário: "adiciona o --action")
- `--action '[rótulo@]N:v1,v2;...'`: roteiro de ações fixas em segmentos, no lugar das ações aleatórias.
- `--control`: passa `control_abstraction` ao `gym.make` (`cmd_motor_speeds`, `cmd_vel`, `cmd_vel_yaw`, `cmd_pos_yaw`).
- `--no-reset`: com `--action`, não reseta quando o episódio termina, para o movimento seguir contínuo.
  **Não fazia parte do pedido literal:** foi adicionado porque o Nav termina ao sair de ±10 m em xy e
  o reset teleportaria o barco no meio do roteiro. Foi avisado ao usuário.
- `--tag`: sufixo da pasta de saída (`smoke_results/<env>__<tag>/`), para não sobrescrever os resultados v0.
- Com `--action`, o script grava `trajectory.csv` (posição, roll/pitch/yaw, velocidade xy, ação e recompensa
  por passo) e `segments` no `summary.json` (deslocamento, velocidade média/máx, "travadas" = passos com
  velocidade < 0.05 m/s num segmento em movimento, faixa de z, yaw inicial/final). Salva um frame no fim de cada segmento.

### Comandos (log em `smoke_results/blueboat_acoes.log`)
Todos com `smoke_test.py --env BlueBoatNav-v0 --show-viewer --no-reset --frame-every 0`:
1. `--tag motores --control cmd_motor_speeds --action 'parado@40:0,0;frente_lento@80:60,60;frente@80:120,120;parado2@60:0,0;re@80:-100,-100;giro_esq@60:-80,80;giro_dir@60:80,-80;curva_esq@100:60,120;parado3@40:0,0'`
2. `--tag cmd_vel --control cmd_vel --action 'parado@40:0,0,0;frente_1ms@120:1,0,0;frente_2ms@100:2,0,0;re_1ms@100:-1,0,0;parado2@60:0,0,0'`
3. `--tag cmd_vel_yaw --control cmd_vel_yaw --action 'parado@40:0,0,0,0;gira_90@100:0,0,0,90;frente_reto@100:1,0,0,0;frente_curva@120:1,0,0,-30;parado2@40:0,0,0,0'`
4. `--tag cmd_pos_yaw --control cmd_pos_yaw --action 'ponto_frente@200:108,100,0,0;ponto_lado@200:108,106,0,0;volta_origem@200:100,100,0,0'`

Todos terminaram com `status: ok`, ~20 steps/s, e 0 processos do simulador depois de cada um.

### Resultados por segmento (`summary.json` → `segments`)
**1. `cmd_motor_speeds`** (r1 = motor esquerdo, y = +0.285; r2 = direito)
| Segmento | Ação | Desloc. xy | v média / máx (m/s) | Yaw início→fim | Observação |
|---|---|---|---|---|---|
| frente_lento | 60, 60 | 2.43 m | 0.61 / 0.80 | 0 → 0 | acelera suave até 0.80 m/s |
| frente | 120, 120 | 6.08 m | 1.53 / 1.62 | 0 → 0 | estabiliza em 1.62 m/s |
| parado2 | 0, 0 | 1.82 m | desacelera | 0 → 0 | sai da caixa ±10 m (terminated sem reset) |
| re | -100, -100 | 4.29 m | 1.09 / 1.35 | 0 → 0 | ré funciona |
| giro_esq | -80, 80 | 1.67 m (inércia) | — | 0 → **-3.2°** | quase não gira, e **para o lado errado** |
| giro_dir | 80, -80 | 0.63 m | 0.21 | -3.3 → -6.6° | quase não gira |
| curva_esq | 60, 120 | 5.44 m | 1.09 / 1.28 | -6.6 → **-14.0°** | curva sai para a direita e muito aberta |

**2. `cmd_vel`**: 1 m/s pedido → 0.44 m/s atingido; 2 m/s → 0.68 m/s; ré a -1 m/s → recuou só 0.73 m. Anda reto, mas
com grande erro de regime (P puro, `k_vx = 1`, contra o arrasto). Yaw fica em 0.

**3. `cmd_vel_yaw`**: `gira_90` (Δyaw = 90°, parado) → yaw 0 → **0.3°** (não gira); `frente_reto` a 0.44 m/s ok;
`frente_curva` (Δyaw = -30°) → yaw 0.7 → 0.5° (**não curva**).

**4. `cmd_pos_yaw`** (spawn em [100, 100]): `ponto_frente` (108, 100) → andou só 2.96 m em 10 s (0.3 m/s, `kp_pos = 0.1`);
`ponto_lado` (108, 106) → seguiu em +x até 106.4, com yaw de só 0 → 4°; `volta_origem` (100, 100) → em vez de virar 180°,
seguiu em +x até **110.05** (saiu da caixa) com yaw 4 → 24°. **Não consegue navegar até pontos fora da proa.**

### Achados
1. **"Trava e volta" não aparece na física com ação constante.** A velocidade do sensor sobe de forma monotônica até o
   regime (ex.: 0.00 → 0.80 m/s em 80 passos, sem nenhuma queda). O travamento visto no teste anterior vem das
   ações aleatórias (comandos opostos a cada 50 ms). *A confirmar com o que o usuário viu no viewer nesta rodada.*
2. **Oscilação vertical sem amortecimento** (a "altura ruim"): z oscila entre -0.13 e -0.025 m, com período de ~1.5 s
   (~30 passos), durante todo o roteiro e em todos os modos, sem assentar. Spawn em z = 0; o primeiro mergulho vai até -0.141.
   Provável causa: o arrasto é só quadrático (`D ∝ v·|v|`), então quase não amortece em velocidades baixas.
3. **Roll e pitch sempre exatamente 0.0.** Em `_compute_body_wrench`, `mt_x = mt_y = 0` e `ft_y = ft_z = 0` (modelo 3-DoF no plano).
4. **BUG: o barco não gira (causa encontrada).** `biguasim/dynamics/usv.py`, `Catamaran._compute_body_wrench`:
   ```python
   M = k_m * rotor_speeds**2 * sign(rotor_speeds)
   mt_z = (M[:, 0] - M[:, 1])      # só contra-torque das hélices
   ```
   O momento de guinada ignora o empuxo diferencial com braço (motores em y = ±0.285 m). Com -80/+80 rad/s:
   atual ≈ **-0.14 N·m** (k_m = 1.12e-5); correto τz = -Σ yᵢ·Tᵢ = 0.285·(T2 − T1) ≈ **+12.9 N·m** (k_eta = 3.55e-3).
   É ~90× menor e com **sinal trocado**, o que explica: giro quase nulo, curva para o lado errado, e `cmd_vel_yaw`/`cmd_pos_yaw`
   sem autoridade de guinada (os controladores alocam o momento via `TM_to_f`, mas o modelo não gera o torque).
   O código parece copiado do ROV (o comentário "Surge = front rotors push forward, rear backward" não se aplica ao catamarã).
   Isso é coerente com a nota do TCC de que `cmd_vel_yaw`/`cmd_pos_yaw` "não produzem movimento real".

### Correção proposta (NÃO aplicada — aguardando o usuário)
Na branch `testes-biguagym` do biguasim, em `Catamaran._compute_body_wrench`:
```python
y = [rotor_pos['r1'][1], rotor_pos['r2'][1]]          # +0.285, -0.285
mt_z = -(y[0] * TT[:, 0] + y[1] * TT[:, 1]) + (M[:, 0] - M[:, 1])   # braço do empuxo + contra-torque
```
Depois, repetir os 4 roteiros e comparar os `segments`. Talvez seja preciso reajustar `kp_yaw`/`kd_yaw`, porque os
controladores foram calibrados com o modelo sem torque. A oscilação vertical (achado 2) fica para depois,
porque o usuário já corrigiu o mesmo tipo de problema de flutuação no BlueROV e pode indicar a abordagem.

## Correção do giro do BlueBoat e novos roteiros (2026-09-28)

### Alteração aplicada (autorizada pelo usuário)
- `~/biguasim`, branch `testes-biguagym`, commit **`e4f8ff9a`** — `src/biguasim/dynamics/usv.py` (classe `Catamaran`,
  usada por BlueBoat e LandingPlatform):
  - `__init__`: novo `batched_params.rotor_y` (braço lateral de cada rotor).
  - `_compute_body_wrench`: `mt_z = -(rotor_y * TT).sum(1) + (M[:,0] - M[:,1])` (empuxo diferencial com braço + contra-torque).
- Verificação offline (sem simulador, `thrust_submerged_mask = 1`): (-80, 80) → Mz = **+12.81 N·m** (antes -0.143);
  (80, -80) → -12.81; (60, 120) → +10.81 com Fx = 63.9 N; (100, 100) → Mz = 0.

### Roteiros repetidos e novos (log em `smoke_results/blueboat_giro.log`)
Mesmos comandos da seção anterior, com `--tag <modo>_giro`, e mais:
- `--tag curvas --control cmd_motor_speeds --action 'parado@20:0,0;curva_esq_longa@300:60,120;parado2@60:0,0;curva_dir_longa@300:120,60;parado3@40:0,0'`
- Percursos do biguagym (`TrajectoryEnv._figure8_trajectory`, escala 2.5, 15.2 m; `_sine_trajectory`, 10.9 m),
  deslocados para (100, 100) e seguidos com `cmd_pos_yaw` usando um alvo "cenoura" 3 m à frente, avançando a 0.3 m/s,
  trocado a cada 10 passos. Gerados pelo script `gen_percursos.py` (no scratchpad).
- **Erro meu no script de execução:** o arquivo de percursos tinha 2 linhas de comentário antes dos programas e eu peguei
  as linhas erradas. O `oito_pos` recebeu um comentário e falhou no parse
  (`ValueError: invalid literal for int() with base 10: '# seno'`); o `seno_pos` executou o **programa do 8**.
  A pasta `BlueBoatNav-v0__seno_pos` foi renomeada para `BlueBoatNav-v0__oito_pos`. **O seno ainda não foi rodado.**
- Todos terminaram sem crash; 0 processos do simulador depois de cada um.

### Resultados (yaw desembrulhado a partir de `trajectory.csv`)
| Roteiro / segmento | Antes (`e4f8ff9a` não aplicado) | Depois |
|---|---|---|
| motores `giro_esq` (-80, 80), 3 s | Δyaw -3.2° | **+209.8°** (média 71°/s, pico 108°/s) ✅ sentido certo |
| motores `giro_dir` (80, -80), 3 s | -3.3° | continua girando por inércia, depois inverte: -17.5° líquido |
| motores `curva_esq` (60, 120), 5 s | -7.4° | **+203.9°** ✅ |
| motores `parado3` (0, 0), 2 s | — | **+137° com os motores desligados** (segue girando a 70°/s) ⚠️ |
| curvas `curva_esq_longa` (60, 120), 15 s | — | +1447° (4 voltas), 106°/s, deslocamento líquido 0.94 m: **gira quase no lugar** (raio ≈ v/ω ≈ 0.7/1.85 ≈ 0.4 m) ⚠️ |
| curvas `curva_dir_longa` (120, 60), 15 s | — | -1361°, -106°/s (simétrico) |
| cmd_vel (yaw deve ficar 0) | 0 | 0 ✅ (motores iguais) |
| cmd_vel_yaw `gira_90` | +0.3° | **-135.8°** ❌ lado oposto |
| cmd_pos_yaw `ponto_lado` (108, 106) | yaw 4° | **-158.6°** ❌ lado oposto; parou em (103.1, 99.2) |
| "8" (cmd_pos_yaw + cenoura), 1080 passos | — | ❌ desvio médio 1.97 m, máx 7.65 m, 25% dos passos a menos de 0.5 m; sai em +x balançando até x = 110 (`BlueBoatNav-v0__oito_pos/trajetoria.png`) |

### Achados novos
1. **O modelo agora gira no sentido certo** (correção validada).
2. **Controladores de alto nível com sinal invertido.** Em `usv.py` (Catamaran), `cmd_vel` / `cmd_vel_yaw` / `cmd_pos_yaw`
   (linhas 356, 403, 456) usam `M_yaw = -kd_yaw * (yaw_rate_des - yaw_rate)`. Verificação offline: o alocador `TM_to_f` e o
   modelo corrigido concordam (Mz pedido +5 → motores (-49.7, +49.7) → Mz gerado +4.94). Então o sinal "-" virou
   **realimentação positiva**: ele compensava o modelo antigo, que era invertido. É por isso que `cmd_vel_yaw`/`cmd_pos_yaw`
   giram para o lado oposto e o "8" falha. (A linha 806 é da classe `Differential` e não é usada pelo BlueBoat.)
3. **Amortecimento de guinada muito fraco:** o barco segue girando a ~70°/s com os motores desligados e, em curva
   constante, acelera até ~106°/s girando quase no lugar (raio ~0.4 m). Não se parece com um barco. O único
   amortecimento é `M2 = -0.5·rho·Cr·w|w|·rotor_distance`, com `rotor_distance = 0.1·|r1| ≈ 0.07 m`.
   Antes isso não aparecia porque o barco quase não girava.

### Correções propostas (NÃO aplicadas — aguardando o usuário)
- **P1 (sinal dos controladores):** nas 3 linhas do Catamaran, `M_yaw = +kd_yaw * yaw_dot_err`. Depois, repetir cmd_vel_yaw,
  cmd_pos_yaw, o 8 e o seno.
- **P2 (amortecimento de guinada):** somar um termo linear `-N_r · w_z` (e/ou aumentar o quadrático) em
  `_compute_external_forces`. O valor precisa de uma referência (ex.: taxa máxima de giro do BlueBoat real, ou o
  comportamento que o usuário validou no TCC). Pedir ao usuário a referência.

## P1 + P2 no BlueBoat (2026-09-28)

### Alterações aplicadas (autorizadas: "Aplique P1 e P2 e conferimos")
- `~/biguasim`, branch `testes-biguagym`, commit **`cd2905fa`**:
  - **P1**, `dynamics/usv.py` (Catamaran, 3 controladores `cmd_vel`/`cmd_vel_yaw`/`cmd_pos_yaw`):
    `M_yaw = -kd_yaw * yaw_dot_err` → `M_yaw = +kd_yaw * yaw_dot_err`. A classe `Differential` não foi alterada.
  - **P2**, `dynamics/usv.py`: amortecimento de guinada `-(yaw_damp_lin·r + yaw_damp_quad·r|r|)·submerged_mask`
    somado a `MtotB` em `_compute_external_forces`. Os parâmetros são lidos com `params.get(..., 0.0)`, então
    LandingPlatform fica sem efeito (verificado: 0.0).
  - **P2**, `dynamics/agents.py` (`BlueBoat._params`): `yaw_damp_lin = 10.0`, `yaw_damp_quad = 17.0`.
    **Valores escolhidos por mim, sem referência do barco real**: meta de ~30°/s em regime na curva (60, 120)
    (Mz = 10.8 N·m) e parada em ~1 s com os motores desligados. O amortecimento que já existia (`M2`) era de
    só 0.86 N·m a 30°/s. Verificação offline: amortecimento total 4.8 / 10.7 / 30.2 N·m a 17 / 30 / 57°/s. **Revisar.**
- Comandos: os mesmos roteiros, com `--tag <nome>_p1p2` (log em `smoke_results/blueboat_p1p2.log`); os percursos
  foram gerados com `gen_percursos.py` (cenoura 3 m, 0.3 m/s). Todos com `exit=0` e 0 processos no fim.

### Resultados (yaw desembrulhado)
| Roteiro / segmento | Só o modelo corrigido (`e4f8ff9a`) | Com P1 + P2 (`cd2905fa`) |
|---|---|---|
| motores `giro_esq` (-80, 80), 3 s | +210°, taxa final 108°/s | **+103°, 43°/s** |
| motores `giro_dir` (80, -80), 3 s | -17.5° (inércia) | **-74°, -40°/s** (inverte de verdade) |
| motores `curva_esq` (60, 120), 5 s | +204°, 102°/s | **+137°, 36°/s** |
| motores `parado3` (0, 0), 2 s | +137°, ainda a 52°/s | **+27°, cai para 5°/s** ✅ |
| curvas `curva_esq_longa` (60, 120), 15 s | +1447°, 106°/s, raio ~0.4 m | **+535°, 36°/s, v 0.90 m/s → raio ≈ 1.4 m** ✅ |
| curvas `curva_dir_longa` (120, 60), 15 s | -1361° | **-533°, -37°/s** (simétrico) ✅ |
| cmd_vel_yaw `gira_90` | -136° ❌ | **+47°** ✅ sentido certo (desacelera para 11°/s; não gira continuamente) |
| cmd_vel_yaw `frente_curva` (Δ -30°) | -115° | **-22°** ✅ |
| cmd_pos_yaw `ponto_lado` (108, 106) | yaw -159° ❌ | **yaw +48.7°** (rumo desejado atan2(6, 5) ≈ 50°) ✅ |
| cmd_pos_yaw `volta_origem` (100, 100) | — | yaw vai para +155° (virando para ~180°) ✅, lento |
| "8" (cenoura 3 m, 0.3 m/s) | desvio médio 1.97 / máx 7.65 m | **desvio médio 0.66 / máx 1.82 m**, 43% dos passos a <0.5 m; mas faz **um oval só para a direita (-361°)**, não o 8 |
| seno (cenoura 3 m, 0.3 m/s) | não rodado | desvio médio 0.46 / máx 0.77 m; **forma certa, mas achatada** (amplitude ~0.25 m contra 1 m) e não chegou ao fim (x = 108.3 de 110) |

Gráficos: `smoke_results/BlueBoatNav-v0__{oito_pos,oito_p1p2,seno_p1p2}/trajetoria.png` (gerados por `analisa_percurso.py` no scratchpad).

### Interpretação
- O BlueBoat agora **gira como barco**: curvas com raio de ~1.4 m, taxa de ~36°/s e parada suave. O modelo e os
  controladores estão no sentido certo.
- O que falta no 8 e no seno é **o meu roteiro de teste, não a física**: a cenoura 3 m à frente corta caminho num
  laço de ~7.6 m, e ela avança a 0.3 m/s, mais rápido que o barco (0.21 a 0.23 m/s, limitado por `kp_pos = 0.1`).
  Repetindo com cenoura de 1.5 m a 0.15 m/s (ver abaixo).
- Continua pendente: oscilação vertical de ~1.5 s entre z -0.13 e -0.025 (igual em todas as rodadas).

### Percursos com cenoura curta, ainda em malha aberta (2026-09-28)
- `gen_percursos.py 0.15 1.5` (cenoura 1.5 m à frente, avançando a 0.15 m/s), `--tag oito_lento` / `seno_lento`
  (log em `smoke_results/blueboat_percursos_lento.log`). Os dois com `exit=0` e 0 processos no fim.
- **8:** 2090 passos; desvio médio **0.47 m**, máx 1.19 m; 54% dos passos a <0.5 m; cobertura 71%; volta ao ponto de
  partida. **Ainda não é um 8:** o laço da direita sai certo (horário), mas na volta o barco corta por baixo
  (y ≈ 98.8) em vez de cruzar o centro, e faz o laço da esquerda também no sentido horário (yaw total -334°).
  Causa: a cenoura avança por tempo, sem olhar onde o barco está; o atraso acumulado nas curvas faz o alvo passar
  do cruzamento antes do barco.
- **Seno:** 1520 passos; desvio médio **0.36 m**, máx 0.71 m; 70% a <0.5 m; cobertura 66%.

### Alteração no `smoke_test.py`: `--follow` (autorizada pelo usuário: "pode adicionar essa nova opção")
- Classe nova `PathFollower`: pure pursuit sobre `TrajectoryEnv._figure8_trajectory` / `_sine_trajectory`
  (parametrizado por comprimento de arco e deslocado para `u._location`). A cada passo, acha o ponto mais próximo
  do barco só para frente do progresso atual (janela de 2 m, para não pular de laço no cruzamento do 8) e manda como
  alvo do `cmd_pos_yaw` o ponto `--lookahead` m adiante. Termina quando o progresso chega ao fim (`--steps` é o máximo).
- Novos argumentos: `--follow figure8|sine`, `--lookahead` (padrão 1.5), `--laps` (padrão 1). Com `--follow` e sem
  `--control`, usa `cmd_pos_yaw`.
- Saídas: `trajetoria.png` e `follow_result` no `summary.json` (desvio médio/máx, % de passos a <0.5 m, cobertura,
  progresso e `completed`).
- Verificação offline (veículo cinemático ideal a 0.15 m/s): completa o 8 (progresso 14.87 de 15.17 m).

### 8 e seno em malha fechada (`--follow`) (2026-09-28)
- Comandos (log em `smoke_results/blueboat_follow.log`):
  `smoke_test.py --env BlueBoatNav-v0 --show-viewer --no-reset --frame-every 0 --tag oito_follow --follow figure8 --lookahead 1.5 --steps 3000`
  e o mesmo com `--tag seno_follow --follow sine`. Os dois com `exit=0`, ~20 steps/s e 0 processos no fim.

| Percurso | Passos | Completou | Desvio médio / máx | % passos a <0.5 m | Cobertura | Yaw |
|---|---|---|---|---|---|---|
| 8 (15.2 m) | 1663 | sim | 0.47 / 1.00 m | 53% | 70% | -383° (sempre horário) |
| seno (10.9 m) | 1965 | sim | **0.34 / 0.67 m** | **79%** | 77% | — |

- **Seno:** forma certa, mas com atraso de fase (~1.2 m) e amplitude de ~0.65 m contra 1 m.
- **8:** ainda não sai. Laço direito ok, mas o barco corta por baixo do cruzamento e faz o laço esquerdo no sentido
  errado (`BlueBoatNav-v0__oito_follow/trajetoria.png`).
- **Causa medida:** no `cmd_pos_yaw` a taxa de guinada ficou em média 5.8°/s e no máximo **14°/s**, contra 39°/s que o
  barco faz com os motores direto (`curvas_p1p2`). Os ganhos `kp_yaw = kd_yaw = 1.2` do BlueBoat foram calibrados
  sem amortecimento de guinada; com a P2, o momento pedido `kd·(kp·erro − r)` equilibra o amortecimento numa taxa
  baixa. Regime teórico (casco 70% submerso): erro de rumo 60° → **7.9°/s** (antes da P2 era 20.5°/s); 90° → 10.8°/s.
  O barco vira devagar demais para os laços de ~1.25 m de raio e atrasa até o cruzamento.
- A velocidade de avanço também é baixa: `v_des = kp_pos·dist = 0.1 × 1.5 m = 0.15 m/s`.

### Proposta P3 (NÃO aplicada — aguardando o usuário)
- Recalibrar o controlador de guinada do BlueBoat para o novo amortecimento: em `BlueBoat._params`,
  **`kd_yaw` 1.2 → ~10** (mantendo `kp_yaw = 1.2`). A conta de regime dá ~30°/s com 60° de erro de rumo.
  É só mudança de parâmetro, sem alterar código. Depois, repetir `--follow figure8` e `--follow sine`.
- Opcional: `kp_pos` 0.1 → 0.3 para andar a ~0.45 m/s com lookahead de 1.5 m.

## P3 — ganhos do controlador do BlueBoat (2026-09-28)

### Alteração aplicada (autorizada: "Sim, pode aplicar e testar novamente")
- `~/biguasim`, branch `testes-biguagym`, commit **`53ad1f9d`**, `dynamics/agents.py` (`BlueBoat._params`):
  `kd_yaw` 1.2 → **10.0** e `kp_pos` 0.1 → **0.3**. O "sim" foi interpretado como resposta às duas perguntas
  (P3 e o `kp_pos`, que era opcional). `kp_yaw` continua 1.2.
- Regime teórico com os novos ganhos (casco 70% submerso): erro de rumo 30° → 15.9°/s; 60° → **27.1°/s**; 90° → 36.2°/s.

### Testes (log em `smoke_results/blueboat_p3.log`; todos com `exit=0`, ~20 steps/s e 0 processos no fim)
- `--tag oito_p3 --follow figure8 --lookahead 1.5 --steps 3000`
- `--tag seno_p3 --follow sine --lookahead 1.5 --steps 3000`
- `--tag cmd_pos_yaw_p3 --control cmd_pos_yaw --action 'ponto_frente@200:108,100,0,0;ponto_lado@200:108,106,0,0;volta_origem@200:100,100,0,0'`

| Percurso | Antes da P3 (`oito_follow` / `seno_follow`) | Com a P3 |
|---|---|---|
| **8**, tempo | 1663 passos (83 s) | **1036 passos (52 s)** |
| 8, desvio médio / máx | 0.47 / 1.00 m | **0.40 / 1.29 m** |
| 8, % passos a <0.5 m | 53% | **74%** |
| 8, formato | oval, sempre horário (yaw -383°) | **8 de verdade**: cruza o centro e o laço esquerdo sai anti-horário (yaw vai a -250° e volta a +76°) ✅ |
| 8, guinada | máx 14°/s | p95 35.8°/s, máx 50.3°/s |
| **Seno**, tempo | 1965 passos (98 s) | **868 passos (43 s)** |
| seno, desvio médio / máx | 0.34 / 0.67 m | **0.28 / 0.59 m** |
| seno, % passos a <0.5 m | 79% | **85%** |

`cmd_pos_yaw` (erro final até o alvo de cada segmento de 10 s):
| Segmento | Antes da P3 | Com a P3 |
|---|---|---|
| ponto_frente (108, 100) | 5.04 m, v 0.30 | **2.60 m, v 0.54** |
| ponto_lado (108, 106) | 5.61 m, yaw +49° | 4.02 m, yaw +101° |
| volta_origem (100, 100) | 6.54 m, yaw +155° | **2.10 m, v 0.83, yaw +222°** (virou para voltar) |

Gráficos: `smoke_results/BlueBoatNav-v0__{oito_p3,seno_p3}/trajetoria.png`.

### Situação do BlueBoat
- Funciona: frente/ré (motores e `cmd_vel`), giro no sentido certo com amortecimento de barco, curvas de raio
  ~1.4 m a ~36°/s, `cmd_pos_yaw` apontando e indo para os alvos, 8 e seno do biguagym seguidos em malha fechada.
- Limitações que continuam: os laços do 8 e o seno saem achatados (lookahead de 1.5 m corta a curva; amplitude
  ~±0.6 m contra ±1.25 m no 8); `cmd_vel` com erro de regime (1 m/s → 0.44 m/s); `cmd_vel_yaw` interpreta Δyaw como
  relativo a cada passo.
- **Pendente:** oscilação vertical sem amortecimento (z entre -0.13 e -0.025, período ~1.5 s) em todas as rodadas.
- Os valores de P2 (`yaw_damp_lin`/`quad`) e P3 foram escolhidos por mim, sem referência do barco real. **Revisar.**

---

# Resumo da sessão de 2026-09-28 (encerramento)

## Estado das etapas do CLAUDE.md
| Etapa | Situação |
|---|---|
| 1 — Ambiente de execução | ✅ Venv novo `/home/teteu/venv-biguagym` (Python 3.12); `requirements-venv.txt` e `requirements-lock.txt`. GPU RTX 3050 6 GB. |
| 2 — Registro | ✅ 54 ids (20 v0, 20 v1, 14 v2). `DjiMatriceLand-v2`/`HydroneLand-v2` são `LandCoopPixelEnv`, fora da convenção v2. |
| 3 — DjiMatriceLand-v0 | ✅ Com patches (ver abaixo). 20 steps/s, reset 2.2 s, obs 19, ação 4, sem NaN, `obs_in_space` ok. Landing pad não aparece nos frames. |
| 4 — Todos os v0 / v2 | ⚠️ Parcial: ok BlueBoat Nav/Trajectory e BlueROV2 Dock/Nav/Trajectory. **BlueROVHeavy crasha o Unreal** (`Assertion failed: SpawnedAgent`). Faltam DjiMatrice Hover/Nav/Trajectory, Torpedo, Hydrone (sem modelo de dinâmica) e todos os v2. |
| 5 — Vazamento do simulador | ⚠️ Confirmado indiretamente em todos os testes (`sim_alive_after_env_close: true`; `atexit` do biguasim segura a referência). A run com `run.py` **não foi feita** (sem treino por decisão do usuário). Spec `vazamento-simulador` não aberta. |
| 6 — Pixels (v1) | ❌ Não iniciada. |
| 7 — Relatório final | ❌ Não iniciado. |

## Contexto que mudou o plano
- O biguagym foi escrito para o **biguasim 1.1.0** (estava no `environment.yml` antes do commit `1d9bfed`), que não está
  disponível. O instalado é o 1.0.0 (branch `sitl-test`), incompatível: bug em `action_space`, estado aninhado por
  agente, Hydrone sem dinâmica. A versão do TCC (`~/biguasim_tcc`) é igual e **não foi alterada**.
- Os autores devem publicar a versão nova do simulador na **quarta-feira, 2026-09-30**. Até lá, os testes rodaram
  com patches temporários, a pedido do usuário. **Nenhum treino foi feito.**

## Estado dos repositórios (nada foi enviado para remoto)
| Repositório | Branch ativa | Commits desta sessão | Não commitado |
|---|---|---|---|
| `biguagym-v0.1.0` (principal) | `testes-ambientes` | nenhum | ponteiro do submódulo alterado; novos: `TESTES.md`, `smoke_test.py`, `requirements-venv.txt`, `requirements-lock.txt`, `smoke_results/` (454 MB); `CLAUDE.md` e `specs/` já existiam como não rastreados |
| `biguagym` (submódulo) | `testes-ambientes` | `32698e5` patch temporário (`_unwrap_state` + `action_space` pela dinâmica) | — |
| `~/biguasim` | **`testes-biguagym`** | `8dc366a0` action_space; `e4f8ff9a` guinada do Catamaran; `cd2905fa` P1 + P2; `53ad1f9d` P3 | `biguasim_docs/packages/SkyDive.zip` (já existia) |
| `~/biguasim_tcc` | `main` | nenhum | nenhum |

⚠️ **`~/biguasim` é instalação editável também do `venv-ardupilot`.** Com `testes-biguagym` ativa, o SITL/ardubridge usa a
física do BlueBoat alterada (guinada, amortecimento, ganhos). Para voltar: `git -C ~/biguasim switch sitl-test`.

## Arquivos criados/alterados nesta sessão (todos com motivo registrado nas seções acima)
- `TESTES.md`: este registro.
- `smoke_test.py`: criado (não existia); depois ganhou `--show-viewer`, `--filter` repetível (os dois sem autorização
  explícita, antes da regra 6), `--action`, `--control`, `--no-reset`, `--tag` e `--follow`/`--lookahead`/`--laps` (autorizados).
- `requirements-venv.txt`, `requirements-lock.txt`: dependências do venv novo.
- `biguagym/core/environments.py` (submódulo): patch temporário para o biguasim 1.0.0.
- `~/biguasim/src/biguasim/agents.py`, `dynamics/usv.py`, `dynamics/agents.py`: correções/ajustes do BlueBoat.
- Scripts auxiliares **só no scratchpad da sessão** (serão perdidos): `check_imports.py`, `diag_state.py`,
  `gen_percursos.py` (percursos em malha aberta) e `analisa_percurso.py` (métricas e gráfico). O `--follow` do
  `smoke_test.py` substitui os dois últimos.

## Bugs confirmados
1. biguasim `agents.py:182`: `action_space` lê `_current_control_abstraction` (inexistente) → crash em qualquer env. Todas as branches.
2. biguasim 1.0.0 devolve o estado aninhado `{'robot': [ {...} ]}`; o biguagym espera o plano.
3. biguasim `ModelsFactory` sem Hydrone (13 envs).
4. Binário do mundo não cria `BlueROVHeavy` (8 envs) — provável renomeação para `BlueROV2Heavy` (`origin/main` `dec40557`).
5. biguagym `_init_spaces`: `action_space` vinha do esquema Unreal (BlueBoat/BlueROV com 3 dims ±10), e não dos motores.
6. biguasim `Catamaran._compute_body_wrench`: guinada só pelo contra-torque (~90× menor, sinal trocado) → o barco não girava.
7. biguasim Catamaran: controladores de alto nível com o sinal do `M_yaw` invertido (compensava o bug 6).
8. biguasim Catamaran: amortecimento de guinada quase nulo; com a guinada corrigida, o barco girava "no gelo".
9. biguagym `BiguaGymEnv.close()` não encerra o simulador (Etapa 5).
10. biguasim não detecta a morte do simulador e fica bloqueado até 900 s no primeiro tick.

## Descartado
- "Trava e volta" do BlueBoat: não aparece na física com ação constante (velocidade sobe de forma monotônica). Vinha das
  ações aleatórias do smoke test.

## Pendentes para a próxima sessão
1. **Quando a versão nova do biguasim chegar:** voltar `~/biguasim` para a branch nova, reinstalar (`pip install -e` no
   `venv-biguagym`), refazer o `smoke_test.py` e conferir se os bugs 1–4 sumiram. Verificar se as correções 6–8 do
   BlueBoat entraram; se não, levá-las aos autores. O patch do submódulo (`32698e5`) deve deixar de ser necessário.
2. Oscilação vertical do BlueBoat (z entre -0.13 e -0.025 m, período ~1.5 s, sem amortecer). O usuário resolveu algo
   parecido no BlueROV; comparar a abordagem.
3. Revisar os valores escolhidos sem referência do barco real: `yaw_damp_lin = 10`, `yaw_damp_quad = 17`, `kd_yaw = 10`, `kp_pos = 0.3`.
4. Etapa 4: DjiMatrice Hover/Nav/Trajectory-v0, v2; teste de movimentos do BlueROV2 e do DjiMatrice.
5. Etapas 5 e 6 → specs `vazamento-simulador`, `logs-por-run`, `pipeline-pixels`.
6. `smoke_results/` tem 454 MB (frames 1280×720): decidir se entra no `.gitignore`.

### Após o encerramento (2026-09-28): biguasim de volta à `sitl-test`
- Pedido do usuário: "volta o biguasim para a sitl-test".
- Comando: `git -C ~/biguasim switch sitl-test`. HEAD em `b0c6685e`, working tree limpo (só o `SkyDive.zip` não rastreado, que
  já existia). Conferido: nenhum "PATCH testes-biguagym" em `usv.py`/`agents.py`, e `agents.py:182` voltou ao original.
- A branch `testes-biguagym` (4 commits) foi **mantida** para uso futuro. O `venv-ardupilot` e o `venv-biguagym` agora
  usam o código da `sitl-test`.
- Consequência: sem a `testes-biguagym`, **o `smoke_test.py` volta a falhar no `gym.make`** (bug 1). Para testar de
  novo com os patches: `git -C ~/biguasim switch testes-biguagym`.

### Commit no repositório principal (2026-09-28)
- Pedido do usuário: "faz o commit dos arquivos novos na testes-ambientes". Escolhas do usuário: do `smoke_results/`,
  só os arquivos leves; incluir `CLAUDE.md` e `specs/README.md`; **não** incluir o ponteiro do submódulo.
- Commit na `testes-ambientes`, mensagem "Testes dos ambientes biguagym no BiguaSim 1.0.0 (sessão 2026-09-28)" (68 arquivos, `.git` com 2.0 MB): `TESTES.md`, `smoke_test.py`,
  `requirements-venv.txt`, `requirements-lock.txt`, `CLAUDE.md`, `specs/README.md`, `smoke_results/resumo.csv` e, em cada
  pasta de resultado, `summary.json`, `trajectory.csv` e `trajetoria.png`.
- Ficaram fora, não rastreados: `smoke_results/*/frames/` (~451 MB), `smoke_results/*/log.txt`, os `*.log` (já ignorados
  pelo `.gitignore` via `*log`) e o ponteiro do submódulo (`a05e14b` → `32698e5`, que só existe localmente). O
  `.gitignore` não foi alterado.
- Esta seção foi escrita depois do commit (hash original `65abbc7`) e incluída nele com `git commit --amend`, a pedido
  do usuário ("inclui o TESTES.md no commit"). O amend mudou o hash; para ver o atual: `git log -1 testes-ambientes`.
