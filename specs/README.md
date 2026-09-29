# Specs

Cada mudança de código tem uma pasta aqui:

```
specs/<nome>/
  requirements.md   o quê e por quê (fase 1)
  design.md         como (fase 2)
  tasks.md          checklist de implementação (fase 3)
  log.md            registro do que foi executado (fase 4)
```

Para aprovar uma fase, troque a primeira linha do arquivo para `Status: aprovado`
(ou peça ao Claude Code para fazer isso depois de revisar).

Specs sugeridas:
- vazamento-simulador — encerrar o simulador no close() e reutilizar o ambiente de avaliação
- logs-por-run — fault.log e crash.log por execução
- pipeline-pixels — trocar np.resize por cv2.resize + transpose
- acelerar-treino — frames_per_sec e CameraView só na avaliação
- sensores-isolados — configs para testar um sensor por vez
