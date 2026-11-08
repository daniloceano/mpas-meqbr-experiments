# Sincronização segura entre GitHub, Swell e Macs

Use o GitHub como referência do conteúdo versionado e o Swell como referência
dos dados científicos volumosos. Não copie NetCDF, GRIB, caches ou históricos
brutos para os Macs.

## 1. Preflight

Em cada checkout:

```bash
git status --short --branch
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
```

Interrompa se houver alteração rastreada inesperada ou divergência que impeça
fast-forward. Preserve arquivos não rastreados; não use `reset --hard`,
`git clean` ou force push.

## 2. Publicação

Depois de validar testes, tabelas e relatório no ambiente controlador:

```bash
git add <arquivos pertencentes à unidade de trabalho>
git diff --cached --check
git commit -m "<descrição objetiva>"
git fetch origin
git push origin main:main
```

Não adicione dados volumosos, backups, credenciais ou cópias redundantes do
relatório.

## 3. Atualização dos outros computadores

Com a árvore rastreada limpa:

```bash
git switch main
git fetch origin
git merge --ff-only origin/main
```

Confira novamente `git status --short --branch` e preserve qualquer conteúdo
local não rastreado.

## 4. Relatório offline

Do Swell para o MacBook, sem exclusões:

```bash
rsync -a swell:/p1-swell/danilocs/mpas-meqbr-experiments/results/report/ results/report/
python3 scripts/06_report/validate_technical_report.py --report-dir results/report
```

Do MacBook para o Mac Mini:

```bash
rsync -a results/report/ mini:Documents/Programs_and_scripts/mpas-meqbr-experiments/results/report/
ssh mini 'cd ~/Documents/Programs_and_scripts/mpas-meqbr-experiments && python3 scripts/06_report/validate_technical_report.py --report-dir results/report'
```

O uso de `rsync -a` sem `--delete` evita remover backups ou artefatos locais.
Ao final, confirme que GitHub e os três checkouts apontam para o mesmo commit e
que `index.html` e `report_manifest.json` têm hashes idênticos.
