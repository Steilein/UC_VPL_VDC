# Resumo dos resultados — UC day-ahead com VPL e VDC

Cenários resolvidos: **320**. Solver: gurobi. Gap MIP máximo: 1.20e-03. Tempo médio MILP: 51 s.

## 1. Valor marginal e complementaridade (custo total, $)

| day_key     | variation   | axis              |     cost_total_A |   delta_B_A |   delta_C_A |   delta_D_A |   complementarity |   delta_B_A_pct |   delta_C_A_pct |   delta_D_A_pct |
|:------------|:------------|:------------------|-----------------:|------------:|------------:|------------:|------------------:|----------------:|----------------:|----------------:|
| median      | base        | base              |      1.59387e+06 |    -74058.7 |    -25895.8 |   -100587   |             632.8 |            -4.6 |            -1.6 |            -6.3 |
| solar_ramp  | base        | base              |      1.39981e+06 |    -86671.5 |    -26416.4 |   -108264   |           -4823.5 |            -6.2 |            -1.9 |            -7.7 |
| spring_wind | base        | base              | 684722           |    -73442.3 |    -24506.6 |    -98507   |             558.1 |           -10.7 |            -3.6 |           -14.4 |
| summer_peak | base        | base              |      2.77074e+06 |    -72085.9 |    -20281.9 |    -90907.9 |           -1459.8 |            -2.6 |            -0.7 |            -3.3 |
| median      | f02         | dc_flex           |      1.63489e+06 |    -74535.3 |    -12953.5 |    -87298.1 |            -190.6 |            -4.6 |            -0.8 |            -5.3 |
| solar_ramp  | f02         | dc_flex           |      1.43017e+06 |    -89674.4 |    -10401.5 |    -99531.9 |            -544   |            -6.3 |            -0.7 |            -7   |
| spring_wind | f02         | dc_flex           | 709204           |    -74216   |    -11762.7 |    -84895.3 |           -1083.3 |           -10.5 |            -1.7 |           -12   |
| summer_peak | f02         | dc_flex           |      2.82546e+06 |    -75813.5 |    -10118.8 |    -82642.4 |           -3289.9 |            -2.7 |            -0.4 |            -2.9 |
| median      | f08         | dc_flex           |      1.55482e+06 |    -73433.2 |    -45733.9 |   -120733   |            1565.9 |            -4.7 |            -2.9 |            -7.8 |
| solar_ramp  | f08         | dc_flex           |      1.37013e+06 |    -83363.3 |    -35676.3 |   -117445   |           -1594.2 |            -6.1 |            -2.6 |            -8.6 |
| spring_wind | f08         | dc_flex           | 662346           |    -74189.8 |    -37745.6 |   -112330   |             394.8 |           -11.2 |            -5.7 |           -17   |
| summer_peak | f08         | dc_flex           |      2.7168e+06  |    -71635.8 |    -29749.2 |    -96751.2 |           -4633.8 |            -2.6 |            -1.1 |            -3.6 |
| median      | reson       | reserve_from_flex |      1.59387e+06 |    -74080.3 |    -27644.4 |   -102783   |            1058.5 |            -4.6 |            -1.7 |            -6.4 |
| solar_ramp  | reson       | reserve_from_flex |      1.39981e+06 |    -86671.5 |    -28306.9 |   -112081   |           -2897.4 |            -6.2 |            -2   |            -8   |
| spring_wind | reson       | reserve_from_flex | 684722           |    -74193.2 |    -26959.6 |   -103378   |            2225.4 |           -10.8 |            -3.9 |           -15.1 |
| summer_peak | reson       | reserve_from_flex |      2.77074e+06 |    -72089.1 |    -25006.3 |    -96131.8 |            -963.6 |            -2.6 |            -0.9 |            -3.5 |
| median      | dedicated   | vpl_mode          |      1.59387e+06 |    -41150.9 |    -25895.8 |    -73893   |            6846.3 |            -2.6 |            -1.6 |            -4.6 |
| solar_ramp  | dedicated   | vpl_mode          |      1.39981e+06 |    -53184   |    -26416.4 |    -77833.3 |           -1767.2 |            -3.8 |            -1.9 |            -5.6 |
| spring_wind | dedicated   | vpl_mode          | 684722           |    -33986.4 |    -24506.6 |    -61688   |            3194.9 |            -5   |            -3.6 |            -9   |
| summer_peak | dedicated   | vpl_mode          |      2.77074e+06 |    -31501.7 |    -20281.9 |    -49536.3 |           -2247.2 |            -1.1 |            -0.7 |            -1.8 |
| median      | explicit    | vpl_mode          |      1.59387e+06 |    -41776.2 |    -25895.8 |    -74832.1 |            7160.1 |            -2.6 |            -1.6 |            -4.7 |
| solar_ramp  | explicit    | vpl_mode          |      1.39981e+06 |    -53862.5 |    -26416.4 |    -78211   |           -2068   |            -3.8 |            -1.9 |            -5.6 |
| spring_wind | explicit    | vpl_mode          | 684722           |    -48537   |    -24506.6 |    -74752.6 |            1709   |            -7.1 |            -3.6 |           -10.9 |
| summer_peak | explicit    | vpl_mode          |      2.77074e+06 |    -32954.1 |    -20281.9 |    -51151.8 |           -2084.1 |            -1.2 |            -0.7 |            -1.8 |
| median      | vpl100      | vpl_size          |      1.59387e+06 |    -33737.4 |    -25895.8 |    -66638.3 |            7005.1 |            -2.1 |            -1.6 |            -4.2 |
| solar_ramp  | vpl100      | vpl_size          |      1.39981e+06 |    -44758   |    -26416.4 |    -68118.7 |           -3055.7 |            -3.2 |            -1.9 |            -4.9 |
| spring_wind | vpl100      | vpl_size          | 684722           |    -36983.5 |    -24506.6 |    -62825.5 |            1335.4 |            -5.4 |            -3.6 |            -9.2 |
| summer_peak | vpl100      | vpl_size          |      2.77074e+06 |    -36680   |    -20281.9 |    -57175.1 |             213.2 |            -1.3 |            -0.7 |            -2.1 |
| median      | vpl400      | vpl_size          |      1.59387e+06 |   -141456   |    -25895.8 |   -167536   |             183.4 |            -8.9 |            -1.6 |           -10.5 |
| solar_ramp  | vpl400      | vpl_size          |      1.39981e+06 |   -165038   |    -26416.4 |   -180804   |          -10650.7 |           -11.8 |            -1.9 |           -12.9 |
| spring_wind | vpl400      | vpl_size          | 684722           |   -138418   |    -24506.6 |   -163037   |             111.7 |           -20.2 |            -3.6 |           -23.8 |
| summer_peak | vpl400      | vpl_size          |      2.77074e+06 |   -121186   |    -20281.9 |   -124939   |          -16529.3 |            -4.4 |            -0.7 |            -4.5 |
| median      | vpl650      | vpl_size          |      1.59387e+06 |   -195427   |    -25895.8 |   -201391   |          -19931.5 |           -12.3 |            -1.6 |           -12.6 |
| solar_ramp  | vpl650      | vpl_size          |      1.39981e+06 |   -228895   |    -26416.4 |   -242653   |          -12658.1 |           -16.4 |            -1.9 |           -17.3 |
| spring_wind | vpl650      | vpl_size          | 684722           |   -177487   |    -24506.6 |   -184990   |          -17003.6 |           -25.9 |            -3.6 |           -27   |
| summer_peak | vpl650      | vpl_size          |      2.77074e+06 |   -141266   |    -20281.9 |   -145990   |          -15558.4 |            -5.1 |            -0.7 |            -5.3 |
| median      | vre30       | vre_share         |      1.82187e+06 |    -29850.9 |    -21924.6 |    -39794.7 |          -11980.8 |            -1.6 |            -1.2 |            -2.2 |
| solar_ramp  | vre30       | vre_share         |      1.64078e+06 |    -75208.1 |    -22352.4 |    -93398.9 |           -4161.6 |            -4.6 |            -1.4 |            -5.7 |
| spring_wind | vre30       | vre_share         | 977059           |    -78201.5 |    -24476.6 |    -90588.1 |          -12090   |            -8   |            -2.5 |            -9.3 |
| summer_peak | vre30       | vre_share         |      3.35522e+06 |    -44097.2 |     -4077   |    -43206.7 |           -4967.6 |            -1.3 |            -0.1 |            -1.3 |
| median      | vre70       | vre_share         |      1.48411e+06 |    -86820.6 |    -37148.3 |   -120201   |           -3768.1 |            -5.9 |            -2.5 |            -8.1 |
| solar_ramp  | vre70       | vre_share         |      1.29434e+06 |    -86911   |    -28715.7 |   -111341   |           -4285.6 |            -6.7 |            -2.2 |            -8.6 |
| spring_wind | vre70       | vre_share         | 634578           |    -83644.7 |    -26016.6 |   -105847   |           -3814.2 |           -13.2 |            -4.1 |           -16.7 |
| summer_peak | vre70       | vre_share         |      2.36573e+06 |    -69927.1 |    -24282.1 |    -93478.1 |            -731.2 |            -3   |            -1   |            -4   |
| median      | w05         | window_scale      |      1.56046e+06 |    -73866.4 |     -6682.7 |    -80956.4 |             407.4 |            -4.7 |            -0.4 |            -5.2 |
| solar_ramp  | w05         | window_scale      |      1.37521e+06 |    -86053.1 |     -8888.7 |    -90062.2 |           -4879.5 |            -6.3 |            -0.6 |            -6.5 |
| spring_wind | w05         | window_scale      | 664070           |    -73154.4 |     -7477.1 |    -82011.4 |            1380   |           -11   |            -1.1 |           -12.3 |
| summer_peak | w05         | window_scale      |      2.72338e+06 |    -70992.7 |     -8806.3 |    -77614.4 |           -2184.6 |            -2.6 |            -0.3 |            -2.8 |
| median      | w20         | window_scale      |      1.59202e+06 |    -73911.1 |    -32506.4 |   -107195   |             777.6 |            -4.6 |            -2   |            -6.7 |
| solar_ramp  | w20         | window_scale      |      1.39951e+06 |    -86561.3 |    -38898.3 |   -119936   |           -5523.4 |            -6.2 |            -2.8 |            -8.6 |
| spring_wind | w20         | window_scale      | 684360           |    -74026.2 |    -32751.7 |   -106766   |             -12.1 |           -10.8 |            -4.8 |           -15.6 |
| summer_peak | w20         | window_scale      |      2.76868e+06 |    -71364.5 |    -28719.3 |    -99050.5 |           -1033.3 |            -2.6 |            -1   |            -3.6 |

