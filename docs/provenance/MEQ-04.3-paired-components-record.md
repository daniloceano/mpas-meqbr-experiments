# MEQ-04.3 — Decomposição do erro e testes pareados por componente (registro)

- **Data:** 18/11/2026. Análise nova aprovada pelo pesquisador em 18/11/2026.
- **Base:** `origin/main@30bb18328f630bda326ec6f41746b72de8f96ad7`.
- **Branch:** `analysis/meq-04-3-paired-components`.
- **Escopo:** sem simulações, sem código do MPAS; nenhuma tabela, figura ou HTML existente alterado (o HTML é a MEQ-04.4).
- **Script:** `scripts/04_era5/paired_components.py`; teste `tests/test_meq04_3_decomposition.py`.

## Execução

As observações LiDAR (`data/obs/P0_LIDAR_matrix.mat`, `data/obs/LPI_processed.csv.gz`) e as séries do modelo/ERA5 só existem no clone do Swell (`/p1-swell/danilocs/mpas-meqbr-experiments`). Por autorização do pesquisador, esse clone foi antes sincronizado por fast-forward de `784e9bc` para `30bb183` (árvore rastreada limpa; só arquivos não rastreados preexistentes). O script foi copiado para lá, executado com o Python base do Swell (3.11.8; numpy 1.26.4; pandas 3.0.1) e as duas CSVs trazidas para este repositório. Depois, o script e as CSVs foram removidos do clone do Swell, que voltou a `30bb183` sem alterações rastreadas.

```bash
python scripts/04_era5/paired_components.py
```

## Entradas

| Arquivo | SHA-256 |
|---|---|
| `results/tables/era5_added_value_current.csv` | `b0bc7e776245120ad9be3845e77ef40efa0f321f2971ce1b880d6a4a15153921` |
| `results/tables/pairwise_tests_current.csv` | `c36037471b6a462a4d6a817b68cc8c65578417a56c77ee5f7f160652cc51425a` |

Pareamento: `pairing.load_paired(..., common=True)` + `pairing.add_era5(height_for_era5=100)`, mesma junção de `scripts/04_era5/added_value.py` (as 7 fontes MPAS e o ERA5 em interseção horária). `obs.to_hourly` usado sem correção (limitação da `DEC-MEQ-004`).

## Saídas

| Arquivo | SHA-256 |
|---|---|
| `results/tables/meq04_3_error_decomposition.csv` | `95dc8b6690d7b6ae55c7c0c5eaf8080149dfcaa48377c685ebe60156ae2906f2` |
| `results/tables/meq04_3_paired_components.csv` | `873a58de9daae28a301b8643c0c55404f790f32663f43e23b3ea8a09f0a3dd75` |

## Métodos e parâmetros

1. **Decomposição exata** por fonte: MSE = bias² + (σm − σo)² + 2·σm·σo·(1 − r), desvios-padrão populacionais (ddof = 0). Resíduo máximo da identidade: **8,0 × 10⁻¹⁵ (m/s)²**.
2. **Testes pareados** por bootstrap em blocos móveis: block_hours = 24, n_boot = 2000, seed = 20260902, IC95% por percentis. Em cada sorteio, os mesmos índices valem para as duas fontes. Diferenças B − A em |bias|, r, |1 − σm/σo| ("amplitude"), RMSE (m/s) e skill vs ERA5 (= (MSE_A − MSE_B)/MSE_ERA5, com MSE_ERA5 da amostra completa como em `added_value.py`). A coluna `better_*` indica a fonte melhor no componente, ou "no difference" quando o IC inclui zero. Melhor significa menor |bias|, amplitude e RMSE, e maior r e skill.
3. **Reamostrador:** igual ao da tabela conferida, para comparação um a um:
   - experimento vs ERA5: `metrics._block_indices` (o de `metrics.paired_skill_test`, usado em `added_value.py`);
   - experimento vs experimento: `metrics._gap_aware_resample_indices` (o de `metrics.gap_aware_paired_skill_test`, usado em `rank_experiments.py`).
4. **Pares:** (a) cada experimento vs ERA5 (7 × 2 sítios); (b) os 21 pares entre experimentos de `pairwise_tests_current.csv` a 100 m (× 2 sítios). Total: 56 linhas.

## Reprodução das tabelas atuais

- n = **507** (P0/nov-2021) e **740** (LPI/out-2022) para todas as fontes, como nas tabelas atuais.
- O RMSE de cada uma das 16 combinações fonte × sítio reproduz `era5_added_value_current.csv` com tolerância de 10⁻⁹ m/s (coluna `rmse_table` da decomposição).
- Os ICs de Δskill reproduzem os publicados (os de `era5_added_value_current.csv` e os de `pairwise_tests_current.csv` divididos por MSE_ERA5) com diferença máxima de 2,8 × 10⁻¹⁶.
- O veredito de ΔRMSE e Δskill concorda em sinal e significância com o das tabelas atuais em **56/56** comparações. **Discrepâncias: nenhuma.**

