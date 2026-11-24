# hydrone-goto-dique — Log

## 2026-11-17 — Fases 1 a 3
- Pedido do usuário (2026-11-17): artigo do biguagym com 8 ambientes treinados + 2 do Hydrone (Goto RGB+Depth do Dranaju e
  Goto LiDAR+sonar do Ricardo); recompensa do Dranaju nos dois; `cmd_vel_yaw` recebendo velocidade, não ângulo; "aplique o
  pipeline-pixels, o hydrone-goto-dique e a configuração dos sensores" (tratado como aprovação; fases escritas para registro).
- Mensagens do coorientador (2026-11-16): dique inundado do Pier-Harbor, 4 pilares sem colidir com o barco; depois o dique inteiro.
- Leitura: `dynamics/hauv.py` (`cmd_vel_yaw`: [vx, vy, vz] no mundo + desvio de guinada em graus, alvo = ψ + desvio a cada
  tick), `environments.py` do BiguaSim 1.1.0 (`spawn_prop`: cilindro de 1 m; props somem no reset; `_props` é limpo),
  `sensors.py` (`CollisionSensor`); código do Dranaju (`setReward`, `getState`, `step`, `respawnGoal.py`); paper Depth-CUPRL.
- Arquivos: `specs/hydrone-goto-dique/{requirements,design,tasks}.md`.

## 2026-11-17 — T1 a T6
- T1: `spec/hydrone-goto-dique` a partir da `spec/pipeline-pixels` (principal e submódulo).
- T2–T5 (um commit só no submódulo, porque estão no mesmo arquivo novo `core/goto.py`):
  - `config/goto_dique.json`: cenários `pilares` e `dique`, **provisórios** (tanque de 10 × 10 m em torno de (100, 100),
    spawn do paper (3,6; −2,6; 2,0) relativo ao centro).
  - `GotoEnv(HoverEnv)`: ação [−1, 1]³ → v = (a₀+1)/2·0,3 + 0,01, ω = 0,3·a₁, v_z = 0,3·a₂; ψ_ref integrada a 20 Hz;
    `cmd_vel_yaw` = [v cos ψ, v sin ψ, v_z, desvio (graus, ≤ 45°)]; pilares recriados a cada reset (`spawn_prop('cylinder')`);
    alvos sorteados na área, no ar (0,5–3 m) ou na água (−0,7 a −0,3 m), fora dos pilares/caixas e a ≥ 2 m do veículo;
    colisão: `CollisionSensor`, < 0,625 m da borda/pilar/caixa, z fora de [−1,1; 4,8]; recompensa do Dranaju
    (`recompensa_dranaju`); 1000 passos; observação `-v0` = pose de 9 + 3 ações anteriores.
  - `register.py`: `HydroneGotoPilares-v0` e `HydroneGotoDique-v0` (56 ids no total).
- Problema achado pelos testes: no cenário provisório com pilares em ±2,5 m, o spawn do paper ficava a 0,6 m da superfície de um
  pilar (colisão no 1º passo). Correção: pilares em ±2,0 m (spawn a 1,2 m) e `_validar_spawn()` recusa cenários assim.
- T6: `tools/diag_goto.py` (ω = ±0,3 rad/s e v_z = +0,3 m/s por 5 s; imprime Δyaw e Δz medidos e esperados).
- Testes: `tests/test_hydrone_goto.py` (37). `~/venv-biguagym/bin/python -m pytest -q tests` → **144 passed**.
- Pendente: T7 e T8 no lab (⏱), depois que o usuário terminar de explorar o mapa e trouxer as coordenadas do dique.

## 2026-11-17 — Mudança durante a execução: nível da água na física
- Achado: o `biguasim.make` da 1.1.0 aceita `agents[i].dynamics.water_level` (`environments.py:333`). O `GotoEnv._build_params`
  passa o `nivel_agua` do cenário para lá, então a física e a recompensa usam o mesmo nível (antes a física ficaria em 0).
  `design.md` (Riscos) atualizado. Teste novo `test_nivel_da_agua_vai_para_a_dinamica`; `pytest tests` → 145 passed.

## 2026-11-17 — Script de exploração (pedido do usuário, fora das tarefas)
- Pedido: "faça um script de exploração com spawn configurável e câmera do veículo salva em PNG. E certifique-se de que o
  hydrone seja spawnado sem erros".
- `tools/explorar_mapa.py`: BiguaSim direto (sem biguagym, então sem o erro dos limites por motor do `cmd_motor_speeds`),
  Hydrone em `cmd_vel_yaw` com comando zero (parado); `--ponto x,y,z[,yaw]` (repetível), `--grade`, `--giro`, `--viewer`;
  teleporte com `set_physics_state` (velocidade zerada) para cada ponto numa sessão só; PNG da câmera da frente, de baixo
  (presas ao corpo, sem socket) e em terceira pessoa (socket `Viewport`); `pontos.csv` com posição medida, colisão, contato
  com a água, obstáculo mais próximo (36 lasers) e distância até o que está embaixo; níveis de sensores com recuo automático
  (`completo` → `sem_medidas` → `minimo`, este = sensores do `state.json`, que já abriram o Hydrone no lab).
- Verificação sem simulador (o notebook não tem os mundos da 1.1.0):
  `python tools/explorar_mapa.py --ponto 100,100,2 --ponto 103.6,97.4,-0.5,90 --grade 90,110,90,110,10,1.5 --dry-run` →
  11 pontos, aceleração 0 com comando zero no ar e na água, 0 erros; tipos de sensor registrados na 1.1.0 e `socket` opcional.
- A confirmar no lab: o spawn de verdade, a orientação das câmeras do corpo e o sentido dos lasers.