## 2. Métricas operacionais por caso (variação base, média entre dias)

| case   |   cost_total |   curtailment_pct |   startups_total |   pmin_mwh |   frus_mean_mw |   frds_mean_mw |   corridor_congested_hours |   lmp_spread_mean |   vpl_virtual_capacity_mw |   vdc_spatial_shift_pct |   vdc_temporal_shift_pct |   co2_t |
|:-------|-------------:|------------------:|-----------------:|-----------:|---------------:|---------------:|---------------------------:|------------------:|--------------------------:|------------------------:|-------------------------:|--------:|
| A      |  1.61229e+06 |             21.7  |            17.25 |    23600.1 |          55.98 |          38.26 |                       9.5  |              4.08 |                      0    |                  nan    |                   nan    | 43206.4 |
| B      |  1.53572e+06 |             19.55 |            11.75 |    23144.5 |          55.99 |          39.1  |                      12.75 |              5.04 |                     15.63 |                  nan    |                   nan    | 42636.6 |
| C      |  1.58801e+06 |             20.67 |             9.5  |    23175.1 |          58.43 |          38.61 |                      12.25 |              5.1  |                      0    |                   13.07 |                    50.67 | 42595.3 |
| D      |  1.51272e+06 |             18.44 |            10.25 |    22815.6 |          57.88 |          38.7  |                      12.5  |              5.41 |                     16.53 |                   13.2  |                    49.78 | 42024.1 |

