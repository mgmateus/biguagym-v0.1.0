Status: aprovado

# colapso-blueboat — Requisitos

## Contexto
No BlueBoatNav-v0 o TD3 converge para **girar parado**: os dois motores ficam travados nos extremos, em sentidos
opostos (+288 / −296, desvio 0), e o barco gira a ~3,1 rad/s sem sair do lugar. O retorno fica em ~−231 por episódio,
sempre com 400 passos (fim por tempo), enquanto a ação aleatória dá ~−27 a −30.

Evidências (TESTES.md e `specs/ajuste-ambientes/log.md`):
- Linha de base de 100k (recompensa v0, ambiente v0): retorno de treino −27 → −231, avaliação −219 → −242
  (`treinos/100k`).
- `tools/diag_politica.py` com o ator final: motores saturados em sentidos opostos, `spin` −0,60 por passo, alvo a
  5,6–9,4 m.
- Piloto de 5000 passos com recompensa v1 e ambiente v1 (alvo − posição na observação, alvo na superfície): mesmo
  colapso logo depois do início do aprendizado (passo ~2400), −211 no trecho 1000–5000. Ou seja, **corrigir o alvo
  não resolveu**.
- O BlueBoatTrajectoryFollower-v0 **aprende** com o mesmo TD3, os mesmos motores e o mesmo `cmd_motor_speeds`
  (155 → 1468 na linha de base). O TD3 consegue controlar o barco, então a causa não pode ser só o algoritmo.

Onde está no código:
- **Recompensa:** `biguagym/core/environments.py`, `HoverEnv._reward` (o `NavEnv` herda) =
  `exp(−2·dist)` + `3·(dist_anterior − dist)` + `stable` + `spin` (−0,2·|guinada|). Com o alvo a 5–10 m,
  `exp(−2·dist)` é ~0. O sucesso exige `dist ≤ 0,15 m` (`_on_target`), o que é difícil para um barco sem freio.
- **Término:** `HoverEnv._step`. Limites de `NavEnv._build_params`: ±10 m em x e y em torno do spawn
  `(100, 100, 0)`; z em [−1; 0,1] (superfície); inclinação máxima de 15° (barco). Episódio de 400 passos
  (`max_episode_steps`).
- **Ação:** `HoverEnv._init_spaces` monta o `Box` dos dois motores a partir de `rotor_speed_min`/`rotor_speed_max`
  da dinâmica do BlueBoat (~±290).
- **Agente:** `src/agents/td3.py`. O ator usa `tanh` reescalado para o `Box`. Ruído de exploração de 0,1·escala,
  `policy_noise` 0,2, `noise_clip` 0,5 (`config/agent/td3.yaml`). O fim por tempo não conta como estado terminal
  (`runner.store` repassa `TimeLimit.truncated`).

Hipóteses, ainda não confirmadas (o design escolhe a correção depois do diagnóstico):
1. **A recompensa não favorece ir até o alvo:** longe do alvo, o único sinal é o `smooth`, e ultrapassar o alvo ou
   sair da área (±10 m) pode custar mais do que girar.
2. **Escala da ação:** ação em ±290 sem normalização. O crítico vê ações enormes e o ator satura o `tanh`, de onde
   não sai mais (gradiente ~0). O Trajectory tem recompensa densa desde o primeiro passo e escaparia disso.
3. **Exploração:** 25k passos aleatórios uniformes nos motores mal tiram o barco do lugar, e o buffer quase não tem
   exemplos de "andar até o alvo".

## Objetivo
Fazer o TD3 deixar de colapsar para "girar parado" no BlueBoatNav-v0, com uma política que se aproxima do alvo,
sem mudar o comportamento dos outros ambientes nem a reprodução da linha de base.

## Fora de escopo
- Outros agentes (PPO, SAC, DDPG, CUPRL) e outros ambientes. A mudança, se for no agente, vale só quando pedida
  para o BlueBoatNav.
- BlueBoatNav-v1 (pixels) e v2 (sonar): herdam a correção, se ela for no ambiente, mas só são verificados pelo smoke.
- Encurtamento dos episódios do Dock e do Land: acompanhado nos 250k, não nesta spec.
- Abstração de controle diferente (`cmd_vel`, `cmd_pos_yaw`): o artigo usa `cmd_motor_speeds`.
- Vazamento do simulador, logs por run e pipeline de pixels (specs próprias).
- Treinos longos (> 5k passos) sem autorização: as tarefas de piloto serão ⏱.

