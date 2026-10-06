Status: rascunho (emenda de 2026-10-06 aguardando aprovação; o restante já foi aprovado)

# recompensas — Design

Decisões do usuário sobre as perguntas dos requisitos (2026-10-06, "aprovado, use as propostas e faça no fork"):
- mudar direto nas classes do submódulo, numa branch do fork `ttszin/biguagym`;
- penalidade de término −10; bônus de sucesso +10 (Hover/Nav) e +20 (Land/Dock);
- Trajectory: pagar o acompanhamento do caminho em proporção ao avanço;
- revisão dos autores: não definida; assumo mostrar depois.

## Arquivos afetados
| Arquivo | Mudança |
|---|---|
| `biguagym/core/environments.py` (fork `ttszin/biguagym`, branch `spec/recompensas` a partir de `testes-ambientes`/`32698e5`) | Parâmetro `reward_version` (`"v1"` padrão, `"v0"` = original); constantes `TERM_PENALTY`/`SUCCESS_BONUS`; novo cálculo em `HoverEnv._step`, `LandEnv._step`, `DockEnv._step`, `TrajectoryEnv._reward`/`_step`; `reward_terms`/`termination_reason` no `info`; repasse do `reward_version` nos 13 construtores das subclasses (inclusive Pixel/Range/LandCoop) |
| `run.py` (`Experiment.train`, linha 155) e `workspace.py` (`_build_eval_env`, linha 42) | **Correção de bug encontrada no design:** o `gym.make` não recebe `cfg.env.kwargs`, então todo `env_kwargs` (inclusive os padrões do CUPRL em `_resolve_env`) é ignorado. Passar `**cfg.env.kwargs` no treino e na avaliação |
| `tests/test_recompensas.py` (novo, neste repositório) | Testes unitários sem simulador (R1–R5) |
| `tests/dados/recompensa_v0.json` (novo) | Valores de referência da recompensa original, gerados com o código atual (`32698e5`) **antes** da mudança (R5) |
| ponteiro do submódulo em `spec/recompensas` | Aponta para o commit novo do fork. Só entra na `testes-ambientes` no merge, depois que a fila do notebook terminar (R7) |
| `treinos/cluster/runs.csv`, `LEIAME.md`, `fila_cluster.sh` | Com a recompensa nova, os seeds 0 dos 8 ambientes do notebook voltam para o cluster (64 → 72 runs); a espera pelas curvas do notebook e o `enviar_do_notebook.sh` deixam de ser usados (mantidos, mas desligados) |

## Solução proposta

### Seleção da versão (R5)
```python
class HoverEnv(BiguaGymEnv):
    TERM_PENALTY = -10.0
    SUCCESS_BONUS = 10.0
    def __init__(self, seed, agent_type, ..., render_mode=None, reward_version: str = "v1"):
        if reward_version not in ("v0", "v1"):
            raise ValueError(f"reward_version inválido: {reward_version}")
        self._reward_version = reward_version
        ...
class LandEnv(HoverEnv):
    SUCCESS_BONUS = 20.0      # DockEnv herda
```
- Cada subclasse ganha `reward_version: str = "v1"` no fim da assinatura e o repassa a `super().__init__(...)`.
- Uso: `gym.make("DjiMatriceNav-v0", reward_version="v0")` ou, no harness, `+env_kwargs.reward_version=v0` (depois da
  correção do `run.py`/`workspace.py`).
- O caminho `v0` mantém as expressões originais intactas: o código antigo fica dentro de `if self._reward_version == "v0"`,
  sem refatorar.

### Hover/Nav (R1, R2, R6) — `HoverEnv._step`
`_reward()` não muda; ele já devolve o shaping do passo e atualiza `_on_target`. Só o fim do `_step` muda:
```python
shaping = self._reward()
tilt = abs(r) > np.radians(15) or abs(p) > np.radians(15)
reason = ("success" if self._on_target else "tilt" if tilt else
          "out_of_bounds" if out_of_bounds else ("timeout" if truncated else None))
if self._reward_version == "v0":
    reward = 3.0 * abs(shaping) if self._on_target else shaping          # original
else:
    reward = shaping
    if reason == "success":
        reward += self.SUCCESS_BONUS
    elif reason in ("tilt", "out_of_bounds"):
        reward += self.TERM_PENALTY
info = {"reached_goals": ..., "termination_reason": reason,
        "reward_terms": {**self._last_terms, "terminal": reward - shaping}}
```
- `_reward()` passa a guardar os componentes em `self._last_terms` (`norm`, `smooth`, `stable`, `spin`) antes do `return`,
  sem mudar o valor devolvido.
