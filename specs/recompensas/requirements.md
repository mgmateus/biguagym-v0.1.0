Status: rascunho

# recompensas — Requisitos

## Contexto
As funções de recompensa dos ambientes biguagym (`biguagym/core/environments.py`) têm incentivos que levam a
comportamentos degenerados. Análise completa no `TESTES.md`, seção "Análise das funções de recompensa (2026-10-06)".

1. **Hover/Nav/Land/Dock: terminar cedo compensa.**
   - Em `HoverEnv._reward`/`_step` (herdados pelo `NavEnv`), a recompensa por passo é
     `exp(-2d) + 3·(d_ant − d) − inclinação − giro`. Com ações aleatórias ela é negativa: DjiMatriceNav −0,38,
     DjiMatriceHover −0,31, BlueROV2Nav −0,14.
   - O episódio termina com |roll| ou |pitch| > 15° ou fora da área, sem penalidade e sem bônus de vida.
   - Evidência: no run de 100k do DjiMatriceNav-v0 (TD3, seed 0), a partir de ~30k passos o agente encerra todo
     episódio em ~3 passos (R ≈ −1,7, contra −2,7 da política aleatória) e fica nisso até o fim.
   - `LandEnv._step`/`DockEnv._step`: o pouso ou a docagem dura dá −5, mas tombar não custa nada, então tombar é
     preferível.
   - O sucesso paga `3·|r|` (`HoverEnv._step`, `LandEnv._step`, `DockEnv._step`): um bônus pequeno (~3), que depende do
     estado e transforma uma recompensa negativa em positiva.
2. **Trajectory: não terminar compensa.**
   - Em `TrajectoryEnv._reward`, `r_cte` (até `W_CTE` = 2) e `r_align` (até `W_ALIGN` = 0,5) pagam por passo para quem
     está sobre o caminho, mesmo sem avançar (+1,9 a +2,3 por passo com ações aleatórias).
   - O progresso inteiro vale `W_PROG` = 3, mais `BONUS_END` = 10, e `reached_end` **termina** o episódio.
   - Com γ = 0,99, ficar parado sobre o caminho vale ~250, contra ~13 de completar o percurso.
3. **Torpedo: o veículo não se move.** Em todos os smokes Torpedo, a posição final é igual à inicial depois de 200 passos
   aleatórios, e a recompensa fica ~0. Não é problema de recompensa: é do veículo, do controle
   (`cmd_rudders_sterns_motor_speed`) ou da dinâmica no biguasim 1.0.0.

## Objetivo
Corrigir esses incentivos, para que o retorno ótimo corresponda a cumprir a tarefa: chegar ao alvo, pousar ou docar
com suavidade, ou percorrer o caminho até o fim. A recompensa original deve continuar disponível para comparação.

## Fora de escopo
- Corrigir o Torpedo (dinâmica ou controle): vira uma investigação ou spec própria. Nesta spec ele só fica registrado.
- Mudar observações, espaços de ação, dinâmica, sensores ou agentes.
- Ajustar hiperparâmetros dos agentes (por exemplo, `learning_starts`).
- Os ambientes Hydrone (sem simulador) e BlueROVHeavy (sem agente no binário). A mudança vale para eles por herança, mas
  não será testada neles.
- A recompensa de `LandCoopPixelEnv` (DjiMatriceLand-v2 não roda no biguasim 1.0.0).

## Requisitos
- **R1** — QUANDO um episódio de Hover/Nav/Land/Dock termina por falha (|roll| ou |pitch| > 15°, saída da área, pouso ou
  docagem dura), O SISTEMA DEVE dar uma penalidade de término fixa e configurável, igual para todas essas falhas, de modo
  que terminar por falha nunca renda mais retorno que continuar o episódio parado.
- **R2** — QUANDO o veículo atinge o alvo (`_on_target`), O SISTEMA DEVE dar um bônus de sucesso fixo e configurável, que
  não dependa do sinal nem do valor da recompensa do passo, no lugar de `3·|r|`.
- **R3** — QUANDO um episódio de Trajectory está em andamento, O SISTEMA DEVE pagar o acompanhamento do caminho (`r_cte`,
  `r_align`) só em proporção ao avanço ao longo dele, de modo que ficar parado sobre o caminho renda no máximo zero
  por passo.
- **R4** — QUANDO um episódio de Trajectory chega ao fim (`reached_end`), O SISTEMA DEVE garantir que completar o
  percurso renda mais retorno que qualquer política que fique parada ou ande para trás pelos mesmos passos.
