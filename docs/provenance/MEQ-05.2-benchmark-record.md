# MEQ-05.2 — Registro do benchmark de paralelismo da EXP03

- **Autorização:** pesquisador, 13/11/2026 (diretório de benchmark e partições METIS no Swell; integrações curtas até 24 h de nó; branch, commit e PR sem merge).
- **Branch:** `meq-05.2-parallel-benchmark`, criada a partir de `86a3a152c2ce992dff315d4f47fbae165bae8126` em 2026-11-13T15:56:29Z.
- **Execução:** driver iniciado em 2026-11-13T15:59:54Z e encerrado em 2026-11-13T20:53:24Z (`records/DONE`: "all planned trials finished"). Nenhuma condição de parada foi atingida.
- **Tabela:** `results/tables/meq05_parallel_benchmark.csv` (20 linhas, uma por ensaio), gerada por `scripts/05_benchmark/parse_benchmark_logs.py`.
- **Logs e registros:** `results/benchmark/MEQ-05.2/` (sem NetCDF).

Este documento registra o que foi feito e medido. Não contém interpretação científica nem recomendação de configuração para a MEQ-06.

## Hardware

Nó `swell` (Linux 6.8.0-147-generic). Snapshot completo em `results/benchmark/MEQ-05.2/records/hardware_snapshot.txt`, capturado após o benchmark. A topologia também foi inspecionada na Etapa 0, antes das rodadas.

| Item | Valor |
|---|---|
| CPU | 2× Intel Xeon Gold 5420+ |
| Núcleos físicos | 28 por soquete, 56 no total |
| SMT | 2 threads por núcleo, 112 CPUs lógicas |
| Soquete 0 / NUMA node0 | físicos 0–27, irmãos SMT 56–83 |
| Soquete 1 / NUMA node1 | físicos 28–55, irmãos SMT 84–111 |
| Irmão SMT da CPU *c* | *c* + 56 |
| Distâncias NUMA | 10 local / 21 remoto |
| Memória | 1007 GiB |
| Sistema de arquivos | `/p1-swell` (ext4) |

`lstopo`/`hwloc-ls` não estão instalados no Swell. A topologia foi registrada com `lscpu` e `numactl --hardware`.

## Ambiente e artefatos

| Item | Valor |
|---|---|
| Modelo | MPAS-Atmosphere 8.4.1, precisão simples, I/O SMIOL |
| Ambiente | `source ~/mpas-build/mpas_build_env.sh`. O driver registrou `PNETCDF=/home/danilocs/mpas-build/libs` (PIO/NETCDF não definidos, logo SMIOL) |
| Threads | `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` |
| MPI | MPICH 4.2.3, Hydra: `/home/danilocs/mpas-build/libs/bin/mpiexec` |
| Executável | `/p1-swell/danilocs/MPAS-Research/atmosphere_model`, sha256 `095ee3b1debac20cf58de77717cc9a7934f61621bef7c393dac765541cd1e494` |
| Grafo da malha | `grids/meqbr_05km_oval_meq02a/meqbr_05km_oval_meq02a.graph.info`, sha256 `4362d47d78da1bdb67411bc260040c8c090d59ce21f00ef1bff55c4f16aaca75` |
| METIS | 5.2.1 (`/home/danilocs/.conda/envs/cgfd-usp-mpas/bin/gpmetis`) |

- O hash do executável foi conferido na Etapa 0 e de novo após o benchmark (2026-11-14), contra `runs/meqbr_05km_oval_meq02a/provenance/source_hashes.txt` no Swell. O valor é idêntico.
- Os diretórios de ensaio usam links simbólicos para o executável (`readlink -f`). Não houve recompilação.
- Diretório do benchmark no Swell: `/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2/`.
- Scripts no repositório: `results/benchmark/MEQ-05.2/scripts/`.

| Script | sha256 | Registro |
|---|---|---|
| `setup_bench.sh` | `7d678b48…` | `records/scripts_sha256.txt` |
| `run_benchmark.sh` | `40cae869…` | `records/scripts_sha256.txt` |

## Configuração comum dos ensaios

- **Partida:** restart da EXP03 de produção (`runs/meqbr_05km_oval_meq02a/20211101_20211201/`), `restart.2021-11-15_00.00.00.nc`.
  - Foram linkados, em leitura: LBCs `lbc.2021-11-15_*` e `lbc.2021-11-16_00`, `sfc_update`, tabelas, `stream_list.*`, `zeta_wind.txt`.
  - Nenhum arquivo de produção foi escrito ou alterado.
- **Namelist:** só três linhas diferem da produção (`common/namelist.diff`):

