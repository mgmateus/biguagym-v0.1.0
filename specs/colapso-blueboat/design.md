Status: aprovado

# colapso-blueboat — Design

Design aprovado em 2026-10-20 ("aprovado, pode seguir para as tarefas"). Requisitos aprovados em 2026-10-20 ("aprovado, segue suas sugestões nas perguntas em aberto"). Correção primeiro no
ambiente; o TD3 só entra se o piloto ainda colapsar, e de forma opcional.

## O que o código mostra (leitura feita nesta fase)

**Física usada nos treinos.** O `venv-biguagym` usa `~/biguasim-treino` (`53ad1f9d`, branch `testes-biguagym`), e o
PC do lab usa o mesmo commit (`setup/instalar_pc_lab.sh`). O `~/biguasim` na `sitl-test` **não** tem as correções do
giro, mas não é o usado nos treinos. No `Catamaran` (`dynamics/usv.py`) e no `BlueBoat._params` (`dynamics/agents.py`):
- empuxo por motor `T = k_eta·w·|w|`, com `k_eta = 3,55e-3` (o patch local de 10×). No limite (+288 / −296 rad/s)
  dá **+294 N / −311 N** para um barco de 14,5 kg;
- guinada `mt_z = −Σ yᵢ·Tᵢ + contratorque`, com braço y = ±0,285 m, contra o amortecimento
  `10·r + 17·r|r|` (P2). Com os motores opostos no limite, `mt_z` ≈ 172 N·m e o equilíbrio fica em **r ≈ 2,9 rad/s**,
  a mesma taxa medida na política colapsada (3,1 rad/s);
- com os dois motores para frente no limite, a velocidade final estimada é ~3,9 m/s (1,62 m/s medido com 120 rad/s,
  e a força cresce com w²). Os 10 m até a borda passam em ~2,5 s, ~50 passos.

**Ambiente** (`biguagym/core/environments.py`):
- o alvo é sorteado em **todo** o volume de `_bounds` (`HoverEnv._reset`), que também é o limite de saída
  (`NavEnv._build_params`: ±10 m em x e y). Um alvo na borda exige parar a 0,15 m dela sem passar;
- o sucesso exige `dist ≤ 0,15 m` (`_reward`, `_on_target`), muito apertado para um barco que anda a ~3,9 m/s e
  não tem freio;
- a ação é a velocidade dos motores em rad/s, sem normalização (`HoverEnv._init_spaces`): o `Box` vai de −295,75 a
  288,08.

**Agente** (`src/agents/td3.py`): o ator usa `tanh·escala` (±290), mas o crítico recebe a ação **crua**, na casa das
centenas, ao lado de observações de ordem 1 a 100. É um cenário clássico para o gradiente do ator empurrar a ação
para um canto do `Box` e o `tanh` saturar. Dos cantos, "girar" é o único que não termina o episódio (os outros saem
da área em ~50 passos), então é o canto que sobra.

**Por que o Trajectory aprende:** a recompensa dele é densa desde o primeiro passo (`cte` e `align` ao longo do
caminho) e recompensa andar devagar sobre o caminho, então o crítico tem sinal antes de o ator saturar.

## Arquivos afetados
| Arquivo | Mudança |
|---|---|
| `tools/diag_referencia.py` (novo) | R1/R2: avalia 4 políticas fixas no BlueBoatNav-v0 (parado, girar, aleatória, controlador até o alvo) e imprime retorno, motivo do término e distância inicial/final por episódio |
| `tools/diag_politica.py` | Aceita `reward_version`/`env_version` (hoje fixo em `reward_version='v0'`); mede a fração de passos com **os dois** motores a ≥ 95% do limite e a distância inicial/final **por episódio** (R3, R4); lê ação normalizada da v2 |
| `biguagym/core/environments.py` | Nova `env_version="v2"` (padrão novo), igual à v1 em tudo, exceto no **BlueBoatNav** (superfície, com alvo): alvo sorteado com margem da borda, raio de sucesso de superfície e ação normalizada em [−1, 1] (detalhes abaixo) |
| `tests/test_colapso_blueboat.py` (novo) | Testes sem simulador: v2 = v1 fora do BlueBoatNav; margem do alvo; raio de sucesso; mapeamento da ação; v0/v1 iguais aos de hoje |
| `tests/test_ajuste_ambientes.py` | Só se algum teste fixar a lista `("v0", "v1")`: passar a aceitar `"v2"` |
| ponteiro do submódulo | Commit novo no fork `ttszin/biguagym`, branch `spec/colapso-blueboat` a partir de `ff452dc` |
| `treinos/cluster/LEIAME.md` | Uma linha: como reproduzir os runs feitos antes desta spec (`+env_kwargs.env_version=v1`) |

