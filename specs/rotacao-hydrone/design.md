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

---

## Extensão — integração linear (aprovada pelo usuário em 2026-11-17: "pode seguir sim")

**Por quê:** no lab (log, 2026-11-17), o motor também descarta acelerações lineares pequenas (0,035 e 0,2 m/s² por 5 s → 0 m)
e amortece a velocidade linear a 1 s⁻¹. O controlador de velocidade dos autores no ar pede ~0,03 m/s² para a frente
(pitch de 0,2°): sozinho, em Python, o Hydrone anda 0,44 m em 5 s; no motor, 0 m. Com só a rotação integrada, o Goto não
avança a partir do repouso.

**O que muda (só `biguagym/core/goto.py`):**
- O envoltório guarda a aceleração inteira (linear e angular) e manda **zero** ao motor.
- `_impor_rotacao` vira `_impor_estado`: além de ω, impõe `v_novo = (v + a·dt)·e^(AMORTECIMENTO_LINEAR_MOTOR·dt)`, com `v` do
  `DynamicsSensor` (o mesmo que a dinâmica lê) e `AMORTECIMENTO_LINEAR_MOTOR = 1.0` (medido).
- O motor fica com a cinemática (integra a posição e a atitude a partir de v e ω) e as colisões; a posição e a atitude
  continuam do motor (não teleportamos para posições integradas por nós).
- `integrar_rotacao` vira `integrar_dinamica` (padrão `True`); sem sinônimo, porque só as ferramentas e os testes usavam o nome
  antigo. `_w_dot` vira `_acc` (as 6 acelerações).

**Verificação:** testes sem simulador (v imposta = v + a·dt compensada; motor recebe zeros); no lab, `diag_rotacao_hydrone.py
goto` com v medido/previsto ≈ 1, e `diag_goto.py` com avanço ≈ 0,4 m em 5 s a partir do repouso (o que a dinâmica dos autores
dá sozinha), subida e guinada como hoje.

**Riscos:** depois de uma colisão a velocidade imposta parte da velocidade que o motor deixou (pós-colisão), então o contato
continua sendo do motor; se o motor aplicar o teleporte depois da física, o resultado seria o mesmo de hoje (a verificação
pega). O avanço continuará lento (é o controlador dos autores: 0,16 m/s depois de 5 s para 0,31 pedidos); ajustar ganhos
seria alterar a dinâmica do BiguaSim, fora do escopo.

---

## Ajuste — integrador com estado próprio (aprovado pelo usuário em 2026-11-18: "Sim")

**Por quê:** no lab (T7, log), com o Hydrone em movimento a velocidade imposta é respeitada 1:1, mas a partir do repouso o
corpo "dorme" no motor: partindo da velocidade **medida** a cada tick (0 + 0,03·0,05 = 0,0015 m/s), a velocidade imposta é
pequena demais para acordá-lo, o motor devolve 0 e a integração recomeça do zero. Avanço a partir do reset: 0 m.

**O que muda (só `biguagym/core/goto.py`):**
- O `GotoEnv` guarda `_v` e `_w` (mundo): a leitura esperada do `DynamicsSensor` no próximo tick (v + v̇·dt, ω + ω̇·dt),
  zeradas no reset.
- No envoltório da dinâmica, antes de chamar o `step` original, `_conciliar(v_medido, ω_medido)` decide qual v/ω vale
  neste tick:
  - **corpo dormindo** — o motor mede v = ω = 0 (|·| < 1e-4) e o integrado ainda está abaixo do limiar em que o corpo
    acorda (`VEL_DORMINDO = 0,1` m/s e `VEL_ANG_DORMINDO = 0,1` rad/s; medido: 0,05 m/s por tick acorda, 0,01 não):
    valem os integrados;
  - **qualquer outro caso** (motor respeitou a velocidade imposta, colisão, contato com o chão): valem os medidos, como hoje.
- A dinâmica recebe uma **cópia** do `DynamicsSensor` com esse v/ω (o estado do motor e a observação não mudam).
- `_impor_estado` impõe `(v + v̇·dt)·e^(c·dt)` e `(ω + ω̇·dt)·e^(c·dt)` a partir de `_v`/`_w` (não mais da medida) e
  guarda `v + v̇·dt` e `ω + ω̇·dt` como a leitura esperada.

```python
def _conciliar(self, v_med, w_med):
    dormindo = (np.allclose(v_med, 0, atol=1e-4) and np.allclose(w_med, 0, atol=1e-4)
                and np.linalg.norm(self._v) < self.VEL_DORMINDO and np.linalg.norm(self._w) < self.VEL_ANG_DORMINDO)
    if not dormindo:
        self._v, self._w = np.array(v_med, np.float64), np.array(w_med, np.float64)
    return self._v, self._w
```

**Alternativas:** detectar colisão comparando medido × esperado com uma tolerância (mais regras e um limiar a mais, sem
ganho: acordado, o medido é igual ao esperado); impor sempre o integrado (sem a medida, o Hydrone atravessaria o chão e as
paredes depois de um contato). Descartadas.

**Riscos:** o limiar de 1e-4 supõe que o motor mede zero exato (ou quase) com o corpo dormindo; se medir resíduos maiores, o
ajuste não ativa (fica como hoje) e o `diag_goto.py ... avanco` mostra. Parado no chão com aceleração para baixo, o
integrado cresce até 0,1 m/s, o motor resolve o contato e a medida (0) volta a valer: sem atravessar o chão.

**Verificação:** testes sem simulador (motor medindo zero: v imposta cresce a·dt por tick e a dinâmica recebe o integrado;
acima do limiar ou com o motor medindo velocidade, vale a medida; reset zera); no lab, `diag_goto.py ... avanco` andando a
partir do repouso (~0,4 m em 5 s), `diag_rotacao_hydrone.py goto` com as razões ≈ 1 e `testar_goto_lab.sh` (R4, R5).
