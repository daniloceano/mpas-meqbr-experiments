# MEQ-02D — Inventário das configurações experimentais

**Data da auditoria:** 20/10/2026
**Servidor:** `danilocs@swell`
**Estado:** arquivos arquiváveis identificados e copiados; lacunas documentadas;
nenhum original do Swell foi modificado.

## Escopo e regra de fidelidade

Foram examinados os oito casos científicos válidos: CTL, EXP01, EXP02 e
EXP03, cada um nos períodos P0/2021 e LPI/2022. Os diretórios históricos
`EXP01_BADSST` e `EXP02_BADSST` foram consultados apenas nos registros que
explicam a renomeação; nenhum arquivo deles foi adotado como configuração
válida.

As cópias em [`config/namelists/`](../../config/namelists/) preservam os bytes
dos arquivos resolvidos no Swell. Quando a origem era um link simbólico, o
conteúdo do alvo foi materializado como arquivo regular para tornar cada caso
autocontido. A natureza e o destino do link original permanecem registrados
abaixo. Nenhum arquivo ausente foi reconstruído.

## Fontes autoritativas consultadas

- Registro de execução convencional:
  `/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km`.
- Registro de EXP03, conforme `config/experiments.yaml`:
  `/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a`.
- Registro operacional dos experimentos: `README.md`, `EXPERIMENTS.md` e
  READMEs por experimento no primeiro diretório.
- Pacote MEQ-00B:
  `/p1-swell/danilocs/mpas-meqbr-experiments/local_provenance/MEQ-00B_20261008`.
  O marcador `VERIFIED` é de `2026-10-08T20:04:47Z`; o manifesto publicado em
  MEQ-00B tem SHA-256
  `ce4a8fe311f6544bd1007f6239821131ed631acf6799d26a46d106cc374b597a`.
- EXP03/2021: `provenance/run_core_sha256.txt` e
  `provenance/MEQ-02B_completion_record.txt`, verificado em
  `2026-10-13T23:24:10Z`.
- EXP03/2022: `provenance/EXP03_2022/critical_sha256.txt` e
  `provenance/EXP03_2022/MEQ-02C_EXP03_2022_completion_record.txt`, verificado
  em 18/10/2026.

## Inventário dos oito casos

Todos os horários desta seção são UTC. A contagem científica corresponde às
janelas P0/2021 e LPI/2022, não necessariamente a todos os arquivos de spin-up.

| Caso | Origem relativa ao diretório do experimento | Evidência temporal e operacional | Situação do arquivo |
|---|---|---|---|
| CTL/2021 | `CTL/20211101_20211201` | configuração datada de 16/07/2026; 721 saídas científicas completas | arquivado; não foi localizado log terminal autoritativo |
| CTL/2022 | `CTL/20221001_20221101` | configuração datada de 17/07/2026; 745 saídas científicas completas | arquivado o namelist do segundo trecho, por restart; original do spin-up não localizado |
| EXP01/2021 | `EXP01/20211101_20211201` | configuração datada de 26/08/2026; log concluído em 08/09/2026; 985 históricos, 721 científicos | arquivado e conferido por MEQ-00B |
| EXP01/2022 | `EXP01/20221001_20221101` | configuração datada de 26/08/2026; log concluído em 09/09/2026; 985 históricos, 745 científicos | arquivado e conferido por MEQ-00B |
| EXP02/2021 | `EXP02/20211101_20211201` | namelist inicial de 31/08/2026 e retomada de 24/09/2026; conclusão em 26/09/2026 | ambos os namelists originais arquivados; 721 saídas científicas completas |
| EXP02/2022 | `EXP02/20221001_20221101` | configuração datada de 31/08/2026; conclusão em 07/10/2026 | arquivado e conferido por MEQ-00B; 745 saídas científicas completas |
| EXP03/2021 | `20211101_20211201` no diretório Oval | configuração datada de 09/10/2026; integração encerrada em 12/10/2026 e verificada em 13/10/2026 | arquivado; 985 históricos e 721 científicos completos |
| EXP03/2022 | `20221001_20221101` no diretório Oval | configuração datada de 14/10/2026; integração encerrada em 17/10/2026 e verificada em 18/10/2026 | arquivado; 985 históricos, 745 científicos e auditoria integral aprovada |

## Checksums

