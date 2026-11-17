Status: rascunho

# hydrone-limites-motor — Requisitos

## Contexto
Pedido do usuário (2026-11-17): "faça a alteração necessária para o biguasim abrir no pc do lab".

No PC do lab, o clone de treino `~/biguasim` está no BiguaSim 1.1.0 (tag `v1.1.0`, com o Hydrone) e o mundo SkyDive
novo está instalado. O `DjiMatriceLand-v0` roda (19,95 passos/s), mas **todo ambiente do Hydrone falha na criação**
(smoke `HydroneHover-v0`, log `~/smoke_hydrone_110.log` no lab; registro em `TESTES.md`, seção "2026-11-17 (cont.)"):

```
File ".../biguagym/core/environments.py", line 260, in _init_spaces
  self._motor_lo = float(dyn_params['rotor_speed_min'])
TypeError: only length-1 arrays can be converted to Python scalars
```

Onde está:
- `biguagym/core/environments.py`, `BaseEnv._init_spaces` (submódulo no commit `e73d85d`, branch `spec/colapso-blueboat`,
  que é a que o lab roda; na `testes-ambientes` o mesmo problema está nas linhas 241–242, no `Box` direto).
  Com `control_abstraction == 'cmd_motor_speeds'`, o espaço de ação vem dos parâmetros do modelo de dinâmica
  (`PATCH TEMPORÁRIO`), supondo `rotor_speed_min`/`rotor_speed_max` **escalares**.
- `_to_motor_speeds` (linha 282) usa `self._motor_lo/_motor_hi` como escalares. Hoje só é chamado na v2 dos ambientes de
  superfície (`_boat_acao_v2`), que não inclui o Hydrone.
- As subclasses com `_init_spaces` próprio (linhas 1020 e 1197) chamam `super()._init_spaces()`, então dependem da mesma correção.

No BiguaSim 1.1.0 (`src/biguasim/dynamics/agents.py:411`), o Hydrone tem 8 rotores e limites por domínio:
`rotor_speed_min = [0, -278.9]` e `rotor_speed_max = [592.4, 278.9]` (aéreo, aquático). A dinâmica (`dynamics/hauv.py:873`)
aplica o índice 0 aos rotores 0–3 (aéreos, eixo +z) e o índice 1 aos rotores 4–7 (aquáticos). Os outros modelos com
`cmd_motor_speeds` (DJI Matrice, BlueBoat, BlueROV2/Heavy, Torpedo…) continuam com limites escalares.

## Objetivo
Fazer os 13 ambientes do Hydrone serem criados e rodarem no BiguaSim 1.1.0 do PC do lab, com espaço de ação
com limites por motor (4 aéreos + 4 aquáticos), sem mudar nada nos ambientes dos outros veículos.

## Fora de escopo
- Alterar o BiguaSim (nenhum clone; `~/biguasim_gold` e `~/biguasim_tcc` nunca).
- Instalar mundos no notebook ou rodar `packagemanager.prune()`.
- Retirar o `PATCH TEMPORÁRIO` de `_init_spaces` (usar o `action_space` do próprio BiguaSim 1.1.0): pode virar outra spec.
- Normalizar a ação do Hydrone em [-1, 1], como a v2 do BlueBoat, e mexer em recompensa, término ou observação do Hydrone.
- Corrigir outros erros do Hydrone que aparecerem depois deste (sensores, superfície da água, pixels da v1). Se aparecerem,
  são registrados com o traceback e viram proposta à parte (CLAUDE.md, regra 5).
- Treinos (> 5k passos).

## Requisitos
- **R1** — QUANDO o modelo de dinâmica do agente tiver `rotor_speed_min`/`rotor_speed_max` como vetores de 2 elementos
  (aéreo, aquático) e `control_abstraction == 'cmd_motor_speeds'`, O SISTEMA DEVE criar o `action_space` como `Box` de
  dimensão igual ao número de rotores, com limites por motor: rotores 0–3 em [0; 592,4] e rotores 4–7 em [−278,9; 278,9],
  na mesma ordem que a dinâmica do BiguaSim usa para cortar a ação.
