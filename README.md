# UC day-ahead com Virtual Power Lines e Virtual Data Centers (PyPSA / RTS-GMLC)

Implementação do brief `UC_VPL_VDC_pypsa_brief.md` para o artigo destinado ao
IEEE PES GTD Latin America. O modelo é um *Unit Commitment* (UC) determinístico
day-ahead com rede (fluxo de potência linear), resolvido como MILP em
**PyPSA 1.3 / linopy 0.9**, sobre o **RTS-GMLC modificado** conforme Ferreira &
Unsihuay-Vila (Energies 2026) / tese PPGEE-UFPR: +40 % de carga na Área 2 e
geração VRE equivalente adicionada na Área 3, com o corredor **N_318–N_223**
(ramo `CB-1`, 500 MW) como objeto de estudo.

Dois recursos de flexibilidade são co-otimizados:

| Camada | Modelagem | Desloca |
|---|---|---|
| **VPL** (Virtual Power Line) | par de `StorageUnit` (BESS) em 318 e 223, 85 % ida-e-volta, SOC cíclico | energia **no tempo** dentro do corredor |
| **VDC** (Virtual Data Center) | por workload: `Bus` virtual + `Link` de cada site viável (eficiência 1/PUE, janela via `p_max_pu`, custo de migração) + `Store` com `e_min_pu` saltando para 1 no deadline | carga **no espaço e no tempo** |

Casos: **A** base · **B** +VPL · **C** +VDC · **D** VPL+VDC. A tabela central do
artigo é o valor marginal ΔCusto(B−A), ΔCusto(C−A), ΔCusto(D−A) e a
complementaridade (ΔB + ΔC) − ΔD (benefício conjunto menos soma dos isolados;
positivo = complementares, negativo = substitutos).

---

## 1. Instalação

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt   # pins: pypsa 1.3.0, linopy 0.9.1, highspy 1.15.1, pandas 3.0.5, ...
git clone --depth 1 https://github.com/GridMod/RTS-GMLC data/RTS-GMLC
git clone --depth 1 https://github.com/Falferreira/Phd_Files data/Phd_Files   # dados complementares da tese
```

Solvers: **HiGHS** (instalado com `highspy`) para desenvolvimento e validação;
**Gurobi** para a grade final quando a licença acadêmica estiver ativa
(`pip install gurobipy` e licença acadêmica). Gap MIP: 0,5 % na depuração com
HiGHS e **0,05 % na grade final com Gurobi** (config `solver`); `time_limit = 1800 s`.
A grade HiGHS a 0,5 % foi mantida apenas localmente; o que ficou versionado dela são
as figuras correspondentes, em `figures_highs_gap05/`, e o comparativo de tempos em
`results/bench_solver.txt`.

## 2. Estrutura

```
config/base.yaml        parâmetros do caso base (todas as fases, comentados)
config/scenarios.yaml   grade de sensibilidades (um eixo por vez) e grade reduzida
src/rts_import.py       Fase 1  parser RTS-GMLC -> pypsa.Network
src/layers.py           Fases 2-4  stress_system, scale_vre, limit_corridor, add_vpl, add_vdc
src/constraints.py      extra_functionality: reserva girante, capacidade e rampa agregada
                        por site, SOC inicial do VPL, regra de chaveamento (explícita/dedicada)
src/runner.py           Fase 5  run_case / run_grid (MILP + LP de preços, NetCDF, metrics.csv)
src/metrics.py          Fase 6  métricas, tabela de valor marginal, summary.md
src/plots.py            Fase 7  figuras IEEE (PDF vetorial + PNG)
src/cross_sensitivity.py sensibilidade cruzada VPL x f_d (results/cross_vpl_fd.md, fig8)
src/extra_runs.py       decomposição do VPL, dias mensais, condições iniciais, baseline,
                        migração, SOC inicial, as três leituras da VPL a 400 MW