## 2026-11-17 — T7 no PC do lab (autorizado: "Mande os códigos para o lab e teste os ambientes")
- Push: `spec/{pipeline-pixels,hydrone-goto-dique,sensores-goto}` no origin e no `ttszin/biguagym` (o remote HTTPS do
  submódulo não tem credencial; push pelo SSH). Lab: `~/biguagym-v0.1.0` passou da `spec/colapso-blueboat` para a
  `spec/sensores-goto` (que a contém); dois CSVs dos 250k não rastreados no lab bloqueavam o checkout: movidos para
  `~/backup_checkout_goto/` e idênticos (`cmp`) aos versionados.
- `tools/testar_goto_lab.sh` (logs `~/testar_goto_lab.log`, `~/testar_goto_lab2.log`): pytest 162 passed; smokes de 200 passos
  `HydroneGotoPilares-v0` ok 12,1 passos/s (obs 12), `-v1` ok 9,6 (rgb/depth 9×100×100 + state 9), `-v2` ok 11,8 (26);
  sem NaN/inf, obs no espaço, 0 processos do simulador depois de cada teste.
- `explorar_mapa.py`: Hydrone nasce parado nos pontos pedidos (ar z = 2 e água z = −0,5; 4 guinadas, fotos salvas). O
  `WaterCollisionSensor` trava o spawn (`posix_ipc.BusyError: Semaphore is busy` no 1º tick); colisão + distâncias + fundo
  abrem normalmente → `WaterCollisionSensor` fora do padrão (`--extras`).
- **Guinada do Hydrone não responde no simulador** (`diag_goto.py`, `diag_guinada_hydrone.py`, log `~/diag_guinada.log`):
  - ω = ±0,3 rad/s por 5 s → Δyaw +0,005 / −0,001 rad (esperado ±1,5); o `GotoEnv` envia o desvio certo (cresce de 0,9° a 30,8°);
  - direto no BiguaSim, `cmd_vel_yaw` com desvio fixo de 20°: a dinâmica devolve acc_ang z = 3,14 rad/s² em todo tick, mas o
    `DynamicsSensor` mede w = 0 e o yaw anda 0,17° em 60 ticks; `cmd_pos_yaw` com 90°: acc_ang z = 14,1 rad/s², yaw 0,17°;
  - mesmo teste com o `DjiMatrice`: yaw +82° (`cmd_vel_yaw`) e +89° (`cmd_pos_yaw` 90°) → a cadeia biguagym → BiguaSim está
    certa; **o simulador não aplica a aceleração angular de guinada ao Hydrone** (a linear, sim: subida de 1,1 m).
  - Causa fora do biguagym (BiguaSim 1.1.0, provavelmente o ator do Hydrone no Unreal); não alterei o BiguaSim. Precisa ir
    para os autores (hydrone-furg). Sem guinada, o agente não consegue apontar para o alvo nem virar a câmera.

## 2026-11-18 — T8: `tools/mapear_dique.py` (ferramenta, sem mudar o ambiente)
- Pedido do usuário: "Faça um código que mapeie o dique e encontre as coordenadas corretas para colocar os pilares".
- Onde fica o dique: a documentação do BiguaSim (`biguasim_docs/packages/SkyDive/Pier-Harbor/`) mostra a bacia com o navio
  cinza no canto inferior direito da vista de cima; com a escala dos eixos da figura, o navio fica em ≈ (150, −183), que
  bate com o ponto "Moored Vessel" (142, −185) da documentação, e a bacia em x ≈ 126–177, y ≈ −260 a −114. É só uma
  estimativa: a ferramenta mede.
- `tools/mapear_dique.py`: varredura com laser para baixo a 40 m de altura (grossa de 3 m na região 110–200 × −275 a −95;
  fina de 1 m na bacia) → mapa de alturas; água = topo ≤ nível + 0,5 m; bacia = maior grupo de água cercado por sólido
  nas 4 direções (o mar aberto não é); área quadrada de 10 m onde a folga até parede/navio é máxima (transformada de
  distância), 4 pilares em centro ± 2 m e spawn em centro + (3,6; −2,6), como o cenário provisório; o navio vira caixa de
  exclusão do cenário `dique`. Depois confere com o Hydrone (obstáculo horizontal, fundo e colisão no centro, nos cantos
  e no spawn, na água e no ar) e fotografa com os pilares criados por `spawn_prop`. Sai `cenario_sugerido.json`; o
  `goto_dique.json` não é alterado. `--dry-run` usa um mapa sintético.
- `tests/test_mapear_dique.py` (7 testes, mapa sintético): bacia certa (não o mar), área longe do navio e das paredes,
  caixa do navio, dique aberto para o mar, semente. `pytest tests` → 180 passed.

## 2026-11-18 — T8 no lab: mapa do dique (`~/mapear_dique.log` e `~/mapear_dique2.log`; saídas em `~/biguagym-v0.1.0/mapear_dique/` no lab)
Combinado com a outra sessão (TCC), que liberou o lab; o treino dela seguiu rodando.

1ª rodada (12:47–13:01, `1af24b6`, `python tools/mapear_dique.py`, saída `mapear_dique/20261118-124759/`):
- Passada grossa (3 m, 1.891 pontos, ~4 min, ~8 pontos/s com a dinâmica `cmd_vel_yaw` rodando a cada ponto) e fina (1 m).
- **O dique tem duas bacias**, uma atrás da outra, separadas por uma faixa sólida em y ≈ −200 a −205, cada uma com um navio:
  norte em x 125,5–159,5, y −198,5 a −139,5 (a escolhida: maior grupo de água cercada); sul em y ≈ −250 a −208.
  Fundo em z ≈ −10 m.
