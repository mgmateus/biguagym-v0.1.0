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