- Por que R1 vale: parado e nivelado, o shaping fica ≥ ~0 por passo (`exp(-2d)` ≥ 0, `stable` = `spin` = 0), enquanto
  tombar dá ≈ −10. Com γ = 0,99, −10 no passo 3 é pior que qualquer sequência ≥ 0.

### Land/Dock (R1, R2) — `LandEnv._step` e `DockEnv._step`
- Mesma estrutura, com `reason` ∈ {`success`, `hard_landing`/`hard_docking`, `tilt`, `out_of_bounds`}.
- Em `v1`, todas as falhas recebem `TERM_PENALTY` somado ao shaping, no lugar do `-5.0` fixo do pouso duro. Assim, tombar
  deixa de ser melhor que pousar duro.
- O sucesso recebe `+SUCCESS_BONUS` (20).

### Trajectory (R3, R4, R6) — `TrajectoryEnv._reward`/`_step`
```python
# _reset: self._best_wp = 0
adv = max(self._wp_idx - self._best_wp, 0)          # waypoints novos neste passo (andar para trás não paga)
self._best_wp = max(self._best_wp, self._wp_idx)
if self._reward_version == "v0":
    r_track = r_cte + r_align                        # original: paga por passo
else:
    r_track = (r_cte + r_align) * adv                # paga por waypoint novo
return r_track + r_prog + r_stable + r_smooth
```
- Parado (ou andando para trás): `adv` = 0, então `r_track` = 0, e `r_stable` e `r_smooth` são ≤ 0. Soma ≤ 0 (R3).
- Percorrendo os ~300 waypoints: até ~2,5 × 300 ≈ 750, mais `W_PROG` + `BONUS_END` = 13. Completar sempre rende mais
  que ficar parado ou voltar (R4).
- `_best_wp` (o máximo já atingido) impede o "farm" de ir e voltar: `_find_nearest_wp` aceita voltar até 2 waypoints.
- Em `v1`, o término por inclinação ou saída da área também recebe `TERM_PENALTY`, pela mesma razão do R1. Sem isso,
  tombar (0 dali em diante) empataria com ficar parado (≤ 0). **Extensão do R1 à Trajectory: confirme na aprovação.**
- `strayed` continua sendo truncamento, sem penalidade.

### Correção do `env_kwargs` no harness
```python
# run.py, Experiment.train
env = gym.make(cfg.env.name, **cfg.env.kwargs)
# workspace.py: guardar os kwargs em __init__ e usar em _build_eval_env
eval_env = gym.make(self.eval_env, render_mode="rgb_array", **self.eval_env_kwargs)
```

### Testes (`tests/test_recompensas.py`, `pytest`, sem simulador)
- O ambiente é criado com `object.__new__(Classe)`, sem simulador. Os atributos usados pelo `_reward`/`_step` são
  injetados (`_dynamics`, `_target`, `_bounds`, `_last_norm`, `_reward_version`, ...), e `_env` é um falso cujo `step()`
  devolve um estado pronto.
- Para a Trajectory: trajetória sintética reta, com `_tangents`, `n_wp` e `_wp_idx` controlados.
- Referência do v0: `tests/dados/recompensa_v0.json`, gerado rodando os mesmos casos no código atual antes da mudança.

## Alternativas consideradas
- **Wrapper `gym.Wrapper` no harness** — descartada por decisão do usuário (mudar no fork). Além disso, o wrapper precisaria
  ler `_dynamics`, `_on_target` e `_wp_idx` privados do ambiente.
- **Bônus de vida por passo, no lugar da penalidade de término** — descartada: um bônus de vida cria o incentivo oposto
  (ficar parado longe do alvo para acumular), e a penalidade de término resolve sem mudar o ótimo.
- **Trajectory sem terminar no fim (episódio até truncar)** — descartada em favor da proposta escolhida. Exigiria voltas
  e redefinir o que é sucesso.
- **`reward_version` por variável de ambiente ou atributo de classe** — descartada: não aparece no `gym.make` nem nos
  logs, e é fácil esquecer ligado.
- **Padrão `v0`** — descartado: quem usar o fork sem saber continuaria com a recompensa com defeito. O `v0` fica explícito
  para comparação.

## Riscos
- **O repasse do parâmetro nos 13 construtores quebra algum ambiente** → smoke de todos os ids que rodam (`--all`,
  200 passos), depois que a fila do notebook terminar.
- **Os resultados mudam e não são comparáveis com os runs antigos** → `v0` disponível; saídas separadas por diretório
  (cluster `saida/` = v1; notebook `treinos/100k/` = v0); a versão vai registrada no `TESTES.md` e no `estado.csv`.
