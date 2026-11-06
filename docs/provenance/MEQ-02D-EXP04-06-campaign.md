# MEQ-02D — conclusão da campanha EXP04, EXP05 e EXP06

**Auditoria final:** 06/11/2026

**Servidor:** `swell`

**Estado:** seis integrações completas e verificadas; nenhuma seleção
científica entre EXP01/EXP04/EXP05/EXP06 foi realizada.

## Resultado operacional

O controlador registrou
`COMPLETE 2026-11-02T13:17:56Z all_six_cases_verified`. Todos os casos
terminaram com código de saída zero, 985 históricos horários e 41 restarts
diários. Após o encerramento não restavam processos `mpiexec` ou
`atmosphere_model` da campanha.

| Caso | Término UTC | Ranks | Tempo de parede | History/restart | Volume |
|---|---:|---:|---:|---:|---:|
| EXP04/2021 | 23/10 11:57 | 90 | 39:32:43 | 985/41 | 230,893 GB |
| EXP04/2022 | 02/11 07:22 | 22 | 235:09:13 | 985/41 | 230,893 GB |
| EXP05/2021 | 02/11 06:52 | 22 | 234:39:07 | 985/41 | 232,379 GB |
| EXP05/2022 | 02/11 03:41 | 22 | 231:28:18 | 985/41 | 232,379 GB |
| EXP06/2021 | 02/11 03:17 | 22 | 231:04:03 | 985/41 | 232,379 GB |
| EXP06/2022 | 02/11 13:17 | 22 | 241:04:28 | 985/41 | 232,379 GB |

O conjunto ocupa 1,391 TB (1,265 TiB). A contabilidade de `/usr/bin/time`
soma aproximadamente 29.124 CPU-h; os cinco casos concorrentes consumiram
entre 5.039 e 5.256 CPU-h cada. O lançamento concorrente usou cinco grupos de
22 ranks com afinidades exclusivas. EXP04/2021, concluído antes desse lote, foi
o caso de calibração com 90 ranks.

## Identidade e integridade

- Executável realmente utilizado: MPAS-Atmosphere 8.4.1,
  `v8.4.1-92-gb5fb94d2`, SHA-256
  `095ee3b1debac20cf58de77717cc9a7934f61621bef7c393dac765541cd1e494`.
- Partição dos cinco casos de 22 ranks: SHA-256
  `e9f33754bd35c59aaa5a27de811e22f3dd2389f19ff2dcc9f5f1ef7b64f9588f`.
- EXP04/2021 usou a partição histórica de 90 ranks, SHA-256
  `8b1bf4ce060c37eee75e6dffa5289897536d66afee1a557703fa60b764243c87`.
- Os manifestos do pacote de preparação, dos scripts operacionais e da correção
  do detector foram validados integralmente por SHA-256 após a campanha.
- Os hashes dos seis `namelist.atmosphere` e `streams.atmosphere` copiados dos
  diretórios concluídos constam em
  [`config/namelists/SHA256SUMS`](../../config/namelists/SHA256SUMS).
- O checkout atual do código no Swell já avançou para `13eced8a` em `develop`.
  Esse estado posterior não é atribuído às execuções: a versão e o hash acima
  vêm do executável e dos logs efetivamente usados.

## Diferenças físicas controladas

As seis configurações preservam malha, níveis, timestep, condições iniciais,
LBCs, OISST diária corrigida e streams de EXP01. Os únicos deltas científicos
nos namelists são:

| Experimento | Delta relativo ao candidato anterior |
|---|---|
| EXP04 | `config_pbl_scheme = bl_mynn` e `config_sfclayer_scheme = sf_mynn` |
| EXP05 | EXP04 + `config_convection_scheme = cu_grell_freitas` |
| EXP06 | EXP05 + `config_sstdiurn_update = true` |

Cada caso começou das entradas de EXP01 do período correspondente; nenhum
consumiu history ou restart de outro candidato.

## Auditoria de SST do EXP06

Os metadados dos dois períodos registram `config_sst_update=YES` e
`config_sstdiurn_update=YES`. Em dias interiores, o campo prescrito `sst`
mudou na atualização diária e permaneceu constante nas amostras posteriores de
06/12/18 UTC, enquanto `skintemp` continuou evoluindo entre essas horas. Assim,
a evolução subdiária confirmada é a temperatura de superfície usada pelo
modelo, não uma falsa interpretação da OISST diária como arquivo sub-horário.
Os valores reproduzíveis estão em
[`SST_AUDIT.txt`](../../results/provenance/MEQ-02D_EXP04-06/SST_AUDIT.txt).

## Prontidão para incorporação no HTML

Os resultados estão completos e tecnicamente aptos à validação observacional.
A incorporação ao HTML é possível, mas **ainda não foi executada**. O pipeline
atual enumera CTL--EXP03 explicitamente em `scripts/run_all.sh`, scripts de
validação/exploração, construtor, template e validador do relatório. A próxima
etapa deve:

1. registrar EXP04--EXP06 em `config/experiments.yaml` sem alterar a identidade
   dos casos concluídos;
2. ampliar as listas explícitas e os controles visuais do relatório;
3. extrair os mesmos locais/alturas e restringir às mesmas horas observadas;
4. recalcular métricas e bootstrap temporal em blocos de 24 h para
   EXP04-EXP01, EXP05-EXP04, EXP06-EXP05 e todos contra EXP01;
5. regenerar e validar o pacote HTML, preservando o relatório atual como
   baseline antes da substituição.

O desenho incremental identifica efeitos condicionais, não efeitos fatoriais
independentes nem todas as interações. A existência de integrações completas
não autoriza selecionar uma física antes dessa validação.

## Evidência preservada

Os registros originais copiados sem edição do diretório da campanha estão em
[`results/provenance/MEQ-02D_EXP04-06/`](../../results/provenance/MEQ-02D_EXP04-06/):
estado final, transições por caso, lançamento, workers, códigos de saída e seis
arquivos de uso de recursos. As saídas NetCDF permanecem no Swell e não foram
copiadas para Git.
