Status: rascunho

# vazamento-simulador — Requisitos

## Contexto

Cada ambiente biguagym abre um processo próprio do simulador (Unreal) em `biguasim.make(...)`
(`biguagym/core/base_env.py`, `_build_env()` das subclasses, linha ~528). Esse processo só é encerrado
por `__on_exit__()` do biguasim (`~/biguasim/src/biguasim/environments.py:1053`), que faz
`self._client.unlink()`, `self._world_process.kill()` e `wait(10)`. O `__exit__` (linha 1069) também chama
`__on_exit__()`.

O problema está em três pontos:

1. **`BiguaGymEnv.close()`** (`biguagym/core/base_env.py:636`) só faz `stop_recording()` e `del self._env`.
   Como o biguasim registra `atexit.register(self.__on_exit__)` (`environments.py:997`), o `atexit` guarda
   uma referência ao ambiente: o `del` não libera nada, e o processo do simulador continua vivo até o
   Python sair.
   Evidência medida em todos os smoke tests de 2026-09-28 (`TESTES.md`, Etapas 3 e 4):
   `sim_alive_after_env_close: true` e `sim_alive_after_on_exit: false`.
2. **`Workspace.evaluate()`** (`workspace.py:88`) chama `_build_eval_env()` (`workspace.py:41`, um
   `gym.make` novo) **a cada avaliação** e no fim chama `eval_env.close()`. Como o `close()` não encerra
   o simulador, cada avaliação deixa um processo aberto. Com `eval_freq: 100000` (`config/config.yaml`),
   no passo 800k seriam 9 simuladores de avaliação vivos (passos 0, 100k, …, 800k; `workspace.py:150`
   avalia já no passo 0), mais o de treino, consumindo VRAM até esgotar
   (hipótese do "bug dos ~800k steps"; a GPU de desenvolvimento tem 6 GB).
3. **`Experiment.train()`** (`run.py`, laço `for idx in range(self.seed, cfg.runs)`) cria um ambiente de
   treino por seed, e `Workspace.train()` (`workspace.py:216`) chama `self.env.close()` no fim. Pelo mesmo
   motivo, o simulador de treino de cada seed também continua vivo enquanto as seeds seguintes rodam.

Observação sobre reprodutibilidade (relevante para reutilizar o ambiente de avaliação):
os alvos e as trajetórias são sorteados com `self.rng = np.random.default_rng(seed)`
(`base_env.py`, construtor; usos em `biguagym/core/environments.py:161, 309, 470, 717–761`), com
`seed=42` fixo vindo dos `kwargs` do `register.py`. `reset(seed=...)` só re-semeia o `np_random` do
gymnasium, não o `self.rng`. Hoje, como cada avaliação recria o ambiente, **todas as avaliações veem a
mesma sequência de alvos**.

A reprodução pedida no CLAUDE.md (Etapa 5, `run.py` com `eval_freq=500`) ainda **não foi feita**
(suspensa por decisão sobre a versão do simulador; ver `TESTES.md`, resumo de 2026-09-28).

## Objetivo

Garantir que todo simulador aberto pelo harness seja encerrado quando o ambiente correspondente é fechado,
para que o número de processos e a VRAM fiquem constantes ao longo de um treino de 100k+ passos com
avaliações periódicas, sem mudar os resultados dos experimentos.

## Fora de escopo

- Logs por run (`fault.log` / `crash.log` com modo `"w"` em `logger.py`): spec `logs-por-run`.
- Pipeline de pixels (`np.resize` em `PixelStack.append`): spec `pipeline-pixels`.
- Velocidade do treino (`frames_per_sec`, câmera só na avaliação): spec `acelerar-treino`.
- Alterações no pacote `biguasim` (`~/biguasim`, `~/biguasim_tcc`): a correção usa a API existente
  (`__on_exit__` / `__exit__`).
- Corrigir o fato de `reset(seed=idx)` não alterar `self.rng` no ambiente de **treino** (todas as seeds
  sorteiam os mesmos alvos). Isso é registrado como achado em Perguntas em aberto e pode virar outra spec.
- Processos mortos por `SIGKILL` / OOM-killer (o `atexit` não roda nesses casos).
- Alterar `smoke_test.py` ou outros arquivos de apoio.

## Requisitos

- **R1** — QUANDO `close()` é chamado num ambiente biguagym, O SISTEMA DEVE encerrar o processo do
  simulador associado (via `__on_exit__()` do biguasim) e só retornar depois que o processo terminou
  (com o limite de espera de 10 s que o próprio biguasim usa).
- **R2** — QUANDO `close()` é chamado mais de uma vez no mesmo ambiente, ou num ambiente cuja construção
  falhou antes de `self._env` existir, O SISTEMA DEVE retornar sem lançar exceção.
- **R3** — QUANDO uma gravação está ativa no momento do `close()`, O SISTEMA DEVE finalizar o arquivo de
  vídeo (`stop_recording()`) antes de encerrar o simulador, como faz hoje.
- **R4** — QUANDO ocorrem várias avaliações durante um mesmo run, O SISTEMA DEVE manter no máximo
  **um** simulador de avaliação vivo por vez, além do simulador de treino. Ou seja, o número de processos
  do simulador durante o treino nunca passa de 2.
- **R5** — QUANDO o ambiente de avaliação é reutilizado entre avaliações (se essa opção for aprovada; ver
  Perguntas em aberto), O SISTEMA DEVE re-semear o sorteio de alvos/trajetórias no início de cada
  avaliação, para que cada avaliação veja exatamente a mesma sequência de episódios que veria com um
  ambiente recém-criado (comportamento atual).