## 3. Sensibilidade à penetração VRE (média entre dias)

|                |   cost_total |   curtailment_pct |   startups_total |   corridor_congested_hours |
|:---------------|-------------:|------------------:|-----------------:|---------------------------:|
| ('base', 'A')  |  1.61229e+06 |             21.7  |            17.25 |                       9.5  |
| ('base', 'B')  |  1.53572e+06 |             19.55 |            11.75 |                      12.75 |
| ('base', 'C')  |  1.58801e+06 |             20.67 |             9.5  |                      12.25 |
| ('base', 'D')  |  1.51272e+06 |             18.44 |            10.25 |                      12.5  |
| ('vre30', 'A') |  1.94873e+06 |              5.7  |            17.5  |                       4    |
| ('vre30', 'B') |  1.89189e+06 |              4.48 |            10.25 |                       5.25 |
| ('vre30', 'C') |  1.93052e+06 |              5.35 |            12    |                       3.75 |
| ('vre30', 'D') |  1.88198e+06 |              4.41 |             8.25 |                       5.25 |
| ('vre70', 'A') |  1.44469e+06 |             35.21 |            18    |                      10.75 |
| ('vre70', 'B') |  1.36286e+06 |             33.07 |            13.5  |                      10.75 |
| ('vre70', 'C') |  1.41565e+06 |             34.41 |            13.5  |                       8.75 |
| ('vre70', 'D') |  1.33697e+06 |             32.61 |            11    |                      13.25 |