- **R2** — QUANDO os limites forem vetores, O SISTEMA DEVE guardar `_motor_lo`/`_motor_hi` por motor (vetores do tamanho
  da ação), para que `_to_motor_speeds` continue correto se um dia for usado com o Hydrone.
- **R3** — QUANDO os limites forem escalares (todos os outros veículos), O SISTEMA DEVE produzir o mesmo `action_space`
  (forma, `low`, `high`, dtype) e o mesmo comportamento de `_to_motor_speeds` de antes da mudança.
- **R4** — QUANDO um ambiente do Hydrone for criado no BiguaSim 1.1.0 do PC do lab, O SISTEMA DEVE completar o smoke test
  de 200 passos sem exceção, com observação dentro do espaço, sem NaN/inf e sem deixar processo do simulador aberto.
- **R5** — QUANDO o formato dos limites não for nem escalar nem vetor de 2 (aéreo, aquático), O SISTEMA DEVE falhar na
  criação do ambiente com uma mensagem que diga o agente e os limites recebidos, em vez de um `TypeError` genérico.

## Critérios de aceitação
| Requisito | Comando | Resultado esperado |
|---|---|---|
| R1, R2, R3, R5 | Verificação sem simulador (script em `smoke_results/` ou `python -c`) que, para cada modelo em `biguasim.dynamics.agents.ModelsFactory._types` com `rotor_pos`, monta os limites com a função nova | Hydrone: `low = [0,0,0,0,-278.9×4]`, `high = [592.4×4, 278.9×4]`, forma (8,); todos os escalares: `low`/`high` iguais a `full(n_rotores, min/max)` como hoje; formato inválido → `ValueError` com o nome do agente |
| R1 | No lab: `python smoke_test.py --env HydroneHover-v0 --steps 200` e leitura de `summary.json` | `ok`, ação de dimensão 8 com os limites de R1, `obs_in_space` verdadeiro, sem NaN/inf |
| R4 | No lab: `python smoke_test.py --all --filter Hydrone --steps 200 --frame-every 100` | 13 ids do Hydrone criados; os que falharem por outro motivo ficam registrados com traceback e causa (fora de escopo) |
| R4 | No lab, depois de cada teste: `ps aux \| grep -i -E "biguasim\|holodeck\|unreal"` | nenhum processo do simulador órfão |
| R3 | No lab: `python smoke_test.py --env DjiMatriceLand-v0 --steps 200` e `--env BlueBoatNav-v2 --steps 200` | mesmas dimensões e limites de ação de antes da mudança (comparar com `smoke_results/` anteriores) |

## Impacto nos experimentos
- Muda só o espaço de ação dos ambientes do Hydrone, que até hoje **não abriam** (nenhuma run antiga do Hydrone).
  Os runs dos outros veículos (incluindo os 250k) não mudam (R3).
- HydroneNav-v0, -v1 e -v2 estão entre os 10 ambientes do artigo: este é o primeiro passo para treiná-los. O espaço de
  ação assimétrico (aéreo só positivo) é o mesmo que a dinâmica do BiguaSim impõe; registrar no artigo que a ação do Hydrone
  é em rad/s, com limites por motor, e que esses treinos rodam no BiguaSim 1.1.0 (não comparáveis com os 250k da 1.0.0).

## Perguntas em aberto
- **Branch base:** o CLAUDE.md manda criar `spec/<nome>` a partir da `testes-ambientes`, mas o lab roda a
  `spec/colapso-blueboat` (que tem `_motor_lo/_motor_hi` e `_to_motor_speeds`, ausentes na `testes-ambientes`).
  Proposta: criar `spec/hydrone-limites-motor` a partir da `spec/colapso-blueboat`, para a correção valer no código que o lab
  usa. A alternativa é partir da `testes-ambientes` e depois juntar as duas, o que dá conflito nessas mesmas linhas.
- Os critérios de R1/R4 só rodam no lab (o notebook não tem mundos da 1.1.0). Execução pelo AnyDesk, como na instalação.
- Rodar só os 8 ids `-v0`/`-v2` (estado) primeiro e deixar os `-v1` (pixels) para depois? Os `-v1` dependem da correção dos
  pixels (Etapa 6) para fazer sentido no treino, mas aqui o critério é só abrir e rodar.