- Na bacia norte o navio ocupa quase tudo: sobram canais de 6–8 m dos lados e dois cantos de ~11 m na frente da proa.
  Só 1.072 m² de água livre; o quadrado de 10 m ficou a 0,5 m da parede, e a conferência mostrou colisão no ar a 1 m dela
  (z = 2 e 4,5 no canto sudoeste da área).
- Erros da ferramenta vistos nas fotos: a câmera "para baixo" com pitch −90° olhava para cima (mesmo erro no
  `explorar_mapa.py`); corrigido para +90°.
- **Os pilares não aparecem nas fotos.** O log do motor (`~/.local/share/biguasim/1.1.0/worlds/SkyDive/Linux/Biguasim/
  Saved/Logs/HolodeckLog*.txt`) tem `Warning: CommandFactory failed to make command:  SpawnProp` para cada pilar, em
  **todas** as rodadas do Goto no lab (4 ou 8 por log desde 2026-11-18 00:56 UTC, incluindo os smokes do T9 da
  rotacao-hydrone): o mundo SkyDive 1.1.0 instalado não conhece o comando `SpawnProp` do cliente Python 1.1.0. Os pilares
  do `GotoEnv` nunca existiram no simulador (nem para as câmeras, nem para os lasers/sonar); só a checagem de colisão em
  Python sabe deles. Para os autores (não dá para corrigir no biguagym sem alterar o BiguaSim).

Ajustes (`2cbec27`): `--folga` (padrão 1,5 m) e `--lado-min` (maior retângulo com a folga), `--mapa` (reaproveita a varredura),
aviso de SpawnProp recusado, câmera com pitch +90°; Hydrone em `accel` com aceleração zero (`1e86784`, varredura mais rápida).

2ª rodada (13:17–13:18, `python tools/mapear_dique.py --mapa mapear_dique/20261118-124759/`, saída
`mapear_dique/20261118-131734/`):

| Item | Resultado |
|---|---|
| área do cenário `pilares` | x 127–135, y −155 a −145 (8 × 10 m), centro (131, −150), canto noroeste da bacia norte, na frente da proa |
| folga até parede/navio | 1,5 m no mapa; conferência: obstáculo horizontal mínimo 1,91 m na água e 1,84 m no ar, 0 colisões |
| pilares (raio 0,5, base −3, altura 8) | (129,4; −152), (129,4; −148), (132,6; −152), (132,6; −148) |
| spawn | (133,88; −152,6; 2,0) |
| fundo | z ≈ −10 m |
| SpawnProp | 4 recusados no log da rodada das fotos (o aviso da ferramenta não pegou: lia só um log; corrigido para contar os logs desde o início das fotos) |

- A caixa de exclusão do cenário `dique` dessa rodada está incompleta: o navio encosta na parede sul e era tratado como parede.
  Corrigido (só faixas de até 2 m que tocam a borda são ignoradas); falta rodar de novo com `--mapa` para o cenário `dique`.
- `goto_dique.json` **não** foi alterado (os pilares não aparecem no simulador; ver acima).
- Testes: `tests/test_mapear_dique.py` com 10 testes; `pytest tests` → 183 passed.

## 2026-11-18 — Pilares que aparecem: estruturas já existentes no mapa (`tools/achar_pilares.py`)
- Usuário: "os pilares tem que aparecer no mapa, pode usar estruturas já existentes no mundo parecidas ou algo assim".
- O motor do mundo SkyDive (binário 1.0.0 do notebook; o 1.1.0 do lab recusa igual) só registra os comandos SpawnAgent,
  DebugDraw, TeleportCamera, AddSensor, RemoveSensor, RotateSensor, RenderViewport, RGBCameraRate, AdjustRenderQuality,
  CustomCommand, SendAcousticMessage e SendOpticalMessage (`strings` do binário): não há como criar objeto estático.
- `tools/achar_pilares.py`: mapa de alturas do porto inteiro, fatias de LiDAR (360 lasers) abaixo e acima da água em pontos
  de água perto de estruturas, sentido dos lasers escolhido pela nuvem mais nítida, pilares = grupos pequenos e isolados
  presentes nas duas fatias, grupos de pilares; fotos dos grupos e teste do DebugDraw (caixas nas coordenadas do dique,
  fotografadas com RGB e profundidade). `mapear_dique.sensores/abrir` aceitam sensores extras.
- `tests/test_achar_pilares.py` (7 testes, cenário sintético com traçado de raios).

### Lab, 2026-11-18 13:57–14:24 (combinado com a outra sessão; `~/achar_pilares{,2,3}.log`, saídas em `achar_pilares/`)
- 1ª rodada (`f5ba1f4`, `20261118-135730`): mapa de alturas do porto (4.332 pontos a 20 pontos/s com `accel`), mas
  **todas** as fatias de LiDAR ficaram presas em (120,41; −242,28): o teleporte do motor varre o caminho e para no
  primeiro obstáculo (a 40 m de altura nada bloqueia; a −0,7 m, a primeira parede). Corrigido com o teleporte por cima
  (`mapear_dique.ir(por_cima=...)`: sobe no lugar, vai por cima, desce na vertical; `8ade2c7`).
- Teste do DebugDraw (`b128b05`, `20261118-140840`, fotografado do spawn do dique): as caixas desenhadas **aparecem na
  câmera RGB** (barras vermelhas) e **não aparecem na câmera de profundidade**; também não têm colisão (LiDAR/sonar não
  veem). Não serve como pilar para RGB+Depth nem para LiDAR+sonar.
