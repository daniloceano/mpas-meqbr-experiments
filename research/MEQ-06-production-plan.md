# MEQ-06 — Plano de produção da `EXP03`

> **Versão:** 1.0 — 19/11/2026 (missão MEQ-06.3), base `main@41b7019`.
> **Situação:** plano. Nenhuma simulação, download ou pré-processamento foi feito ou autorizado por este documento. Cada missão da seção (i) exige autorização própria.
> **Decisões de base:** `DEC-MEQ-001` (`EXP03`), `DEC-MEQ-005` (90 processos compactos com fixação), `DEC-MEQ-006` (período e pontos de decisão), em [`MEQ-03-selection-decision.md`](MEQ-03-selection-decision.md).

## a) Período e pontos de decisão (`DEC-MEQ-006`)

| Item | Valor |
|---|---|
| Início da integração (spin-up) | 2021-10-21 00 UTC |
| Início da produção (fim do spin-up) | 2021-11-01 00 UTC — 11 dias de spin-up descartados, como na perna 2021 das rodadas validadas (a perna 2022 teve 10) |
| Duração | aberta, em trechos mensais por restart |
| Ponto de decisão 1 | 2023-06-30 (fim do dia; restart de 2023-07-01 00 UTC) |
| Ponto de decisão 2 | 2023-11-30 (restart de 2023-12-01 00 UTC) |
| Ponto de decisão 3 | 2025-01-31 (restart de 2025-02-01 00 UTC) |
| Continuação além de cada ponto | exige nova autorização do responsável (nova `DEC-MEQ-NNN`) |

Meses "dentro da amostra" (usados na seleção MEQ-03): **nov/2021** e **out/2022**. Os demais são independentes; a validação final reporta os dois grupos em separado. Observações da validação final: P0, SODAR P1 (complementa a `DEC-MEQ-003`), LPI, ANM-1/PPE1A e estações ISD, conforme o painel [`results/obs_availability/`](../results/obs_availability/index.html).

Disponibilidade nas janelas com início em 2021-11 (`results/obs_availability/candidate_windows_12_24_36.csv`):

| Janela | Fim | Horas válidas (total) | Perfiladores (h) | SODAR P1 (h) | ANM-1/PPE1A (h) | Dias simultâneos | Meses MEQ-04 |
|---|---|---|---|---|---|---|---|
| 12 meses | 2022-10-31 | 70 443 | 10 944 | 6 830 | 6 768 | 121 | 2 |
| 24 meses | 2023-10-31 | 153 445 | 19 092 | 6 830 | 14 781 | 121 | 2 |
| 36 meses | 2024-10-31 | 232 026 | 27 745 | 6 830 | 23 213 | 121 | 2 |

## b) Configuração

- **Modelo e física:** `EXP03` (`DEC-MEQ-001`), malha oval `meqbr_05km_oval_meq02a` (102 968 células, 55 níveis); namelist e streams da `EXP03` validada, sem alteração do início ao fim. **Proibido mudar a física** durante a produção.
- **Paralelismo:** 90 processos compactos, 45 núcleos físicos × 2 tarefas SMT, 11 núcleos livres no nó de 56 (`DEC-MEQ-005`).
- **Partição:** `graph.info.part.90` (a mesma usada no benchmark MEQ-05.5), **copiada** para o diretório de produção antes da 1ª execução; registrar o MD5 da cópia e da origem.
- **Comando** (lista de fixação da configuração `P90C`, verificada contra `lscpu`/sysfs no benchmark; fonte: `results/tables/meq05_5_parallel_benchmark_complement.csv`, coluna `mpiexec_cmd`; registro em `docs/provenance/MEQ-05.5-benchmark-complement-record.md`, listas exatas em `logs/*/mpiexec_cmd.txt` e verificação em `records/blocks_cpu_list_check.tsv` no Swell):

```bash
mpiexec -n 90 -bind-to user:0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105 ./atmosphere_model
```

  Núcleos físicos 0–22 e 28–49 com seus irmãos SMT (c + 56); ficam livres os núcleos 23–27 e 50–55.

## c) Saída — **DECISÃO PENDENTE**