`src/agents/td3.py` **não** muda nesta spec, salvo pela etapa 4 abaixo (condicional, com nova aprovação do design).

## Solução proposta

Em etapas, cada uma só se a anterior não bastar. As etapas 1 e 2 não precisam de treino.

### Etapa 1 — Diagnóstico da recompensa (R1)
`tools/diag_referencia.py <env_id> [episodios=6] [env_version=v1]`, um ambiente por processo, limitado por passos
(sem `timeout`, por causa do órfão do Unreal). As mesmas sementes de alvo para as 4 políticas (`env.reset(seed=s)`):
```python
def controlador(u):                       # "aponta e acelera", em rad/s nos motores (r1 = bombordo, y > 0)
    pos, yaw = u._dynamics[6:9], u._dynamics[17]
    d = u._target[:2] - pos[:2]
    erro = np.arctan2(d[1], d[0]) - yaw; erro = (erro + np.pi) % (2*np.pi) - np.pi
    frente = np.clip(40.0 * np.linalg.norm(d), 0, 150) * max(np.cos(erro), 0)  # freia perto do alvo e quando desalinhado
    giro = np.clip(120.0 * erro, -150, 150)
    return np.clip([frente - giro, frente + giro], lo, hi)   # sinal do giro conferido no 1º episódio
POLITICAS = {'parado': lambda u: [0, 0], 'girar': lambda u: [hi, lo],
             'aleatoria': lambda u: env.action_space.sample(), 'controlador': controlador}
```
Saída `REF {json}`, com retorno médio, motivos de término, passos medianos e distância inicial/final média, por
política. ⏱ ~5 min (4 × 6 episódios × ≤ 400 passos a ~20 passos/s ≈ 8 min no pior caso).
Expectativa (pela conta à mão): controlador ≈ +20 a +30 (o `smooth` soma ~3 × a distância percorrida, mais +10 de
sucesso se chegar), parado ≈ 0, girar ≈ −230. Se for isso, **R2 já vale com a recompensa de hoje** e o problema está
no aprendizado, não no ranking das recompensas.

### Etapa 2 — Ajuste do BlueBoatNav (ambiente, `env_version="v2"`)
Uma versão nova, para que os 250k que estão rodando (v1) continuem reproduzíveis. A `v2` é igual à `v1` em todos
os ambientes **exceto** quando `_boat_nav_v2()` é verdadeiro:
```python
def _boat_nav_v2(self) -> bool:
    return self._env_version == "v2" and self._agent_type in DOMAIN['surface'] and self._HAS_TARGET
```
(`TrajectoryEnv._HAS_TARGET = False`, então o BlueBoatTrajectoryFollower não muda; o BlueBoatNav-v1/v2 de pixel e
sonar herda.)
- **Comparações de versão:** as 5 checagens `== "v1"` de hoje viram `!= "v0"` (validação passa a aceitar
  `("v0", "v1", "v2")`). Padrão do construtor: `"v2"`.
- **2a. Alvo com margem da borda** (`HoverEnv._reset`): no BlueBoatNav v2, x e y do alvo sorteados em
  `±(10 − 3) m` em torno do spawn (`TARGET_MARGIN_SURFACE = 3.0`). Sobra espaço para frear e corrigir sem sair.
- **2b. Raio de sucesso de superfície** (`HoverEnv._reward`): `SUCCESS_RADIUS = {'surface': 1.0}`, demais 0,15
  (no v2). Um BlueBoat real (1,2 m de comprimento) tem um raio de aceitação de ~1 m num waypoint. O `norm_reward`
  continua `exp(−2·dist)`; muda só o critério de `_on_target`.
- **2c. Ação normalizada** (`HoverEnv._init_spaces` e `HoverEnv._step`): no BlueBoatNav v2, `action_space =
  Box(−1, 1, (2,))`, e o `_step` converte para rad/s antes de chamar o simulador:
  ```python
  def _to_motor_speeds(self, a):            # 0 → 0 rad/s; ±1 → limites reais (assimétricos)
      a = np.clip(a, -1.0, 1.0)
      return np.where(a >= 0, a * self._motor_hi, -a * self._motor_lo)
  ```
  O crítico do TD3 (e de qualquer agente) passa a ver a ação em ±1, na mesma escala da observação. O ruído de
  exploração (0,1·escala) fica igual em termos relativos.

**Por que juntar 2a, 2b e 2c numa versão só:** cada piloto custa ~25 min de simulador e o objetivo aprovado é "não
colapsar e se aproximar". Testar uma de cada vez multiplicaria os pilotos. Se o piloto da etapa 3 passar, o log
registra que o efeito é do conjunto. Se o usuário quiser isolar a contribuição de cada uma, é uma tarefa opcional
depois.

