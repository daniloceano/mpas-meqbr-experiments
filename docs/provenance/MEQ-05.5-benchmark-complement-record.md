# MEQ-05.5 — Registro do ensaio complementar de paralelismo e do levantamento de disco

- **Autorização:** pesquisador, 17/11/2026: missão original "MEQ-05.4", depois a retomada com desenho em dois blocos e a resolução do conflito de códigos. O escopo incluía partições METIS N = 45 e 90, ensaios de 3 h a partir de restart dentro de um teto de 8 h de máquina, inventário de disco somente leitura, branch, commit e PR sem merge.
- **Código:** **MEQ-05.5**. Na `main@de28eb1`, o item `MEQ-05.4` da §8 do `research/ROADMAP.md` já descrevia outra tarefa (ascendência da `EXP03` e aba de timelines no HTML principal), e o código MEQ-05.3 já estava usado pelo relatório separado do benchmark (PR #19). Por decisão do pesquisador:
  - `MEQ-05.4` mantém a tarefa do HTML principal, sem a curva de saturação;
  - `MEQ-05.5` é este ensaio;
  - `MEQ-05.6` é a atualização do relatório do benchmark.
- **Nomes sem renomeação:** a branch `meq-05.4-parallel-complement`, a pasta `results/benchmark/MEQ-05.4/` e os diretórios `MEQ054_*` no Swell mantêm os nomes. Correspondência: **`MEQ054_*` → MEQ-05.5**.
- **Correção "Os":** não existe na `main`, portanto foi descartada.
- **Base:** `origin/main` em `de28eb1412239e3256e9a7b54c5fed12910e061f`.
- **Tabela:** `results/tables/meq05_5_parallel_benchmark_complement.csv` (26 linhas), gerada por `scripts/05_benchmark/parse_benchmark_complement.py`. Ela não altera `results/tables/meq05_parallel_benchmark.csv`.
- **Logs e registros:** `results/benchmark/MEQ-05.4/` (`logs/`, `records/`, `partitions/`, `scripts/`), sem NetCDF e sem links simbólicos.

Este documento registra o que foi feito e medido. Não contém interpretação nem recomendação de configuração.

## Ambiente

Mesmo nó, executável, ambiente MPI e caso de restart da MEQ-05.2 (ver `MEQ-05.2-benchmark-record.md`):
- MPAS-Atmosphere 8.4.1 e MPICH 4.2.3 (Hydra);
- restart de 2021-11-15 00 UTC da `EXP03`, 3 h simuladas, 360 passos de 30 s, mesma saída da MEQ-05.2;
- diretório de trabalho `/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2/MEQ054_*`.

Nada foi recompilado. Nenhum dado, forçante, rodada de produção ou código do MPAS foi alterado, e nada foi apagado.

| Script | sha256 |
|---|---|
| `scripts/setup_meq054.sh` (partições) | `897e202e8f7186fa166af25974649f8e7fbdc827efab58ce427477e5e394f050` |
| `scripts/run_meq054_launch1.sh` (tentativa 1, reconstruído) | `19feb6b7a4cc836c56831647e8121a59ac7f476bfac63e4c7d9d375dee6a0401` |
| `scripts/run_meq054.sh` (tentativa 2) | `0d56162f4cc8a36cc5b143b4a1bd2a44767b2066a77bc5ac38a64af663c60131` |
| `scripts/run_meq054_blocks.sh` (desenho em blocos) | `b8e32cba4f219a8396e798c0585ffeb8ff4a160ad658b3375b3f7e528829b352` |
| `scripts/cpu_others.py` (CPU de outros usuários e MHz) | `ee28a40572f04db57c2cd6fdff1079c4a043667cebbc7f6ce804b957f7444f01` |
| `scripts/disk_inventory_meq054.sh` (Etapa 4) | `3c1c39d8e44e17546aa6a23d01988fa9465142a406687c140e4ab541d545d1f4` |

## Partições (Etapa 1)

Parâmetros: `gpmetis -minconn -contig -niter=200`, sobre o mesmo `graph.info` da MEQ-05.2. Logs em `partitions/`.

| N | Corte de arestas | Volume de comunicação | Desbalanço | Contíguas |
|---|---|---|---|---|
| 45 | 8770 | 8891 | 1.001 | sim |
| 90 | 12798 | 13052 | 1.002 | sim |

## Casos

Na fixação com `-bind-to user:<lista>`, o irmão SMT da CPU *c* é a CPU *c* + 56.

| Caso | Processos | Fixação |
|---|---|---|
| `REF_A56` | 56 | físicos 0–55, como `A_N056` da MEQ-05.2 |
| `REF_B112` | 112 | todas as CPUs lógicas, como `B_N112` |
| `P90C` | 90 | compacto: 45 núcleos físicos com os 2 threads (soquete 0 inteiro + 17 núcleos do soquete 1); 11 núcleos inteiros livres |
| `P90E` | 90 | espalhado: os 56 físicos + 34 irmãos SMT |
| `Q45S` | 2 × 45 | pares simultâneos, espalhado |
| `Q45C` | 2 × 45 | pares simultâneos, compacto (10 núcleos inteiros livres) |
| `Q56` | 2 × 56 | pares simultâneos; cada membro usa um thread de cada núcleo físico |
| `E90C` | 90 | igual a `P90C`, com a saída horária do `wind_energy` escrita (`outputs_stat.tsv`) |

As listas exatas estão em `logs/*/mpiexec_cmd.txt`, e a verificação contra `lscpu`/sysfs em `records/blocks_cpu_list_check.tsv`.

## Histórico das tentativas

1. **Tentativa 1** (desenho original): o controle `CTRL_A56_r1` deu 1.19519 s/passo, −2.30 % em relação a `A_N056` da MEQ-05.2. Antes do P90C, o usuário `japq` estava rodando `julia` a ~112 % de CPU, e o driver parou por nó ocupado. Registros: `records/*_launch1*`.
2. **Tentativa 2** (relançamento): o controle `CTRL_A56_r2` deu 1.27681 s/passo, +4.37 % em relação a `A_N056`. A diferença entre r1 e r2 foi de 6.8 %, e havia um processo `python` do usuário `ronald` ativo. A condição de parada do controle foi atingida. Registros: `records/*_launch2*` e `records/trials_launch1_2.tsv`.
3. **Mudança de desenho** (retomada aprovada pelo pesquisador): dois blocos, cada um na ordem REF_A56 → P90C → P90E → Q45S → REF_B112 → Q45C → Q56 → E90C → REF_A56.
   - Critério de nó livre a cada checagem: carga(1 min) < 2, nenhum processo de modelo alheio e nenhum processo de outro usuário com CPU instantânea > 10 %. Antes de cada bloco, 3 checagens limpas espaçadas de 2 min; antes de cada ensaio, 1.
   - Monitoramento a cada 30 s durante os ensaios. Um processo alheio acima de 25 % em 2 amostras seguidas marca o ensaio como `interferido`, e ele é repetido uma vez ao fim do bloco.
   - Um bloco é válido se os dois REF_A56 diferem em no máximo 3 %.
   - `CTRL_A56_r1`/`r2` ficam fora dos cálculos (logs preservados em `logs/MEQ054_CTRL_A56_r*`). A comparação com a MEQ-05.2 é apenas informativa.

## Execução em blocos

- Driver iniciado em 2026-11-17T15:50:49Z e encerrado em 2026-11-17T22:54:47Z (`records/DONE`).
- Espera por nó livre: 13579 s (3.77 h) no total, dentro do limite de 48 h.
- Tempo de máquina dos ensaios em blocos: 11852 s, mais 1144 s das tentativas 1 e 2, ou seja, **12996 s (3.61 h) de 8 h**.

| Bloco | Tentativa | REF_A56 inicial (t_int, s) | REF_A56 final (t_int, s) | Diferença | Válido |
|---|---|---|---|---|---|
| 1 | 1 | 448.53 (`REF_A56_first_redo`) | 436.91 | −2.63 % | sim |
| 2 | 1 | 431.28 | 434.72 | +0.79 % | sim |

Nenhum bloco precisou ser refeito.

**Ensaios interferidos** (bloco 1), ambos repetidos ao fim do bloco:

| Ensaio | CPU alheia máxima | Repetição | Uso nos cálculos |
|---|---|---|---|
| `REF_A56_first` | 133 % | `REF_A56_first_redo` limpo | o ensaio interferido fica fora (`used_in_stats = False`); a repetição entra |
| `P90C` | 130 % | `P90C_N090_redo` limpo | idem |

Nos demais ensaios, a CPU alheia máxima ficou ≤ 6.8 %, exceto em `B2 Q56` (20.2 %, abaixo do limiar de 25 %).

## Resultados medidos (Etapa 2/3)

Médias por bloco dos ensaios usados nos cálculos:
- **s/passo** = `time_integration / 360`;
- **vazão** = dias simulados por dia de parede, só integração;
- **norm.** = valor dividido pela média dos REF_A56 do mesmo bloco;
- **par** = soma da vazão dos dois membros (dias simulados por dia de nó).

| Caso | Bloco | s/passo | s/passo norm. | Vazão | Vazão norm. | Par | Par norm. | MHz médio |
|---|---|---|---|---|---|---|---|---|
| REF_A56 | 1 | 1.2298 | 1.0000 | 24.40 | 1.000 | | | 2622 |
| REF_A56 | 2 | 1.2028 | 1.0000 | 24.94 | 1.000 | | | 2590 |
| REF_B112 | 1 | 1.1216 | 0.9121 | 26.75 | 1.096 | | | 2432 |
| REF_B112 | 2 | 1.1115 | 0.9241 | 26.99 | 1.082 | | | 2435 |
| P90C | 1 | 1.1910 | 0.9685 | 25.19 | 1.033 | | | 2577 |
| P90C | 2 | 1.1915 | 0.9906 | 25.18 | 1.010 | | | 2568 |
| P90E | 1 | 1.2115 | 0.9851 | 24.76 | 1.015 | | | 2493 |
| P90E | 2 | 1.1905 | 0.9898 | 25.20 | 1.010 | | | 2468 |
| E90C | 1 | 1.1930 | 0.9701 | 25.15 | 1.031 | | | 2567 |
| E90C | 2 | 1.1745 | 0.9765 | 25.54 | 1.024 | | | 2638 |
| Q45S s0 / s1 | 1 | 2.2554 / 2.7511 | 1.834 / 2.237 | 13.30 / 10.91 | 0.545 / 0.447 | 24.21 | 0.992 | 2287 |
| Q45S s0 / s1 | 2 | 2.2505 / 2.7424 | 1.871 / 2.280 | 13.33 / 10.94 | 0.534 / 0.439 | 24.27 | 0.973 | 2251 |
| Q45C s0 / s1 | 1 | 2.2579 / 2.7062 | 1.836 / 2.201 | 13.29 / 11.09 | 0.545 / 0.454 | 24.37 | 0.999 | 2306 |
| Q45C s0 / s1 | 2 | 2.2427 / 2.6988 | 1.865 / 2.244 | 13.38 / 11.12 | 0.536 / 0.446 | 24.49 | 0.982 | 2325 |
| Q56 s0 / s1 | 1 | 1.9923 / 2.5321 | 1.620 / 2.059 | 15.06 / 11.85 | 0.617 / 0.486 | 26.91 | 1.103 | 2096 |
| Q56 s0 / s1 | 2 | 2.0548 / 2.5343 | 1.708 / 2.107 | 14.60 / 11.84 | 0.585 / 0.475 | 26.44 | 1.060 | 2172 |

- **Pares:** nos pares (s0/s1), o membro s1 mede sistematicamente mais tempo de integração que o s0. A mesma assimetria aparece nos pares `D_N028x2` da MEQ-05.2 (2.4010 / 2.7985 s/passo).
- **E90C contra P90C do mesmo bloco:** s/passo +0.17 % no bloco 1 e −1.43 % no bloco 2. O `stream_output` acrescentou 5.97 s e 6.25 s em relação à linha de base sem saída.
- **Memória:** maior processo (`/usr/bin/time -v`) entre 535 e 599 MB em todos os casos, nas colunas `max_rss_kb_*` e `*_vmhwm_*` do CSV.
- **Comparação informativa com a MEQ-05.2** (média dos casos equivalentes, s/passo):
  - `REF_A56` = 1.2162 contra `A_N056` = 1.2233 (−0.57 %);
  - `REF_B112` = 1.1166 contra `B_N112` = 1.1072 (+0.85 %).

## Levantamento de disco (Etapa 4)

Inventário somente leitura das duas pernas de produção da `EXP03` (`20211101_20211201` e `20221001_20221101`), capturado em 2026-11-17T23:03Z:
- `records/disk_inventory.txt`: saída completa, inclusive o `ncdump -h` de um history;
- `records/history_variables.csv`: 34 variáveis com tipo, dimensões e bytes por arquivo.

Tamanhos por perna (aparentes, em bytes; as duas pernas são idênticas nos tamanhos):

| Categoria | Arquivos | Por arquivo | Total |
|---|---|---|---|
| history (horário, `wind_energy`) | 985 | 192 475 360 | 189 588 229 600 |
| restart (diário) | 41 | 2 284 781 648 | 93 676 047 568 |
| lbc (links para `preproc*/`) | 165 | 159 188 972 | 26 266 180 380 |
| init + sfc_update (links) | 2 | 875 129 724 + 34 731 176 | 909 860 900 |
| diretório da perna, arquivos reais (`du -s`, sem seguir links) | | | 283 221 565 440 (2021) / 283 221 229 568 (2022) |

- **Formato:** history, restart, init, sfc_update, lbc e static em CDF5 (`ncdump -k`); `grid.nc` em "64-bit offset". São formatos netCDF-3, sem compressão por variável. O `ncdump -hs` reporta "Attempting netcdf-4 operation on netcdf-3 file", e só `_Storage = "contiguous"` aparece.
- **Dimensões do history:** `nCells` = 102968, `nVertLevels` = 55, `nVertLevelsP1` = 56, `Time` = 1 por arquivo.
- **Bytes por arquivo:** a soma dos bytes das 34 variáveis é 192 344 288, e o arquivo tem 192 475 360. A diferença, 131 072 B, é o cabeçalho.
- **Lista `stream_list.atmosphere.wind_energy`:** 34 entradas, idêntica nas duas pernas. Resolve para `runs/meqbr_05km/stream_list.atmosphere.wind_energy`. O stream `output` usa `output_interval="1:00:00"`.
- **Links das forçantes:** na perna 2021, os links de `init.nc` e `lbc` resolvem para `preproc/attempt_01_contaminated_oisst/…`, via um link intermediário em `preproc/20211101_20211201/`. Isso já está documentado em `MEQ-02D-experimental-configurations.md` e `MEQ-05.2-benchmark-record.md`. Na perna 2022, eles resolvem para `preproc_2022/`.

Sem projeções, conforme a missão.

## Desvios

- **Código:** MEQ-05.5 no lugar de MEQ-05.4, com branch e diretórios mantidos com o nome antigo (ver o início deste documento).
- **Validade do bloco 1:** o critério do bloco 1 comparou `REF_A56_first_redo` com `REF_A56_last`, porque o `REF_A56_first` original foi interferido.
- **Script de inventário:** `disk_inventory_meq054.sh` foi copiado para `MEQ054_scripts/` no Swell para ser executado. O banner de login do ssh foi removido do arquivo de saída.
- **Ordem dos ensaios repetidos:** no CSV, os ensaios repetidos aparecem depois do `REF_A56_last` do bloco 1, na ordem em que rodaram.
