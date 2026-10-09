# Meq-BR — Roadmap científico e operacional

> **Estado:** conteúdo v1.0 e publicação Git de `research/ROADMAP.md` aprovados especificamente pelo pesquisador em 08/10/2026; registro de publicação rastreável no histórico do repositório.
> **Versão aprovada para publicação:** 1.0 — 08/10/2026.
> **Destino autorizado:** `research/ROADMAP.md` na `main` de `daniloceano/mpas-meqbr-experiments`, por branch e PR dedicados.
> **Referência remota consultada na preparação:** `main` em `5833f3e36d1744edf97f0c4f08847db5d1550e98` (08/10/2026). Conferir novamente antes de qualquer publicação.

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

O HTML principal existente cobre desenho experimental, andamento e custo, campos espaciais, estrutura vertical, validação INMET/LiDAR, valor adicionado sobre ERA5, mecanismos, seleção e limitações. Sua existência **não** implica que todas as conclusões tenham sido aprovadas pelo pesquisador. O manifesto da versão examinada (`generated_utc` 2026-10-08T12:52:53Z) registra `working_tree_dirty: true`; isso deve acompanhar a proveniência, sem inferir que os resultados sejam inválidos.

## 3. Situação experimental de referência

| Identificador | Significado científico | Uso na decisão |
| --- | --- | --- |
| `CTL` | Controle: SST inicial do ERA5 mantida fixa; malha `meqbr_05km`. | Comparação de referência. |
| `EXP01` | Atualização diária NOAA OISST v2.1, com tratamento costeiro corrigido; malha `meqbr_05km`. | Melhor candidato entre os experimentos analisados até aqui; **não ratificado definitivamente**. |
| `EXP02` | Herda `EXP01` e altera conjuntamente a malha para `meqbr_05km_buf` **e** a caixa ERA5 de fronteira. | Testa o efeito **incremental do tratamento de fronteira**, não o buffer isolado. |
| `EXP01_BADSST`, `EXP02_BADSST` | Integrações históricas com OISST costeiro contaminado por valor de preenchimento sobre terra. | Preservadas como evidência da falha; **excluídas da seleção científica atual**. |

O registro de análise indica integrações completas nos dois períodos amostrados e auditoria positiva das quatro pernas corrigidas em `results/audit/corrected_runs_validation.json`. Nos testes pareados atuais, `EXP01` é favorecido frente ao `CTL` em **8/8** comparações sítio–período–altura; `EXP02` e `EXP01` não apresentam diferença estatisticamente distinguível em **8/8** comparações, apesar de a malha do `EXP02` possuir aproximadamente **24% mais células**. Esses são **resultados documentados**, ainda sujeitos à avaliação de novas configurações e à ratificação final.

A diferença `EXP01 − CTL` não isola apenas a evolução temporal da SST: a média da SST também muda. Comparações devem usar horas comuns e distinguir melhora estatística, mecanismo físico, representatividade observacional e custo computacional.

## 4. Frentes de trabalho

### MEQ-00 — Auditoria e preservação da proveniência

