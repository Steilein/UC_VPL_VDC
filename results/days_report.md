# Seleção de dias representativos

Série anual de demanda líquida (configuração estressada, VRE escalado por 1.273 para 50 % de penetração anual).

## Periodicidades dominantes (DFT da demanda líquida)

|   period_h |   amplitude_mw |
|-----------:|---------------:|
|     8784   |         1616.6 |
|       24   |         1372.6 |
|       12   |          661.8 |
|     4392   |          539.1 |
|       24.1 |          397.9 |
|      488   |          397.5 |


## Estatísticas diárias (resumo)

|       |   peak_load_mw |   energy_net_mwh |   vre_surplus_mwh |   max_ramp_1h_mw |   max_ramp_3h_mw |
|:------|---------------:|-----------------:|------------------:|-----------------:|-----------------:|
| count |            366 |              366 |               366 |              366 |              366 |
| mean  |           5940 |            58103 |              3215 |             1390 |             2762 |
| std   |           1358 |            37979 |              6399 |              450 |              764 |
| min   |           4237 |           -27154 |                 0 |              600 |             1340 |
| 25%   |           4926 |            30407 |                 0 |             1069 |             2192 |
| 50%   |           5193 |            59931 |                 0 |             1365 |             2721 |
| 75%   |           7222 |            86465 |              2393 |             1607 |             3177 |
| max   |           9282 |           134460 |             31000 |             3148 |             5777 |


## Dias selecionados (confirmar manualmente em config/base.yaml)

| chave | data | critério | pico (MW) | excedente VRE (MWh) | rampa 3 h (MW) | share VRE dia |
|---|---|---|---|---|---|---|
| spring_wind | 2020-03-12 | maior excedente VRE diário na primavera: 26487 MWh | 4987 | 26487 | 3376 | 115 % |
| summer_peak | 2020-08-26 | pico anual de carga no verão: 9282 MW | 9282 | 0 | 4171 | 33 % |
| solar_ramp | 2020-01-14 | maior rampa de 3 h da demanda líquida (out–fev): 5777 MW | 5349 | 13606 | 5777 | 85 % |
| median | 2020-03-16 | energia de demanda líquida mais próxima da mediana anual (60493 MWh) | 5063 | 0 | 3562 | 41 % |