Proposta: manter a lista horária atual (`stream_list.atmosphere.wind_energy`, 34 variáveis, `output_interval="1:00:00"`), igual à das rodadas validadas, para comparabilidade com a MEQ-03/04 e com o teste 60 × 90.

- Tamanho medido: **192 475 360 B por arquivo horário (192,5 MB)** → **~140,6 GB por mês** (30,44 dias), ~1,69 TB por ano, sem compressão (CDF5). Fonte: `docs/provenance/MEQ-05.5-benchmark-complement-record.md`, "Levantamento de disco".
- 8 variáveis 3D ocupam ~95 % do arquivo (ROADMAP, MEQ-06). Alternativa a decidir: reduzir as variáveis 3D ou mover parte delas para um stream de menor frequência. A decisão deve ser tomada **antes** da MEQ-06.7, porque a lista não muda depois de iniciada a produção.
- O history é escrito desde o início da integração; os 264 arquivos do spin-up (~50,8 GB) são mantidos até o fim do trecho de nov/2021 e só apagados com autorização.

## d) Restart e trechos

- **Trechos mensais:** cada trecho começa do restart do dia 1 do mês e termina no dia 1 do mês seguinte (o 1º trecho vai de 2021-10-21 a 2021-12-01, cobrindo spin-up e nov/2021). Restart diário (`restart` a cada 24 h, 2,28 GB cada), como nas rodadas validadas.
- **Teste de restart prévio (MEQ-06.6):** a 90 processos, com a mesma partição e a lista de fixação acima, a partir das condições iniciais do bloco 1 (2021-10-21 00 UTC):
  1. rodada A: 2 dias contínuos;
  2. rodada B: 1 dia, parada, reinício pelo restart do dia 1, mais 1 dia;
  3. comparar os history horários de A e B no dia 2 (diferença máxima absoluta por variável; esperado: idênticos bit a bit). Diferença não nula é reportada antes de qualquer produção.
  Custo: 4 dias simulados (~0,16 dia de máquina) e ~18,5 GB temporários de history (96 arquivos), apagáveis após o registro.
- **Retenção:** manter o restart do dia 1 de cada mês e os 3 mais recentes; os demais restarts diários podem ser removidos **somente com autorização**. Até o ponto 1, isso é no máximo 24 restarts (~55 GB).

## e) Teste 60 × 90 (invariância com o número de processos)

Comparar nov/2021 da produção (90 processos, fixação) com a rodada existente da `EXP03` de out–nov/2021 (60 processos, sem fixação), que **não** é emendada à produção (`DEC-MEQ-006`). As duas partem do mesmo instante (2021-10-21 00 UTC) e devem usar as mesmas forçantes (ver f).

- **Variáveis:** vento a 10 m e a 100 m (velocidade; componentes quando disponíveis).
- **Métricas:** diferença máxima absoluta e RMS da diferença, por hora e no mês, (1) nos sítios (P0, P1/SODAR, LPI, ANM-1/PPE1A e estações do painel) e (2) no domínio inteiro.
- **Leitura:** diferença nula = invariância; diferença pequena e não crescente = arredondamento de ponto flutuante dependente da decomposição; diferença que altera métricas de validação de nov/2021 é reportada ao responsável antes de seguir além do ponto 1.

## f) Pré-processamento em blocos

**Bloco 1:** 2021-10-21 00 UTC → 2023-07-01 00 UTC (618 dias; cobre o ponto de decisão 1). Blocos seguintes até 2023-12-01 e 2025-02-01, cada um sob autorização própria.

| Produto | Base de cálculo | Bloco 1 |
|---|---|---|
| ERA5 bruto (caixa larga `15/-64/-16/-24`, da `EXP02`) | ~2,85 GB/mês × 21 meses (out/2021 a jun/2023) | ~60 GB |
| LBC | 159 188 972 B a cada 6 h × 2 473 arquivos | ~394 GB |
| init (`init.nc`) | 875 129 724 B, uma vez | ~0,9 GB |
| sfc_update (OISST diária corrigida) | 34 731 176 B por perna de 41 dias (~0,85 MB/dia) | ~0,5 GB |
| **Total do bloco 1** | | **~455 GB** |

