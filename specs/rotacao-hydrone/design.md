Status: aprovado

> Aprovação: pedido do usuário em 2026-11-17 ("Resolva isso do giro"). Ver `log.md`.

# rotacao-hydrone — Design

## Arquivos afetados
- `biguagym/core/goto.py` (submódulo): integração angular no `GotoEnv` (vale também para `GotoPixelEnv` e `GotoRangeEnv`).
- `tests/test_rotacao_hydrone.py` (novo): testes sem simulador.
- `tools/diag_goto.py`: a fase "direto" passa pela integração; nova fase "avanço" (deslocamento na direção do nariz).
- `tools/diag_rotacao_hydrone.py`: modo `goto` que mede, com a integração ligada, ω medido × ω previsto no ar e na água.

## Solução proposta
No `BiguaSim.step`, cada tick faz: `tick()` (aplica a ação anterior e o teleporte pendente) → `modelo.step(estado)` →
`agente.act(aceleração)`. O `GotoEnv` passa a:

1. **Envolver o `step` da dinâmica** (`self._env._dynamics_dict['robot'].step`, atributo de instância; o BiguaSim não é
   alterado): guarda ω̇ (colunas 3:6, mundo, rad/s²) e devolve a aceleração com a parte angular zerada, para o motor não
   aplicá-la (no DJI ele aplica às vezes; no Hydrone, se algum dia aplicar, não conta duas vezes).
   ```python
   def _instalar_integrador(self):
       modelo = self._env._dynamics_dict['robot']
       if getattr(modelo, '_step_original', None) is None:
           modelo._step_original = modelo.step
       original = modelo._step_original
       def step(*a, **k):
           acc = np.asarray(original(*a, **k), dtype=np.float64).reshape(-1, 6)
           self._w_dot = acc[0, 3:6].copy()
           acc[:, 3:6] = 0.0
           return acc.tolist()
       modelo.step = step
   ```
2. **Avançar tick a tick** (`_passo_sim`): para cada tick do `action_repeat`, `self._env.step(cmd, action_repeat=1)` e
   depois `_impor_rotacao(estado)`:
   ```python
   w = np.asarray(state['DynamicsSensor'])[12:15]          # ω no mundo (rad/s), o mesmo que a dinâmica lê
   rpy = np.asarray(state['RPYDynamicsSensor'])            # posição do ator, velocidade e [roll, pitch, yaw] em graus
   w_novo = (w + self._w_dot * dt) * math.exp(self.AMORTECIMENTO_ANGULAR_MOTOR * dt)
   agente.set_physics_state(rpy[6:9], rpy[15:18], rpy[3:6], np.degrees(w_novo))
   ```
   O teleporte fica pendente e é aplicado no próximo `tick()`, junto com a aceleração linear do mesmo passo da dinâmica.
   Posição, atitude e velocidade vêm do `RPYDynamicsSensor` (`UseCOM: false`: posição do ator, que é o que o teleporte
   espera; atitude em graus na convenção do próprio motor), então o teleporte não move o agente. `dt = 1/TICKS_POR_S`.
   `AMORTECIMENTO_ANGULAR_MOTOR = 1.0` s⁻¹ (medido: ω imposto de 0,524 rad/s lido como 0,498 no tick seguinte = e^(−0,05)).
3. `integrar_rotacao: bool = True` no construtor (R3); desligado, `_passo_sim` é o `self._env.step(cmd, action_repeat)` de
   antes. `self._w_dot` volta a zero no reset.

## Alternativas consideradas
- **Guinada cinemática** (impor ω_z = comando do agente, sem a dinâmica): resolve só o yaw; o Hydrone também não inclina
  (roll/pitch), então não andaria na horizontal no ar. Descartada.
- **Teleportar a atitude integrada** (em vez da velocidade angular): o motor não saberia da rotação (ω medido = 0, e a
  dinâmica usa ω no amortecimento e no controlador). Descartada.
- **Corrigir no BiguaSim/motor:** fora do alcance (binário do Unreal) e proibido alterar o BiguaSim; vai para os autores.
- **Aumentar a aceleração angular enviada:** o Hydrone não respondeu nem a 10 rad/s². Descartada.

## Riscos
- Se o motor aplicar o teleporte depois da física do tick, a velocidade linear seria reposta a cada tick e o Hydrone não
  aceleraria. Verificação no lab: subida e avanço no `diag_goto` (R5).
- O amortecimento do motor pode ser outro debaixo d'água; o modo `goto` do `diag_rotacao_hydrone.py` compara ω medido e
  previsto nos dois meios.
- `set_physics_state` com atitude em graus: convenção [roll, pitch, yaw] do motor; usa a leitura do próprio motor
  (`RPYDynamicsSensor`), sem conversão nossa.
- Custo: só escrita em memória compartilhada por tick.

## Plano de verificação
- R1–R3: `tests/test_rotacao_hydrone.py` com simulador falso (modelo que devolve ω̇ conhecido; agente que grava o
  `set_physics_state`).
- R4, R5: no lab, `tools/diag_goto.py`, `tools/diag_rotacao_hydrone.py goto` e `tools/testar_goto_lab.sh`.
