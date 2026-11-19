# 07_production — acompanhamento da produção MEQ-06

`monitor_production.py` mostra, em uma tela, o andamento da integração climatológica da `EXP03` no Swell (MEQ-06.8):
barra de 2021-10-21 até o próximo ponto de decisão da `DEC-MEQ-006` (2023-06-30, 2023-11-30, 2025-01-31), data simulada, trecho mensal, fase (spin-up/produção), vazão (dias simulados por dia real) e ETA de cada ponto, processos `atmosphere_model`, idade do log (aviso de travamento), erros no log, disco livre e carga/outros usuários.

**Somente leitura:** uma conexão `ssh swell` por atualização, só `ls`, `tail`, `grep`, `ps`, `df`, `stat` e `/proc/loadavg`; nenhum arquivo é escrito ou baixado, nenhum processo é tocado. Só a biblioteca padrão do Python 3 (o do macOS serve).

```bash
python3 scripts/07_production/monitor_production.py --watch 10
```

- Sem `--watch`: uma consulta e sai. `--watch N` atualiza a cada N minutos (Ctrl-C sai).
- `--no-color` (ou `NO_COLOR=1`) para saída sem cores; sem terminal, as cores saem sozinhas.
- `--run-dir <dir>` consulta outra rodada, por exemplo a EXP03 2021 validada:
  `--run-dir /p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/20211101_20211201`.
- Configuração em `monitor_production.cfg`: host, diretório de produção, padrões de log/history/restart, marcos e limites (log parado, disco mínimo, janela da vazão, %CPU de processo alheio).

**Leituras:** a data simulada vem do nome do último `history.*.nc` (ou do último `Begin timestep` do log, se mais recente); a vazão compara a data simulada com a hora de modificação dos history nas últimas 24 h de saída; o ETA supõe essa vazão constante. Se o diretório não existir ou não houver saída nem modelo rodando, mostra "NÃO INICIADA".

**Atenção:** o diretório de produção (`run_dir`) não está fixado no plano (`research/MEQ-06-production-plan.md`); o valor do `.cfg` é provisório e deve ser reconferido antes da MEQ-06.7.