- 3ª rodada (`8ade2c7`, `20261118-141438`): 296 pontos de LiDAR, 0 descartados; 37–39% dos lasers com impacto,
  mediana 15 m; sentido dos lasers +1 (16.290 × 32.324 células). Candidatos: 23 só abaixo da água (fileira a cada
  ~20 m em x ≈ 247,5 sob o cais leste; pedras do quebra-mar em x ≈ −130 a −80; canto sudeste), 5 só acima (postes do
  portão entre as bacias do dique em (133,9; −200,5) e (133,9; −207,5); peças da proa do navio) e **1 nas duas alturas**
  ((90,5; −229,1), junto à proa do porta-contêineres). **Não há grupo de pilares em água aberta no Pier-Harbor.**
- Agentes disponíveis (alternativa com geometria real): BlueBoat, BlueROV2, BlueROV2Heavy, DjiMatrice, Hydrone,
  TorpedoAUV; nenhum tem forma de pilar.
- Aguardando decisão do usuário (opções no relatório): pedir aos autores um mundo com SpawnProp; agentes parados como
  obstáculos; ou o dique como está (navio e paredes) sem pilares.

## 2026-11-18 — "Dê um jeito de criar os pilares ou quadrado compridos utilizando as paredes"
- `achar_pilares.py --analisar ... --diam-max 12 --isolamento 1.0` (blocos até 12 m): continua 1 só ((90,5; −229,1)). As
  paredes do mapa não formam pilares nem blocos dentro da água.
- `tools/pilares_agentes.py` (`7c4199f`, `41fe862`, `a5c7284`), lab 14:55–15:05:
  - 1ª rodada: TypeError (o estado do lote vem como dicionário, não lista); corrigido.
  - 2ª: sem segurar, os torpedos derivaram 0,6–0,9 m e os empilhados encostados foram arremessados 8–19 m.
  - 3ª (segurando a cada tick, 15 cm entre os empilhados): 17,96 passos/s; 11 de 12 agentes no lugar (atitude exata,
    0,861 m fixo entre origem do ator e centro); 1 (base do pilar (129,4; −148)) não chegou (6,94 m; o teleporte varre
    o caminho a partir de onde os clones nascem). LiDAR no ar: 4,28 / 6,24 / 1,20 / 4,61 m medidos × 4,52 / 6,42 /
    1,41 / 4,77 m geométricos (centro); na água, 3 de 4 (o que não chegou não aparece). Câmera RGB: colunas visíveis.
- Proposta de mudança no design.md (pilares feitos de agentes no GotoEnv), aguardando aprovação.

## 2026-11-18 — Obstáculos feitos de agentes no GotoEnv (T9)
- Aprovação do usuário: "Prefiro pilares mais grossos, pode colocar, e também, adicione mais obstácuos". design.md atualizado
  ("Mudança aprovada — obstáculos feitos de agentes"); tarefas T9–T11 no tasks.md. Trabalho na branch `spec/rotacao-hydrone`
  (a mesma cadeia em que o Goto já está, principal e submódulo).
- `config/goto_dique.json`: `agente_obstaculo` (TorpedoAUV 2,1 × 0,19 m, folga 0,15 m, feixe 0,05 m, `origem_eixo` 0 até
  calibrar); `pilares` → `obstaculos`; coordenadas reais da área conferida (x 127–135, y −155 a −145, `provisorio: false`):
  `pilares` = 4 pilares 2 × 2 × 3 níveis (48 torpedos); `dique` = esses + pilar central + 2 vigas na linha d'água + 2
  travessas no ar (66 torpedos). Motivo: os pilares precisam existir no simulador (SpawnProp recusado) e o usuário pediu
  pilares mais grossos e mais obstáculos.
- `core/goto.py`: `geometria_obstaculos`, `dist_capsulas`, `carregar_agente_obstaculo`, `_preparar_cenario`; agente em lote
  `obstaculo` no `_build_params`; `_posicionar_obstaculos` no `_reset` (espera no alto, descida de um nível por tick,
  repete quem não chegou, até 3 vezes); `_segurar_obstaculos` antes de cada tick em `_passo_sim`; `cmds` em dicionário;
  `_unwrap_state` lê `state['robot']`; colisão "pilar"/"viga" por cápsulas; `_spawn_pilares` removido.
- Testes: `tests/test_hydrone_goto.py` (17 novos: geometria, cápsulas, sobreposição, cobertura da faixa de voo, cenário do
  simulador, descida por nível, repetição, aviso, deslocamento por orientação, reimposição a cada tick; coordenadas
  antigas trocadas); `tests/test_sensores_goto.py` e `tests/test_rotacao_hydrone.py` adaptados (`_preparar_cenario`,
  simulador falso com os torpedos; a integração testada sem obstáculos). `pytest tests` → 209 passed.

## 2026-11-18 — T10: ferramenta de conferência no simulador
- `tools/conferir_obstaculos.py`: reset (tempo, fora do lugar, medido − imposto por orientação), varredura vertical do
  LiDAR a 1,5 m de um pilar (extensão real da coluna → `origem_eixo` sugerida), fotos RGB/profundidade (spawn no ar e na
  água, de cima do centro), anel do LiDAR × raio traçado em Python nas cápsulas (por obstáculo), passos/s com ações
  aleatórias e términos por motivo. Motivo: verificar no lab que os obstáculos existem para todos os sensores e calibrar o
  deslocamento da origem do ator (sinal desconhecido).
- `tools/testar_obstaculos_lab.sh`: pytest, conferência dos dois cenários, smokes `HydroneGotoPilares-v0/-v1/-v2` e
  `HydroneGotoDique-v0` (200 passos), processos do simulador a cada etapa.
- `tests/test_conferir_obstaculos.py` (8 testes: raio nas cápsulas, extensão da coluna, índice do laser, anel). `pytest tests`
  → 217 passed.

