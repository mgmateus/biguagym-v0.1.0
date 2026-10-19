Status: aprovado

# ajuste-ambientes — Design

Design aprovado em 2026-10-19 ("aprovado, pode deixar o ROV em 60° também"). Requisitos aprovados em 2026-10-19 ("aprovado, só aumenta o limite de inclinação do drone"). Mudanças no submódulo,
numa branch `spec/ajuste-ambientes` do fork `ttszin/biguagym` a partir de `fcf4358` (recompensa v1), como na spec
`recompensas`.

## Arquivos afetados
| Arquivo | Mudança |
|---|---|
| `biguagym/core/environments.py` | Parâmetro `env_version` (`"v1"` padrão, `"v0"` = original) nos 13 construtores; spawn subaquático mais fundo; tetos de Hover/Land/Dock; limite de inclinação por domínio (`_tilt_limit`); alvo do barco na superfície; alvo relativo na observação (Hover/Nav/Land/Dock e variantes) |
| `tests/recompensas_util.py` | Ambientes falsos ganham `_env_version = "v0"` (os testes da spec `recompensas` usam a geometria original: inclinação de ~20° tem de terminar o episódio) |
| `tests/test_ajuste_ambientes.py` (novo) | Testes sem simulador de R1–R5 |
| `tools/diag_termino.py` | Aceita `env_version` (para comparar v0 × v1 com o mesmo script) |
| ponteiro do submódulo em `spec/ajuste-ambientes` | Aponta para o commit novo do fork |
| `treinos/cluster/runs_250k.csv`, `LEIAME.md` | Sem mudança de conteúdo: os 250k usam os padrões (`reward_version=v1`, `env_version=v1`) |

## Solução proposta

### Versão do ambiente (R5)
Parâmetro separado do `reward_version`, para a linha de base continuar reproduzível com as duas opções originais:
```python
def __init__(self, seed, agent_type, ..., reward_version: str = "v1", env_version: str = "v1"):
    if env_version not in ("v0", "v1"):
        raise ValueError(f"env_version inválido: {env_version!r} (use 'v0' ou 'v1')")
    self._env_version = env_version
```
- As 12 subclasses com `__init__` próprio repassam `env_version` como já fazem com `reward_version`.
- Linha de base de 100k: `+env_kwargs.reward_version=v0 +env_kwargs.env_version=v0`.
- Com `env_version="v0"`, todo o código abaixo segue o caminho original, sem refatorar as expressões antigas.

### Spawn e limites em z (R1)
Constantes novas em `HoverEnv`:
```python
UNDERWATER_SPAWN_Z = -1.5   # BlueROV2/Heavy/Torpedo nascem em -0,2 no register.py
AIR_CEILING_ABOVE_SPAWN = 5.0
```
1. **Spawn subaquático** (`HoverEnv.__init__`, antes de `_build_params`, porque a cena e o caminho da Trajectory saem
   de `self._location`):
   ```python
   if env_version == "v1" and agent_type in DOMAIN['underwater'] and location[2] > self.UNDERWATER_SPAWN_Z:
       location = [location[0], location[1], self.UNDERWATER_SPAWN_Z]
   ```
   Teto subaquático continua −0,1 (Nav/Trajectory) → folga de 1,4 m. A Trajectory constrói o caminho a partir do spawn
   novo, então continua ancorada no veículo.
2. **Teto do Hover/Land** (`HoverEnv._build_params`): hoje `max(z_spawn, 2·z_min)` = 5,0 (= spawn). Na v1:
   `self._bounds[1, 2] = loc[2] + AIR_CEILING_ABOVE_SPAWN` (10 m). O piso continua `max(z_spawn − 10, 0,1)`.
   Efeito colateral: no Hover o alvo é sorteado no volume todo, então passa a poder ficar até 10 m de altura.
3. **Teto do Dock** (`DockEnv._build_params`): hoje `min(z_spawn, −0,2)` = spawn. Na v1: `self._bounds[0, 2] = -0.1`
   (superfície), fundo continua −10. Com o spawn em −1,5: 1,4 m até o teto e 8,5 m até o fundo.