- **A correção do `env_kwargs` muda o CUPRL nos v1:** passa a receber rgb+depth+state em 100×100, como o `_resolve_env`
  queria. Isso usa mais VRAM e RAM, e a pose de 9 dimensões do CUPRL pode não bater → o piloto do
  `verificar_cluster.sh` cobre. Se falhar, os v1 saem do cluster até o CUPRL ser validado (fora desta spec).
- **Escala da Trajectory:** ~750 no total, contra ~13 antes, muda a escala dos valores Q → TD3 com `tau` e `lr` padrão
  costuma tolerar; acompanhar nos pilotos.
- **Fila do notebook (R7):** o checkout principal continua no `32698e5`. Todo o trabalho fica no worktree; o merge na
  `testes-ambientes` só acontece com a fila terminada.
- **Os autores mudarem o `environments.py` na versão nova do biguasim/biguagym** → conflito de merge. Documentar o
  patch para reaplicar.

## Plano de verificação
| Requisito | Como verificar |
|---|---|
| R1 | `pytest tests/test_recompensas.py -k termino`: tilt, out_of_bounds e hard_landing/docking dão shaping + (−10); o retorno de tombar no passo 3 é menor que o de 400 passos parado |
| R2 | `-k sucesso`: o sucesso dá shaping + 10 (Hover/Nav) ou + 20 (Land/Dock), com shaping positivo e negativo |
| R3 | `-k trajetoria_parado`: 50 passos parado sobre o caminho → soma ≤ 0; andando para trás → soma ≤ 0 |
| R4 | `-k trajetoria_completa`: percorrer até `reached_end` → soma > 0, maior que parado e que ir e voltar |
| R5 | `-k v0`: com `reward_version="v0"`, os casos reproduzem `tests/dados/recompensa_v0.json` (tolerância 1e-9); `reward_version="x"` → `ValueError` |
| R6 | testes conferem as chaves `reward_terms` e `termination_reason`; smoke com simulador depois da fila: `python smoke_test.py --env DjiMatriceNav-v0 --steps 200` e `--env BlueBoatTrajectoryFollower-v0 --steps 200` → `status ok` |
| R1–R4 com simulador | depois da fila do notebook: retorno de políticas fixas (BlueBoatTrajectoryFollower-v0 parado contra `--follow`; DjiMatriceHover-v0 motores em hover contra máximo) com `v0` e `v1` → no `v1`, seguir > parado e hover > tombar |
| R7 | durante o trabalho: `git -C ~/biguagym-v0.1.0/biguagym rev-parse HEAD` = `32698e5…` e a fila do notebook continua avançando |
| correção `env_kwargs` | `python run.py env=DjiMatriceNav-v0 +env_kwargs.reward_version=v0 num_train_steps=300 ...` (piloto < 5k passos, depois da fila) e checar no log/`info` que a versão chegou ao ambiente de treino e ao de avaliação |

## Aprovação (2026-10-06)
Usuário: "aprovado, pode aplicar a penalidade na trajetória também". A penalidade de término (−10) por inclinação ou
saída da área vale também na Trajectory (extensão do R1).

## Emenda (2026-10-06, durante a T2): o sucesso termina um passo atrasado
**Achado:** em `HoverEnv._step`, `LandEnv._step` e `DockEnv._step`, o `terminated` é calculado **antes** de
`self._reward()`, e é o `_reward()` que atualiza `self._on_target`. Consequências no código original:
- ao atingir o alvo, o passo sai com `terminated=False`, e o episódio só termina no passo seguinte, onde quer que o
  veículo esteja. Confirmado nos casos `*_sucesso` da referência `v0`;
- no Hover/Nav, o bônus `3·|r|` também vai para o passo seguinte, porque a condição do `if` usa o `_on_target` antigo.

**Mudança proposta (só no `v1`; o `v0` mantém o atraso, como exige o R5):**
```python
shaping = self._reward()                       # 1º: atualiza _on_target com o estado deste passo
terminated = bool(tilt or out_of_bounds or self._on_target or hard_landing)
reason = ...                                   # success / tilt / out_of_bounds / hard_landing / timeout
reward = shaping + (SUCCESS_BONUS if reason == "success" else TERM_PENALTY if reason in falhas else 0.0)
```
O sucesso termina o episódio e recebe o bônus no próprio passo em que o alvo é atingido. Sem isso, o `+10`/`+20` do R2
iria para o passo seguinte, e o `termination_reason` do R6 não bateria com o `terminated`. A Trajectory não tem o
problema: o `reached_end` é calculado no próprio passo.

**Verificação acrescentada:** nos testes do `v1`, o passo em que o veículo chega ao alvo tem `terminated=True`,
`termination_reason="success"` e recompensa = shaping + bônus.