## Divergência registrada (sem alteração)

As docstrings e os padrões de `metrics.block_bootstrap_ci`, `paired_skill_test`, `gap_aware_block_bootstrap_ci` e `gap_aware_paired_skill_test` usam `n_boot=1000`. Já os scripts `added_value.py` e `rank_experiments.py` têm `--n-boot` padrão 2000 e o repassam explicitamente, e por isso as tabelas trazem 2000. Não há inconsistência nos resultados: o padrão da função não é usado nessas tabelas. Nada foi alterado.

Outra observação: as duas tabelas atuais usam reamostradores diferentes (blocos móveis simples × blocos que respeitam lacunas). Este registro segue cada uma; não há proposta de mudança.

## Resultados

### Decomposição (100 m)

| Sítio | Fonte | bias (m/s) | r | σm/σo | RMSE (m/s) | bias² | amplitude | correlação |
|---|---|---|---|---|---|---|---|---|
| P0 | ERA5 | −1,896 | 0,531 | 0,574 | 2,492 | 57,9% | 10,6% | 31,5% |
| P0 | CTL | −1,236 | 0,422 | 0,673 | 2,178 | 32,2% | 8,2% | 59,5% |
| P0 | EXP01 | −0,945 | 0,431 | 0,690 | 2,024 | 21,8% | 8,5% | 69,7% |
| P0 | EXP02 | −0,890 | 0,474 | 0,633 | 1,924 | 21,4% | 13,2% | 65,4% |
| P0 | EXP03 | −0,900 | 0,457 | 0,623 | 1,946 | 21,4% | 13,6% | 65,0% |
| P0 | EXP04 | −0,707 | 0,483 | 0,958 | 2,026 | 12,2% | 0,1% | 87,7% |
| P0 | EXP05 | −1,130 | 0,427 | 1,185 | 2,518 | 20,1% | 2,0% | 77,9% |
| P0 | EXP06 | −1,093 | 0,329 | 1,226 | 2,712 | 16,2% | 2,5% | 81,2% |
| LPI | ERA5 | −1,903 | 0,845 | 0,684 | 2,466 | 59,6% | 12,9% | 27,5% |
| LPI | CTL | −0,963 | 0,711 | 0,965 | 2,310 | 17,4% | 0,2% | 82,4% |
| LPI | EXP01 | −0,554 | 0,737 | 0,951 | 2,066 | 7,2% | 0,4% | 92,4% |
| LPI | EXP02 | −0,491 | 0,734 | 0,890 | 2,018 | 5,9% | 2,4% | 91,7% |
| LPI | EXP03 | −0,366 | 0,771 | 0,901 | 1,861 | 3,9% | 2,2% | 93,9% |
| LPI | EXP04 | −0,282 | 0,728 | 0,937 | 2,030 | 1,9% | 0,8% | 97,3% |
| LPI | EXP05 | −0,354 | 0,713 | 0,894 | 2,063 | 2,9% | 2,1% | 95,0% |
| LPI | EXP06 | −0,406 | 0,716 | 0,896 | 2,066 | 3,9% | 2,0% | 94,1% |

Frações = termo / MSE de cada fonte.

### Experimento − ERA5 (B − A, IC95%)

