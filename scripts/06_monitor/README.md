# 06_monitor — painel automático da produção MEQ-06 (MEQ-06.8)

`monitor_production.py` roda **no Swell** (cron do usuário `danilocs`, a cada 6 h, `nice 19` + `ionice` ociosa, ~5 s de leitura (amostra de CPU) + ~4 s de push). Lê `meq06_production/` **sem escrever nada lá** (history, restarts, `log.atmosphere.0000.out`,
`logs/production.log`, manifestos LBC, intermediários ERA5, `df`, `/proc/loadavg`, CPU instantânea por thread em duas leituras de `/proc/<pid>/task/*/stat` com 5 s de intervalo) e gera
`index.html`, `status.json` e `status_history.csv` (acumulado) em `~/meq06_monitor/site`, um clone separado só
para isso. Com `--publish`, grava um **commit único** no branch órfão `monitor` e faz `push --force` **só** de
`refs/heads/monitor`; aborta se o branch atual não for `monitor`. Nunca toca no `main`.

## Abrir o painel

```bash
git fetch origin monitor && git show origin/monitor:index.html > /tmp/meq06_monitor.html && open /tmp/meq06_monitor.html
```

Histórico: `git show origin/monitor:status_history.csv`; estado bruto: `git show origin/monitor:status.json`.

## No Swell

```bash
# cron (crontab -l)
17 */6 * * * nice -n 19 ionice -c3 $HOME/meq06_monitor/bin/run_monitor.sh >> $HOME/meq06_monitor/cron.log 2>&1
```

- `run_monitor.sh` (cópia em `~/meq06_monitor/bin/`) busca `origin/main` no clone separado e copia **só**
  `scripts/06_monitor/monitor_production.py` para `bin/` antes de rodar; se falhar, roda a cópia atual e o painel
  mostra o alerta "script não sincronizado" (esperado até o merge deste PR). O rodapé mostra o SHA do blob do
  script, comparável com `git hash-object`. O próprio `run_monitor.sh` não se atualiza sozinho.
- Execução manual sem publicar: `python3 bin/monitor_production.py --out /tmp/teste_monitor`.
- Credencial: a já existente no Swell (`credential.helper=store`, HTTPS).

## Cálculos e alertas (resumo)

- Vazão = dias simulados por dia de máquina a partir do mtime dos `history.*.nc` (24 h, 6 h, média desde o 1.º START;
  também s/passo do log). ETA de cada ponto de decisão = o maior entre a conta pela vazão e a chegada dos dados
  (só o ponto 1 tem ERA5 previsto). Pontos 2023-11-30 e 2025-01-31: "projeção; pressupõe ERA5 e autorização a tempo".
- Disco projetado = ocupação de `meq06_production/` + 5,35 GB por dia simulado (24 history + 4 LBC + ERA5).
- Alertas (indícios, não causas): thread de outro usuário > 20 % de CPU instantânea (5 s) nos núcleos da P90C; script não sincronizado; carga > 95; vazão 6 h
  < 90 % da mediana; sem restart novo > 36 h; falha/retomada/STOP no driver (48 h); disco < 5 TB; folga de
  contorno < 2 dias.
- `scripts/07_production/monitor_production.py` (consulta interativa pelo Mac via SSH) continua válido.