| Caso | `namelist.atmosphere` | `streams.atmosphere` resolvido |
|---|---|---|
| CTL/2021 | `e43f10c6703ffd0d3af0d0c3456c0965b02913735c46765a0b4575b481ac6fce` | `c038166b3e400f530b9c98b3ad20bd4ec1abb102746c7a032eb4d4738a8d3db9` |
| CTL/2022 | `a43f4a96fbda93df81978df0f959e3e2104f053cb32e8bb6ac4cffeaff3abc6d` | `c038166b3e400f530b9c98b3ad20bd4ec1abb102746c7a032eb4d4738a8d3db9` |
| EXP01/2021 | `8ddbc2970fba48beb4c4edc4077f5692d5fc7ffd90cddeb5261a19ae6a1a1353` | `a79777bea1d4ed795c956f1f7d0a8ec0ff9f532cc4a70fd7944e85d9a0118c45` |
| EXP01/2022 | `0269f830454e03b0c0884c7f309c6089814e9ff547057e0969dd11062b51559c` | `a79777bea1d4ed795c956f1f7d0a8ec0ff9f532cc4a70fd7944e85d9a0118c45` |
| EXP02/2021, retomada | `1b9d535227fe18064c5090ab0a0f864c0f52edf2e34ada9843d75e260e980690` | `8454608a19ff144e15bae00a375b39609a595c16730881e9ab21fadbe50c98ce` |
| EXP02/2022 | `15abe9c1dfca70fa8727e0ae3a7562c81aa9491b0b516af62c3dba1a5119687f` | `8454608a19ff144e15bae00a375b39609a595c16730881e9ab21fadbe50c98ce` |
| EXP03/2021 | `de58110074472fe4d50d15bae8422f7811b712d97f9aa41e951e2e12473069f7` | `0eceac9704a49033271d407d1c233f25bea0af2d1d04607321384408a05bf535` |
| EXP03/2022 | `e315fa406f03277ae25188e73e904008a95f8c5178241a4082af28bdc99d6ac4` | `0eceac9704a49033271d407d1c233f25bea0af2d1d04607321384408a05bf535` |

O namelist inicial adicional de EXP02/2021,
`namelist.atmosphere.pre_restart_20260924`, tem SHA-256
`21294a168cc49fc50f44d43dfabd4fb6671d9d47a7c35c1525183ebb196b78c7`.

Os hashes diretos no Swell dos seis casos CTL/EXP01/EXP02 coincidiram com
`source-pre.sha256.tsv`, `source-post.sha256.tsv`, `destination.sha256.tsv` e
`package-content.sha256` do MEQ-00B. EXP03/2021 coincidiu com
`run_core_sha256.txt`. EXP03/2022 coincidiu com `critical_sha256.txt` e com os
campos `namelist_sha256` e `streams_sha256` do registro de conclusão. Por fim,
os hashes das cópias locais coincidiram com os hashes diretos das fontes. A
lista verificável está em
[`config/namelists/SHA256SUMS`](../../config/namelists/SHA256SUMS).

## Links simbólicos de origem

Os `streams.atmosphere` de EXP01/2021, EXP01/2022, EXP02/2021 e EXP02/2022
eram links para `../streams.atmosphere`, registrados como íntegros no MEQ-00B.
EXP03/2021 tinha a mesma forma de link no diretório Oval. CTL/2021, CTL/2022 e
EXP03/2022 continham arquivos regulares. Em todos os casos, o hash desta cópia
é o hash do conteúdo que o MPAS abriu.

## Diferenças de configuração

### Valores explicitamente informados

| Aspecto | CTL | EXP01 | EXP02 | EXP03 |
|---|---|---|---|---|
| SST | `config_sst_update = false`; stream de superfície com `input_interval = none` | `true`; atualização `86400` s | igual a EXP01 | igual a EXP01 |
| Arquivo de superfície | `meqbr_05km.sfc_update.nc`, mas não aplicado durante a integração | `meqbr_05km.sfc_update.nc` | `meqbr_05km_buf.sfc_update.nc` | `meqbr_05km_oval_meq02a.sfc_update.nc` |
| Malha/decomposição | prefixo `meqbr_05km.graph.info.part.` | igual a CTL | `meqbr_05km_buf.graph.info.part.` | `meqbr_05km_oval_meq02a.graph.info.part.` |
| Integração 2021 | início 21/10/2021, 41 dias, sem restart | igual a CTL | início original de 41 dias; retomada com `start_time = file`, 37 dias e restart | início 21/10/2021, 41 dias, sem restart |
| Integração 2022 | namelist preservado: `start_time = file`, 31 dias, restart | início 21/09/2022, 41 dias, sem restart | igual a EXP01 | igual a EXP01 |
| Histórico | horário, `stream_list.atmosphere.wind_energy` | igual | igual | igual |
| Diagnósticos | a cada 3 h | desativados (`none`) | desativados | desativados |
| Restart de saída | diário | diário | diário | diário |
| LBC | a cada 6 h, `config_apply_lbcs = true` | igual | igual | igual |
| Passo e dinâmica | 30 s; ordem 2; transporte/dinâmica separados; 2 subpassos acústicos; 3 subpassos dinâmicos; Smagorinsky 2D | igual | igual | igual |
| Física | suíte `mesoscale_reference`; intervalos radiativos de 30 min; opções Noah-MP listadas no namelist | igual | igual | igual |
| Assimilação | IAU explicitamente desligado | igual | igual | igual |

