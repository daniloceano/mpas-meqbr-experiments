# MEQ-02C — QA do refinamento final da interface científica

Data: 2026-10-19

Branch de trabalho: `codex/meq-02c-oval-postprocessing`

Commit-base: `3c4e43335b70d3c418686999c924d00c30e5fffa`

## Escopo

Validação do HTML portátil em `results/report/index.html`, sem alterar os
derivados científicos, sem reexecutar o MPAS e sem realizar operações Git de
escrita.

## Cenários verificados

1. O validador estático confirmou 7 seções, 66 IDs, 54 referências locais,
   9 tabelas, 110 ativos, 6 pontos observacionais e 68 registros de métricas.
2. Regressão do destaque: em P0/2021/150 m, EXP02 permanece vencedora de RMSE
   (`1.875137722760282 m s-1`) mesmo quando o cartão EXP02 é ocultado. EXP03 não
   recebe um destaque substituto; o painel informa o vencedor oculto.
3. Casos sintéticos de empate, valor ausente e direções distintas de otimização
   foram exercitados pelo validador.
4. O clique no marcador LPI atualizou o explorador para LiDAR/LPI/2022 e
   preservou a altura anterior de 150 m, válida no novo ponto. O botão explícito
   “Ir para métricas deste ponto” moveu o foco para o seletor correspondente.
5. Disponibilidade dos controles: P0 expôs 2021 e 50/100/150/200/250 m; LPI
   expôs 2022 e 50/100/150/200 m. As quatro estações INMET expuseram somente
   10 m e apenas seus períodos efetivamente disponíveis.
6. O conflito entre arraste e clique dos marcadores foi detectado no teste e
   corrigido; o mapa não captura o ponteiro quando o alvo é um marcador.
7. A síntese LiDAR completa apresentou 9 unidades por experimento e apenas 2
   unidades com valor adicionado calculado (100 m). A síntese INMET apresentou
   6 unidades estação-período e 6 valores adicionados por experimento.
8. As médias LiDAR foram recalculadas independentemente a partir de
   `results/tables/validation_point_metrics.csv` e coincidiram com o JSON
   incorporado. RMSE médio: CTL 2.1697, EXP01 1.9915, EXP02 1.9336 e EXP03
   1.8717 m s-1.
9. As contagens LiDAR completas foram: CTL 1 ganho, 0 perda, 1 diferença não
   detectável e 7 não avaliadas; EXP01/EXP02/EXP03, cada um, 2 ganhos, 0 perdas,
   0 diferenças não detectáveis e 7 não avaliadas.
10. O contraste CTL−EXP03 em LPI/2022/50 m mostrou delta de MSE `+2.32` com
    IC95% `[1.35; 3.46]`; ao inverter A e B, mostrou `-2.32` e
    `[-3.46; -1.35]`. Também foi verificado um caso de diferença não detectada
    (EXP01−EXP02, P0/2021/50 m).
11. A responsividade foi inspecionada visualmente em 1440 px, 700 px e 390 px:
    quatro, duas e uma coluna, respectivamente. Capturas desktop e móvel foram
    produzidas no navegador integrado durante a auditoria. Tabelas largas
    permanecem em contêineres com rolagem horizontal; o documento bloqueia
    overflow horizontal externo.
12. Não houve mensagens de erro ou aviso no console. A abertura por `file://`
    não pôde ser executada porque o navegador integrado autoriza somente HTTP e
    HTTPS. O pacote foi testado por servidor estático local em
    `http://127.0.0.1:8765/`, sem dependências externas.

## Integridade

- `results/report/index.html`:
  `6ec3103fc9c4b91e2873067bbb4e5aed7f41c5b8415126afd2954a500f60e8bc`
- `results/report/report_manifest.json`:
  `11f31a439a590052a911821d51f78d5a699fe0b1d823d7b48ada626d060cdc73`
- backup anterior ao refinamento:
  `results/backups/report_pre_final_interface_20261019.tar.gz`
  (`1d0399562b6d837ccc5297d11d95d1656d8b18c2782239b593cc237ce8f20c38`)

Os hashes dos quatro insumos científicos verificados antes e depois da edição
permaneceram inalterados:

- `validation_panel.json`: `614bcd7fce324556a91ed63da86ce40c05bb182dee312a9dd49f51543113f7af`
- `pairwise_tests_current.csv`: `da32d97a098503fda8a577b6ec5298710e8a184d2ae0d3faf86849c223968d21`
- `inmet_added_value.csv`: `c49ed0cc23b5df6c6e28c702a86f5daa3eda0cacdd53e82ae778efd247785cc5`
- `era5_added_value.csv`: `483e782fa65f11ea907218744543d9786cc6e670f33b3345585fed0176bc2068`

Nenhum commit, push, merge, rebase ou abertura de pull request foi realizado.
