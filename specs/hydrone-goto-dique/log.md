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