O diff byte a byte dos namelists iniciais de 2021 confirma que CTL → EXP01
altera somente `config_sst_update`, EXP01 → EXP02 somente o prefixo de
decomposição e EXP02 → EXP03 somente esse prefixo novamente. Nos streams,
CTL → EXP01 altera apenas o intervalo de diagnósticos e o intervalo da
superfície; as transições seguintes alteram somente os nomes dos arquivos da
malha e da atualização de superfície. As mesmas relações valem para as
configurações de início contínuo de 2022. As diferenças de restart descritas na
tabela são operacionais e foram mantidas sem normalização.

A correção costeira da OISST não é codificada por um nome distinto no
namelist: ela é propriedade do conteúdo de `sfc_update.nc`. Os registros de
execução e a auditoria OISST demonstram que EXP01, EXP02 e EXP03 usam a versão
corrigida; o par `_BADSST`, excluído deste arquivo, usa a versão contaminada.

A caixa de ERA5 também não aparece nos dois arquivos runtime. Os registros do
servidor documentam CTL/2021 com caixa `8/-56/-8/-30`, CTL/2022 com
`12/-60/-12/-28`, EXP01 reutilizando as condições iniciais/laterais da malha
base por período, e EXP02/EXP03 com a caixa larga `15/-64/-16/-24`. Assim, a
mudança EXP02 inclui conjuntamente a malha com buffer e a ampliação da caixa de
forçante; não é um contraste apenas de malha.

O número de ranks MPI também é externo ao namelist: 80 para CTL, 90 para
EXP01/EXP02 e 60 para EXP03, segundo os registros operacionais.

### Valores resolvidos fora destes namelists

Os componentes WSM6, RRTMG, YSU, Monin-Obukhov e Tiedtke são a expansão da
suíte `mesoscale_reference`; seus seletores individuais não estão escritos nos
namelists arquivados. Opções omitidas são resolvidas pelos padrões do
MPAS-Atmosphere 8.4.1 e pela suíte, e não devem ser apresentadas como valores
explicitamente configurados nestes arquivos.

A resolução vertical também não é definida no namelist runtime arquivado. Os
arquivos iniciais, históricos e os registros de preparação demonstram 55
camadas, 56 interfaces e topo em 30 km; o `zeta_wind.txt` define as interfaces.
Esses valores são evidência do estado inicial resolvido, não linhas dos oito
`namelist.atmosphere` aqui copiados.

## Checagem de informações sensíveis

Foi feita busca nos 16 arquivos principais por indicadores de senha, segredo,
token, chave de API, chave privada, credenciais AWS e CDSAPI. Não houve
correspondências. A leitura manual mostrou apenas nomes relativos de arquivos
MPAS; não há credenciais ou dados pessoais nos arquivos preparados para Git.
O namelist adicional de EXP02/2021 também não contém esses indicadores.

## Limitações e pendências

1. **CTL/2022:** o próprio README operacional afirma que o
   `namelist.atmosphere` sobrevivente corresponde ao segundo trecho, iniciado
   por restart e executado por 31 dias. Não foi localizado um arquivo original
   separado para o spin-up de 21/09 a 01/10/2022. O namelist compartilhado na
   raiz também foi examinado: ele inicia em 01/10, desliga restart e não possui
   vínculo inequívoco com o primeiro trecho, portanto foi excluído. Nenhuma
   reconstrução foi incluída.
2. **CTL/2021:** o encerramento operacional continua sem log terminal
   autoritativo identificado. A configuração é preservada e os 721 históricos
   da janela científica existem, mas essa limitação do MEQ-00B permanece.
3. **Padrões do modelo:** este arquivo não contém um dump completo das opções
   finais resolvidas pelo Registry/physics suite. Somente as linhas presentes
   nos namelists podem ser chamadas de explícitas.
4. **Forçantes e listas de variáveis:** `sfc_update.nc`, LBCs, arquivos de
   condição inicial e `stream_list.atmosphere.wind_energy` não fazem parte do
   escopo de cópia desta missão. Suas propriedades são documentadas por
   registros externos, não reproduzidas como se fossem conteúdo destes dois
   arquivos.

## Estado do repositório durante a preparação

A branch local `codex/meq-02d-config-archive` foi criada a partir de
`0344a4a5a6a239452ffe457f55b172504ff65100`, que correspondia ao remoto da
MEQ-02C no início da tarefa. Já existiam `results/backups/` e
`results/report.zip` não rastreados; eles foram preservados e não fazem parte
desta entrega. Não foram feitos commit, push, abertura de PR ou merge.
