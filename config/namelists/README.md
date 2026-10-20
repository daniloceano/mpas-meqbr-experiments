# Configurações executadas dos experimentos Meq-BR

Este diretório arquiva cópias byte a byte das configurações de execução
identificadas para CTL, EXP01, EXP02 e EXP03 nos períodos P0/2021 e LPI/2022.
Os arquivos são evidência histórica: **não devem ser editados para preparar
novas simulações**.

A proveniência completa, as limitações e a comparação das opções estão em
[`docs/provenance/MEQ-02D-experimental-configurations.md`](../../docs/provenance/MEQ-02D-experimental-configurations.md).
Os hashes das cópias estão em [`SHA256SUMS`](SHA256SUMS).

## Organização

```text
config/namelists/<experimento>/<ano>/
├── namelist.atmosphere
└── streams.atmosphere
```

O caso EXP02/2021 contém também
`namelist.atmosphere.pre_restart_20260924`, o namelist do trecho inicial. O
arquivo `namelist.atmosphere` desse mesmo diretório é o trecho de retomada.
Ambos são originais preservados, não reconstruções.

Nos diretórios operacionais, os `streams.atmosphere` de EXP01/2021-2022,
EXP02/2021-2022 e EXP03/2021 eram links simbólicos para o arquivo compartilhado
do experimento. Aqui eles foram materializados como arquivos regulares para que
cada caso seja autocontido. O conteúdo resolvido e o SHA-256 foram preservados.
CTL/2021-2022 e EXP03/2022 já possuíam arquivos regulares por período.

## Verificação

A partir deste diretório:

```bash
shasum -a 256 -c SHA256SUMS
```

Uma verificação de informações sensíveis não encontrou senhas, tokens, chaves
privadas, chaves de API ou credenciais nos arquivos arquivados.
