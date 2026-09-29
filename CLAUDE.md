# Teste dos ambientes biguagym no BiguaSim

## Contexto

Este repositório (`biguagym-v0.1.0`) é um harness de treino de RL (Hydra, `run.py`,
`workspace.py`, `logger.py`, agentes TD3/PPO/SAC/DDPG/CUPRL em `src/agents/`).
Os ambientes vêm do repositório `biguagym`, que é um submódulo git em `./biguagym`
(`register.py` registra 54 ids no gymnasium; classes em `biguagym/core/environments.py`).

- Simulador: BiguaSim (derivado de Holodeck/HoloOcean, processo Unreal separado).
- Mundo: todos os configs usam `"world": "Pier-Harbor"`, pacote `SkyDive`.
- Convenção de ids: `-v0` estado (vetor), `-v1` pixels (Dict de imagens), `-v2` estado + range/sonar.
- O objetivo final é rodar ~100k timesteps em ~10 ambientes principais (ver `train_routines.yaml`)
  e testar diferentes sensores, para um artigo. **Agora a tarefa é só validar os ambientes.**

## Regras

1. Antes de modificar qualquer arquivo do código original, crie uma branch `testes-ambientes`
   (no repositório principal e no submódulo). Nunca faça commit na main.
2. Não rode treinos longos (> 5k steps) sem me perguntar antes. O simulador parece rodar
   em tempo real (~20 steps/s), então 100k steps ≈ 1,4 h.
3. Depois de cada teste, verifique se sobrou processo do simulador aberto
   (`ps aux | grep -i -E "biguasim|holodeck|unreal"`) e me avise se houver processos órfãos.
   Não mate processos que não foram iniciados por você.
4. Registre tudo o que fizer, os resultados e os problemas encontrados em `TESTES.md`
   (crie o arquivo), com data, comando rodado e resultado.
5. Se algo falhar, mostre o traceback completo e proponha a correção antes de aplicá-la.
6. Arquivos de apoio (`CLAUDE.md`, `smoke_test.py`, `.claude/skills/`, `specs/*/template.md`)
   só podem ser alterados com minha autorização. Se precisar mudar, explique antes o quê e por quê.
7. Antes de encerrar cada etapa ou tarefa, atualize o `TESTES.md` com: o que foi feito,
   comandos rodados, resultados, arquivos criados ou alterados e decisões tomadas.
   Só depois me mostre o resumo.
8. Toda alteração em qualquer arquivo deve ser registrada no `TESTES.md` (ou no `log.md` da spec),
   com o motivo.

## Etapas

### Etapa 1 — Ambiente de execução
- Confira se `./biguagym` tem conteúdo (`register.py`, `core/`, `config/`). Se estiver vazio,
  tente `git submodule update --init --recursive` e me avise se falhar (acesso privado / git-lfs).
- Confira se `biguasim`, `gymnasium`, `torch`, `hydra-core`, `cv2`, `scipy`, `dm_env` importam.
  Compare com `environment.yml` e liste o que falta, sem instalar nada sem me perguntar.
- Rode `nvidia-smi` e registre GPU, VRAM total e livre.

### Etapa 2 — Registro dos ambientes
- Rode `python smoke_test.py --list` e confirme que aparecem 54 ids.

### Etapa 3 — Primeiro ambiente, com visualização
- Rode `python smoke_test.py --env DjiMatriceLand-v0 --steps 200`.
- Leia `smoke_results/DjiMatriceLand-v0/summary.json` e resuma: espaços de observação e ação,
  sensores carregados, `steps_per_s`, `hours_per_100k`, NaN/inf, `obs_in_space`,
  posição inicial e final.
- Abra algumas imagens em `smoke_results/DjiMatriceLand-v0/frames/` e descreva o que aparece
  (o mapa, o veículo, o landing pad desenhado).
- Confirme se `steps_per_s` fica em torno de 20 (limite `ticks_per_sec`/`frames_per_sec` = 20).