src/report_pt.py        tabelas e números do relatório em português (docs/relatorio/)
src/select_days.py      seleção dos dias representativos (DFT + rampas da demanda líquida)
src/validate.py         critérios de aceite F1 (rede original) e F2 (saturação do corredor)
src/common.py           utilidades (config, solver options)
tests/test_model.py     testes mínimos (parser/lpf, escalonamento, VDC, VPL explícito)
results/                metrics.csv, summary.md, relatórios F1/F2/dias (os NetCDF por
                        cenário não são versionados; regere com os alvos do Makefile)
figures/                fig1..fig9 (.pdf e .png); figures/en/ = versão em inglês para o artigo
paper/main.tex          artigo IEEE (GTD LA) com resultados da grade Gurobi
```

## 3. Reprodução (Makefile)

```bash
make validate                  # F1: results/base_validation.nc + results/F1_validation.md
make days                      # results/days_report.md (confirmar em config/base.yaml)
make corridor                  # F2: caso A nos 4 dias + results/F2_corridor.md
make grid SOLVER=highs QUICK=1 # grade reduzida (2 dias x 4 casos x eixo VRE)
make grid SOLVER=gurobi        # grade completa (4 dias x 4 casos x 7 eixos)
make cross SOLVER=gurobi       # sensibilidade cruzada VPL x f_d (16 casos D extras, fig8)
make extra SOLVER=gurobi       # decomposição do VPL, dias mensais, condições iniciais, baseline, migração
make leituras SOLVER=gurobi    # VPL de 400 MW nas três leituras (emergente/explícita/dedicada)
make relatorio                 # relatório em português: tabelas, números e PDF (docs/relatorio/)
make metrics                   # recalcula metrics.csv e summary.md a partir dos .nc
make figures                   # figures/fig1..fig9 (PLOTS_LANG=en python src/plots.py -> figures/en/)
make test                      # pytest
```

Um caso isolado: `python src/runner.py --day spring_wind --case D --solver highs`.
Assinatura programática (brief §8):

```python
run_case(day, vre_share, layers, vpl_mwh, dc_flex, solver, reserve_from_flex) -> Path
```

## 4. Decisões de modelagem (resumo; detalhes nos docstrings)

**Importação (F1).** Linhas em ohms a partir do p.u. (100 MVA): `Z·v_nom²/100`;
transformadores (Tr Ratio ≠ 0 ou tensões distintas) como `Transformer` com x em
p.u. sobre `s_nom`; elo CC como `Link` bidirecional; linhas CA nunca viram
`Link`. Térmicas `committable` com custo marginal linear no ponto de 80 % de
PMax, partida a frio, nuclear must-run (168 h, p_min 0,9). Séries DAY_AHEAD já
em MW (`p_max_pu = série/PMax`; a coluna *Scaling Factor* é ignorada). Hidro com
despacho fixo (PMin = PMax no RTS); CSP como disponibilidade direta;
313_STORAGE_1 como `StorageUnit`. Condição inicial: unidades com
`min_up_time ≥ 8 h` iniciam ligadas (p_init no ponto médio) e as demais
desligadas, evitando partidas artificiais na hora 0. Validado: erro de
balanço nodal no `lpf` de 1e-12 MW e fluxos idênticos aos do UC.

**Estresse (F2).** Carga da Área 2 × 1,40; acréscimo de 1 140 MW de VRE
(70 % eólica / 30 % PV) na Área 3. A alocação padrão usa os **nós candidatos da
tese** (eólica em 314/316/319, PV em 320 — anel de 230 kV que alimenta 318).
A alternativa proporcional ao VRE existente concentra o acréscimo em 317 e
congestiona a linha interna C29 antes do corredor (documentado em
`results/F2_corridor.md`). `limit_corridor` permanece só como fallback.

**Penetração VRE.** `scale_vre` escala `p_nom` por fator único. Base padrão
**anual** (parque idêntico em todos os dias; penetração = energia disponível
anual / carga anual, como na tese). A base **diária** (leitura literal do brief)
está disponível (`vre.scaling_basis: day`), mas reduz o parque a 55 % nos dias
ventosos e impede a saturação do corredor.

**VPL.** Três leituras, selecionadas por `vpl.mode`:

- *emergente* (padrão): sem acoplamento entre os dois terminais; o
  comportamento de linha virtual, se houver, emerge da localização e dos preços;
- *explícita* (`explicit`): binária `z_t` de sentido do fluxo (big-M) e binária
  `w_t` de modo dos BESS ligada a `sigma_t` (P90/P30 da demanda líquida do dia);
  horas intermediárias livres para arbitragem, como no *revenue stacking* da
  versão inter-área (cap. 5 da tese);
- *dedicada* (`dedicated`): a mesma regra aplicada nas 24 h, sem hora livre.
  É a leitura estrita da seção 4.2.3 da tese, em que o armazenamento alocado a
  uma VTL emula transferências exclusivamente. Reproduzível com
  `make leituras` (VPL de 400 MW nas três leituras).

**VDC.** Três sites (118, 218, 318; 200 MW; PUE 1,3; f_d = 0,5). Energia
flexível diária = `u·f_d·C_d·24` com `u = 0,7` (`flex_utilization`): com u = 1
a carga flexível teria de operar a plena capacidade 24 h e não haveria
flexibilidade. Nos casos sem VDC (A, B) os DCs entram como carga plana com a
**mesma energia**, de modo que ΔCusto isola o valor da flexibilidade. Workloads
determinísticos por seed, com verificação de factibilidade EDF por site.

**Reserva girante.** `Σ(status·Pmax − p) ≥ 0,03·carga + 0,05·VRE_disponível`;
`reserve.from_flex` inclui VDC/VPL como provedores (sensibilidade).

**Preços.** Após o MILP, todas as binárias são fixadas e o LP é re-resolvido
para obter LMPs e multiplicadores (formação de preço com commitment fixo).

## 5. Resultados

* `results/F1_validation.md`, `results/F2_corridor.md`, `results/days_report.md`
* `results/metrics.csv` (uma linha por cenário) e `results/summary.md`
  (tabelas de valor marginal e complementaridade prontas para o artigo)
* `figures/fig1_map … fig7_complementarity` (PDF vetorial, 3,5 in, 8 pt)
* `results/cross_vpl_fd.md` e `figures/fig8_cross_vpl_fd` (sensibilidade cruzada VPL × f_d)

## 6. Fora de escopo (brief §12)

UC estocástico/robusto, expansão de transmissão, rede CA não linear, rede de
dados/latência dos data centers, redispacho intradiário.

## 7. Reprodução dos resultados do artigo

| Item do artigo | Comando | Arquivo gerado |
|---|---|---|
| Tabela I (casos A–D, dia de primavera) e Tabela II (interação × penetração) | `make grid SOLVER=gurobi` e `make metrics` | `results/summary.md` (seções 1–4) |
| Decomposição do VPL, baseline *native*, 12 dias mensais | `make extra SOLVER=gurobi` | `results/extra_runs.md` |
| Fig. 1 (corredor e SOC) e demais figuras | `make figures` (`PLOTS_LANG=en` para o artigo) | `figures/`, `figures/en/` |
| Fig. 2 (superfície VPL × f_d) | `make cross SOLVER=gurobi` | `results/cross_vpl_fd.md`, `figures/en/fig8_cross_vpl_fd.pdf` |
| Verificações F1/F2 e seleção de dias | `make validate`, `make corridor`, `make days` | `results/F1_validation.md`, `F2_corridor.md`, `days_report.md` |

Sem licença Gurobi, use `SOLVER=highs`: o pipeline roda igual, mas com gap de 0,5 %
a métrica de interação fica dentro do ruído do solver (ver §V do artigo). A grade
completa leva ~3 h com Gurobi em 12 núcleos; `make grid SOLVER=highs QUICK=1` valida
a instalação em ~15 min e `make test` em ~3 min. As redes resolvidas (`results/*.nc`)
não são versionadas; estão disponíveis como anexo de release.

## 8. Licença e citação

Código sob licença MIT (`LICENSE`). Os dados do RTS-GMLC e do Phd_Files não são
redistribuídos e seguem as licenças de origem. Para citar, use `CITATION.cff`
(artigo submetido ao IEEE PES GTD Latin America 2026).
