#!/usr/bin/env python
"""Build a portable static technical report from consolidated analysis outputs.

This stage never opens raw MPAS history. It consumes the small tables and
figures produced by stages 00-05, copies a curated set of media into a report
bundle, and records every included asset in a manifest.

Outputs:
    results/report/index.html
    results/report/report_manifest.json
    results/report/assets/
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr.config import REPO_ROOT, load_config  # noqa: E402


TABLE_SPECS = [
    {
        "id": "inventory",
        "title": "Andamento das integrações",
        "path": "results/tables/experiment_inventory.csv",
        "columns": ["experiment", "period", "mesh", "n_in_window",
                    "complete_pct", "n_gaps", "last_time"],
        "labels": {
            "experiment": "Experimento",
            "period": "Período",
            "mesh": "Malha",
            "n_in_window": "Saídas horárias na janela",
            "complete_pct": "Janela concluída (%)",
            "n_gaps": "Lacunas temporais",
            "last_time": "Último horário disponível",
        },
        "numeric": {"n_in_window": 0, "complete_pct": 1, "n_gaps": 0},
        "description": (
            "Inventário do snapshot congelado para este relatório. A contagem considera "
            "somente a janela científica, depois do spin-up."
        ),
        "notes": [
            "100% significa que todos os horários esperados da janela de análise estão presentes.",
            "Lacuna temporal é um salto maior que uma hora entre duas saídas consecutivas.",
        ],
    },
    {
        "id": "runtime",
        "title": "Custo computacional normalizado",
        "path": "results/tables/runtime_metrics.csv",
        "columns": ["experiment", "period", "status", "quality",
                    "machine_hours_per_sim_hour_single_core",
                    "wall_days_per_model_year_100_cores"],
        "labels": {
            "experiment": "Experimento",
            "period": "Período",
            "status": "Situação da execução",
            "quality": "Origem do tempo",
            "machine_hours_per_sim_hour_single_core": (
                "Tempo de máquina equivalente (h por hora simulada, 1 núcleo)"),
            "wall_days_per_model_year_100_cores": (
                "Tempo estimado para simular 1 ano com 100 núcleos (dias)"),
        },
        "numeric": {
            "machine_hours_per_sim_hour_single_core": 2,
            "wall_days_per_model_year_100_cores": 2,
        },
        "value_maps": {
            "status": {
                "complete": "concluída",
                "complete_estimated": "concluída; tempo reconstruído",
                "running_provisional": "em execução",
            },
            "quality": {
                "measured": "medido",
                "estimated": "estimado",
                "provisional": "provisório",
            },
        },
        "description": (
            "A métrica principal é (tempo real da execução × número de núcleos) / "
            "horas simuladas: ela expressa quantas horas uma máquina de um único "
            "núcleo levaria para produzir uma hora de modelo. Menor é melhor."
        ),
        "notes": [
            "Situação “concluída” indica que a integração terminou; “em execução” usa somente o trecho produzido até o snapshot.",
            "Tempo “medido” vem do wrapper da execução; “estimado” foi reconstruído de logs/arquivos porque o wrapper do CTL não foi preservado.",
            "“Provisório” é uma medição parcial que pode mudar quando a execução terminar.",
            "A estimativa anual é: tempo por hora simulada × 8.760 h / 100 núcleos, convertido para dias.",
            "A projeção para 100 núcleos supõe escalabilidade linear ideal; comunicação MPI, filas e I/O podem aumentar o tempo real.",
        ],
    },
    {
        "id": "inmet",
        "title": "Validação de superfície — estações automáticas INMET",
        "path": "results/tables/inmet_summary.csv",
        "columns": ["experiment", "n_stations", "n_station_periods", "obs_mean",
                    "model_mean", "bias", "rmse", "r", "diurnal_phase_error_h"],
        "labels": {
            "experiment": "Fonte",
            "n_stations": "Estações",
            "n_station_periods": "Pares estação–período",
            "obs_mean": "Vento observado médio (m s⁻¹)",
            "model_mean": "Vento modelado médio (m s⁻¹)",
            "bias": "Viés modelo − observação (m s⁻¹)",
            "rmse": "RMSE (m s⁻¹)",
            "r": "r",
            "diurnal_phase_error_h": "Erro de fase do máximo diário (h)",
        },
        "numeric": {
            "n_stations": 0, "n_station_periods": 0, "obs_mean": 2,
            "model_mean": 2, "bias": 2, "rmse": 2, "r": 2,
            "diurnal_phase_error_h": 2,
        },
        "description": (
            "Média das métricas calculadas separadamente para cada estação e período, "
            "incluindo ERA5 a 10 m como referência; as estações têm o mesmo peso, "
            "independentemente do número de registros."
        ),
        "notes": [
            "Viés positivo significa que o MPAS superestima a velocidade observada.",
            "RMSE mede o erro típico; r mede a associação temporal linear.",
            "Erro de fase = hora local do máximo do ciclo diurno médio modelado − hora local do máximo observado, envolvido no intervalo de −12 a +12 h. Valor negativo/positivo indica máximo antes/depois do observado; menor valor absoluto é melhor.",
            "ERA5 e MPAS são avaliados contra as mesmas observações e nos mesmos horários disponíveis em cada estação.",
            "Negrito indica o melhor valor da coluna: menor valor absoluto para viés e erro de fase, menor RMSE e maior r. Empates são mantidos em negrito.",
        ],
    },
    {
        "id": "lidar",
        "title": "Validação offshore em alturas de rotor — LiDAR",
        "path": "results/tables/experiment_ranking.csv",
        "columns": ["experiment", "period", "site", "height_m", "n", "rmse",
                    "rmse_lo", "rmse_hi", "bias", "r", "wpd_rel_bias_pct"],
        "labels": {
            "experiment": "Fonte",
            "period": "Período",
            "site": "Sítio",
            "height_m": "Altura (m)",
            "n": "Horas pareadas",
            "rmse": "RMSE (m s⁻¹)",
            "rmse_lo": "RMSE — IC95% inferior",
            "rmse_hi": "RMSE — IC95% superior",
            "bias": "Viés modelo − observação (m s⁻¹)",
            "r": "r",
            "wpd_rel_bias_pct": "Viés relativo da densidade de potência eólica (%)",
        },
        "numeric": {
            "height_m": 0, "n": 0, "rmse": 2, "rmse_lo": 2,
            "rmse_hi": 2, "bias": 2, "r": 2, "wpd_rel_bias_pct": 1,
        },
        "description": (
            "Comparação horária entre o vento do MPAS e os LiDARs P0/LPI, na célula "
            "oceânica mais próxima e em níveis verticais coincidentes."
        ),
        "notes": [
            "IC95% é o intervalo de confiança de 95% obtido por bootstrap em blocos de 24 h.",
            "O viés relativo da densidade de potência eólica compara grandezas proporcionais a U³; valor negativo indica subestimativa do recurso.",
            "A densidade de potência eólica é WPD = ½ ρ × média(U³), com ρ = 1,15 kg m⁻³ e U em m s⁻¹; o cubo é calculado antes da média.",
            "ERA5 aparece somente a 100 m, seu nível diagnóstico diretamente comparável ao LiDAR; não é extrapolado para as demais alturas.",
            "Todos os experimentos estão completos e são comparados nas mesmas horas observacionais disponíveis dentro de cada janela científica.",
            "Em cada altura, o negrito indica o melhor entre CTL, EXP01 e EXP02: menor valor absoluto para os vieses, menor RMSE e maior r. As rodadas superadas EXP01_BADSST e EXP02_BADSST aparecem como registro da contaminação de SST e não concorrem; ERA5 permanece como benchmark e também não entra nessa seleção.",
        ],
    },
    {
        "id": "selection",
        "title": "Seleção da configuração — testes pareados",
        "path": "results/tables/pairwise_tests_current.csv",
        "columns": ["period", "site", "height_m", "experiment_a", "experiment_b",
                    "n", "rmse_a", "rmse_b", "delta_mse", "lo", "hi", "better"],
        "labels": {
            "period": "Período",
            "site": "Sítio",
            "height_m": "Altura (m)",
            "experiment_a": "Experimento A",
            "experiment_b": "Experimento B",
            "n": "Horas pareadas",
            "rmse_a": "RMSE de A (m s⁻¹)",
            "rmse_b": "RMSE de B (m s⁻¹)",
            "delta_mse": "MSE(A) − MSE(B) (m² s⁻²)",
            "lo": "IC95% inferior",
            "hi": "IC95% superior",
            "better": "Melhor",
        },
        "numeric": {
            "height_m": 0, "n": 0, "rmse_a": 2, "rmse_b": 2,
            "delta_mse": 2, "lo": 2, "hi": 2,
        },
        "value_maps": {"better": {"no difference": "sem diferença detectável"}},
        "description": (
            "Cada linha testa se um experimento tem erro quadrático menor que o "
            "outro nos mesmos horários, com intervalo de confiança de 95 % por "
            "bootstrap de blocos móveis (blocos de 24 h, 2.000 reamostragens). "
            "Apenas CTL, EXP01 e EXP02 aparecem aqui: as rodadas superadas "
            "EXP01_BADSST/EXP02_BADSST não concorrem pela escolha."
        ),
        "notes": [
            "Valor positivo de MSE(A) − MSE(B) significa que B errou menos; negativo, que A errou menos.",
            "“Sem diferença detectável” significa que o intervalo cruza zero — é um resultado válido, não uma falha do teste.",
            "O pareamento nos mesmos horários cancela a variabilidade sinótica compartilhada e é muito mais sensível que comparar dois RMSE isolados.",
            "A comparação EXP01 × EXP02 é o efeito incremental do tratamento de fronteira, com a atualização de SST já ligada nos dois.",
        ],
    },
    {
        "id": "added_value",
        "title": "Valor adicionado em relação ao ERA5",
        "path": "results/tables/era5_added_value.csv",
        "columns": ["source", "period", "site", "height_m", "n", "rmse",
                    "bias", "r", "rmse_reduction_vs_era5", "skill_vs_era5",
                    "skill_lo", "skill_hi", "significant"],
        "labels": {
            "source": "Fonte",
            "period": "Período",
            "site": "Sítio",
            "height_m": "Altura (m)",
            "n": "Horas pareadas",
            "rmse": "RMSE (m s⁻¹)",
            "bias": "Viés (m s⁻¹)",
            "r": "r",
            "rmse_reduction_vs_era5": "Redução do RMSE frente ao ERA5 (%)",
            "skill_vs_era5": "Redução do MSE frente ao ERA5 (%)",
            "skill_lo": "Redução do MSE — IC95% inferior (%)",
            "skill_hi": "Redução do MSE — IC95% superior (%)",
            "significant": "Diferença estatisticamente detectável",
        },
        "numeric": {
            "height_m": 0, "n": 0, "rmse": 2, "bias": 2, "r": 2,
            "rmse_reduction_vs_era5": 1,
            "skill_vs_era5": 1, "skill_lo": 1, "skill_hi": 1,
        },
        "multiply_100": ["rmse_reduction_vs_era5", "skill_vs_era5",
                         "skill_lo", "skill_hi"],
        "value_maps": {"significant": {True: "sim", False: "não"}},
        "description": (
            "MPAS e ERA5 são comparados com o mesmo LiDAR nos mesmos horários. "
            "Redução de RMSE = 100 × [1 − RMSE(MPAS)/RMSE(ERA5)]; redução de MSE = "
            "100 × [1 − MSE(MPAS)/MSE(ERA5)]."
        ),
        "notes": [
            "Valor positivo significa que o downscaling reduz o MSE do ERA5; valor negativo significa perda de habilidade.",
            "Como MSE = RMSE², a redução do MSE também é 100 × {1 − [RMSE(MPAS)/RMSE(ERA5)]²}.",
            "A diferença só é considerada detectável quando o IC95% não cruza zero.",
            "Nas duas colunas de redução, verde indica melhora frente ao ERA5 e vermelho indica piora; zero é a referência.",
        ],
    },
    {
        "id": "resource",
        "title": "Recurso eólico médio no domínio",
        "path": "results/tables/resource_comparison.csv",
        "columns": ["experiment", "period", "n_hours_model",
                    "domain_mean_speed_mpas", "domain_mean_speed_era5",
                    "domain_mean_speed_diff", "domain_wpd_rel_diff_pct"],
        "labels": {
            "experiment": "Experimento",
            "period": "Período",
            "n_hours_model": "Saídas horárias",
            "domain_mean_speed_mpas": "Vento médio MPAS (m s⁻¹)",
            "domain_mean_speed_era5": "Vento médio ERA5 (m s⁻¹)",
            "domain_mean_speed_diff": "Diferença MPAS − ERA5 (m s⁻¹)",
            "domain_wpd_rel_diff_pct": "Diferença relativa da potência eólica (%)",
        },
        "numeric": {
            "n_hours_model": 0, "domain_mean_speed_mpas": 2,
            "domain_mean_speed_era5": 2, "domain_mean_speed_diff": 2,
            "domain_wpd_rel_diff_pct": 1,
        },
        "description": (
            "Médias espaciais do vento a 100 m e da densidade de potência eólica "
            "sobre a área comum entre o MPAS e o ERA5."
        ),
        "notes": [
            "A densidade de potência é WPD = ½ ρ × média(U³), usando ρ = 1,15 kg m⁻³; pequenas diferenças de vento produzem diferenças percentuais maiores de recurso.",
            "Esta comparação descreve os campos. A validação observacional acima determina se a diferença representa ganho de qualidade.",
        ],
    },
]


GROUP_TITLES = OrderedDict([
    ("design", "Mudanças introduzidas em cada experimento"),
    ("spatial_fields", "Campos espaciais do modelo"),
    ("site_structure", "Estrutura local e ciclo diurno"),
    ("animations", "Evolução temporal dos campos"),
    ("validation_network", "Região e rede observacional"),
    ("observed_data", "Características dos dados nos sítios LiDAR"),
    ("inmet_validation", "Comparação com estações automáticas INMET"),
    ("lidar_validation", "Comparação com os LiDARs offshore"),
    ("added_value", "Comparação com ERA5 e valor adicionado"),
    ("mechanisms", "Mecanismos físicos e seleção da configuração"),
])


def media(group, path, title, caption, *, kind="image"):
    return {"group": group, "path": path, "title": title,
            "caption": caption, "kind": kind}


MEDIA_SPECS = [
    media("design", "figures/report/experimental_design_ctl_mesh.png",
          "CTL: malha de referência",
          "Distribuição do espaçamento horizontal da malha quase uniforme usada no controle; no mapa turbo invertido, vermelho indica menor espaçamento. Pontos escuros mostram a relaxação lateral, círculos/quadrados os LiDARs e triângulos as estações INMET."),
    media("design", "figures/report/experimental_design_exp01_sst.png",
          "EXP01: mudança da condição de superfície",
          "Diagnóstico da anomalia corrigida: diferença da SST média EXP01 − CTL em novembro de 2021. Tons azuis indicam SST mais fria no EXP01, e a faixa costeira extrema é o valor de preenchimento terrestre da OISST entrando em células oceânicas. Em EXP01 essa faixa desaparece: nenhuma célula oceânica fica abaixo de 296 K. Círculo/quadrado mostram P0/LPI e triângulos mostram as estações INMET."),
    media("design", "figures/report/experimental_design_exp02_mesh.png",
          "EXP02: tratamento da fronteira",
          "Malha com aproximadamente 5 km no interior e transição gradual para 32 km junto à fronteira; vermelho indica menor espaçamento. A zona de relaxação escura fica mais distante dos LiDARs e das estações INMET."),
    media("spatial_fields", "figures/exploration/mean_fields_CTL_2021.png",
          "Estado médio do controle — novembro de 2021",
          "Vento médio e densidade de potência a 100 m, constância direcional e amplitude do ciclo diurno. Estes quatro campos descrevem o recurso e a variabilidade resolvidos pelo CTL."),
    media("spatial_fields", "figures/exploration/mean_fields_CTL_2022.png",
          "Estado médio do controle — outubro de 2022",
          "Mesmas grandezas do painel anterior para o segundo período, permitindo separar diferenças de configuração de diferenças meteorológicas entre os meses."),
    media("spatial_fields", "figures/exploration/diff_EXP01_vs_CTL_2021_common.png",
          "Resposta espacial à SST diária corrigida",
          "Diferenças EXP01 − CTL para vento, potência, amplitude diurna e SST, sobre a janela completa comum. Este é o efeito real da atualização diária de SST, livre da contaminação costeira."),
    media("spatial_fields", "figures/exploration/diff_EXP01_vs_EXP01_BADSST_2021_common.png",
          "Tamanho do artefato de SST que foi removido",
          "Diferenças EXP01 − EXP01 nas mesmas horas. Como as duas integrações só diferem no preenchimento terrestre da OISST, este painel mede diretamente quanto a contaminação costeira deslocava o vento, a potência e a SST."),
    media("spatial_fields", "figures/exploration/diff_EXP02_vs_EXP01_2021_common.png",
          "Resposta espacial ao tratamento de fronteira",
          "Diferenças EXP02 − EXP01 na janela científica completa e comum de 2021. O uso de horas idênticas evita confundir a mudança de configuração com mudança do tempo meteorológico."),
    media("site_structure", "figures/exploration/xsection_P0_CTL_2021_composite_15local.png",
          "P0 — CTL, composto às 15 h locais",
          "Seção aproximadamente normal à costa em P0 no experimento de referência, mostrando a estrutura térmica e a circulação média às 15 h locais."),
    media("site_structure", "figures/exploration/xsection_P0_EXP01_2021_composite_15local.png",
          "P0 — EXP01, composto às 15 h locais",
          "A mesma seção e horário para o experimento com SST diária, permitindo comparação direta com CTL e EXP02."),
    media("site_structure", "figures/exploration/xsection_P0_EXP02_2021_composite_15local.png",
          "P0 — EXP02, composto às 15 h locais",
          "A mesma seção e horário para o experimento com malha expandida e zona de relaxação afastada."),
    media("site_structure", "figures/exploration/xsection_LPI_CTL_2022_composite_15local.png",
          "LPI — CTL, composto às 15 h locais",
          "Seção aproximadamente normal à costa em LPI no experimento de referência, para outubro de 2022."),
    media("site_structure", "figures/exploration/xsection_LPI_EXP01_2022_composite_15local.png",
          "LPI — EXP01, composto às 15 h locais",
          "A mesma seção e horário em LPI para o experimento com SST diária."),
    media("site_structure", "figures/exploration/xsection_LPI_EXP02_2022_composite_15local.png",
          "LPI — EXP02, composto às 15 h locais",
          "A mesma seção e horário em LPI para o experimento com malha expandida e fronteira afastada."),
    media("animations", "figures/animations/wind100_CTL_2021_20211101_5d.mp4",
          "Vento a 100 m — CTL, novembro de 2021",
          "Evolução horária do vento a 100 m nos cinco primeiros dias do período, na configuração de referência.", kind="video"),
    media("animations", "figures/animations/wind100_EXP01_2021_20211101_5d.mp4",
          "Vento a 100 m — EXP01, novembro de 2021",
          "Mesma janela do CTL no experimento com SST diária, com escala gráfica idêntica para comparação.", kind="video"),
    media("animations", "figures/animations/wind100_EXP02_2021_20211101_5d.mp4",
          "Vento a 100 m — EXP02, novembro de 2021",
          "Mesma janela do CTL no experimento com malha expandida e fronteira afastada.", kind="video"),
    media("animations", "figures/animations/wind100_CTL_2022_20221001_5d.mp4",
          "Vento a 100 m — CTL, outubro de 2022",
          "Evolução horária do vento a 100 m nos cinco primeiros dias do segundo período, na configuração de referência.", kind="video"),
    media("animations", "figures/animations/wind100_EXP01_2022_20221001_5d.mp4",
          "Vento a 100 m — EXP01, outubro de 2022",
          "Mesma janela de outubro de 2022 no experimento com SST diária.", kind="video"),
    media("animations", "figures/animations/wind100_EXP02_2022_20221001_5d.mp4",
          "Vento a 100 m — EXP02, outubro de 2022",
          "Mesma janela de outubro de 2022 no experimento com malha expandida e fronteira afastada.", kind="video"),
    media("animations", "figures/animations/xsection_P0_CTL_2021_20211101_3d.mp4",
          "Corte vertical em P0 — CTL",
          "Evolução da temperatura e da circulação nos três primeiros dias; setas combinam o vento ao longo da seção e o movimento vertical, e círculos/cruzes indicam o vento perpendicular.", kind="video"),
    media("animations", "figures/animations/xsection_P0_EXP01_2021_20211101_3d.mp4",
          "Corte vertical em P0 — EXP01",
          "Mesmo corte e janela para EXP01, permitindo acompanhar a resposta horária à configuração com SST diária.", kind="video"),
    media("animations", "figures/animations/xsection_LPI_CTL_2022_20221001_3d.mp4",
          "Corte vertical em LPI — CTL",
          "Evolução da estrutura costeira em LPI nos três primeiros dias de outubro de 2022, na configuração de referência.", kind="video"),
    media("animations", "figures/animations/xsection_LPI_EXP01_2022_20221001_3d.mp4",
          "Corte vertical em LPI — EXP01",
          "Mesmo corte e janela para EXP01, mantendo a comparação visual nas mesmas condições meteorológicas.", kind="video"),
    media("validation_network", "figures/report/validation_network.png",
          "Domínios e pontos de validação",
          "À esquerda, os dois domínios em uso: a malha não bufferizada de CTL/EXP01/EXP01 e a malha com buffer de EXP02/EXP02; à direita, os LiDARs P0/LPI e as estações automáticas INMET usadas como eixo primário de validação de superfície."),
    media("validation_network", "figures/report/validation_cells.png",
          "Células usadas na comparação com P0 e LPI",
          "O mapa localiza os LiDARs e amplia as células Voronoi de cada malha. A estrela marca o instrumento; o contorno preto e o x identificam a célula oceânica mais próxima efetivamente usada na validação, com a distância entre o LiDAR e o centro da célula."),
    media("observed_data", "figures/validation/distribution_2021_P0_100m.png",
          "Distribuição observada em P0 a 100 m",
          "Histograma e ajuste de Weibull do LiDAR comparados ao ERA5 e aos experimentos MPAS. A forma da distribuição complementa RMSE e viés ao mostrar quais faixas de vento são mais frequentes."),
    media("observed_data", "figures/validation/distribution_2022_LPI_100m.png",
          "Distribuição observada em LPI a 100 m",
          "Distribuição de velocidade no LPI, no ERA5 e nos experimentos MPAS durante outubro de 2022; diferenças na posição e largura indicam erros de média e variabilidade."),
    media("observed_data", "figures/validation/windrose_2021_P0_100m.png",
          "Regime direcional em P0",
          "Rosas dos ventos observada, ERA5 e MPAS a 100 m. Os setores mostram de onde o vento sopra e com que frequência/intensidade."),
    media("observed_data", "figures/validation/windrose_2022_LPI_100m.png",
          "Regime direcional em LPI",
          "Rosas dos ventos observada, ERA5 e MPAS a 100 m em LPI, permitindo avaliar a direção dominante e a dispersão direcional."),
    media("inmet_validation", "figures/validation/inmet_map.png",
          "Viés do vento de superfície por estação",
          "Cada triângulo representa uma estação automática INMET; a cor mostra o viés médio da fonte − observação. ERA5 a 10 m aparece ao lado dos experimentos MPAS, e P0/LPI são apenas referências geográficas."),
    media("inmet_validation", "figures/validation/inmet_diurnal.png",
          "Ciclo diurno nas estações INMET",
          "Ciclo médio horário em tempo local para observações, ERA5 e MPAS. A comparação avalia amplitude e horário do máximo da circulação costeira de superfície."),
    media("lidar_validation", "figures/validation/profile_2021_P0.png",
          "Perfil vertical médio em P0",
          "Velocidade média observada e simulada entre 50 e 250 m, com ERA5 no nível diretamente comparável de 100 m. O painel de α mostra o expoente de cisalhamento da lei de potência U(z)=U(z₀)(z/z₀)^α: α maior significa aumento mais rápido do vento com a altura."),
    media("lidar_validation", "figures/validation/profile_2022_LPI.png",
          "Perfil vertical médio em LPI",
          "Velocidade média observada e simulada entre 50 e 200 m, com ERA5 em 100 m. O expoente α resume a intensidade do cisalhamento vertical entre os níveis LiDAR inferior e superior."),
    media("lidar_validation", "figures/validation/diurnal_2021_P0.png",
          "Ciclo diurno do vento em P0",
          "Ciclo médio horário em tempo local, por altura, para LiDAR e MPAS; em 100 m o ERA5 também é mostrado nas mesmas horas. Os valores de amplitude e fase resumem quanto cada fonte reproduz a intensidade e o horário do máximo diário observado."),
    media("lidar_validation", "figures/validation/diurnal_2022_LPI.png",
          "Ciclo diurno do vento em LPI",
          "Ciclo médio horário equivalente para LPI. A comparação direta com ERA5 é restrita a 100 m, seu nível diagnóstico compatível, evitando impor uma extrapolação vertical artificial ao benchmark."),
    media("lidar_validation", "figures/validation/timeseries_2021_P0_100m.png",
          "Evolução horária em P0 a 100 m",
          "Série temporal do LiDAR, ERA5 e experimentos MPAS nas mesmas horas, usada para identificar episódios de maior erro e diferenças de fase."),
    media("lidar_validation", "figures/validation/timeseries_2022_LPI_100m.png",
          "Evolução horária em LPI a 100 m",
          "Série temporal equivalente para LPI, incluindo ERA5; mostra simultaneamente viés, variabilidade e sincronismo."),
    media("lidar_validation", "figures/validation/scatter_2021_P0_100m.png",
          "Dispersão modelo–observação em P0",
          "Cada painel compara LiDAR com ERA5 ou MPAS, e cada ponto é uma hora pareada. A linha 1:1 representa concordância perfeita; afastamentos sistemáticos revelam viés e dispersão."),
    media("lidar_validation", "figures/validation/scatter_2022_LPI_100m.png",
          "Dispersão modelo–observação em LPI",
          "Comparação horária a 100 m em LPI para ERA5 e MPAS, com a mesma escala e interpretação da figura de P0."),
    media("lidar_validation", "figures/validation/taylor_2021_P0.png",
          "Síntese estatística em P0",
          "Diagrama de Taylor combinando correlação, desvio-padrão e erro quadrático centrado; pontos mais próximos da referência observada representam melhor desempenho conjunto."),
    media("lidar_validation", "figures/validation/taylor_2022_LPI.png",
          "Síntese estatística em LPI",
          "Diagrama de Taylor do segundo sítio/período, permitindo comparar experimentos e alturas sem reduzir tudo a uma única métrica."),
    media("lidar_validation", "figures/validation/cell_sensitivity.png",
          "Sensibilidade à célula escolhida",
          "RMSE nas cinco células oceânicas MPAS mais próximas aos LiDARs; a linha tracejada mostra o ERA5 nas horas comuns. A variação entre células quantifica a incerteza de representatividade de comparar um instrumento pontual com uma célula de aproximadamente 5 km."),
    media("added_value", "figures/era5/climatological_context.png",
          "Contexto climatológico dos meses simulados",
          "Posição de novembro de 2021 e outubro de 2022 dentro da distribuição climatológica do ERA5. Isso indica se os períodos avaliados são típicos ou extremos."),
    media("added_value", "figures/era5/added_value.png",
          "Ganho ou perda de habilidade frente ao ERA5",
          "Calculado como 100 × [1 − MSE(MPAS)/MSE(ERA5)] usando o mesmo LiDAR e exatamente os mesmos horários. Barras acima de zero indicam que o MPAS remove parte do erro do ERA5; valores negativos indicam perda. As hastes são IC95% por bootstrap em blocos de 24 h; intervalos que cruzam zero não sustentam diferença detectável."),
    media("added_value", "figures/era5/resource_comparison_CTL_2021.png",
          "Estrutura espacial MPAS e ERA5 — 2021",
          "Mapas do recurso eólico a 100 m no CTL e no ERA5, colocados na mesma grade para evidenciar estruturas costeiras adicionadas pelo downscaling."),
    media("added_value", "figures/era5/resource_comparison_CTL_2022.png",
          "Estrutura espacial MPAS e ERA5 — 2022",
          "Comparação equivalente para outubro de 2022; descreve onde o MPAS intensifica ou reduz o recurso em relação à reanálise."),
    media("mechanisms", "figures/selection/sst_forcing_2021.png",
          "SST efetivamente vista pelo modelo",
          "SST no primeiro horário da janela de 2021. As células oceânicas muito frias junto à costa são valores de preenchimento terrestre da OISST e constituem um problema de integridade."),
    media("mechanisms", "figures/selection/attribution_2021_P0.png",
          "Cadeia física da resposta em P0",
          "Diagnóstico conjunto de SST, fluxos de superfície, camada limite e vento para verificar se a mudança de desempenho segue o mecanismo físico esperado."),
    media("mechanisms", "figures/selection/attribution_2022_LPI.png",
          "Cadeia física da resposta em LPI",
          "Mesmo diagnóstico para o segundo sítio/período; permite distinguir uma melhora estatística de uma resposta fisicamente coerente."),
    media("mechanisms", "figures/selection/boundary_influence_2021.png",
          "Influência da distância à fronteira",
          "Magnitude da diferença EXP02 − EXP01 em função da distância da zona de relaxação do EXP01. Organização espacial reforça que o tratamento de fronteira está atuando."),
    media("mechanisms", "figures/selection/ranking.png",
          "Síntese comparativa dos experimentos",
          "Ranking multicritério nas horas comuns das janelas completas. A comparação numérica está consolidada para estas simulações, mas o problema da OISST impede atribuir as diferenças somente à SST ou ao tratamento de fronteira e bloqueia uma recomendação definitiva."),
]


def git_value(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=False,
        capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def format_number(value, decimals: int) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.{decimals}f}".replace(".", ",")


def _best_indices(frame: pd.DataFrame, column: str, *, largest: bool = False,
                  absolute: bool = False) -> set[int]:
    values = pd.to_numeric(frame[column], errors="coerce")
    transformed = values.abs() if absolute else values
    valid = transformed[np.isfinite(transformed)]
    if valid.empty:
        return set()
    target = valid.max() if largest else valid.min()
    return {
        int(index) for index, value in transformed.items()
        if np.isfinite(value) and np.isclose(value, target, rtol=1e-9, atol=1e-12)
    }


def prepare_table_rows(spec: dict, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Sort rows and attach semantic CSS classes before display formatting."""
    if spec["id"] == "lidar":
        order = {"CTL": 0, "EXP01": 1, "EXP01_BADSST": 2,
                 "EXP02": 3, "EXP02_BADSST": 4, "ERA5": 5}
        frame = frame.assign(
            _source_order=frame["experiment"].map(order).fillna(99)
        ).sort_values(
            ["period", "site", "height_m", "_source_order"], kind="stable"
        ).drop(columns="_source_order")
    frame = frame.reset_index(drop=True)

    cell_classes: dict[tuple[int, str], set[str]] = {}
    row_classes: dict[int, set[str]] = {}

    def add_cell(indices: set[int], column: str, css_class: str) -> None:
        for index in indices:
            cell_classes.setdefault((index, column), set()).add(css_class)

    if spec["id"] == "inmet":
        add_cell(_best_indices(frame, "bias", absolute=True), "bias", "best-value")
        add_cell(_best_indices(frame, "rmse"), "rmse", "best-value")
        add_cell(_best_indices(frame, "r", largest=True), "r", "best-value")
        add_cell(_best_indices(frame, "diurnal_phase_error_h", absolute=True),
                 "diurnal_phase_error_h", "best-value")

    if spec["id"] == "lidar":
        group_columns = ["period", "site", "height_m"]
        first_group = True
        for _, group in frame.groupby(group_columns, sort=False, dropna=False):
            if not first_group:
                row_classes.setdefault(int(group.index[0]), set()).add(
                    "height-separator")
            first_group = False
            # Only the current set competes for "best": highlighting a
            # superseded contaminated run would recommend an artefact.
            experiments = group[group["experiment"].isin(
                ["CTL", "EXP01", "EXP02"])]
            add_cell(_best_indices(experiments, "bias", absolute=True),
                     "bias", "best-value")
            add_cell(_best_indices(experiments, "rmse"), "rmse", "best-value")
            add_cell(_best_indices(experiments, "r", largest=True),
                     "r", "best-value")
            add_cell(_best_indices(experiments, "wpd_rel_bias_pct", absolute=True),
                     "wpd_rel_bias_pct", "best-value")

    if spec["id"] == "added_value":
        for column in ["rmse_reduction_vs_era5", "skill_vs_era5"]:
            values = pd.to_numeric(frame[column], errors="coerce")
            for index, value in values.items():
                if not np.isfinite(value) or np.isclose(value, 0.0):
                    continue
                css_class = "metric-improved" if value > 0 else "metric-worsened"
                add_cell({int(index)}, column, css_class)

    return frame, cell_classes, row_classes


