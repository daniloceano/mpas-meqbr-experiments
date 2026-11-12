# MEQ-03 — Decisão científica de seleção da configuração

**Status:** concluída; EXP03 selecionado para prosseguir às próximas simulações.

> **Nota (11/11/2026):** a seleção foi **reaberta** para reavaliação com o SODAR EOSOLAR P1 — ver [`DEC-MEQ-002`](#registro-de-decisão-dec-meq-002) ao final. O texto abaixo e a `DEC-MEQ-001` são preservados como histórico; até nova decisão ratificada, EXP03 permanece como a seleção registrada, sob reavaliação.

**Decisão (10 de novembro de 2026):** o pesquisador comunicou a decisão conjunta com seu supervisor de adotar **EXP03 (malha oval MEQ-02A)** como melhor candidato para a etapa seguinte. Trata-se da ratificação de uma escolha científica apoiada na evidência disponível, **não** de demonstração de superioridade universal da configuração em todas as condições climatológicas.

## Base da decisão

- **Observação offshore:** EXP03 apresentou o desempenho mais forte no agregado dos experimentos válidos. Frente a EXP01, mostrou redução do erro quadrático detectável em LPI/2022 nas alturas de 50 e 100 m; nos outros seis contrastes principais não houve diferença detectável, o que não demonstra equivalência.
- **Valor agregado:** a 100 m, a habilidade relativa ao ERA5 baseada em MSE foi de aproximadamente +0,39 em P0/2021 e +0,43 em LPI/2022 para EXP03, com intervalos documentados nas tabelas de validação.
- **Alternativas:** EXP01 manteve o mérito de menor domínio/custo e ganho consistente sobre CTL; EXP02 teve desempenho competitivo em P0. EXP04 não demonstrou ganho detectável em relação a EXP01, e o ramo cumulativo EXP05/EXP06 não demonstrou benefício consistente.
- **Geometria e custo:** EXP03 possui 102.968 células versus 76.813 em EXP01 (aproximadamente +34% de células). Esse aumento não equivale automaticamente a +34% de custo real; os históricos utilizaram diferentes números de ranks e não substituem benchmark controlado.

## Limitações preservadas

1. Validação principal baseada em P0/novembro de 2021 e LPI/outubro de 2022, não em uma série observacional multianual.
2. Comparações de erros pareadas por horas comuns, com bootstrap em blocos de 24 h, 2.000 reamostragens e IC95%; múltiplos contrastes exploratórios sem ajuste global de multiplicidade.
3. Sensibilidade relevante à célula oceânica escolhida perto de LPI; a célula mais próxima foi definida sem otimizar pelo desempenho.
4. Diferenças entre domínios, geometria e forçantes não permitem atribuição causal isolada de todo o ganho ao desenho oval.
5. A seleção representa compromisso entre qualidade observacional, coerência física e viabilidade, deliberado pelo pesquisador e supervisor.

## Encerramento e próxima frente

A **MEQ-03 está cientificamente encerrada**, com EXP03 selecionado. Não há autorização implícita para iniciar simulações multianuais, alterar o código-fonte do MPAS ou modificar os dados.

> **Nota (11/11/2026):** o encerramento acima foi revertido pela `DEC-MEQ-002`; a MEQ-03 está em andamento — reavaliação com SODAR.

A próxima frente operacional é **MEQ-05**, com benchmark reprodutível de paralelismo na malha/configuração EXP03, estimativa de custo para as integrações multianuais e verificação de recursos antes da MEQ-06. A MEQ-04 (valor agregado sobre ERA5) mantém seu escopo científico próprio.

O relatório HTML v2 contém as evidências já validadas, mas sua conclusão, escrita antes desta ratificação, ainda pode declarar que nenhuma configuração foi selecionada. Atualizar o texto de decisão no **template fonte** e regenerar o HTML via Swell é um ajuste editorial subsequente; não implica refazer os cálculos.

> **Nota (11/11/2026):** pendência atendida no PR #9 (merge `784e9bc`). O veredito da síntese do HTML v2 passou a registrar a adoção da EXP03 (DEC-MEQ-001) e as ressalvas, o validador exige esse texto, e o relatório foi regenerado no Swell sem recalcular resultados.

## Evidências versionadas

- [Métricas LiDAR](../results/tables/site_metrics.csv)
- [Testes pareados](../results/tables/pairwise_tests_current.csv)
- [Síntese comparativa](../results/tables/selection_summary_current.md)
- [Valor agregado frente ao ERA5](../results/tables/era5_added_value_current.csv)
- [Sensibilidade espacial](../results/tables/cell_sensitivity.csv)
- [Custos históricos](../results/tables/runtime_metrics.csv)
- [Relatório técnico HTML](../results/report/index.html)

**Registro:** decisão humana comunicada em conversa de 10/11/2026; os resultados e suas limitações derivam dos produtos versionados e não de simulações adicionais.

## Registro de decisão `DEC-MEQ-001`

Entrada no formato da seção 7 do [ROADMAP](ROADMAP.md). Resume e remete às seções acima; não as substitui.

- **Identificador:** `DEC-MEQ-001`
- **Data:** 10/11/2026
- **Frente:** MEQ-03 — Validação e seleção científica da configuração
- **Enunciado:** adotar EXP03 (malha oval `meqbr_05km_oval_meq02a`, OISST diária corrigida, caixa ERA5 ampliada) como configuração para as próximas simulações; escolha apoiada na evidência disponível, sem demonstração de superioridade universal.
- **Responsável pela aprovação:** o pesquisador, em decisão conjunta com seu supervisor.
- **Alternativas consideradas:** EXP01, EXP02, EXP04 e o ramo EXP05/EXP06 (ver “Base da decisão”).
- **Justificativa:** ver “Base da decisão”.
- **Fontes:** este documento e as tabelas listadas em “Evidências versionadas”; ratificação no commit `8394fbb`; encerramento da MEQ-03 no roadmap em `085f96c`; reconciliação do roadmap v1.1 no PR #7 (merge `c2e15cd`).
- **Limitações:** as cinco listadas em “Limitações preservadas”.
- **Consequências:** MEQ-03 encerrada; MEQ-05 passa a ser a próxima frente operacional, sobre a configuração EXP03; nenhuma autorização implícita para simulações multianuais, alterações no código do MPAS ou nos dados; o texto de decisão do relatório HTML v2 segue pendente de atualização editorial (atendida em 11/11/2026, PR #9, merge `784e9bc`).
- **Condição de revisão:** nova decisão do pesquisador e do supervisor, registrada em entrada `DEC-MEQ-NNN` que referencie esta, por exemplo diante de custo inviável medido na MEQ-05 ou de evidência observacional adicional contrária. Esta entrada não é apagada. Condição de revisão aprovada pelo pesquisador em 11/11/2026.

## Registro de decisão `DEC-MEQ-002`

Reabertura da seleção registrada na `DEC-MEQ-001`. Entrada no formato da seção 7 do [ROADMAP](ROADMAP.md); a `DEC-MEQ-001` acima não é apagada nem alterada.

- **Identificador:** `DEC-MEQ-002`
- **Data:** 11/11/2026
- **Frente:** MEQ-03 — Validação e seleção científica da configuração
- **Referencia:** `DEC-MEQ-001` (reabre; não substitui enquanto não houver nova seleção ratificada).
- **Enunciado:** reavaliar a seleção da MEQ-03 incluindo o SODAR MFAS/Scintec da estação EOSOLAR P1 (Maranhão; lat −2,7249, lon −42,5752; ~4,1 km do P0; 10/11/2021–09/10/2022; resolução de 10 min; 30–280 m). O SODAR entra no pipeline completo, com peso igual ao LiDAR, mesmo que isso altere a conclusão. A nova seleção final exigirá ratificação conjunta do pesquisador e do supervisor.
- **Responsável pela aprovação:** o pesquisador (responsável), em 11/11/2026. A nova seleção final dependerá de ratificação conjunta com o supervisor.
- **Alternativas consideradas:** não especificadas na comunicação da decisão.
- **Justificativa:** a condição de revisão da `DEC-MEQ-001` prevê nova decisão diante de evidência observacional adicional; o SODAR P1 é uma fonte observacional não utilizada na seleção anterior.
- **Fontes:** decisão comunicada pelo responsável em 11/11/2026; roadmap v1.2 (`research/ROADMAP.md`, MEQ-03) e entrada datada de 11/11/2026 em `SCIENTIFIC_NOTES.md`, publicados pelo PR da branch `docs/meq-03-reopening-sodar`.
- **Limitações:** nenhuma análise com SODAR existe ainda; os resultados da `DEC-MEQ-001` não foram recalculados. Pelas datas informadas, a série do SODAR (10/11/2021–09/10/2022) cobre apenas parte das janelas de análise atuais (01/11–01/12/2021 e 01/10–01/11/2022), o que deve ser verificado na implementação. As cinco limitações da `DEC-MEQ-001` continuam válidas para as evidências existentes.
- **Consequências:** MEQ-03 passa a **em andamento — reavaliação com SODAR (DEC-MEQ-002)**; MEQ-05 passa a depender da conclusão da reavaliação; MEQ-04 será atualizada para a configuração resultante. Entregas da reavaliação, **registradas e não implementadas nesta decisão:** síntese do HTML principal em três visões (LiDAR/SODAR, INMET e geral) e explicitação da resolução temporal das comparações. **Decisão pendente da reavaliação:** renomeação de sítios proposta (P0 → ML, SODAR P1 → MS, LPI inalterado), não aplicada. Nenhuma autorização implícita para simulações, alterações no código do MPAS ou nos dados.
- **Condição de revisão:** encerra-se com nova entrada `DEC-MEQ-NNN` que registre a seleção final ratificada conjuntamente pelo pesquisador e pelo supervisor e referencie esta e a `DEC-MEQ-001`. Esta entrada não é apagada.