## Requisitos
- **R1 (diagnóstico da recompensa)** — QUANDO políticas de referência fixas forem avaliadas no BlueBoatNav-v0 com
  a recompensa e o ambiente padrão (v1) — parado, girar parado (motores em ±máx opostos), aleatória e um controlador
  simples que aponta para o alvo e acelera —, O SISTEMA DEVE registrar o retorno médio, o motivo do término e a
  distância final de cada uma, para mostrar se ir até o alvo rende mais que girar parado.
- **R2 (ordem das recompensas)** — QUANDO o controlador que vai até o alvo for comparado com girar parado e com
  ficar parado, O SISTEMA DEVE dar a ele o maior retorno médio dos três. Se isso já for verdade hoje, R2 está
  cumprido sem mudança na recompensa.
- **R3 (sem colapso)** — QUANDO o TD3 treinar no BlueBoatNav-v0 com a correção, O SISTEMA DEVE produzir uma política
  que não fique travada nos extremos (menos de 50% dos passos com os dois motores a ≥ 95% do limite) e cujo retorno
  médio supere o da política aleatória no mesmo trecho do treino.
- **R4 (progresso até o alvo)** — QUANDO a política treinada for avaliada, O SISTEMA DEVE terminar os episódios mais
  perto do alvo do que começaram (distância final média menor que a inicial).
- **R5 (sem efeito colateral)** — QUANDO qualquer outro ambiente for criado, ou o BlueBoatNav for criado com
  `reward_version=v0` e `env_version=v0`, O SISTEMA DEVE se comportar exatamente como hoje. Se a correção for no
  agente, ela só deve valer quando ativada por configuração (padrão de hoje mantido).
- **R6 (regressão)** — QUANDO a correção for aplicada, O SISTEMA DEVE continuar com os 54 ids registrados, os testes
  sem simulador passando e o smoke do BlueBoatNav v0/v1/v2 `ok`.

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1 | `python tools/diag_referencia.py BlueBoatNav-v0 <episódios>` (novo, ⏱ curto, ~5 min) | Tabela com retorno médio, motivo do término e distância inicial/final das 4 políticas, registrada no `log.md` |
| R2 | idem, depois da correção | retorno(controlador) > retorno(parado) e > retorno(girar parado) |
| R3 | ⏱ piloto TD3 de 15k passos, `agent.learning_starts=1000`, com a correção (pede autorização) e `tools/diag_politica.py` no ator final | retorno médio no trecho 5k–15k > retorno da fase aleatória (0–1k); < 50% dos passos com os dois motores ≥ 95% do limite |
| R4 | `tools/diag_politica.py BlueBoatNav-v0 <actor_last.pt> 600` | distância final média < distância inicial média |
| R5 | `pytest tests/` (+ testes novos da correção) | todos passam; com `reward_version=v0`/`env_version=v0`, recompensa igual à de hoje nos mesmos estados |
| R6 | `python smoke_test.py --list`; smoke de 200 passos em BlueBoatNav-v0/v1/v2 | 54 ids; 3/3 `ok`; 0 simuladores no fim |

## Impacto nos experimentos
- **Se a correção for na recompensa ou no ambiente:** muda o BlueBoatNav (e, se for no `HoverEnv`, possivelmente
  outros ambientes de navegação; nesse caso o design restringe ao domínio superfície ou cria versão nova). Os
  resultados do BlueBoatNav nos 250k que estão rodando agora no PC do lab ficam como "antes da correção" e o run
  teria de ser refeito.
- **Se for no TD3 (normalização da ação, ruído):** muda todos os ambientes, a menos que seja opcional por
  configuração (R5). Uma mudança padrão no agente tornaria os 250k e a linha de base incomparáveis com os runs novos.
- A linha de base de 100k continua reproduzível com `+env_kwargs.reward_version=v0 +env_kwargs.env_version=v0`.

## Decisões (2026-10-20)
Requisitos aprovados pelo usuário em 2026-10-20 ("aprovado, segue suas sugestões nas perguntas em aberto"):
- **Onde corrigir:** primeiro no ambiente (vale para qualquer agente); normalização da ação no TD3 só se o piloto
  ainda colapsar, e opcional por configuração (R5).
- **Critério de sucesso:** não colapsar e se aproximar do alvo (R3, R4); atingir o alvo não é exigido. Aumentar o
  raio de sucesso da superfície pode ser proposto no design.
- **Orçamento:** piloto TD3 de 15k passos (~25 min no notebook), com autorização na fase de execução (⏱).
- **BlueBoatNav nos 250k atuais:** continua na fila do PC do lab, como registro do "antes da correção".