## 2026-11-18 — T11, 1ª rodada no lab (19:59–20:05, `e78a387`/`4867883`, `tools/testar_obstaculos_lab.sh`)
Combinado com a sessão "tcc" (o treino `teste_5m_rotrc_1` dela seguiu rodando; não foi tocado).

| Item | Resultado |
|---|---|
| pytest no lab | 217 passed |
| `pilares`, reset (posiciona 48 torpedos) | 7,7 s; 45 de 48 fora do lugar (mediana 4,12 m acima do ponto, atitude certa: pitch 90) |
| varredura vertical do LiDAR | nenhuma batida (pilares fora do lugar) |
| passos/s (Hydrone com 3 câmeras 960², profundidade e LiDAR 360) | 3,96 |
| smoke `HydroneGotoPilares-v0` | ok: 5,41 passos/s (6,1 h por 100k), reset 7,1 s, 2 episódios, sem NaN, obs no espaço |
| smoke `HydroneGotoPilares-v1` | `TypeError: float() argument must be a string or a real number, not 'dict'` |
| `dique` (66 torpedos) | `OSError: [Errno 24] Too many open files` (`/dev/shm/...obstaculo-id42...`); limite do lab: 1024 (rígido 1048576) |

Causas e correções (sem simulador; `pytest tests` → 220 passed):
- **Fora do lugar:** as aletas do TorpedoAUV têm ~0,27 m de envergadura (vista de cima na documentação,
  `biguasim_docs/.../torpedo-top.png`), mais que os 0,24 m entre eixos do feixe: os vizinhos se esbarram ao descer e o
  teleporte para no primeiro obstáculo. `folga_feixe` 0,05 → 0,13 (0,32 m entre eixos).
- **0,861 m:** é o `IMUSocket` (no nariz, ~0,89 m do centro na mesma figura), onde estavam os sensores dos torpedos; a origem
  do ator é o centro. `origem_eixo` fica 0 e os torpedos passam a ter só o DynamicsSensor com `UseCOM` (centro de massa).
- **`-v1`:** com mais de um agente, o BiguaSim devolve cada sensor do robô numa lista de um elemento (a DepthCamera vinha
  como `[dict]`); `GotoEnv._unwrap_state` tira da lista. O simulador falso dos testes passou a imitar esse formato.
- **Arquivos abertos:** `GotoEnv._subir_limite_arquivos` sobe o limite flexível do processo até 65536 (sem passar do rígido)
  quando há obstáculos.
- **Passos/s:** um sensor a menos por torpedo e a dinâmica em Python dos torpedos trocada por uma que devolve zero
  (`_dinamica_parada`); `tools/perfil_obstaculos.py` mede 0/12/48 torpedos e faz o cProfile para ver o que sobra.

## 2026-11-18 — T11, 2ª rodada no lab (20:08–20:20, `9574158`/`b855d92`)
- `perfil_obstaculos.py` (GotoEnv -v0 sem câmeras, 100 passos): sem obstáculos 5,02 passos/s; 12 torpedos 5,03 (5,12 segurando
  a cada 10 ticks); 48 torpedos 5,31 (5,57). **Os obstáculos quase não custam:** o passo é lento por causa da dinâmica do
  Hydrone em Python (cProfile: `hauv.step` ~180 ms por tick, `_s_dot_fn` 20× por tick com `roma`/torch) e da CPU dividida
  com o treino da sessão "tcc" (52% de CPU no momento). Os 17,96 passos/s do `pilares_agentes.py` eram com o Hydrone em
  `accel` (sem o modelo `hauv`).
- Posicionamento ainda falha: 12 torpedos → 2 fora do lugar; 48 → 36; `pilares` na conferência → 35 de 48; `dique` → ~40 de
  66. Hipótese: os clones nascem sobrepostos no mesmo ponto e o `set_physics_state` varre o caminho e para no primeiro
  obstáculo (inclusive na sobreposição). Mudança: no posicionamento os torpedos andam com `teleport` (outro comando do
  BiguaSim; testar no lab se não varre) e o último tick do posicionamento e os seguintes usam `set_physics_state` (zera a
  velocidade). `conferir_obstaculos.py` passa a imprimir as posições dos torpedos fora do lugar.
- Smokes: `HydroneGotoPilares-v0` ok; `HydroneGotoPilares-v1` ok (2 episódios, sem NaN, obs no espaço) depois da correção do
  estado por agente. `dique` abriu com 66 torpedos (limite de arquivos resolvido). LiDAR no ar mediu o pilar 0 (no lugar)
  com mediana 0,057 m de diferença para o raio traçado nas cápsulas.
- `pytest tests` → 221 passed.
- 3ª rodada (20:29, `c5eef0f`/`3547bcd`): `perfil_obstaculos.py` parou no 2º caso com `TypeError: Perfil._segurar_obstaculos()
  takes 1 positional argument but 2 were given` (a sobrescrita da ferramenta não recebia o parâmetro `teleporte` novo);
  corrigido na ferramenta. Antes disso: sem obstáculos 5,74 passos/s. A espera da fila (`pgrep -f testar_obstaculos_lab.sh`)
  achava o próprio `bash -c` e nunca terminava; o processo (meu) foi morto e a rodada relançada sem a espera.
- 4ª rodada (20:35–21:06, `432695f`): **com `teleport` no posicionamento, 0 torpedos fora do lugar** nos dois cenários
  (`pilares` 48, reset 6,64 s; `dique` 66 incluindo as vigas, reset 7,81 s; medido − imposto mediano 0,0 m por orientação).
  Varredura vertical: coluna medida −1,0 a 5,4 m × geométrica −1,2 a 5,4 m (passo 0,2 m; `origem_eixo` sugerida −0,1, dentro
  da resolução: fica 0). LiDAR × cápsulas, mediana por pilar: ar −0,16 / −0,09 / −0,15 m, água −0,20 / −0,28 / −0,13 m (o
  LiDAR mede um pouco antes: aletas). Perfil -v0: sem obstáculos 5,89; 12 torpedos 5,87 (6,02 segurando a cada 10 ticks).