- **Tempo (estimativa, sem contar o download):** o pré-processamento da perna 2022 da `EXP03` (`run_preproc_2022.log` no Swell; `init_atmosphere` casos 7/9/8) levou ≈ 148 s para 41 dias. O registro versionado em `results/provenance/EXP03_2022/` dá `preproc.elapsed_seconds` = 149 s (2026-10-14 16:12:25 → 16:14:54 UTC) e 12 s para a conversão da OISST (`oisst_conversion.elapsed_seconds`). Extrapolado linearmente para os 618 dias do bloco 1: ~37 min de pré-processamento e ~3 min de conversão da OISST. O download do ERA5 não está incluído e tende a dominar. A MEQ-06.5 mede e registra o tempo real do 1º mês antes de seguir.
- **Fonte dos números:** LBC, init e sfc_update em `docs/provenance/MEQ-05.5-benchmark-complement-record.md`; o valor do ERA5 (~2,85 GB/mês) foi informado na missão e **não está registrado no repositório**; a MEQ-06.5 deve medi-lo e registrá-lo em `data/metadata/`.
- **Correção costeira da OISST:** a conversão OISST → intermediário deve usar `usp-utils/pre_proc/real_data/oisst_to_intermediate.py` com `oisst_land_fill.py` (função `fill_land_sst_nearest_ocean`). Log esperado, por arquivo: `[QC] coastal-safe SST: preserved N ocean cells; extended M land cells from nearest ocean; ocean range a..b degC`, seguido de `[OK] <arquivo> (… MB)`. Depois do `init_atmosphere` caso 8, `scripts/03_selection/check_sst_forcing.py` é **portão obrigatório**: deve retornar zero células oceânicas no valor de preenchimento de terra.
- **Verificação do MPAS-Research em `6754c6f` (consulta somente leitura à API do GitHub, 19/11/2026):** `6754c6f40fa41c96416067c82ee3219a6526acac` (09/10/2026 11:28 UTC; mensagem "Merge pull request #19 from CGFD-USP/fix/oisst-coastal-land-fill") é a ponta de `master` e ancestral de `develop` (124 commits atrás). Tem um único pai, e nem a cabeça do PR #19 (`df62398`) nem o merge registrado pelo GitHub (`13eced8`, em `develop`) são seus ancestrais: é uma reaplicação do PR #19 em `master`, não o mesmo commit. **Conteúdo:** os 5 arquivos alterados pelo PR #19 (`README.md`, `oisst_to_intermediate.py`, `oisst_clim_to_intermediate.py`, `oisst_land_fill.py`, `test_oisst_land_fill.py`, em `usp-utils/pre_proc/real_data/`) têm blobs Git idênticos em `6754c6f` e em `df62398`. **Conclusão:** `6754c6f` contém a correção do PR #19. Falta confirmar, na MEQ-06.5, que a cópia usada no Swell está nesse commit (`git rev-parse HEAD` e `git status` limpo).
- **Reaproveitamento de out–nov/2021:** só se os arquivos forem idênticos (MD5) aos usados na rodada validada da `EXP03`. Atenção: na perna 2021, os links de `init.nc` e `lbc` resolvem para `preproc/attempt_01_contaminated_oisst/…` (MEQ-05.5; `MEQ-02D-experimental-configurations.md`); o nome do diretório não implica contaminação desses arquivos (a SST corrigida está no `sfc_update.nc`), mas o MD5 decide. Arquivos sem MD5 coincidente são regenerados.

## g) Custos

Vazão de referência: **25,2 dias simulados por dia de máquina** (90 compactos, MEQ-05.5; P90E/P90C ≈ 25,2 no bloco 2). Com a correção pela produção do relatório do benchmark (fator 1,2233 sobre s/passo; 16,7 dias de máquina por ano simulado), a vazão efetiva cai para ~21,9 dias/dia; ambas são mostradas. Contagem a partir de 2021-10-21 (spin-up incluído).

| Até | Dias simulados (acumulado) | Dias de máquina a 25,2 | Dias de máquina corrigidos (~21,9) | History (TB) | Restarts retidos (GB, máx.) | LBC (GB) | ERA5 (GB) | Disco total (TB) |
|---|---|---|---|---|---|---|---|---|
| Ponto 1 — 2023-06-30 | 618 | 24,5 | 28,3 | 2,85 | 55 | 394 | 60 | ~3,4 |
| Ponto 2 — 2023-11-30 | 771 (+153) | 30,6 (+6,1) | 35,3 (+7,0) | 3,56 | 66 | 491 | 74 | ~4,2 |
| Ponto 3 — 2025-01-31 | 1 199 (+428) | 47,6 (+17,0) | 54,9 (+19,6) | 5,54 | 98 | 764 | 114 | ~6,5 |