## 4. Complementaridade por dia e penetração

| day_key     |    base |    vre30 |   vre70 |
|:------------|--------:|---------:|--------:|
| median      |   632.8 | -11980.8 | -3768.1 |
| solar_ramp  | -4823.5 |  -4161.6 | -4285.6 |
| spring_wind |   558.1 | -12090   | -3814.2 |
| summer_peak | -1459.8 |  -4967.6 |  -731.2 |

## 5. Variantes com regra de chaveamento: horas em serviço VTL vs. arbitragem

| scenario                     | vpl_mode   |   vpl_hours_vtl |   vpl_hours_arbitrage |       cost_total |
|:-----------------------------|:-----------|----------------:|----------------------:|-----------------:|
| median__B__dedicated         | dedicated  |              17 |                     0 |      1.55272e+06 |
| median__B__explicit          | explicit   |              10 |                     7 |      1.5521e+06  |
| median__D__dedicated         | dedicated  |              15 |                     0 |      1.51998e+06 |
| median__D__explicit          | explicit   |              10 |                     7 |      1.51904e+06 |
| solar_ramp__B__dedicated     | dedicated  |              21 |                     0 |      1.34663e+06 |
| solar_ramp__B__explicit      | explicit   |               9 |                    14 |      1.34595e+06 |
| solar_ramp__D__dedicated     | dedicated  |              20 |                     0 |      1.32198e+06 |
| solar_ramp__D__explicit      | explicit   |               9 |                    13 |      1.3216e+06  |
| spring_wind__B__dedicated    | dedicated  |              14 |                     0 | 650736           |
| spring_wind__B__explicit     | explicit   |               8 |                    14 | 636185           |
| spring_wind__D__dedicated    | dedicated  |              12 |                     0 | 623034           |
| spring_wind__D__explicit     | explicit   |               9 |                    14 | 609970           |
| summer_peak__B__dedicated    | dedicated  |              16 |                     0 |      2.73924e+06 |
| summer_peak__B__explicit     | explicit   |               7 |                    10 |      2.73779e+06 |
| summer_peak__D__dedicated    | dedicated  |              16 |                     0 |      2.72121e+06 |
| summer_peak__D__explicit     | explicit   |              10 |                    11 |      2.71959e+06 |
| spring_wind__B__vpl400dedic  | dedicated  |              15 |                     0 | 615964           |
| spring_wind__B__vpl400explic | explicit   |              10 |                    14 | 591335           |
| spring_wind__D__vpl400dedic  | dedicated  |              14 |                     0 | 592030           |
| spring_wind__D__vpl400explic | explicit   |              10 |                    14 | 568712           |
| summer_peak__B__vpl400dedic  | dedicated  |              18 |                     0 |      2.71587e+06 |
| summer_peak__B__vpl400explic | explicit   |               7 |                    10 |      2.71153e+06 |
| summer_peak__D__vpl400dedic  | dedicated  |              17 |                     0 |      2.69968e+06 |
| summer_peak__D__vpl400explic | explicit   |               9 |                    11 |      2.69485e+06 |
| solar_ramp__B__vpl400dedic   | dedicated  |              23 |                     0 |      1.30315e+06 |
| solar_ramp__B__vpl400explic  | explicit   |              10 |                    14 |      1.30194e+06 |
| solar_ramp__D__vpl400dedic   | dedicated  |              21 |                     0 |      1.2833e+06  |
| solar_ramp__D__vpl400explic  | explicit   |              10 |                    13 |      1.2823e+06  |
| median__B__vpl400dedic       | dedicated  |              18 |                     0 |      1.50802e+06 |
| median__B__vpl400explic      | explicit   |              10 |                     8 |      1.50515e+06 |
| median__D__vpl400dedic       | dedicated  |              17 |                     0 |      1.48294e+06 |
| median__D__vpl400explic      | explicit   |              10 |                     7 |      1.4812e+06  |