def render_html_table(frame: pd.DataFrame, spec: dict,
                      cell_classes: dict, row_classes: dict) -> str:
    labels = spec.get("labels", {})
    headers = "".join(
        f"<th>{html.escape(str(labels.get(column, column)))}</th>"
        for column in frame.columns
    )
    rows = []
    for row_index, (_, row) in enumerate(frame.iterrows()):
        row_css = " ".join(sorted(row_classes.get(row_index, set())))
        row_attr = f' class="{row_css}"' if row_css else ""
        cells = []
        for column in frame.columns:
            css = " ".join(sorted(cell_classes.get((row_index, column), set())))
            cell_attr = f' class="{css}"' if css else ""
            value = row[column]
            shown = "—" if pd.isna(value) else str(value)
            cells.append(f"<td{cell_attr}>{html.escape(shown)}</td>")
        rows.append(f"<tr{row_attr}>{''.join(cells)}</tr>")
    return (
        '<table class="data-table">'
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def read_table(spec: dict) -> dict | None:
    path = REPO_ROOT / spec["path"]
    if not path.exists():
        return None
    df = pd.read_csv(path)
    columns = [column for column in spec["columns"] if column in df.columns]
    df = df[columns].copy()
    df, cell_classes, row_classes = prepare_table_rows(spec, df)
    for column in spec.get("multiply_100", []):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce") * 100.0
    for column, mapping in spec.get("value_maps", {}).items():
        if column in df:
            df[column] = df[column].map(lambda value: mapping.get(value, value))
    for column, decimals in spec.get("numeric", {}).items():
        if column in df:
            numeric = pd.to_numeric(df[column], errors="coerce")
            df[column] = numeric.map(lambda value, d=decimals: format_number(value, d))
    return {
        **spec,
        "n_rows": len(df),
        "html": render_html_table(df, spec, cell_classes, row_classes),
    }


def copy_media(report_dir: Path) -> tuple[dict[str, dict], list[dict]]:
    asset_root = report_dir / "assets"
    if asset_root.exists():
        shutil.rmtree(asset_root)
    groups = OrderedDict()
    manifest = []
    for spec in MEDIA_SPECS:
        source = REPO_ROOT / spec["path"]
        if not source.exists():
            continue
        group = spec["group"]
        target = asset_root / group / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rel = target.relative_to(report_dir).as_posix()
        item = {**spec, "url": rel}
        groups.setdefault(group, {
            "key": group,
            "title": GROUP_TITLES[group],
            "items": [],
        })["items"].append(item)
        manifest.append({
            "source": str(source.relative_to(REPO_ROOT)),
            "bundled_as": rel,
            "bytes": source.stat().st_size,
            "title": spec["title"],
        })
    return groups, manifest


def completeness(inventory: pd.DataFrame) -> tuple[bool, str]:
    if inventory.empty or "complete_pct" not in inventory:
        return True, "Inventário indisponível; trate todos os resultados como provisórios."
    incomplete = inventory[pd.to_numeric(
        inventory["complete_pct"], errors="coerce").fillna(0) < 100]
    if incomplete.empty:
        return False, "Todas as janelas de análise estão completas."
    legs = ", ".join(
        f"{row.experiment}/{row.period} ({float(row.complete_pct):.1f}%)"
        for row in incomplete.itertuples())
    return True, (
        f"Snapshot parcial: {legs}. Conclusões, valor adicionado e ranking "
        "ainda são provisórios."
    )


def report_configuration(cfg) -> tuple[list[dict], list[dict], list[dict]]:
    common = [
        {"item": "Duração de cada integração",
         "value": f"{cfg.common['integration_duration_days']} dias, incluindo spin-up"},
        {"item": "Passo de tempo dinâmico",
         "value": f"{cfg.common['time_step_seconds']} s"},
        {"item": "Saída para análise",
         "value": f"horária ({cfg.common['history_interval_hours']} h)"},
        {"item": "Condições iniciais e laterais",
         "value": f"ERA5; fronteiras atualizadas a cada {cfg.common['lateral_forcing_interval_hours']} h"},
        {"item": "Grade vertical",
         "value": (
             f"{cfg.vertical['n_layers']} camadas / {cfg.vertical['n_interfaces']} interfaces; "
             f"topo em {cfg.vertical['model_top_m'] / 1000:.0f} km; centros em "
             "12,5, 50, 100, 150, 200 e 250 m próximos à superfície"
         )},
        {"item": "Dinâmica e mistura",
         "value": f"{cfg.common['dynamics']}; {cfg.common['horizontal_mixing']}"},
        {"item": "Física atmosférica",
         "value": f"{cfg.common['physics_suite']}: {cfg.common['physics_components']}"},
        {"item": "Superfície terrestre",
         "value": cfg.common["land_surface"]},
        {"item": "Tipo de domínio",
         "value": "área limitada, sem assimilação de dados"},
    ]
    periods = []
    for key, period in cfg.periods.items():
        start = pd.Timestamp(period["integration_start"])
        analysis_start = pd.Timestamp(period["analysis_start"])
        analysis_end = pd.Timestamp(period["analysis_end"])
        periods.append({
            "id": key,
            "integration": f"{start:%d/%m/%Y} – {analysis_end:%d/%m/%Y}",
            "integration_days": int((analysis_end - start).total_seconds() / 86400),
            "spinup": f"{start:%d/%m} – {analysis_start:%d/%m}",
            "spinup_days": int((analysis_start - start).total_seconds() / 86400),
            "analysis": f"{analysis_start:%d/%m} – {analysis_end:%d/%m/%Y}",
            "analysis_days": int((analysis_end - analysis_start).total_seconds() / 86400),
            "site": period["validation_site"],
        })
    descriptions = {
        "CTL": (
            "Referência do estudo: malha quase uniforme de 4,6 km e SST do ERA5 "
            "no instante inicial mantida fixa durante toda a integração."
        ),
        "EXP01": (
            "Mantém a malha e toda a física do CTL, mas passa a aplicar SST diária "
            "NOAA OISST v2.1, com o preenchimento costeiro da OISST corrigido. "
            "É o incremento que testa a condição de superfície."
        ),
        "EXP02": (
            "Mantém a SST diária corrigida do EXP01 e acrescenta o tratamento de "
            "fronteira: malha com buffer 5→32 km e condições ERA5 em uma caixa "
            "mais ampla."
        ),
        "EXP01_BADSST": (
            "Versão superada do EXP01. Foi forçada pelo arquivo de superfície antes "
            "da correção, que levava o valor de preenchimento terrestre da OISST "
            "(273,15 K) para 1.226 células oceânicas costeiras. Mantida apenas como "
            "evidência do problema; não sustenta conclusão alguma."
        ),
        "EXP02_BADSST": (
            "Versão superada do EXP02, herdando a mesma forçante de superfície "
            "contaminada (1.384 células). Mantida apenas como evidência."
        ),
    }
    status_map = {"complete": "concluído", "running": "em execução"}
    images = {
        "CTL": "assets/design/experimental_design_ctl_mesh.png",
        "EXP01": "assets/design/experimental_design_exp01_sst.png",
        "EXP02": "assets/design/experimental_design_exp02_mesh.png",
        "EXP01_BADSST": "assets/design/experimental_design_exp01_sst.png",
        "EXP02_BADSST": "assets/design/experimental_design_exp02_mesh.png",
    }
    experiments = []
    for key, value in cfg.experiments.items():
        mesh_cfg = cfg.meshes[value["mesh"]]
        experiments.append({
            "id": key,
            "description": descriptions.get(key, value.get("delta", "")),
            "mesh": value["mesh"],
            "n_cells": f"{int(mesh_cfg['n_cells']):,}".replace(",", "."),
            "spacing": mesh_cfg["mean_cell_spacing_km"],
            "status": status_map.get(value["status"], value["status"]),
            "mpi_ranks": value["mpi_ranks"],
            "superseded_by": next(
                (k for k, v in cfg.experiments.items() if v.get("supersedes") == key),
                None),
            "supersedes": value.get("supersedes"),
            "figure_url": images.get(key, images["CTL"]),
        })
    return common, periods, experiments


def observation_methods(cfg) -> list[dict]:
    return [
        {
            "site": "P0",
            "instrument": "LiDAR flutuante",
            "period": "novembro de 2021",
            "native": "registros em intervalos de 10 min; cada bin traz disponibilidade por altura",
            "qc": "disponibilidade ≥80% e velocidade entre 0–40 m s⁻¹",
            "heights": "50, 100, 150, 200 e 250 m (250 m = média dos canais 240/260 m)",
        },
        {
            "site": "LPI",
            "instrument": "LiDAR fixo em Porto-Ilha",
            "period": "outubro de 2022",
            "native": (
                "registros em intervalos de 10 min; o arquivo não traz indicador de "
                "disponibilidade nem explicita a estatística interna do instrumento"
            ),
            "qc": "velocidade entre 0–40 m s⁻¹; não foi inventado um limiar ausente",
            "heights": "50, 100, 150 e 200 m",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/report")
    args = parser.parse_args()

    cfg = load_config()
    report_dir = REPO_ROOT / args.output
    report_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = REPO_ROOT / "results/tables/experiment_inventory.csv"
    inventory = pd.read_csv(inventory_path) if inventory_path.exists() else pd.DataFrame()
    provisional, status_text = completeness(inventory)

    tables = {
        table["id"]: table
        for spec in TABLE_SPECS
        if (table := read_table(spec)) is not None
    }
    media_groups, assets = copy_media(report_dir)
    common, periods, experiments = report_configuration(cfg)

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    commit = git_value("rev-parse", "--short", "HEAD")
    dirty = bool(git_value("status", "--porcelain"))
    env = Environment(
        loader=FileSystemLoader(REPO_ROOT / "docs/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("technical_report.html.j2")
    html = template.render(
        generated=generated,
        commit=commit,
        dirty=dirty,
        provisional=provisional,
        status_text=status_text,
        experiments=experiments,
        common_configuration=common,
        periods=periods,
        observation_methods=observation_methods(cfg),
        pairing=cfg.pairing,
        tables=tables,
        media_groups=media_groups,
    )
    output = report_dir / "index.html"
    output.write_text(html, encoding="utf-8")

    manifest = {
        "generated_utc": generated,
        "analysis_commit": commit,
        "working_tree_dirty": dirty,
        "provisional": provisional,
        "tables": [table["path"] for table in tables.values()],
        "assets": assets,
        "builder": "scripts/06_report/build_technical_report.py",
    }
    manifest_path = report_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {output.relative_to(REPO_ROOT)}")
    print(f"-> {manifest_path.relative_to(REPO_ROOT)}")
    print(status_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