| Parâmetro | Produção | Benchmark |
|---|---|---|
| `config_start_time` | `'2021-10-21_00:00:00'` | `'2021-11-15_00:00:00'` |
| `config_run_duration` | `'41_00:00:00'` | `'0_03:00:00'` |
| `config_do_restart` | `false` | `true` |

  Física, `config_dt` (30 s, 360 passos em 3 h) e malha estão inalterados.
- **Streams:**
  - Séries A, B, C e D usam `streams.atmosphere.nooutput`: `output` e `restart` com `output_interval="none"`.
  - Série E usa `streams.atmosphere.production`: `output` horário, como na produção, e `restart` com `output_interval="03:00:00"` (produção: `1_00:00:00`), para que um restart seja escrito dentro das 3 h.
  - Diffs em `common/streams.*.diff` e em `logs/<ensaio>/streams.diff`.
- **Partições:** `gpmetis -minconn -contig -niter=200 <grafo> N`, as mesmas opções de `runs/meqbr_05km_oval_meq02a/provenance/gpmetis_part60.log`. Todas são contíguas. Logs em `partitions/gpmetis_partN.log`.

| N | Edgecut | Balance | Origem |
|---|---|---|---|
| 8 | 2888 | 1.000 | gerada |
| 14 | 4409 | 1.000 | gerada |
| 28 | 6656 | 1.000 | gerada |
| 42 | 8527 | 1.001 | gerada |
| 56 | 9917 | 1.001 | gerada |
| 60 | 10242 | 1.002 | arquivo de produção (link) |
| 112 | 14042 | 1.003 | gerada |

  - Verificação de reprodutibilidade: um `part.60` regenerado com as mesmas opções é byte-idêntico ao de produção (sha256 `39e19d3a…`, `partitions/check60/compare.txt`). Os ensaios C usaram o arquivo de produção.

## Comandos executados

Preparação: `bash setup_bench.sh` (2026-11-13T15:57:35Z–15:57:36Z).

Execução: `setsid nohup bash run_benchmark.sh`, com `PLAN="C A56 A42 A28 A14 A8 B D E"` e 2 repetições por configuração. Uma 3ª repetição seria feita se |a−b|/média > 3%, o que não ocorreu.

Antes de cada ensaio, `wait_idle` exige duas condições, com espera máxima de 15 min (senão, STOP):
- carga de 1 min < 2;
- nenhum processo `atmosphere_mod`/`init_atmospher` em execução.

Cada `mpiexec` roda sob `timeout --signal=TERM --kill-after=60 <2 × previsto>`.

| Série | Comando (`mpiexec_cmd.txt` em cada ensaio) | Previsto | Timeout |
|---|---|---|---|
| C (produção) | `mpiexec -n 60 ./atmosphere_model`, sem fixação (`part.60` de produção) | 11 min | 1320 s |
| A, N = 56/42/28/14/8 | `mpiexec -n N -bind-to user:<lista> ./atmosphere_model`; lista = primeiras N/2 CPUs físicas do soquete 0 (a partir de 0), depois N/2 do soquete 1 (a partir de 28) | 11/15/23/45/80 min | 1320/1800/2760/5400/9600 s |
| B, 112 | `-bind-to user:0-27,56-83,28-55,84-111` (uma rank por CPU lógica, em blocos por soquete) | 11 min | 1320 s |
| D, 2 × 28 simultâneos | caso s0: `-bind-to user:0-27`; caso s1: `-bind-to user:28-55`; mesmo instante de partida | 23 min | 2760 s |
| E, 56 | igual a A56, com escrita de saída (streams de produção) | 11 min | 1320 s |

- **Ordem rank → CPU:** sequencial na lista. Nas séries A/E, as ranks 0…N/2−1 ficam no soquete 0 e as ranks N/2…N−1 no soquete 1.
- **Linha D no `driver.log`:** os dois comandos aparecem separados por `||`. Isso é só o formato da mensagem. Os dois casos foram lançados ao mesmo tempo, o que está confirmado por:
  - os `wrapper_start_utc.txt` idênticos;
  - os `rc` registrados separadamente (0/0);
  - as amostras de fixação, simultâneas, em CPUs 0–27 e 28–55.

## Ensaios realizados

Todos os 20 ensaios planejados terminaram com `rc=0` e `status=ok`.

| Verificação em cada `log.atmosphere.0000.out` | Resultado |
|---|---|
| "Critical error messages" | `= 0` |
| Ocorrências de `CRITICAL ERROR` | nenhuma |
| `NaN` como palavra | nenhuma |
| Arquivos `*.err` | nenhum |
| Tabela de timers | presente |

Nenhum ensaio passou de 2× o tempo previsto. Também não houve ensaios falhos nem ensaios não executados.

Valores medidos (médias de 2 repetições). Fonte: `meq05_parallel_benchmark.csv`.
- s/passo = `time integration` / 360.
- Speed-up e eficiência são relativos a A N = 8.