- **R5** — QUANDO o ambiente é criado com o parâmetro de versão da recompensa no valor original (por exemplo,
  `reward_version="v0"` via `gym.make(..., reward_version=...)` ou `env_kwargs` no `run.py`), O SISTEMA DEVE reproduzir
  exatamente a recompensa atual. Isso mantém os runs já feitos comparáveis.
- **R6** — QUANDO um passo é executado, O SISTEMA DEVE expor no `info` os componentes da recompensa (por exemplo,
  `reward_terms`) e o motivo do término (`termination_reason`), para os logs e as análises.
- **R7** — QUANDO a fila de treinos do notebook (`treinos/100k`) ou outro run em andamento estiver usando o checkout
  principal, O SISTEMA (o processo de desenvolvimento) NÃO DEVE alterar o código usado por esses runs. A mudança fica na
  branch `spec/recompensas`, no worktree `.claude/worktrees/recompensas`, até a fila terminar e a mudança ser aprovada.

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1, R2 | teste unitário sem simulador (`tests/test_recompensas.py`): cria o ambiente com `object.__new__`, injeta `_dynamics`, `_target`, `_bounds` e chama `_reward`/a lógica de término | o término por inclinação, saída da área e pouso duro dá a mesma penalidade configurada; o sucesso dá o bônus fixo, independentemente do sinal de `r` |
| R1 | mesmo teste: soma de um episódio que tomba no passo 3 contra um que fica parado (sem tombar) até o truncamento | o retorno de tombar é menor |
| R3, R4 | teste unitário do `TrajectoryEnv` com uma trajetória sintética: política "parado no início" contra "avança 1 waypoint por passo até o fim" | parado: soma ≤ 0; avançando: soma > 0 e maior que a de parado e a de andar para trás |
| R5 | teste unitário: com `reward_version="v0"`, as mesmas entradas dão os mesmos valores do código atual (comparação com valores gravados antes da mudança) | diferença 0 (tolerância 1e-9) |
| R6 | `python smoke_test.py --env DjiMatriceNav-v0 --steps 200` e `--env BlueBoatTrajectoryFollower-v0 --steps 200` (depois que a fila do notebook terminar) | `info` traz `reward_terms` e `termination_reason`; `status ok` |
| R1–R4 | teste de políticas fixas com simulador (depois da fila do notebook): BlueBoatTrajectoryFollower-v0 parado contra `--follow`; DjiMatriceHover-v0 motores em hover contra motores máximos | o retorno de seguir é maior que o de ficar parado; o retorno do hover é maior que o de tombar |
| R7 | `git -C ~/biguagym-v0.1.0 status` e `git -C ~/biguagym-v0.1.0/biguagym log -1` enquanto a fila roda | o checkout principal continua no commit usado pela fila (submódulo `32698e5`) |

## Impacto nos experimentos
- **Muda o comportamento dos ambientes e, portanto, os resultados do artigo.** Runs com recompensa nova e antiga não são
  comparáveis entre si. O nome das curvas e dos logs deve indicar a versão (decidir no design).
- **Fila do notebook** (TD3, seed 0, recompensa antiga): os resultados ficam como linha de base da recompensa original e
  não se misturam aos novos.
- **Fila do cluster** (64 runs): se a spec for aprovada antes de começar, ela deve rodar com a recompensa nova. Isso
  invalida a dependência dos seeds 1/2 nos seeds 0 do notebook (outra recompensa), e os seeds 0 desses 8 ambientes
  voltam para a lista do cluster. Decidir no design.
- A mudança é no submódulo `biguagym` (código dos autores): fica no fork `ttszin/biguagym`, numa branch, e convém
  combinar com os autores antes de usá-la no artigo.

## Perguntas em aberto
1. **Onde mudar:**
   - direto nas classes do submódulo (`core/environments.py`, fork `ttszin/biguagym`);
   - ou num wrapper `gym.Wrapper` neste repositório, que recalcula a recompensa a partir do `info`/estado, sem mexer no
     código dos autores. O wrapper exige que o estado necessário esteja acessível.
2. **Valores:** a penalidade de término (proposta: −10) e o bônus de sucesso (proposta: +10 no Hover/Nav, +20 no
   Land/Dock) são escolha sua, ou deixo para calibrar com os pilotos?
3. **Trajectory:**
   - a proposta para R3/R4 é `r_cte` e `r_align` multiplicados pelo avanço do passo (Δwaypoint ≥ 0), mais um bônus de fim
     maior;
   - outra opção é manter os termos e não terminar no fim (o episódio continua até truncar, com bônus por volta).
   - Qual prefere?
4. **Os autores do biguagym** devem revisar antes, ou fazemos e mostramos depois?