- **R6** — QUANDO um run (seed) termina em `Workspace.train()`, O SISTEMA DEVE encerrar os simuladores
  de treino e de avaliação desse run antes de a próxima seed começar.
- **R7** — QUANDO o treino é interrompido por exceção ou por Ctrl+C (`KeyboardInterrupt`), O SISTEMA
  DEVE encerrar todos os simuladores abertos pelo processo, sem deixar órfãos.

## Critérios de aceitação

Medição de processos: `pgrep -f -c -i "biguasim|holodeck"` (ou o mesmo filtro da regra 3 do CLAUDE.md),
amostrado a cada 10 s junto com `nvidia-smi --query-gpu=memory.used --format=csv,noheader` e salvo em CSV.

| Requisito | Comando | Resultado esperado |
|---|---|---|
| (linha de base, antes da correção) | `python run.py env=BlueBoatNav-v0 agent=td3 num_train_steps=3000 eval_freq=500 num_eval_episodes=1 runs=1 agent.learning_starts=500` + monitor de processos/VRAM | Registrar no `log.md` que o número de processos cresce em +1 a cada avaliação (esperado: avaliações nos passos 0, 500, …, 2500 + 1 final = 7, logo até 1 + 7 = 8 processos) e a VRAM sobe junto. Isso confirma o bug antes de corrigir. |
| R1 | `python smoke_test.py --env DjiMatriceLand-v0 --steps 50` | `summary.json`: `sim_alive_after_env_close: false`. |
| R1 | `python smoke_test.py --all --filter v0 --steps 50 --frame-every 0` | Todos os ambientes que rodam hoje: `sim_alive_after_env_close: false` em `smoke_results/resumo.csv`; 0 processos no fim. |
| R2 | script de verificação: `env = gym.make(id); env.close(); env.close()` | Sem exceção; 0 processos do simulador depois. |
| R3 | `python smoke_test.py --env DjiMatriceLand-v1 --steps 50` com gravação, ou o próprio `run.py` da linha abaixo | `.mp4` de avaliação abre e tem a duração do episódio (não truncado). |
| R4 | mesmo comando `run.py` da linha de base, depois da correção, + monitor | Número de processos ≤ 2 em todas as amostras; VRAM no fim ≈ VRAM depois da 1ª avaliação (variação < 300 MB). |
| R5 | script que roda `evaluate()` duas vezes com o mesmo agente e salva os alvos sorteados (`env.unwrapped._target`) por episódio | As duas avaliações têm a mesma sequência de alvos, idêntica à obtida recriando o ambiente. |
| R6 | `python run.py ... num_train_steps=1000 eval_freq=500 runs=2` + monitor | Ao começar a seed 2, há no máximo os processos da seed 2; ao terminar `run.py`, 0 processos. |
| R7 | mesmo `run.py` interrompido com Ctrl+C (`kill -INT <pid>`) durante uma avaliação | 0 processos do simulador ~15 s depois. |

Todos os comandos têm ≤ 3000 passos (abaixo do limite de 5k da regra 2). Depois de cada um, conferir
processos órfãos (regra 3).

## Impacto nos experimentos

- **R1, R2, R3, R4, R6, R7** não mudam a dinâmica dos ambientes, as recompensas nem os agentes: só o ciclo
  de vida dos processos. Runs antigas continuam comparáveis.
- **R4 (se feito reutilizando o ambiente de avaliação) + R5:** só não muda os resultados se a re-semeadura
  reproduzir o comportamento atual (mesma sequência de alvos em toda avaliação). Ainda pode haver diferença
  de estado interno do simulador entre "recém-criado" e "reutilizado" (por exemplo, tempo de simulação
  acumulado ou estado da física depois do `reset`). Por isso o critério de R5 compara as duas formas
  explicitamente. Se houver diferença, ela precisa ser registrada, porque altera as curvas de avaliação
  do artigo.
- Efeito colateral esperado: avaliações mais rápidas se o ambiente for reutilizado (sem os ~2 s de reset
  e o tempo de carga do Unreal a cada `gym.make`). O tempo total por run muda, mas não as métricas.

## Perguntas em aberto

1. **Reutilizar o ambiente de avaliação ou só fechar direito?** A opção mínima (só R1 + `close()`
   correto) já cumpre R4: abre e fecha um simulador por avaliação. Reutilizar (sugerido no
   `specs/README.md`) economiza a carga do Unreal a cada avaliação, mas exige R5 e muda o código do
   `workspace.py`. Proposta: fazer só a opção mínima nesta spec e deixar a reutilização para a
   `acelerar-treino`.
2. **Onde fica a correção do `close()`:** no submódulo `biguagym`, que é o repositório dos autores. Pela
   regra 1, uso a branch `spec/vazamento-simulador` também no submódulo, criada a partir da
   `testes-ambientes` dele (commit `32698e5`)? Ou a correção deve ir para o lado do harness
   (`workspace.py`), sem tocar no submódulo?
3. **Ambiente para a reprodução:** a linha de base com `BlueBoatNav-v0` precisa do biguasim na branch
   `testes-biguagym` (hoje `~/biguasim` está na `sitl-test`, e trocar afeta também o venv-ardupilot).
   Posso trocar durante os testes e voltar depois, ou prefere esperar a versão nova do BiguaSim?
   A validação também precisa ser repetida no PC do laboratório.
4. **Achado (fora de escopo):** no treino, `env.reset(seed=idx)` em `run.py` não muda `self.rng`, que é
   sempre `default_rng(42)`. Ou seja, as 3 seeds de cada experimento sorteiam a mesma sequência de alvos.
   Isso afeta a variância entre seeds no artigo. Abrir uma spec separada (`seeds-ambiente`)?