- **Objetivo:** identificar o estado dos repositórios e ambientes e preservar evidências operacionais relevantes antes de intervenções posteriores.
- **Situação:** **encerrada em 08/10/2026**, com MEQ-00A (auditoria factual) e MEQ-00B (preservação seletiva).
- **Evidências:** `docs/provenance/MEQ-00B-preservation.md`, PR científico [#2](https://github.com/daniloceano/mpas-meqbr-experiments/pull/2), integrado à `main` no commit `5833f3e`.
- **Dependências:** nenhuma para o encerramento já registrado; as etapas futuras devem respeitar os arquivos preservados e sua proveniência.
- **Critério de encerramento:** satisfeitos pela aprovação do registro e integração documental; o relato de testes do agente não constitui nova auditoria independente nesta missão.
- **Decisões pendentes:** nenhuma para reabrir ou alterar a MEQ-00 por padrão; novos riscos concretos podem motivar decisão específica.

### MEQ-01 — Planejamento, governança e roadmap

- **Objetivo:** estabelecer a fonte oficial de planejamento, fronteiras de escopo, sequência das frentes, rastreamento de decisões e condições de avanço.
- **Situação:** **em andamento**. A organização, o conteúdo v1.0 e sua publicação Git específica foram aprovados; a conclusão operacional da MEQ-01A depende da confirmação do merge.
- **Evidências:** repositório científico `main`; instruções permanentes; documentação MEQ-00B; relatório técnico existente.
- **Dependências:** aprovação deste roadmap; nova conferência Git antes de operações de escrita.
- **Critério de encerramento:** conteúdo aprovado explicitamente, arquivo publicado no repositório científico por branch/PR autorizados e conferência documentada de commit, push e merge; alternativamente, bloqueio ou cancelamento registrado.
- **Decisões pendentes:** nenhuma quanto à publicação v1.0 especificamente autorizada; novas versões, operações ou alterações fora do escopo exigem decisão própria.

### MEQ-02 — Exploração de novas configurações MPAS

- **Objetivo:** testar alternativas capazes de superar ou complementar `EXP01` antes da seleção para climatologia.
- **Situação:** **planejada**. Primeira candidata indicada pelo pesquisador: **malha oval já criada em `MPAS-BR/grids`**; localização, características, compatibilidade e identidade dos arquivos ainda precisam de verificação operacional. Outras melhorias físicas ou numéricas serão levantadas e priorizadas em decisão futura, sem assumir testes previamente autorizados.
- **Evidências:** `config/experiments.yaml`, registros das simulações existentes e os resultados de validação disponíveis no HTML principal.
- **Dependências:** verificação do artefato da malha, justificativa científica de cada hipótese, orçamento de execução e **uso comprovado da correção OISST**; toda simulação depende de autorização específica.
- **Critério de encerramento:** conjunto de candidatos **aprovado** pelo pesquisador testado com controles comparáveis; diferenças de malha, fronteiras, resolução, parametrizações e custo documentadas; resultados integrados à evidência para MEQ-03.
- **Decisões pendentes:** quais outras melhorias investigar, quais experimentos executar e critérios de priorização após inspeção da malha oval.

### MEQ-03 — Validação e seleção científica da configuração

- **Objetivo:** integrar evidências existentes e novos candidatos, comparar desempenho, custo e mecanismos e ratificar uma configuração para as integrações climatológicas.
- **Situação:** **parcialmente realizada**. `EXP01` é a melhor escolha entre as configurações **já testadas**, não a escolha final ratificada.
- **Evidências:** `results/tables/pairwise_tests_current.csv`, `selection_summary_current.md`, `results/tables/site_metrics*.csv`, diagnóstico de SST e mecanismos; seções de validação/seleção do HTML principal.
- **Dependências:** MEQ-02 e adequação do protocolo de comparação (horas comuns, LiDARs, representatividade, incerteza e custo); não é obrigatório refazer análises que permaneçam válidas.
- **Critério de encerramento:** comparações justificadas entre as alternativas aprovadas, resultados e limitações incorporados ao HTML principal e **decisão científica final do pesquisador registrada com evidências**.
- **Decisões pendentes:** ratificação da configuração, após a exploração experimental; eventual necessidade de ampliar períodos ou testar robustez de hipóteses.

### MEQ-04 — Valor agregado sobre ERA5

- **Objetivo:** estabelecer onde e em que condições o MPAS oferece ganho confiável sobre ERA5 na observação de vento offshore e na representação espacial do recurso.
- **Situação:** **parcialmente realizada**, com análise extensa já disponível. Os resultados corrigidos de `EXP01` a 100 m mostram Murphy skill positivo nos dois sítios/períodos: aproximadamente **+0,34 em P0/2021** e **+0,30 em LPI/2022**, com intervalos de confiança documentados acima de zero.
- **Evidências:** `results/tables/era5_added_value_current.csv`, `resource_comparison.csv`, `era5_month_representativeness.csv`; seção 6 e demais figuras do relatório HTML principal.
- **Dependências:** interpretação da representatividade e da comparabilidade, e atualização seletiva para a configuração que resultar da MEQ-03. A análise existente não deve ser repetida sem justificativa.
- **Critério de encerramento:** síntese científica aprovada do ganho e de suas limitações **para os períodos e variáveis avaliados**, distinção entre habilidade observacional e estrutura espacial plausível, e atualização do HTML principal quando necessária.
- **Decisões pendentes:** necessidade e extensão de validações complementares antes da extrapolação climatológica.

### MEQ-05 — Benchmark de paralelismo e viabilidade computacional

- **Objetivo:** determinar a faixa eficiente de núcleos/processos para a malha selecionada e estimar o custo de simulações multianuais.
- **Situação:** **planejada**. Os custos históricos documentados não constituem uma curva de saturação confiável, pois usam números diferentes de ranks e incluem tempos estimados/reconstruídos.
- **Evidências:** seção de andamento/custo e limitações do HTML; `results/tables/runtime_metrics.csv`; configurações e registros operacionais preservados.
- **Dependências:** infraestrutura de execução estável, configuração controlada, métricas mensuráveis e, para a recomendação definitiva, malha/configuração escolhida na MEQ-03. Ensaios exploratórios podem começar antes, se aprovados.
- **Método proposto:** série de integrações curtas e comparáveis com números crescentes de núcleos/processos; **um dia simulado é hipótese inicial, não duração já aprovada**. Separar tempo de inicialização do regime representativo, manter constantes condições/saídas/ambiente, repetir medições quando viável e registrar tempo de parede, núcleo-horas, aceleração, eficiência paralela e efeitos de I/O. A curva deve apoiar uma decisão de compromisso entre prazo e consumo de recursos, e não simplesmente maximizar núcleos.
- **Critério de encerramento:** curva de saturação reproduzível, faixa de paralelismo recomendada para a malha definitiva e estimativa fundamentada do custo da MEQ-06.
- **Decisões pendentes:** plano concreto de números de processos, duração/repetições dos testes, recursos máximos e critério de eficiência aceitável.

### MEQ-06 — Integrações climatológicas

- **Objetivo:** executar séries multianuais com a configuração aprovada e proveniência suficiente para avaliação do recurso eólico.
- **Situação:** **planejada; não iniciada neste roadmap**.
- **Evidências futuras:** experimentos, logs, metadados, inventários, verificações de integridade e produtos das integrações.
- **Dependências:** decisão final MEQ-03; avaliação pertinente MEQ-04; dimensionamento MEQ-05; disponibilidade de forçantes/recursos; verificação do código e **correção OISST efetivamente utilizada**. A correção está disponível no PR [#19](https://github.com/CGFD-USP/MPAS-Research/pull/19), branch `fix/oisst-coastal-land-fill` do repositório do modelo na verificação de 08/10/2026. O **merge do PR não é pré-requisito** desta frente: é necessário usar e identificar uma implementação corrigida e validada por commit, não confiar apenas no nome da branch.
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

A sequência principal é **MEQ-02 → MEQ-03 → MEQ-05 (recomendação final) → MEQ-06 → MEQ-07**. A MEQ-04 aproveita resultados já disponíveis e prossegue em paralelo, sendo atualizada para a configuração selecionada quando necessário. A MEQ-01 sustenta a governança das demais frentes; a MEQ-00 está encerrada.

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

A organização das frentes e o **conteúdo inicial v1.0 estão aprovados**, assim como a publicação específica de **somente** `research/ROADMAP.md` no repositório científico, por branch, commit, PR e merge dedicados. A execução dessa autorização exige conferência do estado Git e ausência de conflitos ou riscos novos.

Não ratificar `EXP01` definitivamente antes da MEQ-02/MEQ-03; não iniciar novos experimentos ou benchmarking com base apenas neste roadmap. Preparar, em etapa posterior e com autorização própria, a inspeção da malha oval e propostas de hipóteses testáveis. O PR #19 permanece fora do escopo de governança do roadmap, exceto como referência à implementação OISST corrigida necessária às futuras execuções.