4. Nav aéreo ([0; 15], spawn 5) e de superfície ([−1; 0,1]) não mudam.

| Ambiente (v1) | Spawn z | Limites z | Folga até o teto / piso |
|---|---|---|---|
| DjiMatriceLand / Hover | 5,0 | [0,1; 10,0] | 5,0 / 4,9 |
| DjiMatriceNav | 5,0 | [0; 15] | 10 / 5 (igual a hoje) |
| BlueROV2Dock | −1,5 | [−10; −0,1] | 1,4 / 8,5 |
| BlueROV2Nav | −1,5 | [−20; −0,1] | 1,4 / 18,5 |
| BlueROV2TrajectoryFollower | −1,5 | [max(z_min−5; −20); −0,1] | 1,4 / ≥ 5 |

### Limite de inclinação (R2)
Um método usado nos `_step` de Hover/Nav, Land, Dock, Trajectory e LandCoop (hoje cada um tem `np.radians(15)` fixo):
```python
TILT_LIMIT_DEG = {'aereo': 60.0, 'multi-domain': 60.0, 'underwater': 60.0, 'surface': 15.0}

def _tilt_limit(self) -> float:
    if self._env_version == "v0":
        return np.radians(15)
    dom = next((d for d, tipos in DOMAIN.items() if self._agent_type in tipos), 'aereo')
    return np.radians(self.TILT_LIMIT_DEG[dom])
```
- **Drone (decisão do usuário): 60°**, mantendo `cmd_motor_speeds`. Acima de ~60° o quadricóptero perde sustentação e
  não se recupera; entre 15° e 60° ele ainda pode voltar.
- **BlueROV2: 60°.** O requisito R2 aprovado vale para todos os domínios; o ROV tem estabilidade passiva (flutuação)
  e se recupera de inclinações maiores. Se o usuário preferir mexer só no drone, basta pôr 15° aqui.
- **Barco: 15° (sem mudança):** nunca terminou por inclinação no diagnóstico.
- O termo `stable` da recompensa continua penalizando a inclinação (saturando em 35°), então inclinar ainda custa.

### Alvo do barco na superfície (R3)
`HoverEnv._reset` (o Nav herda): na v1, para `DOMAIN['surface']`, o z do alvo é o z do spawn (0), não um sorteio em
[−1; 0,1]. x e y continuam sorteados no quadrado de ±10 m.

### Alvo na observação (R4)
Atributo de classe `_HAS_TARGET = True` em `HoverEnv`; `TrajectoryEnv._HAS_TARGET = False` (ele já tem o caminho na
observação e não tem `_target`).
```python
# HoverEnv._init_spaces: total_dim += 3 se v1 e _HAS_TARGET
# HoverEnv._wrap_state:
obs = np.concatenate([...sensores...])
if self._env_version == "v1" and self._HAS_TARGET:
    rel = (np.asarray(self._target) - np.asarray(self._dynamics[6:9])) if self._target is not None else np.zeros(3)
    obs = np.concatenate([obs, rel.astype(np.float32)])
```
- Ordem segura: em todos os `_reset` o alvo é sorteado **antes** do `_wrap_state`; no `_step` o alvo é fixo (no LandCoop
  ele é atualizado antes do `_wrap_state`).
- Variantes: o `_RangeObsMixin` (v2) e o `_PixelObsMixin` (v1, parte `state` do Dict) leem o tamanho do
  `observation_space` do `HoverEnv` e chamam `super()._wrap_state`, então recebem os 3 valores sem mudança.
- Alvo em coordenadas do mundo, relativo à posição (não no referencial do corpo): o agente já recebe os ângulos na
  própria observação.

### Testes sem simulador (`tests/test_ajuste_ambientes.py`)
Mesma técnica do `recompensas_util.py` (`object.__new__` + atributos injetados): `_build_params` só lê os JSON de
configuração e não abre o simulador. A Trajectory monta os limites no `__init__` depois do simulador; para ela, a
verificação é com o simulador (smoke e `diag_termino.py`).