- History com a lista atual (192,5 MB/h, spin-up incluído); restarts = dia 1 de cada mês + 3 mais recentes (2,28 GB cada); init e sfc_update somam menos de 2 GB.
- Mais o teste de restart (~0,16 dia de máquina, ~18,5 GB temporários) e o pré-processamento (~37 min estimados para o bloco 1, sem o download).
- Espaço livre em `/p1-swell`: ~126 TB em 13/11/2026 (diagnóstico não versionado; reconferir antes de cada trecho).
- Dias de máquina supõem execução contínua no nó compartilhado; interferência de outros usuários aumenta o prazo.

## h) Monitoramento e falhas

- **Antes de cada trecho:** carga do nó (`uptime`), núcleos livres na lista de fixação (nenhum processo alheio em 0–22, 28–49 e irmãos SMT), disco livre ≥ 2 × o volume do trecho (~300 GB por mês com a lista atual), presença e MD5 das forçantes do trecho e do restart de partida.
- **Acompanhamento diário:** data simulada atual, vazão das últimas 24 h (dias simulados/dia), último restart escrito, disco livre e ocupado pela produção, erros no `log.atmosphere.*`. Registrar em arquivo de acompanhamento versionável.
- **Falha:** retomar pelo último restart íntegro, sem alterar configuração, partição ou fixação; registrar a interrupção e o reinício.
- **Instabilidade numérica** (CFL, NaN, valores fora de faixa, abortos repetidos no mesmo instante): **parar e reportar** ao responsável. **Proibido mudar a física**, o passo de tempo ou a difusão sem nova decisão.

## i) Sequência de missões futuras (cada uma exige autorização)

1. **MEQ-06.5** — pré-processamento do bloco 1 (2021-10-21 → 2023-07-01): download do ERA5 com proveniência, OISST com correção costeira, `init`, `lbc` e `sfc_update`; portão `check_sst_forcing.py`; MD5 de tudo; medição do tempo.
2. **MEQ-06.6** — teste de restart (2 dias contínuos × 1+1) a 90 processos.
3. **MEQ-06.7** — produção até o ponto de decisão 1 (2023-06-30), com o teste 60 × 90 em nov/2021 analisado logo após o 1º trecho. Pré-requisito: decisão da lista de saída (c).

## j) Limitações

**Herdadas:**
- Divergência de `to_hourly` (janela de 7/5 amostras em vez de 6), registrada como limitação (`DEC-MEQ-004`); afeta a validação final da mesma forma que a seleção.
- Benchmark medido em janelas de 3 h a partir de restart, não em rodada longa (`DEC-MEQ-005`).
- Controle de qualidade assimétrico entre P0 e SODAR (nota de 13/11/2026 da `DEC-MEQ-003`); fuso do SODAR por inferência.
- Fusos não documentados das janelas de `config/experiments.yaml` (pendência 3 da `DEC-MEQ-003`, não bloqueante).
- Espaço livre em disco de 13/11/2026 não versionado.

**Novas:**
- Invariância 60 × 90 não testada até a MEQ-06.7; se houver diferença, nov/2021 da produção e da seleção não são idênticos.
- ANM-1/PPE1A sem altura nem fuso informados (horário tratado como UTC); qualificação por avaliação independente não versionada.
- Volume do ERA5 por mês não registrado no repositório; tempo de pré-processamento estimado por extrapolação linear de uma perna de 41 dias (download não incluído).
- `6754c6f` é uma reaplicação do PR #19 em `master`, não o merge registrado em `develop`; conteúdo idêntico nos arquivos do PR, demais diferenças de histórico não avaliadas.
- Custos além do ponto 1 são projeções; a condição de revisão da `DEC-MEQ-005` (vazão muito diferente) é avaliada com os números reais do 1º trecho.
- Meses dentro da amostra (nov/2021, out/2022) não são validação independente.
