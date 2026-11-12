# Meq-BR — Roadmap científico e operacional

> **Versão:** 1.2 — 12/11/2026, reconciliação documental após a reabertura da seleção da MEQ-03 (`DEC-MEQ-002`, 11/11/2026); base `main@3b1eb79`.
> **Mudanças da v1.2:** MEQ-03 reaberta (em andamento — reavaliação com SODAR, `DEC-MEQ-002`; `DEC-MEQ-001` preservada); MEQ-04 e MEQ-05 passam a depender da conclusão da reavaliação; manifesto do HTML atualizado (seção 2); divergência sobre o pai da `EXP03` registrada como pendente (seção 3); datas da MEQ-01 esclarecidas; contagem de decisões `DEC-MEQ-NNN` corrigida; pendência do `SCIENTIFIC_NOTES.md` marcada como atendida; situação do PR #19 do repositório do modelo atualizada; seção 8 refeita. Motivo: decisão do responsável de 11/11/2026 e divergências documentais apontadas na conferência de `origin/main@3b1eb79`. Publicação por branch `docs/meq-03-reopening-sodar` e PR, sujeita à aprovação do pesquisador.
> **Histórico:** v1.1 — 10/11/2026, base `main@085f96c` (MEQ-01 concluída; MEQ-04 em andamento com números da EXP03; campos-padrão em MEQ-00 a MEQ-03; seções 3 e 8 atualizadas; os commits `8394fbb` e `085f96c` foram integrados diretamente na `main`, sem PR; reconciliação publicada pelo PR #7, merge `c2e15cd`). v1.0 aprovada pelo pesquisador em 08/10/2026 e publicada pelo PR #3 (commit `fe16f0b`, merge `6fef1bb`, 09/10/2026).

## 1. Propósito e alcance

Organizar o pós-doutorado Meq-BR, baseado em simulações regionais do MPAS-Atmosphere de resolução aproximada de 5 km na Margem Equatorial Brasileira, em duas perguntas centrais: **qual configuração experimental adotar para as integrações climatológicas?** e **qual ganho verificável essas integrações oferecem em relação ao ERA5 para a avaliação do recurso eólico offshore?** A interpretação deverá também considerar os mecanismos físicos, a distribuição espacial do recurso e os limites da extrapolação de simulações curtas para séries multianuais.

O roadmap é a fonte oficial de **planejamento, dependências, prioridades, situação das frentes e decisões aprovadas**. Não substitui a documentação de experimentos, o registro científico, os dados de resultados ou os relatórios. A numeração MEQ-00…MEQ-07 identifica frentes de pesquisa; não se confunde com os estágios `00_setup`…`06_report` nem com os experimentos `CTL`, `EXP01`, `EXP02`.

A organização das frentes MEQ-00 a MEQ-07 e o conteúdo deste roadmap foram **aprovados pelo pesquisador em 08/10/2026** como ponto de partida sujeito a revisões futuras. Essas aprovações **não** ratificam `EXP01` como configuração definitiva nem autorizam simulações, código ou operações Git fora da publicação específica deste roadmap.

## 2. Referências oficiais e interface de resultados

- Repositório científico: <https://github.com/daniloceano/mpas-meqbr-experiments>.
- Repositório do modelo e utilitários: <https://github.com/CGFD-USP/MPAS-Research>. O ciclo de revisão e merge de mudanças nesse repositório é administrado separadamente.
- Definição dos experimentos: `runs/meqbr_05km/EXPERIMENTS.md` no ambiente das simulações; espelho analítico em `config/experiments.yaml`. Em divergência, verificar o registro junto às simulações.
- Registro interpretativo: `SCIENTIFIC_NOTES.md`; protocolos e convenções: `docs/validation_protocol.md` e `docs/analysis_conventions.md`; proveniência operacional: `docs/provenance/MEQ-00B-preservation.md`.
- Evidências calculadas e versionadas: `results/tables/`, `results/audit/corrected_runs_validation.json` e `docs/run_status.md` (este último é gerado, não editado manualmente).
- **Interface científica principal do pesquisador:** `results/report/index.html`, acompanhado dos arquivos `results/report/assets/` e de `results/report/report_manifest.json`. É um produto **gerado**, não editado manualmente: deve organizar as análises e conclusões centrais, com explicações, figuras, incertezas e vínculos à proveniência.
- **Análises especializadas ou secundárias:** relatórios complementares, como `results/report/sst-fix-comparison/index.html` para a auditoria antigo × corrigido do OISST. O relatório principal incorpora somente a síntese cientificamente relevante e o link para o detalhamento.

O HTML principal existente cobre desenho experimental, andamento e custo, campos espaciais, estrutura vertical, validação INMET/LiDAR, valor adicionado sobre ERA5, mecanismos, seleção e limitações. Sua existência **não** implica que todas as conclusões tenham sido aprovadas pelo pesquisador. O manifesto da versão atual em `main` (`generated_utc` 2026-11-11T20:11:45Z, `analysis_commit` `0a19b65`) registra `working_tree_dirty: false`. A versão examinada na v1.0 (`generated_utc` 2026-10-08T12:52:53Z) registrava `working_tree_dirty: true`; o fato permanece como proveniência histórica, sem inferir que aqueles resultados sejam inválidos. A síntese do HTML ainda reflete a `DEC-MEQ-001`; as mudanças decorrentes da `DEC-MEQ-002` estão listadas na MEQ-03.

## 3. Situação experimental de referência

| Identificador | Significado científico | Uso na decisão |
| --- | --- | --- |
| `CTL` | Controle: SST inicial do ERA5 mantida fixa; malha `meqbr_05km`. | Comparação de referência. |
| `EXP01` | Atualização diária NOAA OISST v2.1, com tratamento costeiro corrigido; malha `meqbr_05km`. | Ganho robusto sobre `CTL`; alternativa de menor domínio e custo. |
| `EXP02` | Herda `EXP01` e altera conjuntamente a malha para `meqbr_05km_buf` **e** a caixa ERA5 de fronteira. | Testa o efeito **incremental do tratamento de fronteira**, não o buffer isolado. |
| `EXP03` | Malha Oval `meqbr_05km_oval_meq02a` (102.968 células), com OISST corrigida e caixa ERA5 ampla. **Pai pendente de conferência:** a v1.1 deste roadmap registrava `EXP01`; `config/experiments.yaml` e o `README.md` registram `EXP02`; a fonte prioritária (`runs/meqbr_05km/EXPERIMENTS.md`, no Swell) ainda não foi conferida. | **Selecionado na MEQ-03 (`DEC-MEQ-001`, 10/11/2026)**; seleção **em reavaliação com SODAR** (`DEC-MEQ-002`, 11/11/2026). Não demonstra superioridade universal. |
| `EXP04`–`EXP06` | Ramo de física sobre `EXP01`: MYNN; + Grell–Freitas; + ciclo diurno da SST de pele. | Sem ganho detectável sobre `EXP01` (EXP04) ou sem benefício consistente (EXP05/EXP06). |
| `EXP01_BADSST`, `EXP02_BADSST` | Integrações históricas com OISST costeiro contaminado por valor de preenchimento sobre terra. | Preservadas como evidência da falha; **excluídas da seleção científica atual**. |

O registro de análise indica integrações completas nos dois períodos amostrados e auditoria positiva das quatro pernas corrigidas em `results/audit/corrected_runs_validation.json`. Nos testes pareados atuais, `EXP01` é favorecido frente ao `CTL` em **8/8** comparações sítio–período–altura; `EXP02` e `EXP01` não apresentam diferença estatisticamente distinguível em **8/8** comparações, apesar de a malha do `EXP02` possuir aproximadamente **24% mais células**. Esses resultados descrevem a análise da v1.0 (08/10/2026). A comparação atual, com EXP03–EXP06 e a decisão de seleção, está em `results/tables/selection_summary_current.md` e `research/MEQ-03-selection-decision.md` (`DEC-MEQ-001` e a reabertura `DEC-MEQ-002`).

A diferença `EXP01 − CTL` não isola apenas a evolução temporal da SST: a média da SST também muda. Comparações devem usar horas comuns e distinguir melhora estatística, mecanismo físico, representatividade observacional e custo computacional.

## 4. Frentes de trabalho

### MEQ-00 — Auditoria e preservação da proveniência

- **Objetivo:** identificar o estado dos repositórios e ambientes e preservar evidências operacionais relevantes antes de intervenções posteriores.
- **Situação:** **concluída em 08/10/2026**, com MEQ-00A (auditoria factual) e MEQ-00B (preservação seletiva).
- **Evidências:** `docs/provenance/MEQ-00B-preservation.md`, PR científico [#2](https://github.com/daniloceano/mpas-meqbr-experiments/pull/2), integrado à `main` no commit `5833f3e`.
- **Dependências:** nenhuma para o encerramento já registrado; as etapas futuras devem respeitar os arquivos preservados e sua proveniência.
- **Critério de encerramento:** satisfeitos pela aprovação do registro e integração documental; o relato de testes do agente não constitui nova auditoria independente nesta missão.
- **Decisões pendentes:** nenhuma para reabrir ou alterar a MEQ-00 por padrão; novos riscos concretos podem motivar decisão específica.

### MEQ-01 — Planejamento, governança e roadmap

- **Objetivo:** estabelecer a fonte oficial de planejamento, fronteiras de escopo, sequência das frentes, rastreamento de decisões e condições de avanço.
- **Situação:** **concluída em 09/10/2026**. Roadmap v1.0 publicado pelo PR #3 (commit `fe16f0b`, merge `6fef1bb`); encerramento decidido pelo pesquisador em 10/11/2026. As duas datas têm papéis distintos: 09/10/2026 é a data da publicação que satisfez o critério de encerramento; 10/11/2026 é a data em que o pesquisador decidiu reconhecer a frente como encerrada. As reconciliações v1.1 e v1.2 são manutenção desta governança, não reabertura da frente.
- **Evidências:** PR [#3](https://github.com/daniloceano/mpas-meqbr-experiments/pull/3); histórico de `research/ROADMAP.md`; documentação MEQ-00B.
- **Dependências:** aprovação deste roadmap; nova conferência Git antes de operações de escrita.
- **Critério de encerramento:** conteúdo aprovado explicitamente, arquivo publicado no repositório científico por branch/PR autorizados e conferência documentada de commit, push e merge; alternativamente, bloqueio ou cancelamento registrado.
- **Decisões pendentes:** nenhuma para a frente; novas versões do roadmap seguem as regras da seção 7. O registro `DEC-MEQ-NNN` está em uso: `DEC-MEQ-001` (10/11/2026, seleção da `EXP03`) e `DEC-MEQ-002` (11/11/2026, reabertura da seleção com SODAR), ambos em `research/MEQ-03-selection-decision.md`. A versão v1.1 afirmava que nenhum registro havia sido criado até 10/11/2026, o que já não correspondia ao arquivo de decisão; corrigido na v1.2.

### MEQ-02 — Exploração de novas configurações MPAS

- **Objetivo:** testar alternativas capazes de superar ou complementar `EXP01` antes da seleção para climatologia.
- **Situação:** **concluída em 10/11/2026**. CTL e EXP01–EXP06 foram integrados e validados para P0/2021 e LPI/2022; os produtos EXP01_BADSST/EXP02_BADSST permanecem apenas como evidência do erro histórico de SST, não como candidatos válidos.
- **Evidências:** `config/experiments.yaml`, `docs/provenance/MEQ-02D-EXP04-06-campaign.md`, `results/tables/site_metrics.csv`, `results/tables/pairwise_tests_current.csv`, `results/tables/exp04_06_priority_tests.csv` e relatório HTML.
- **Resultado:** EXP01 trouxe ganhos robustos sobre CTL; EXP02/EXP03 avaliaram o desenho do domínio; EXP04 não apresentou ganho detectável sobre EXP01 e EXP05/EXP06 não justificaram sua adoção com os períodos observados. A seleção final foi deliberada na MEQ-03.
- **Limitações:** dois períodos curtos e diferenças de configuração/recursos que impedem atribuição universal de mecanismos ou escalabilidade.
- **Dependências:** MEQ-00.
- **Critério de encerramento:** experimentos candidatos integrados, auditados e comparados nos dois períodos, com resultado submetido à seleção da MEQ-03.
- **Decisões pendentes:** nenhuma.

### MEQ-03 — Validação e seleção científica da configuração

- **Objetivo:** integrar as evidências, comparar desempenho, custo e mecanismos e selecionar a configuração para a próxima fase.
- **Situação:** **em andamento — reavaliação com SODAR (DEC-MEQ-002)**. Em 11/11/2026, o responsável decidiu reavaliar a seleção da `DEC-MEQ-001` incluindo o SODAR MFAS/Scintec da estação EOSOLAR P1 (Maranhão; lat −2,7249, lon −42,5752; ~4,1 km do P0; 10/11/2021–09/10/2022; 10 min; 30–280 m), com peso igual ao LiDAR, mesmo que isso altere a conclusão. Até nova decisão ratificada, `EXP03` permanece como a seleção registrada na `DEC-MEQ-001`, sob reavaliação.
- **Histórico da situação:** concluída em 10/11/2026 com `EXP03` selecionado (`DEC-MEQ-001`): o pesquisador comunicou a decisão tomada em conjunto com seu supervisor de seguir com `EXP03` como melhor candidato para as próximas simulações. Reaberta em 11/11/2026 (`DEC-MEQ-002`); a `DEC-MEQ-001` é preservada como histórico.
- **Registro da decisão e ressalvas:** `research/MEQ-03-selection-decision.md` (`DEC-MEQ-001` e `DEC-MEQ-002`).
- **Evidências:** `results/tables/pairwise_tests_current.csv`, `results/tables/selection_summary_current.md`, `results/tables/site_metrics.csv`, `results/tables/era5_added_value_current.csv`, `results/tables/cell_sensitivity.csv`, `results/tables/runtime_metrics.csv` e relatório HTML v2 (base da `DEC-MEQ-001`, sem SODAR). As evidências com SODAR ainda não existem.
- **Escopo da ratificação anterior:** a `DEC-MEQ-001` foi escolha científica para prosseguir com `EXP03`; não comprovou superioridade universal/climatológica, não encerrou a MEQ-04 e não substitui o benchmark operacional MEQ-05. A síntese narrativa do HTML foi atualizada para refletir essa decisão, sem recalcular resultados (11/11/2026, PR #9, merge `784e9bc`).
- **Entregas da reavaliação (registradas, não implementadas nesta versão):** (1) SODAR P1 no pipeline completo de extração, pareamento, métricas, testes e seleção, com peso igual ao LiDAR; (2) síntese do HTML principal em três visões — LiDAR/SODAR, INMET e geral; (3) explicitação, no HTML, da resolução temporal de cada comparação.
- **Próxima dependência:** a recomendação final da MEQ-05 (eficiência paralela e custo das integrações multianuais) depende da configuração que resultar desta reavaliação.
- **Dependências:** MEQ-02; incorporação do SODAR P1 às análises; ratificação conjunta da nova seleção.
- **Critério de encerramento:** nova seleção registrada em entrada `DEC-MEQ-NNN` que referencie a `DEC-MEQ-001` e a `DEC-MEQ-002`, ratificada conjuntamente pelo pesquisador e pelo supervisor, com evidências (incluindo SODAR) e ressalvas versionadas.
- **Decisões pendentes:** nova seleção final (ratificação conjunta do pesquisador e do supervisor); renomeação de sítios proposta na reavaliação — P0 → ML, SODAR P1 → MS, LPI inalterado — a decidir, não aplicada; pai da `EXP03` (`EXP01` ou `EXP02`), pendente de conferência em `runs/meqbr_05km/EXPERIMENTS.md` no Swell (seção 3).

### MEQ-04 — Valor agregado sobre ERA5

- **Objetivo:** estabelecer onde e em que condições o MPAS oferece ganho confiável sobre ERA5 na observação de vento offshore e na representação espacial do recurso.
- **Situação:** **em andamento** (decisão do pesquisador, 10/11/2026), com análise extensa já disponível e síntese ainda não ratificada. Para a configuração selecionada na `DEC-MEQ-001` (`EXP03`, seleção em reavaliação pela `DEC-MEQ-002`), o skill de Murphy (MSE) a 100 m frente ao ERA5 é aproximadamente **+0,39 em P0/2021** (IC95% 0,25–0,59) e **+0,43 em LPI/2022** (IC95% 0,32–0,55). Referência histórica da v1.0: `EXP01` com +0,34 e +0,30.
- **Evidências:** `results/tables/era5_added_value_current.csv`, `resource_comparison.csv`, `era5_month_representativeness.csv`; seção 6 e demais figuras do relatório HTML principal.
- **Dependências:** interpretação da representatividade e da comparabilidade, e atualização seletiva para a configuração que resultar da reavaliação da MEQ-03 (`DEC-MEQ-002`). A análise existente não deve ser repetida sem justificativa.
- **Critério de encerramento:** síntese científica aprovada do ganho e de suas limitações **para os períodos e variáveis avaliados**, distinção entre habilidade observacional e estrutura espacial plausível, e atualização do HTML principal quando necessária.
- **Decisões pendentes:** ratificação da síntese do valor agregado para a configuração que resultar da reavaliação da MEQ-03; necessidade e extensão de validações complementares antes da extrapolação climatológica; atualização do HTML principal decorrente da reavaliação (três visões e resolução temporal, entregas da MEQ-03). A atualização editorial do veredito para `EXP03` (template, validador e regeneração) já foi feita no PR #9 (merge `784e9bc`, 11/11/2026).

### MEQ-05 — Benchmark de paralelismo e viabilidade computacional

- **Objetivo:** determinar a faixa eficiente de núcleos/processos para a malha selecionada e estimar o custo de simulações multianuais.
- **Situação:** **planejada**. Os custos históricos documentados não constituem uma curva de saturação confiável, pois usam números diferentes de ranks e incluem tempos estimados/reconstruídos.
- **Evidências:** seção de andamento/custo e limitações do HTML; `results/tables/runtime_metrics.csv`; configurações e registros operacionais preservados.
- **Dependências:** infraestrutura de execução estável, configuração controlada, métricas mensuráveis e, para a recomendação definitiva, conclusão da reavaliação da MEQ-03 (`DEC-MEQ-002`) e a malha/configuração dela resultante. Ensaios exploratórios podem começar antes, se aprovados.
- **Método proposto:** série de integrações curtas e comparáveis com números crescentes de núcleos/processos; **um dia simulado é hipótese inicial, não duração já aprovada**. Separar tempo de inicialização do regime representativo, manter constantes condições/saídas/ambiente, repetir medições quando viável e registrar tempo de parede, núcleo-horas, aceleração, eficiência paralela e efeitos de I/O. A curva deve apoiar uma decisão de compromisso entre prazo e consumo de recursos, e não simplesmente maximizar núcleos.
- **Critério de encerramento:** curva de saturação reproduzível, faixa de paralelismo recomendada para a malha definitiva e estimativa fundamentada do custo da MEQ-06.
- **Decisões pendentes:** plano concreto de números de processos, duração/repetições dos testes, recursos máximos e critério de eficiência aceitável.

### MEQ-06 — Integrações climatológicas

- **Objetivo:** executar séries multianuais com a configuração aprovada e proveniência suficiente para avaliação do recurso eólico.
- **Situação:** **planejada; não iniciada neste roadmap**.
- **Evidências futuras:** experimentos, logs, metadados, inventários, verificações de integridade e produtos das integrações.
- **Dependências:** decisão final MEQ-03; avaliação pertinente MEQ-04; dimensionamento MEQ-05; disponibilidade de forçantes/recursos; verificação do código e **correção OISST efetivamente utilizada**. A correção está no PR [#19](https://github.com/CGFD-USP/MPAS-Research/pull/19), branch `fix/oisst-coastal-land-fill` do repositório do modelo (verificação de 08/10/2026); consulta somente leitura de 12/11/2026 indica o PR como integrado em `develop` em 09/10/2026. O **merge do PR não é pré-requisito** desta frente: é necessário usar e identificar uma implementação corrigida e validada por commit, não confiar apenas no nome da branch.
- **Critério de encerramento:** períodos definidos efetivamente simulados, produtos íntegros e reprodutíveis, eventuais falhas e reinícios documentados, custos e limitações registrados.
- **Decisões pendentes:** períodos climatológicos exatos, resolução temporal das saídas, orçamento e autorização explícita de execução.

### MEQ-07 — Avaliação climatológica do recurso eólico offshore

- **Objetivo:** caracterizar climatologia, variabilidade e distribuição espacial do vento/recurso offshore e avaliar o valor científico e aplicado do downscaling sobre ERA5.
- **Situação:** **planejada**; os diagnósticos dos meses curtos já existem, mas não constituem avaliação climatológica multianual.
- **Evidências:** futura série climatológica, produtos de análise e validação; métricas e procedimentos já estabelecidos (velocidade, distribuição, cisalhamento, densidade de potência eólica, ciclo diurno e incerteza).
- **Dependências:** MEQ-06 e resultados pertinentes da MEQ-04; definição de representatividade, comparação temporal e limitações observacionais.
- **Critério de encerramento:** produtos centrais organizados no HTML principal ou em sua evolução aprovada, evidências rastreáveis, análise de incertezas e conclusões científicas aprovadas.
- **Decisões pendentes:** produtos prioritários, escalas espaciais/temporais de divulgação e extensão das conclusões aplicadas.

## 5. Dependências e prioridades

A sequência principal é **MEQ-02 → MEQ-03 → MEQ-05 (recomendação final) → MEQ-06 → MEQ-07**. A MEQ-03 foi reaberta em 11/11/2026 (`DEC-MEQ-002`); a recomendação final da MEQ-05 aguarda a conclusão dessa reavaliação. A MEQ-04 aproveita resultados já disponíveis e prossegue em paralelo, sendo atualizada para a configuração selecionada quando necessário. A MEQ-01 sustenta a governança das demais frentes; a MEQ-00 está encerrada.

Avançar entre frentes exige verificar **condições relevantes ao próximo passo**, não eliminar toda incerteza do projeto. Identificar um risco não autoriza alterar scripts de `usp-utils`, código MPAS, dados ou simulações sem a aprovação específica exigida.

## 6. Limitações preservadas e classificação de bloqueios

O registro MEQ-00B documenta: preservação **seletiva**, não backup integral; arquivos preservados no **mesmo filesystem** do Swell e sem cópia externa; symlinks históricos nem sempre resolvíveis; ausência de log terminal autoritativo identificado de `CTL/2021`; identidade binária histórica do executável não demonstrada integralmente; e verificações operacionais relatadas pelo agente, **não reauditadas independentemente** nesta missão. Essas limitações devem acompanhar as evidências que afetam, **sem se tornarem bloqueios automáticos**.

Limitações científicas relevantes: somente um mês e um LiDAR por período, P0/novembro de 2021 anormalmente fraco, representatividade das células em LPI, controle de qualidade distinto entre P0 e LPI, diferenças de caixa ERA5 entre pernas de `CTL`, diferenças de decomposição MPI, e vieses de velocidade ainda não explicados completamente. Para o ciclo diurno em P0, o HTML atual ressalta que o horário de máximo pode ser instável em ciclo bimodal: a análise de fase requer cautela. No relatório, distinguir custos medidos de custos reconstruídos.

A MEQ-00 encerrou o problema de **preservar evidências disponíveis**, não demonstrou por si só validade de todas as conclusões científicas. Um item será marcado como **bloqueio** apenas quando houver relação causal documentada com um procedimento ou critério de encerramento, acompanhada de ação corretiva ou decisão requerida.

## 7. Situação, evidências e decisões: regras de governança

Tratar como dimensões **independentes**:

1. **Trabalho executado:** ação realizada, com autor, data, ambiente, configuração e artefato identificáveis.
2. **Resultado auditado:** verificação técnica ou científica registrada, com método, evidências, limitações e indicação de quem auditou; um relato de auditoria do agente deve ser identificado como tal.
3. **Conclusão científica aprovada:** interpretação e alcance explicitamente ratificados pelo pesquisador, ligados às evidências que a sustentam.

Para o andamento das frentes, usar: `planejada`, `em andamento`, `aguardando decisão`, `bloqueada` (com motivo explícito), `concluída` ou `cancelada`. A existência de tabelas, scripts, figuras ou de uma frase de “decisão” em um relatório não equivale à ratificação científica pelo pesquisador.

Registrar decisões aprovadas no histórico versionado com um identificador estável (`DEC-MEQ-NNN`), data, frente, enunciado, responsável pela aprovação, alternativas consideradas, justificativa, fontes exatas (arquivos/commits/PRs), limitações, consequências e condição de revisão. A revisão **não apaga** decisões anteriores: cria entrada que referencia e, se necessário, substitui a precedente.

Mudanças no roadmap devem indicar o que mudou, por quê, quem aprovou e em que commit/PR; nunca pressupor autorização de publicação, modificação do código do MPAS, alteração de `usp-utils`, execução de simulações ou remoção de dados. Antes de operações Git, conferir novamente branches, commits, divergências e estado de trabalho das cópias relevantes; suspender publicação diante de risco novo.

## 8. Próximas ações e decisões científicas

Situação em 12/11/2026 (v1.2); os textos da v1.0 (`fe16f0b`) e da v1.1 (`c2e15cd`) desta seção estão preservados no histórico do repositório.

- **MEQ-03 — reavaliação com SODAR (`DEC-MEQ-002`):** incorporar o SODAR P1 ao pipeline completo, com peso igual ao LiDAR; preparar as entregas registradas na frente (síntese do HTML em três visões e explicitação da resolução temporal); decidir a renomeação de sítios proposta (P0 → ML, SODAR P1 → MS, LPI inalterado); a nova seleção final exige ratificação conjunta do pesquisador e do supervisor. Cada etapa técnica requer autorização própria.
- **Pai da `EXP03`:** conferir `runs/meqbr_05km/EXPERIMENTS.md` no Swell e alinhar roadmap, `config/experiments.yaml` e `README.md` ao resultado (seção 3).
- **MEQ-05:** próxima frente operacional prevista; requer plano concreto e autorização explícita antes de qualquer execução; a recomendação definitiva aguarda a conclusão da reavaliação da MEQ-03.
- **MEQ-04:** síntese do valor agregado a ratificar pelo pesquisador para a configuração que resultar da reavaliação.
- **Revisão editorial do HTML principal para a `DEC-MEQ-001`:** refletir a seleção da EXP03 no template `docs/templates/technical_report_v2.html.j2`, ajustar o validador `scripts/06_report/validate_technical_report.py` e regenerar o relatório, sem recalcular resultados — **atendida em 11/11/2026, PR #9, merge `784e9bc`**.
- **`SCIENTIFIC_NOTES.md`:** registro da decisão da MEQ-03 — **atendido**: entrada datada de 10/11/2026 com a `DEC-MEQ-001`; a entrada de 07/10/2026 está marcada como *superseded*. A v1.2 acrescenta entrada datada da reabertura (`DEC-MEQ-002`).
- **MEQ-06:** não autorizada; depende das condições da própria frente.
