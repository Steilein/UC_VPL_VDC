# F1 — Validação da importação do RTS-GMLC (rede original)

Dia: **2020-08-26** (24 snapshots horários). Solver: highs, gap 2.21e-04, tempo MILP 38.9 s (+5.3 s para o LP de preços).

## Critério de aceite
* `n.optimize(solver_name="highs")` convergiu: **optimal**.
* Custo total do dia: **2,298,579 $** (combustível 2,301,604; partidas 466; 9 partidas).
* Carga do dia: 145,651 MWh; custo médio 15.8 $/MWh; LMP médio 24.7 $/MWh (mín -0.1, máx 48.3).
* Curtailment VRE: 1,052 MWh (2.9 % do disponível).
* Erro máximo de balanço nodal no `lpf` (12 h): **1.62e-12 MW**; diferença máxima entre fluxos do `lpf` e do UC: **0.000 MW** (confirma a modelagem dos transformadores como `Transformer` com x em p.u. sobre s_nom).

## Despacho por combustível

| fuel    |   MWh |   share_% |
|:--------|------:|----------:|
| Coal    | 44153 |      30.3 |
| Hydro   | 12418 |       8.5 |
| NG      | 44514 |      30.6 |
| Nuclear |  9592 |       6.6 |
| Oil     |   104 |       0.1 |
| Solar   | 16430 |      11.3 |
| Wind    | 18473 |      12.7 |

## Fluxos nas interligações entre áreas

| name   | areas   |   p0_mean_MW |   p0_max_MW |   s_nom_MW |
|:-------|:--------|-------------:|------------:|-----------:|
| AB1    | 1→2     |           86 |         159 |        175 |
| AB2    | 1→2     |           55 |         186 |        500 |
| AB3    | 1→2     |          169 |         341 |        500 |
| CA-1   | 3→1     |          -74 |         267 |        500 |
| CB-1   | 3→2     |          170 |         351 |        500 |

## Ramos mais carregados (|p0|máx / s_nom)

| name   |   loading |
|:-------|----------:|
| C6     |     1     |
| A27    |     0.955 |
| C10    |     0.94  |
| AB1    |     0.908 |
| B12-1  |     0.899 |
| C29    |     0.856 |
| C2     |     0.816 |
| A34    |     0.808 |

## Parâmetros térmicos derivados do gen.csv

| carrier   |   n_units |   p_nom_mw |   marginal_cost_mean |   start_up_cost_mean |   min_up_time_mean |   co2_t_per_mwh_mean |
|:----------|----------:|-----------:|---------------------:|---------------------:|-------------------:|---------------------:|
| Coal      |        16 |       2317 |                22.55 |             19449.8  |                 10 |                 1.02 |
| Gas CC    |        10 |       3550 |                28.28 |             28046.7  |                  8 |                 0.39 |
| Gas CT    |        27 |       1485 |                41.61 |              5665.23 |                  2 |                 0.57 |
| Nuclear   |         1 |        400 |                 8.1  |             63999.8  |                168 |                 0    |
| Oil CT    |        12 |        240 |               118.29 |                51.75 |                  1 |                 0.83 |
| Oil ST    |         7 |         84 |               129.3  |               703.76 |                  4 |                 0.96 |

## Comparação de ordem de grandeza com a literatura do RTS-GMLC
O RTS-GMLC (Barrows et al., IEEE TPWRS 2020) tem 8,55 GW de carga de pico e um parque em que carvão, ciclo combinado a gás e nuclear formam a base do despacho, com eólica (2,5 GW) e solar (~2,9 GW entre PV, RTPV e CSP) fornecendo a maior parte da energia renovável. O mix acima (nuclear must-run, carvão e CC como base, CT/óleo marginais, VRE com curtailment baixo no sistema original) e os LMPs na faixa de 10–60 $/MWh são coerentes com os resultados publicados de PCM para este sistema. Os custos marginais derivados (nuclear ≈ 8, carvão ≈ 25–30, CC ≈ 25–35, CT ≈ 45–55, óleo ≈ 110–150 $/MWh) reproduzem a ordem de mérito documentada no repositório.

## Decisões de modelagem registradas
* Linhas: R/X em p.u. (100 MVA) → ohms via `Z·v_nom²/100`; `s_nom` = *Cont Rating*.
* Transformadores (Tr Ratio ≠ 0 ou tensões distintas): `Transformer` com x em p.u. sobre `s_nom` (`X·s_nom/100`), `tap_ratio` do CSV; C35 (r = 0) recebeu piso numérico.
* Elo CC DC1 (113–316): `Link` bidirecional de 100 MW.
* Séries DAY_AHEAD já em MW: `p_max_pu = série/PMax`; hidro com despacho fixo (PMin = PMax no RTS); CSP como disponibilidade direta (armazenamento térmico desprezado); 313_STORAGE_1 como `StorageUnit`.
* Térmicas: custo marginal linear no ponto de 80 % de PMax; partida a frio; nuclear must-run; unidades com min_up ≥ 8 h iniciam ligadas (p_init no ponto médio da faixa).