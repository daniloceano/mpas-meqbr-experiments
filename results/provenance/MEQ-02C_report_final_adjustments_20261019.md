# MEQ-02C — Ajustes finais de apresentação do relatório

Data: 2026-10-19

Branch: `codex/meq-02c-oval-postprocessing`

Commit-base: `3c4e43335b70d3c418686999c924d00c30e5fffa`

## Alterações

1. A síntese configurável inicia na rede LiDAR com P0/2021 e LPI/2022
   selecionados exclusivamente a 100 m. As demais alturas continuam disponíveis
   para seleção manual.
2. P0/250 m está identificado como resultado descritivo e excluído dos testes
   de seleção científica.
3. Valores decimais do indicador passaram a usar o rótulo
   `Murphy skill médio (adimensional)`.
4. O relatório esclarece que 0,41 corresponde a 41% de redução do MSE frente
   ao ERA5 nos mesmos horários e que a síntese representa a média das reduções
   relativas individuais, não necessariamente a redução de um MSE agrupado.

## Verificações

- Seleção inicial: pontos P0 e LPI; períodos 2021 e 2022; altura 100 m.
- Cada experimento usa duas unidades observacionais LiDAR com peso igual.
- Médias idênticas ao estado validado anteriormente. Para EXP03: viés
  `-0.6331600753 m s-1`, RMSE `1.9035545341 m s-1`, correlação
  `0.6138644525` e Murphy skill `0.4101478739`.
- A seleção manual de P0/250 m funciona e informa o caráter descritivo.
- INMET preserva seleção inicial a 10 m e seis unidades estação-período.
- Visualizador meteorológico, figuras de validação e comparação pareada foram
  exercitados após a regeneração.
- Validador: 7 seções, 9 tabelas, 110 assets, 6 pontos e 68 métricas.
- Nenhum erro ou aviso no console do navegador.
- Os arquivos científicos de entrada conservaram seus hashes.

## Integridade final

- `results/report/index.html`:
  `5341e09ed64c15864c49b14090968acf4accb4e275d0a6dbf4cc3510dd1ec435`
- `results/report/report_manifest.json`:
  `a7515181fc9ba73b48264848bd4cea73962b932888f195f3dfb551c712691ff4`
- Backup pré-ajuste:
  `results/backups/report_pre_final_lidar_skill_20261019.tar.gz`
  (`56b36ab9142b14663e8d9a76cf1dc0ed96307936278f2e17eee9d8bb090185ba`)

Não foram executados commit, push, merge, rebase ou pull request. Nenhum valor
científico, método de agregação, script científico ou simulação foi modificado.