### Etapa 3 — Piloto (R3, R4) ⏱
TD3, 15k passos, `agent.learning_starts=1000`, `eval_freq=1000000` (sem avaliação no meio, para não vazar
simulador), seed 0, no notebook, com o padrão novo (v2). Depois, `diag_politica.py` no `actor_last.pt`
(600 passos, `env_version=v2`). Comparação com o piloto T11 da `ajuste-ambientes` (v1, colapsou em ~2400 passos).

### Etapa 4 — Só se o piloto ainda colapsar (condicional)
Parar, atualizar este design e pedir nova aprovação. Candidatas, nesta ordem:
1. normalizar a observação do BlueBoatNav v2 (posição relativa ao spawn em vez de absoluta, ~100 m);
2. no TD3, opção `agent.algo.action_l2` (penalidade pequena em `‖tanh_pre‖²` no ator, contra a saturação),
   desligada por padrão (R5).

## Alternativas consideradas
- **Corrigir no TD3 primeiro (normalizar a ação no crítico)**: descartada pela decisão do usuário (ambiente
  primeiro). A 2c tem o mesmo efeito para o TD3 e vale para os outros agentes.
- **Normalizar a ação em todos os ambientes**: descartada. Mudaria todos os resultados do artigo (R5); pode virar
  spec própria se os 250k mostrarem saturação em outros ambientes (BlueROV2Nav e DjiMatriceTrajectory já saturavam
  na linha de base).
- **Mudar a v1 em vez de criar a v2**: descartada. Os 250k que estão rodando (BlueBoatNav é o 7º da fila) deixariam
  de ser reproduzíveis com um único parâmetro.
- **Ampliar a área (±20 m) em vez de afastar o alvo da borda**: descartada. Mais área com o mesmo episódio de 400
  passos deixa o alvo mais longe em média e a recompensa mais rara; a margem resolve a ultrapassagem sem isso.
- **Aumentar a penalidade de giro (`spin`)**: descartada como primeira opção. Girar já custa −0,6 por passo e é a pior
  das quatro políticas; o problema é o agente chegar nisso apesar da recompensa, não a recompensa favorecer isso.
- **Reduzir o `k_eta` do BlueBoat (empuxo de ~300 N, irreal)**: fora do escopo (é o simulador, `~/biguasim-treino`,
  e mudaria os outros runs do barco). Registrado como observação para os autores.

## Riscos
- **A etapa 1 mostrar o ranking errado** (controlador ≤ parado) → a etapa 2 continua igual (2a e 2b atacam
  exatamente a ultrapassagem e o raio), e o `diag_referencia.py` é rodado de novo com `env_version=v2` antes do piloto.
- **O controlador de referência ser ruim** e subestimar "ir até o alvo" → ele não precisa ser ótimo, só melhor que
  parado/girar. Se não for, ajustar os ganhos (é ferramenta, não ambiente) e registrar.
- **Padrão novo `v2` muda os runs futuros do BlueBoatNav** → os 250k atuais ficam como "v1, antes da correção"; o
  LEIAME documenta `+env_kwargs.env_version=v1` para reproduzi-los. Os outros 7 ambientes têm v2 ≡ v1 (testes).
- **Modelos salvos do BlueBoatNav v1** não servem na v2 (ação em outra escala) → `diag_politica.py` usa o
  `env_version` do run.
- **Piloto de 15k não ser suficiente** para ver aprendizado → o critério de R3 é relativo (melhor que a fase
  aleatória e sem saturar), alcançável em 15k; se não der, é informação para a etapa 4, não falha da spec.
- **Raio de 1 m deixa a tarefa mais fácil que a dos outros veículos** → registrado no impacto do artigo; vale só para
  a superfície.

## Plano de verificação
| Requisito | Como verificar |
|---|---|
| R1 | ⏱ `python tools/diag_referencia.py BlueBoatNav-v0 6 v1` → tabela das 4 políticas no `log.md`; 0 simuladores no fim |
| R2 | idem com `v2` → retorno(controlador) > retorno(parado) e > retorno(girar) |
| R3 | ⏱ piloto TD3 15k (v2) → retorno médio de treino em 5k–15k > retorno em 0–1k (curva/`train.csv`); `diag_politica.py ... 600 v1 v2` → `frac_dois_motores_saturados` < 0,5 |
| R4 | `diag_politica.py` → média da distância final por episódio < média da inicial |
| R5 | `pytest tests/` → os 66 de hoje + os novos passam; testes: v2 = v1 (limites, alvo, recompensa, espaços) em Hover/Land/Dock/Nav (drone, ROV) e BlueBoatTrajectory; v0 e v1 do BlueBoatNav iguais aos de hoje |
| R6 | `python smoke_test.py --list` → 54; ⏱ smoke de 200 passos em BlueBoatNav-v0/v1/v2 → 3/3 `ok`, ação `[-1, 1]` no `summary.json`, 0 simuladores |