| Config. | Ranks | Núcleos físicos | s/passo | Spread rep. (%) | Speed-up | Efic. (ranks) | Efic. (núcl. físicos) |
|---|---|---|---|---|---|---|---|
| A_N008 | 8 | 8 | 5.4860 | 0.005 | 1.000 | 1.000 | 1.000 |
| A_N014 | 14 | 14 | 3.2198 | 0.41 | 1.704 | 0.974 | 0.974 |
| A_N028 | 28 | 28 | 1.9160 | 0.03 | 2.863 | 0.818 | 0.818 |
| A_N042 | 42 | 42 | 1.4500 | 0.34 | 3.783 | 0.721 | 0.721 |
| A_N056 | 56 | 56 | 1.2233 | 0.53 | 4.485 | 0.641 | 0.641 |
| B_N112 | 112 | 56 (SMT) | 1.1072 | 1.97 | 4.955 | 0.354 | 0.708 |
| C_N060 | 60 | 56 (sem fixação) | 1.5507 | 0.99 | 3.538 | 0.472 | 0.505 |
| D_N028x2_s0 | 28 | 28 | 2.4009 | 0.004 | 2.285 | 0.653 | 0.653 |
| D_N028x2_s1 | 28 | 28 | 2.7985 | 0.04 | 1.960 | 0.560 | 0.560 |
| E_N056 | 56 | 56 | 1.2358 | 0.54 | 4.439 | 0.634 | 0.634 |

**Série D:** throughput do par, somando os dois casos simultâneos, em dias simulados por dia de nó:

| Repetição | Base `time integration` | Base wall do par | Wall do par |
|---|---|---|---|
| r1 | 23.22 | 21.37 | 1011 s |
| r2 | 23.21 | 21.34 | 1012 s |

**Série E:** diferenças em relação à média de A56 (mesmas ranks e fixação, sem saída):

| Repetição | Δ total time | Δ time integration | Δ stream_output | Δ wall |
|---|---|---|---|---|
| r1 | +8.36 s | +3.29 s | +5.06 s | +8 s |
| r2 | +10.71 s | +5.70 s | +4.98 s | +11 s |

- Em cada repetição foram escritos 3 `history` horários e 1 `restart`.
- Duração de escrita por arquivo (nascimento → última modificação, `outputs_stat.tsv`, timestamps ext4 em ns):

| Repetição | history (média) | restart |
|---|---|---|
| r1 | 0.215 s | 2.79 s |
| r2 | 0.220 s | 2.80 s |

- **EXTRAPOLAÇÃO** (não medida) do custo de I/O por dia simulado = 24 × history + 1 × restart: **7.96 s (r1)** e **8.08 s (r2)**.

## Verificação de fixação (pinning)

Cada ensaio foi amostrado 3 vezes, a 90, 210 e 330 s do início (`pinning_samples.txt`). Para cada processo `atmosphere_mod` com cwd no diretório do ensaio, foram registrados `ps -o psr` e `taskset -cp`.

**Verificado para todos os ensaios fixados (A, B, D, E):**
- em cada amostra, o número de ranks visto é igual a N;
- cada rank tem afinidade de exatamente 1 CPU;
- o conjunto de CPUs é igual à lista pretendida.

Para D, os conjuntos foram 0–27 (s0) e 28–55 (s1).

**Série C (sem fixação):**
- afinidade 0–111 para todas as ranks;
- nas 3 amostras, as 60 ranks ocupavam 56 núcleos físicos distintos, com 4 ranks em núcleos físicos compartilhados (CPU irmã SMT);
- CPUs distintas observadas no conjunto das amostras: 84 (r1) e 87 (r2).

## Cargas e ocupação do nó

`records/loads.tsv` registra o loadavg imediatamente antes de cada ensaio:
- a carga de 1 min ficou entre 0.00 e 1.93, sempre abaixo do limiar de 2;
- os valores de 5 e 15 min incluem o ensaio anterior do próprio benchmark.

Processos de outros usuários consumindo CPU: nenhum.
- Antes de cada ensaio: `other_user_busy_procs=none`.
- Nas 60 amostras de fixação (20 ensaios × 3): `other_user_busy=` vazio.

Carga após o benchmark (2026-11-14T12:55:59Z): 0.01.

## Tempo de nó consumido

| Medida | Valor |
|---|---|
| Soma dos tempos de parede dos ensaios (`records/cum_wall_s`, D contado uma vez pelo wall do par) | 14478 s = **4.02 h** |
| Duração total do driver, incluindo esperas de ociosidade entre ensaios | 15:59:54Z → 20:53:24Z = 17610 s = 4.89 h |
| Orçamento autorizado | 24 h |

## Falhas

Nenhuma falha de modelo ou do driver ocorreu durante os ensaios.