- Mas o `pilares` terminou por "parede" no 1º passo depois de todo reset (conferência: 100 de 100; perfil com 48 torpedos:
  0,20 passos/s, 3503 ticks em 100 passos). `tools/diag_reset_goto.py` (`62ae78f`): no `pilares`, o Hydrone fica em
  (136,08; −153,84; 1,9) depois do reset (2,5 m do spawn, fora da área); no `dique`, no spawn. Causa provável: os clones
  nascem sobrepostos 28 m acima do spawn, o motor os separa com violência e algum acerta o robô (o resultado muda com o
  número de clones). Correções: (1) `_robo_no_spawn` no fim do posicionamento (teleport e depois set_physics_state no
  spawn, parado); (2) os clones nascem 30 m ao lado e 50 m acima da água (`NASCIMENTO_DESLOC`). `pytest tests` → 222 passed.
- Órfão meu: `pkill -f tools/perfil_obstaculos.py` (para encerrar o último caso, lento) deixou o simulador dele aberto (pid
  536798, SkyDive 1.1.0, iniciado 20:59:26). Morto com `kill`; os Holodeck da sessão "tcc" (bg_home/1.0.0, 19:44) não
  foram tocados.
- Incidente: numa reconexão do AnyDesk, o Chrome do notebook ganhou o foco com uma aba de propaganda do AnyDesk e um comando
  meu (`kill -0 536798 ... kill -9`) foi digitado nessa página (sem campo de texto em foco; nada mudou). Não mexi no Chrome;
  a janela do AnyDesk foi reativada por `xdotool windowactivate`.
- 5ª rodada (21:10–21:21, `656a851`/`58674b3`): **resolvido.**

| Item | `pilares` (48 torpedos) | `dique` (66 torpedos) |
|---|---|---|
| Hydrone depois do reset (`diag_reset_goto.py`, 3 resets) | no spawn (133,88; −152,6; 2,0), 3 passos sem término | igual |
| torpedos fora do lugar | 0 (reset 6,15 s) | 0 |
| conferência, passos/s com 3 câmeras 960², profundidade e LiDAR 360 | 5,22, nenhum término em 100 passos | (4ª rodada: 4,61) |
| smoke `-v0` (200 passos) | 7,18 passos/s (4,53 h por 100k), reset 5,05 s, 2 episódios, sem erro | 6,24 passos/s (5,36 h por 100k), reset 6,51 s, 2 episódios, sem erro |

  Smokes `HydroneGotoPilares-v1/-v2` ok na 2ª rodada (antes do teleport e do retorno do robô; o caminho do estado é o mesmo).
  Fotos no lab: `conferir_obstaculos/20261118-203620/{pilares,dique}/` (ar, água, profundidade, de cima). 0 processos meus
  no fim; sessão "tcc" avisada.

## 2026-11-19 — Smokes finais e piloto de treino (pedido do usuário: rodar no cluster com ~5M passos; aprovado "Sim" para smokes, kit do cluster e piloto)
- Lab (14:21–14:30, `acfa555`/`58674b3`, branch `spec/rotacao-hydrone`; laço de `smoke_test.py --steps 200 --frame-every 50`,
  saída em `~/smokes_goto.log`), com o treino da sessão "tcc" rodando ao mesmo tempo:

| Ambiente | passos/s | h por 100k | abrir (s) | obs | resultado |
|---|---|---|---|---|---|
| `HydroneGotoPilares-v1` | 5,48 | 5,9 | 7,66 | depth 9×100×100, rgb 9×100×100, state 9 | ok, 2 episódios, sem NaN/inf, obs no espaço |
| `HydroneGotoPilares-v2` | 3,88 | 10,6 | 21,06 | 26 | ok, idem |
| `HydroneGotoPilares-v0` | 5,65 | 5,7 | 8,44 | 12 | ok |
| `HydroneGotoDique-v0` | 5,71 | 5,8 | 7,88 | 12 | ok |

  0 simuladores meus no fim: os 4 processos do filtro eram da "tcc" (laço `teste_5m_rotrc_1`, o Python de treino e 2
  Holodeck). Com isso os smokes de `-v1`/`-v2` valem com o código final (teleport e robô de volta ao spawn).
- 5M passos nessas velocidades: ~10 dias (`-v1`) e ~15 dias (`-v2`) por run.
- `tools/piloto_goto_lab.sh` (novo): piloto de 20k passos, um run por vez (pedido da "tcc", por causa da RAM), `-v1`+cuprl
  e `-v2`+td3, `learning_starts=1000` (o padrão do td3, 25000, passa do piloto), avaliação a cada 10k com 1 episódio;
  encerra o meu run se a memória disponível cair abaixo de 5 GB (condição da "tcc").
- Cluster: `ssh -J teteu@10.230.108.173 teteu@cluster2` deu timeout do notebook (fora da rede da universidade).
- 1º lançamento do piloto (14:31): os dois runs saíram em 10 s com `OSError: Cannot save file into a non-existent directory:
  '.../treinos/piloto_goto/HydroneGotoPilares-v1_cuprl/curves'` (o `run.py` não cria a pasta de `curves_path`; a fila do
  cluster criava) e a contagem do grupo dava `0\n0` com `pipefail` (`integer expression expected`). Erros do script, corrigidos;
  nenhum simulador aberto.
