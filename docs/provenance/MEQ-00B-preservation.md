# MEQ-00B — Preservação da proveniência operacional

**Data:** 08/10/2026\
**Estado: Preservação executada e verificada pelo agente; registro documental aprovado pelo pesquisador em 08/10/2026.**

## Objetivo

Preservar as evidências operacionais das dez integrações Meq-BR (CTL, EXP01, EXP02, EXP01_BADSST e EXP02_BADSST, nos períodos de 2021 e 2022), antes de intervenções futuras nos ambientes.

## Localização

Servidor: `danilocs@swell`

Diretório:\
`/p1-swell/danilocs/mpas-meqbr-experiments/local_provenance/MEQ-00B_20261008`

O diretório `local_provenance/` está excluído localmente do Git por `.git/info/exclude`. Seu conteúdo não foi versionado.

## Conteúdo preservado

- 352 arquivos regulares de origem: logs, configurações, scripts, executável MPAS e registros da auditoria OISST.
- 1.788 symlinks, incluindo links originalmente quebrados, com seus destinos textuais preservados.
- Um arquivo NetCDF excepcional de EXP02/2021, referente ao spin-up de 25/10/2021.
- Git bundle do commit de auditoria OISST `1acf96d9830916f6d18fd67d4e27aec24f741ab7`.
- Inventário de 12.630 registros referentes a dados volumosos não copiados.

Pacote final: **861.521.313 bytes (821,6 MiB)** de arquivos regulares.

## Integridade

Segundo o relatório do agente executor:

- Os 352 arquivos copiados apresentaram SHA-256 idêntico aos originais, antes e depois da cópia.
- Os metadados monitorados dos originais permaneceram inalterados.
- Os destinos textuais dos 1.788 symlinks foram preservados.
- O Git bundle passou na verificação e no teste de recuperação.
- Os três worktrees inspecionados permaneceram limpos.

Marcador `VERIFIED`: `2026-10-08T20:04:47Z`.

**SHA-256 informado do manifesto do pacote:**

`ce4a8fe311f6544bd1007f6239821131ed631acf6799d26a46d106cc374b597a`

**SHA-256 do executável preservado:**

`095ee3b1debac20cf58de77717cc9a7934f61621bef7c393dac765541cd1e494`

## Limitações

A preservação é seletiva e não constitui backup integral das simulações.

Os arquivos originais e o pacote permanecem no mesmo filesystem do Swell, por decisão do pesquisador. Não foi realizada cópia externa.

Os symlinks preservam os destinos históricos, mas nem todos os arquivos apontados continuam disponíveis.

O encerramento operacional de CTL/2021 permanece sem log terminal autoritativo identificado.

O executável preservado é compatível com as evidências disponíveis, mas sua identidade binária histórica não foi demonstrada integralmente.

## Governança

O GitHub permanece como registro oficial das decisões e da documentação científica aprovada.

O pacote no Swell constitui o arquivo operacional de evidências. Não deve ser modificado, substituído ou removido sem autorização específica.

Este registro documenta os resultados informados pelo agente executor, sem nova auditoria independente.

Nenhuma conclusão científica comparativa entre CTL, EXP01 e EXP02 foi reavaliada nesta missão.