Problemas de preparação, resolvidos antes da execução:
- **Link do `init.nc`:** um dry-run mostrou que `readlink -f` resolvia o `init.nc` até o arquivo final em `attempt_01_contaminated_oisst/`. O driver foi alterado para reproduzir o link de primeiro nível da produção (ver Observações).
- **Seleção de processos:** a amostragem de fixação usava `pgrep -f`, que também casaria com as linhas de comando de `mpiexec`/`timeout`. Passou a usar `pgrep '^atmosphere_mod'` (nome do comando).
- **Sessão ssh de lançamento:** ficou presa porque o subshell em segundo plano manteve o canal aberto. A sessão local foi encerrada. O driver (`setsid`/`nohup`) continuou normalmente.

## Desvios em relação ao plano

1. **Arquivos copiados para o repositório.** Além de `log.atmosphere.0000.out`, namelists/streams e logs do gpmetis, foram copiados pequenos arquivos de texto. O extrator precisa deles, e sem eles a tabela não pode ser reproduzida:
   - do driver: `wrapper_*_utc.txt`, `wrapper_wall_s.txt`, `mpiexec_cmd.txt`, `pinning_samples.txt`, `pair_wall_s.txt`, `outputs_stat.tsv`, `restart_timestamp`, `namelist.diff`, `streams.diff`;
   - os registros `records/*`, os scripts e `hardware_snapshot.txt`.

   `mpas.out` (stdout do `mpiexec`) não foi copiado. Nenhum NetCDF foi copiado.
2. **Restart na série E.** O intervalo de `restart` foi reduzido para 3 h (produção: 1 dia), para medir a escrita de um restart dentro do ensaio de 3 h. O stream `output` manteve o intervalo horário de produção.
3. **`outputs_stat.tsv` da série E.** Foi gerado após o fim do driver, por leitura (`stat -c '%n %.9W %.9Y'`) dos arquivos escritos nos diretórios E. Não faz parte do driver.
4. **Agrupamento da série D.** As repetições foram agrupadas por caso (s0 e s1 separados) para médias, speed-up e eficiência. Os dois casos simultâneos têm tempos distintos, e agrupá-los misturaria soquetes.
5. **Arquivos de proveniência ausentes do repositório.** `provenance/source_hashes.txt` e `gpmetis_part60.log`, referidos no plano, não estão no repositório. Foram encontrados no Swell, em `runs/meqbr_05km_oval_meq02a/provenance/`, e usados de lá, só para leitura.
6. **Topologia.** `lstopo` não está disponível. A topologia foi registrada com `lscpu`/`numactl`.

## O que não foi verificado

- **Igualdade numérica** dos resultados entre contagens de ranks. Os campos de saída não foram comparados, e os ensaios sem saída não geram arquivos.
- **Frequência de CPU:** governor, turbo e temperatura não foram registrados nem controlados.
- **Uso e banda de memória:** não foram medidos.
- **Fixação contínua:** a fixação foi amostrada só 3 vezes por ensaio, até 330 s. Em ensaios mais longos (A28, A14, A8, D) o restante da execução não foi amostrado.
- **Cache de páginas:** não foi controlado. O restart de entrada é relido a cada ensaio (`stream_input` ≤ 0.07 s).
- **Representatividade da janela:** 3 h a partir de 2021-11-15 00 UTC. Não foi verificado se ela reproduz, na mesma proporção de um dia completo, a frequência de chamadas periódicas (por exemplo, radiação).
- **Extrapolação de I/O:** supõe custo constante por arquivo e não inclui operações antes da criação do arquivo. Os valores de `stream_output` (timer MPAS) e as durações por arquivo não foram reconciliados.
- **Conteúdo dos `history`/`restart`** escritos na série E: não foi inspecionado.
- **Saídas no Swell:** os NetCDF da série E (3 `history` + 1 `restart`, cerca de 2.9 GB por repetição) permanecem no diretório do benchmark. Não foram apagados.

## Observações

- O link `meqbr_05km_oval_meq02a.init.nc` da rodada de produção (`runs/meqbr_05km_oval_meq02a/20211101_20211201/`) aponta para `preproc/20211101_20211201/meqbr_05km_oval_meq02a.init.nc`, que por sua vez é um link para `preproc/attempt_01_contaminated_oisst/20211101_20211201/meqbr_05km_oval_meq02a.init.nc`.
  - Os diretórios do benchmark reproduzem o mesmo link de primeiro nível da produção.
  - No benchmark, esse arquivo não é lido: com `config_do_restart = true`, o modelo inicializa a partir do stream `restart` (`restart.2021-11-15_00.00.00.nc`). O `log.atmosphere.0000.out` mostra isso: "Bootstrapping framework with mesh fields from input file 'restart.2021-11-15_00.00.00.nc'"; "Reading initial state from 'restart' stream".
  - Registro sem conclusão.