- 2º lançamento do piloto (14:33, `a1e5644`), parado:
  - `HydroneGotoPilares-v1` + cuprl: `TypeError: GotoEnv.__init__() got an unexpected keyword argument 'pixel_channels' was
    raised from the environment creator for HydroneGotoPilares-v1 with kwargs ({'seed': 42, 'agent_type': 'Hydrone',
    'control_abstraction': 'cmd_vel_yaw', 'cenario': 'pilares', 'pixel_channels': ['rgb', 'depth'], 'include_state': True,
    'frame_size': [100, 100]})` (`run.py:150 __init__` → `:156 train` → `gym.make`). Causa: `run.py` `_resolve_env`
    (linhas 83–86) sempre põe `pixel_channels`/`include_state`/`frame_size` quando o agente é cuprl, e o
    `GotoPixelEnv.__init__` (`core/goto.py:624`) só aceita `frame_size`. O smoke não passa esses kwargs. **Correção proposta,
    não aplicada.**
  - `HydroneGotoPilares-v2` + td3: a memória disponível caiu de 23.920 MB para 5.114 MB em 86 s; o vigia encerrou o grupo
    (14:34:39), 0 processos meus depois, 24 GB disponíveis de novo. O buffer do td3 não é a causa (medido no notebook com os
    mesmos espaços: 0,2 GB para 1M transições, RSS 550 MB depois de 20k `store`). Suspeita: a octree do `ProfilingSonar`
    (`InitOctreeRange` 20 m, folha padrão `octree_min` 0,02 m) em cada simulador (treino + avaliação). Não medido.
- **Incidente:** às 14:23:18 o kernel matou por OOM o Python do `teste_5m_rotrc_1` da sessão "tcc" (pid 525540), durante o
  meu smoke do `-v2` (14:22:31–14:25:11), o provável causador; o treino dela voltou do checkpoint de 1,25M. O vigia de
  memória só existia no piloto. Combinado com a "tcc": nenhum treino meu no nautec enquanto o rotrc estiver ativo (~4 h),
  salvo aprovação do usuário; smokes curtos só com aviso; o `-v2` não roda no lab até a memória dele ser medida.
- Do PC do lab, `ssh -o BatchMode=yes teteu@10.230.108.173 hostname` responde (`2titancluster.cluster.local`): o cluster
  pode ser preparado a partir do lab.

## 2026-11-19 — Cluster2 para os treinos HydroneGoto (decisão do usuário: "Isso é para rodar nos clusters, não no pc do lab")
- Do notebook o ssh ao cluster dá timeout; o lab serve só de ponte de ssh (sem simulador nem treino lá).
- Cluster2 (16:39): 20 CPUs, 62 GB de RAM (50 disponíveis), `/home` com 322 GB livres, 2× Tesla V100S 32 GB (GPU 0 a 99%
  com 24,9 GB em uso por outro trabalho; GPU 1 com 1 GB). **O kit nunca tinha sido instalado lá** (sem `~/biguagym-v0.1.0`,
  venv nem mundos; só `~/biguasim_gold`, de outro trabalho, não tocado). Tem rsync, zstd, git e gcc; não tem python3.12
  nem conda.
- `setup/instalar_pc_lab.sh` (`735c844`): `SIM_VERSAO=1.1.0` usa a tag pública `v1.1.0` do hydrone-furg/biguasim (só
  leitura), a pasta `~/.local/share/biguasim/1.1.0/worlds`, `pip install -e --ignore-requires-python` (a 1.1.0 declara
  ==3.11 e roda no 3.12) e o manifesto `setup/skydive_manifest_1.1.0.txt`; o padrão (1.0.0) não muda.
- `tools/copiar_mundo_cluster.sh` e `tools/instalar_cluster_goto.sh` (`f2c69c6`): o mundo SkyDive 1.1.0 vai do lab ao cluster
  por rsync (com o manifesto); no cluster, Miniconda no home e o venv 3.12 pelo conda-forge, depois o instalador.
- Clonado no cluster: `~/biguagym-v0.1.0` na `spec/rotacao-hydrone` (`735c844`).
- 16:43: a sequência (cópia do mundo + instalação) foi digitada no terminal do lab, mas o AnyDesk caiu na digitação e não
  reconectou mais (preso em "Connecting"). Não sei se o comando foi aceito (log esperado: `~/cluster_setup.log` no lab).
- Correção do `-v1` + cuprl aplicada (usuário: "Conecta pelo pc do lab mesmo, e coloca 5 seeds por experimento"):
  `GotoPixelEnv.__init__` aceita `pixel_channels`/`include_state` e dá `ValueError` se pedirem algo diferente de
  `['rgb','depth']` com a pose. Testes novos em `tests/test_sensores_goto.py`; `pytest -q tests`: 225 passed.

## 2026-11-19 a 2026-11-24 — Lab fora do ar; setup do cluster concluído; smoke e piloto no cluster2
- O AnyDesk do lab ficou em "Connecting" de 19/11 16:43 até 22/11 03:52 (o AnyDesk do lab travou; o PC reiniciou em 21/11
  ~08:44). Nesse tempo, nada rodou.
- `~/cluster_setup.log` no lab: a sequência de 19/11 tinha sido aceita e terminou antes do reinício (`FIM_SETUP rc=0`):
  mundo SkyDive 1.1.0 copiado (11 GB, 348 arquivos, 16:42–16:58) e conferido pelo manifesto; Miniconda + venv 3.12
  (conda-forge) em `/home/users/teteu`; biguasim `743c6d9`; torch 2.7.1+cu126 com CUDA (V100S); 54 ids registrados.
  O submódulo ficou em `58674b3` (antes da correção do `-v1`): `git pull` + `submodule update` no cluster → `7b0b020`/`364ba77`.