| Sítio | Fonte | Δ\|bias\| (m/s) | Δr | Δamplitude | ΔRMSE (m/s) | Δskill |
|---|---|---|---|---|---|---|
| P0 | CTL | −0,660 [−0,833, −0,501] | −0,109 [−0,190, −0,018] | −0,099 [−0,212, +0,003] | −0,314 [−0,494, −0,152] | +0,236 [+0,112, +0,386] |
| P0 | EXP01 | −0,951 [−1,122, −0,817] | −0,101 [−0,178, −0,019] | −0,116 [−0,234, −0,031] | −0,467 [−0,649, −0,302] | +0,340 [+0,216, +0,497] |
| P0 | EXP02 | −1,006 [−1,235, −0,859] | −0,057 [−0,160, +0,068] | −0,059 [−0,174, +0,036] | −0,568 [−0,818, −0,366] | +0,404 [+0,258, +0,611] |
| P0 | **EXP03** | −0,996 [−1,213, −0,835] | −0,075 [−0,178, +0,043] | −0,049 [−0,169, +0,050] | −0,546 [−0,774, −0,358] | +0,390 [+0,248, +0,587] |
| P0 | EXP04 | −1,189 [−1,503, −0,901] | −0,048 [−0,152, +0,038] | −0,384 [−0,455, −0,253] | −0,466 [−0,750, −0,219] | +0,339 [+0,155, +0,574] |
| P0 | EXP05 | −0,766 [−1,283, −0,298] | −0,105 [−0,221, −0,006] | −0,241 [−0,450, +0,046] | +0,026 [−0,343, +0,341] | −0,021 [−0,275, +0,282] |
| P0 | EXP06 | −0,803 [−1,318, −0,376] | −0,202 [−0,341, −0,069] | −0,200 [−0,442, +0,129] | +0,220 [−0,212, +0,636] | −0,185 [−0,561, +0,175] |
| LPI | CTL | −0,940 [−1,137, −0,751] | −0,134 [−0,173, −0,094] | −0,281 [−0,314, −0,221] | −0,156 [−0,360, +0,023] | +0,122 [−0,018, +0,274] |
| LPI | EXP01 | −1,349 [−1,520, −1,191] | −0,108 [−0,148, −0,069] | −0,267 [−0,305, −0,210] | −0,399 [−0,598, −0,215] | +0,298 [+0,158, +0,441] |
| LPI | EXP02 | −1,412 [−1,640, −1,219] | −0,111 [−0,149, −0,067] | −0,206 [−0,255, −0,146] | −0,448 [−0,635, −0,290] | +0,330 [+0,214, +0,466] |
| LPI | **EXP03** | −1,537 [−1,757, −1,349] | −0,074 [−0,106, −0,041] | −0,217 [−0,261, −0,157] | −0,604 [−0,764, −0,456] | +0,430 [+0,316, +0,553] |
| LPI | EXP04 | −1,621 [−1,774, −1,452] | −0,117 [−0,161, −0,076] | −0,252 [−0,288, −0,208] | −0,435 [−0,618, −0,242] | +0,322 [+0,177, +0,455] |
| LPI | EXP05 | −1,550 [−1,726, −1,363] | −0,132 [−0,178, −0,094] | −0,209 [−0,252, −0,162] | −0,403 [−0,569, −0,208] | +0,300 [+0,153, +0,423] |
| LPI | EXP06 | −1,497 [−1,676, −1,313] | −0,129 [−0,176, −0,090] | −0,212 [−0,255, −0,166] | −0,400 [−0,563, −0,207] | +0,298 [+0,156, +0,420] |

Δ\|bias\|, Δamplitude e ΔRMSE negativos favorecem o experimento; Δr e Δskill positivos favorecem o experimento.

Descritivo: |bias| menor no experimento em 14/14 comparações. r significativamente maior no ERA5 em 11/14 comparações (P0: CTL, EXP01, EXP05, EXP06; LPI: todas); nas outras 3 (P0: EXP02, EXP03, EXP04), sem diferença. Amplitude menor no experimento em 9/14 comparações (P0: EXP01, EXP04; LPI: todas); sem diferença nas outras 5. RMSE/skill: 11/14 a favor do experimento e 3 sem diferença (P0: EXP05, EXP06; LPI: CTL), idênticos às tabelas atuais.

### Entre experimentos (21 pares por sítio)

Número de pares com IC excluindo zero, por componente:

| Sítio | \|bias\| | r | amplitude | RMSE / skill |
|---|---|---|---|---|
| P0 | 7 | 3 | 5 | 12 |
| LPI | 13 | 6 | 9 | 11 |

Detalhe por par em `meq04_3_paired_components.csv`.

## Nota de 18/11/2026 — contagem de horas no fim da janela

Os resultados acima não mudam. O pareamento de P0 inclui a hora 2021-12-01 00:00: o fim da janela de análise é inclusivo, o que dá 507 h. Já a aba "Disponibilidade das observações" do relatório HTML (MEQ-04.4, `observation_availability.csv`) conta as horas em [início, fim), excluindo essa hora, e por isso mostra 506 h para o LiDAR P0 a 100 m. A diferença é só de convenção de borda.

## Limites

- Contrastes exploratórios, **sem ajuste de multiplicidade** (5 componentes × 56 comparações).
- Um mês e um LiDAR por sítio (P0/nov-2021, LPI/out-2022); nada se generaliza para outros períodos.
- `obs.to_hourly` sem correção (limitação da `DEC-MEQ-004`).
- SODAR excluído (`DEC-MEQ-003`).
- Somente 100 m. ERA5 interpolado bilinearmente ao ponto, como em `added_value.py`.
- Os ICs de r e amplitude são de percentis com blocos de 24 h; não há correção de viés do estimador.
- Este registro é descritivo; a interpretação fica para a ratificação da síntese da MEQ-04.