### Etapa 4 — Todos os ambientes de estado
- Rode `python smoke_test.py --all --filter v0 --steps 200 --frame-every 100`.
- Monte em `TESTES.md` uma tabela a partir de `smoke_results/resumo.csv`: ambiente, ok/erro,
  steps/s, dimensão da observação, dimensão da ação, NaN/inf.
- Para cada ambiente com erro, identifique a causa no código.
- Depois repita com `--filter v2` (range/sonar) e compare as dimensões de observação com o
  esperado: aéreo +10 (RangeFinder), subaquático +100 (sonar), BlueBoat/Hydrone +110.

### Etapa 5 — Suspeita de vazamento do simulador de avaliação (bug dos ~800k steps)
Hipótese: `Workspace.evaluate()` cria um ambiente novo a cada avaliação e
`BiguaGymEnv.close()` (em `biguagym/core/base_env.py`) só faz `del self._env`, sem encerrar o
processo do simulador. Com `eval_freq: 100000`, no step 800k haveria ~10 simuladores abertos.
- Antes de corrigir, reproduza: rode
  `python run.py env=BlueBoatNav-v0 agent=td3 num_train_steps=3000 eval_freq=500 num_eval_episodes=1 runs=1 agent.learning_starts=500`
  e, em paralelo, registre a cada 10 s o número de processos do simulador e a VRAM usada.
- Relate se o número de processos cresce a cada avaliação.
- Investigue no pacote `biguasim` instalado qual é o método correto para encerrar o simulador
  (procure `__exit__`, `close`, `atexit`, `__on_exit__`) e proponha a correção em `close()`.
- Observação: `logger.py` abre `fault.log` e `crash.log` com modo `"w"`, então cada execução apaga
  os logs da anterior. Proponha salvar esses logs por run.

### Etapa 6 — Ambientes de pixel (v1)
Suspeita: `PixelStack.append` usa `np.resize(raw[k], (3, H, W))`, que não interpola nem
transpõe; com câmera 1280×720 e frame 84×84 só ~0,8% da imagem é usada.
- Rode `python smoke_test.py --env DjiMatriceLand-v1 --steps 100 --frame-every 25`.
- Compare `frames/cam_*.png` (câmera real) com `frames/obs_rgb_*.png` (o que a rede recebe)
  e descreva a diferença.
- Proponha a correção (redimensionar com `cv2.resize` e depois `transpose(2, 0, 1)`),
  mas não aplique sem me mostrar.

### Etapa 7 — Relatório
Ao final, escreva em `TESTES.md` um resumo com:
- quais ambientes funcionam, quais falham e por quê;
- velocidade medida e estimativa de tempo para 100k steps × 10 ambientes × 3 seeds;
- bugs confirmados e bugs descartados, cada um com a evidência;
- lista de correções propostas, em ordem de prioridade.

## Fluxo de desenvolvimento por spec

Toda alteração de código (correção de bug, otimização, sensor novo) segue o fluxo de spec,
implementado como skills em `.claude/skills/spec-*` (cada uma com um `template.md`).
Testes e investigação (smoke tests, leitura de código, runs curtas de diagnóstico) não precisam de spec.

1. `/spec-requisitos <nome> <objetivo>` → `specs/<nome>/requirements.md`
2. `/spec-design <nome>` → `specs/<nome>/design.md`
3. `/spec-tarefas <nome>` → `specs/<nome>/tasks.md`
4. `/spec-executar <nome>` → implementa uma tarefa por vez, com commit e `log.md`
5. `/spec-status` → andamento de todas as specs

Regras do fluxo:
- Nunca pule uma fase. Cada arquivo começa com `Status: rascunho` e só avança quando eu mudar para `Status: aprovado`.
- Nas fases 1 a 3, não altere código, apenas escreva nos arquivos da spec.
- Cada spec trabalha na sua própria branch `spec/<nome>`, criada a partir da `testes-ambientes`.
- Se durante a execução o design se mostrar errado, pare, atualize o design.md com a mudança e peça nova aprovação.
- As correções propostas nas Etapas 5 e 6 viram specs (`vazamento-simulador`, `logs-por-run`, `pipeline-pixels`).