- Uso da tela do lab combinado com a sessão "tcc" (ela e eu digitamos no mesmo AnyDesk): quem precisa pede e espera o "TELA
  LIVRE" do outro. Meu terminal é uma janela Terminator própria (`~/biguagym-v0.1.0`); a sessão AnyDesk (licença gratuita)
  cai a cada ~5 min e volta com Retry.
- 24/11 03:31 — `tools/smoke_ram_cluster.sh` (novo, `7b0b020`): smoke de 300 passos, GPU 1 (`CUDA_VISIBLE_DEVICES` +
  nvidia-smi falso, como na fila), RAM do grupo a cada 5 s. Cluster ocioso (as 2 GPUs com 0 MiB, 62,5 GB disponíveis).

  | ambiente | exit | passos/s (lab) | h/100k | make | pico RSS do grupo | NaN/inf | obs no espaço |
  |---|---|---|---|---|---|---|---|
  | HydroneGotoPilares-v2 | 0 | 2,06 (3,88) | 20,8 | 139,5 s | 11,4 GB (simulador ~10 GB) | 0 | sim |
  | HydroneGotoPilares-v1 | 0 | 4,15 (5,48) | 8,3 | — | 3,6 GB | 0 | sim |
  | HydroneGotoPilares-v0 | 0 | (a ler) | | | | | |

  - A memória do `-v2` é do simulador (o RSS do Holodeck sobe a ~10 GB na abertura e fica estável); com o vazamento do
    `close()` (`sim_alive_after_env_close: true`), um run do `-v2` pode chegar a ~30 GB (3 simuladores).
  - O Unreal foi para a GPU 0 (2,1–2,9 GB) mesmo com `CUDA_VISIBLE_DEVICES=1`; o Python ficou na GPU 1 (466 MB).
  - O cluster é mais lento que o lab: 5M passos ≈ 28 dias (`-v2`) e ≈ 14 dias (`-v1`) por run, com 1 run por ambiente.
  - 0 simuladores ao fim de cada ambiente.
- 03:42 — piloto pela fila (`treinos/cluster/runs_piloto_goto.csv`, `e43b208`; 20k passos, `eval_freq=10000`,
  `num_eval_episodes=1`, `agent.learning_starts=1000`, WORKERS=2, GPUS=1, MIN_RAM_MB=30000). 1ª tentativa falhou na hora:
  ```
  treinos/cluster/fila_cluster.sh: line 170: treinos/cluster/piloto_goto/runs/HydroneGotoPilares-v2_s0/saida.log: No such file or directory
  03:43:02 w0: fim HydroneGotoPilares-v2_s0 exit=1 processos_restantes=0
  ```
  Causa: `OUT` relativo; o worker faz `cd` para a pasta dele antes de gravar `$d/saida.log`. Parei a fila (kill do grupo;
  nenhum processo meu sobrou), apaguei a saída e relancei com `OUT` absoluto. Correção proposta (não aplicada):
  `OUT=$(realpath -m "$OUT")` no início da `fila_cluster.sh`.
- 03:44:38 piloto `-v2`+td3 e 03:45:38 `-v1`+cuprl em andamento (log `~/piloto_goto.log` no cluster).
- 04:22 — progresso com os dois runs em paralelo: `-v1`+cuprl 4.995 passos (~2,5 passos/s); `-v2`+td3 1.690 passos
  (~1,0–1,4 passos/s); perdas finitas, curvas sendo gravadas; 4 simuladores, VRAM 8,2 GB na GPU 0 e 1,8 GB na GPU 1 (todo
  Unreal renderiza na GPU 0). A ~2,5 e ~1,2 passos/s, 5M passos levariam ~23 dias (`-v1`) e ~45 dias (`-v2`) por run.
- Escolher a GPU do Unreal: o biguasim 1.1.0 monta os argumentos do Holodeck numa lista fixa
  (`environments.py:1047-1088`, `__linux_start_process__`; sem `-graphicsadapter`). O processo herda o ambiente, mas o
  cluster não tem a camada Vulkan `device-select` do Mesa (só `nvidia_layers.json`; loader 1.3.239), então `DRI_PRIME`
  não serve. GPUs: 0 = `17:00.0`, 1 = `65:00.0`. Restaria `r.GraphicsAdapter` no `Engine.ini` do mundo (todos os
  simuladores numa só GPU).
- **04:41 — vazamento de memória no simulador do `-v2` durante o treino.** RAM disponível do cluster em 5,5 GB; o
  Holodeck de treino do `-v2` (pid 129063) com RSS de 42→43,9 GB depois de ~57 min (no smoke de 300 passos ficava em ~10
  GB), o de avaliação (129352) com 5,8 GB. Encerrei o grupo do run (`kill -TERM -128999`, depois `-KILL`): 0 processos
  restantes, 55 GB disponíveis. O `-v1` continuou (simuladores de 1,6 e 1,3 GB). Suspeita: a octree do `ProfilingSonar`
  (folha `octree_min` 0,02 m) cresce conforme o veículo visita regiões novas. **O `-v2` não pode rodar 5M passos assim.**
- 06:11 — piloto do `-v1`+cuprl concluído (`estado.csv`: exit 0, 145 min, 0 simuladores ao fim): 20k passos, 133
  episódios, avaliações em 0/10k/20k (MR −1,02 / −1,04 / −1,03, 1 episódio cada; o agente ainda não aprendeu, esperado com
  20k passos); ~2,3 passos/s contando abertura e avaliações. Perdas finitas (último: A_LOSS −2,96, CR_LOSS 0,0035,
  CU_LOSS 0,40). Ao fim: 0 simuladores (o "1" do `pgrep -c -f` era o próprio `bash -c`), GPUs com 0 MiB, 62,5 GB disponíveis.
  `estado.csv` do `-v2`: exit 143 (o meu kill das 04:41), 57 min.