## Alternativas consideradas
- **Reaproveitar o `reward_version`** para estas mudanças — descartada: misturaria geometria e recompensa; a
  comparação "recompensa nova com ambiente antigo" ficaria impossível.
- **Mudar o `location` no `register.py`** — descartada: valeria também para `env_version="v0"` e quebraria a
  reprodução da linha de base (R5).
- **Teto do Dock em `spawn + 1`, sem mexer no spawn** — descartada: com spawn em −0,2 o teto passaria da superfície.
- **Ação relativa à rotação de hover ou `cmd_vel` no drone** — descartadas pelo usuário (2026-10-19).
- **Alvo no referencial do corpo** — adiada: exige rotação pelo yaw/roll/pitch e não é necessária para o agente
  aprender (os ângulos já estão na observação).

## Riscos
- **Observação +3:** modelos salvos da linha de base não carregam nos ambientes v1 → só com `env_version=v0`. Registrado.
- **Spawn em −1,5 m no Pier-Harbor:** pode haver estrutura (píer) ou fundo perto de (100, 100) → conferir nos frames
  do smoke e no `diag_termino.py` (z inicial e `out_of_bounds`).
- **Drone a 60° com `cmd_motor_speeds`:** com ação aleatória ainda deve virar em poucos passos (só mais devagar) →
  critério de aceitação é "mediana maior que a de hoje (6 e 4)", não ≥ 20; registrado como limitação conhecida.
- **Mudança vale para todos os veículos do domínio** (BlueROVHeavy, Torpedo, Hydrone, LandCoop) → smoke de todos os v0/v1/v2
  da fila (24) depois da mudança.
- **Testes da spec `recompensas`** dependem da inclinação de 15° → `recompensas_util.make` fixa `_env_version="v0"`;
  os 35 testes têm de continuar passando.
- **Hover com alvo até 10 m de altura** (antes 5 m): o Hover não está nos 250k; registrado.

## Plano de verificação
| Requisito | Como verificar |
|---|---|
| R1 | `pytest tests/test_ajuste_ambientes.py`: `_bounds` e spawn de Hover/Land (DjiMatrice), Dock e Nav (BlueROV2) com folga ≥ 1 m, teto subaquático ≤ −0,1, piso aéreo ≥ 0; com `env_version="v0"`, valores de hoje |
| R1, R2 | `python tools/diag_termino.py <env> 300` (v1) em BlueROV2Dock, DjiMatriceLand, BlueROV2Nav, BlueROV2TrajectoryFollower: ação aleatória com mediana ≥ 20 passos e `out_of_bounds` < 50% |
| R2 | idem em DjiMatriceNav e DjiMatriceLand: mediana maior que 6 e 4 (v0); teste unitário: 30° não termina no drone v1 e termina na v0 |
| R3 | teste unitário: 1000 sorteios do alvo do BlueBoat com z = z do spawn; x, y dentro de ±10 m |
| R4 | teste unitário: `observation_space` = sensores + 3 (Hover/Nav/Land/Dock) e igual a hoje na Trajectory e na v0; últimos 3 valores = alvo − posição; smoke: dimensões v0/v1/v2 +3 em relação à tabela de 2026-10-11 (exceto Trajectory) |
| R5 | `pytest tests/`: com `env_version="v0"`, limites/spawn/inclinação/alvo/observação iguais aos de hoje; os 35 testes da spec `recompensas` continuam passando |
| R6 | `python smoke_test.py --list` → 54 ids; smoke de 200 passos nos 24 ambientes da fila (v0/v1/v2) → todos `ok`, 0 simuladores sobrando |
| Geral | Pilotos TD3 de 5000 passos em BlueROV2Dock-v0, DjiMatriceLand-v0 e BlueBoatNav-v0 (notebook): rodam sem erro; Dock e Land com episódios mais longos que na linha de base no mesmo trecho |
