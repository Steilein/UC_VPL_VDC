# UC Day-Ahead com Virtual Power Lines e Virtual Data Centers — Brief de Implementação (PyPSA / RTS-GMLC)

Artigo alvo: IEEE PES GTD Latin America. Este documento é a especificação para o Claude Code construir o modelo, o runner de cenários e a extração de métricas. Siga a ordem das fases; cada fase tem critério de aceite. Não avance sem cumprir o critério.

---

## 0. Contexto e tese do artigo

Sistema termoelétrico com alta penetração de geração renovável variável (VRE). Dois recursos de flexibilidade co-otimizados dentro de um Unit Commitment (UC) com rede:

- **Virtual Power Line (VPL):** par de BESS nos dois terminais de um corredor de transmissão congestionado. Carrega a montante quando o corredor satura, descarrega a jusante no pico. Desloca **energia no tempo** dentro de um corredor.
- **Virtual Data Center (VDC):** carga computacional com janela de execução e conjunto de sites viáveis. Desloca **carga no espaço e no tempo**.

Tese: ambos atacam o mesmo problema (congestionamento + curtailment + ciclagem térmica) por caminhos opostos; o artigo quantifica valor marginal de cada um e a complementaridade/substituibilidade entre eles.

Decisões já tomadas:
- Sistema teste: **RTS-GMLC modificado conforme Ferreira & Unsihuay-Vila (Energies 2026) / tese PPGEE-UFPR**: +40% de carga na Área 2, geração equivalente adicionada na Área 3; corredor VPL = tronco **N_318–N_223 (Área 3 → Área 2)**. Dados complementares (custos, rampas por tecnologia, candidatos) em `https://github.com/Falferreira/Phd_Files`.
- Incerteza VRE: **determinístico + análise de sensibilidade** (não implementar estocástico)
- Stack: **Python + PyPSA (≥ 0.30, backend linopy)**
- Solver: **HiGHS** para desenvolvimento/validação; **Gurobi** para a grade final de resultados (licença acadêmica). Solver parametrizado no runner.

---

## 1. Ambiente

```bash
python -m venv .venv && source .venv/bin/activate
pip install pypsa linopy highspy pandas numpy matplotlib pyyaml
# opcional, quando a licença estiver ativa:
pip install gurobipy
git clone https://github.com/GridMod/RTS-GMLC data/RTS-GMLC
```

Verificar versões e registrar em `requirements.txt` com pins. PyPSA deve usar `n.optimize(...)` (linopy), não `n.lopf`.

Estrutura do repositório:

```
uc_vpl_vdc/
  data/RTS-GMLC/              # clone do repositório (não versionar)
  config/
    base.yaml                 # parâmetros do caso base
    scenarios.yaml            # grade de sensibilidades
  src/
    rts_import.py             # parser RTS-GMLC -> pypsa.Network
    layers.py                 # add_vpl(), add_vdc(), scale_vre(), limit_corridor()
    constraints.py            # extra_functionality (reserva, capacidade de site)
    runner.py                 # constrói cenários, resolve, salva resultados
    metrics.py                # pós-processamento
    plots.py
  results/                    # NetCDF por cenário + CSV de métricas
  notebooks/                  # exploração apenas
  tests/
```

---

## 2. Fase 1 — Importar RTS-GMLC para PyPSA

Fonte: `data/RTS-GMLC/RTS_Data/SourceData/` (`bus.csv`, `branch.csv`, `gen.csv`, `timeseries_pointers.csv`) e `timeseries_data_files/` (usar sempre **DAY_AHEAD**, horário; ignorar REAL_TIME). **Confirmar nomes exatos das colunas lendo os CSVs antes de codar** — não assumir.

### 2.1 Barras
- `Bus`: `v_nom` = BaseKV, `carrier="AC"`, atributos extras `area`, `zone`, `x=lng`, `y=lat` (para plots).

### 2.2 Ramos
- Linhas: `Line` com `r`, `x` (o CSV está em p.u. base 100 MVA — converter para ohms com `v_nom`), `s_nom` = *Cont Rating* (MW).
- Transformadores (Tr Ratio ≠ 0 ou ramos entre níveis de tensão diferentes): `Transformer` com `s_nom`, `x` em p.u. sobre `s_nom`, ou alternativamente `Line` com impedância ajustada. Registrar a escolha.
- Ramos DC (`dc_branch.csv`): `Link` bidirecional (`p_min_pu=-1`).
- Manter o fluxo de potência linear nativo do PyPSA (formulação KVL/ciclos). **Nunca substituir linhas AC por `Link`** — perde a física do congestionamento.

### 2.3 Geradores térmicos (committable)
Para cada unidade com combustível térmico (Coal, Oil, NG, Nuclear):
- `committable=True`
- `p_nom` = PMax; `p_min_pu` = PMin/PMax
- `min_up_time`, `min_down_time` (horas, inteiros)
- `ramp_limit_up = ramp_limit_down` = (Ramp Rate MW/min × 60) / PMax, limitado a 1.0
- `ramp_limit_start_up = ramp_limit_shut_down = p_min_pu`
- `start_up_cost`: usar o custo de partida a frio (Start Heat Cold × Fuel Price + custos fixos se houver). Documentar. Se houver tempo, implementar warm/cold via unidades-espelho é opcional e **não prioritário**.
- `shut_down_cost` = 0 (ou pequeno, para evitar degenerescência)
- `marginal_cost`: linearizar a curva de heat-rate (colunas HR_avg_0 / HR_incr_*) em um único custo médio $/MWh no ponto de ~80% de PMax, × Fuel Price. Manter linear; não usar `marginal_cost_quadratic` no MILP.
- Nuclear: `min_up_time = min_down_time = 168` e `p_min_pu ≥ 0.9` → efetivamente must-run.
- Emissões: guardar fator CO₂ (lbs/MMBtu → tCO₂/MWh usando heat-rate) como coluna extra para pós-processamento.

### 2.4 VRE, hidro, síncrono
- WIND, PV, RTPV, CSP: `Generator` com `p_max_pu` série normalizada (série DA / PMax), `marginal_cost = -0.1` (ver §7, desempate de curtailment), `p_nom_extendable=False`.
- Hydro: `Generator` com `p_max_pu` série (simplificação aceitável para day-ahead determinístico). Documentar.
- Sync_Cond / storage do RTS: ignorar ou modelar como `StorageUnit` se existir.

### 2.5 Carga
- Séries de carga DA são por **área**; distribuir para as barras proporcionalmente a `MW Load` de `bus.csv` dentro de cada área. Criar um `Load` por barra.

### 2.6 Snapshots
- Selecionar dias via config. Um dia = 24 snapshots horários. Não resolver o ano.

**Critério de aceite F1:** `n.optimize(solver_name="highs")` para um dia converge; custo total, despacho por combustível e fluxos inter-área plausíveis; comparar ordem de grandeza com resultados publicados do RTS-GMLC (repositório / NREL). Salvar `results/base_validation.nc` e um relatório curto em `results/F1_validation.md`.

---

## 3. Fase 2 — Configuração estressada e escalonamento VRE

### 3.1 `stress_system(n)` — replicar a configuração da tese/Energies 2026
- Multiplicar por 1,40 todas as `Load` da **Área 2**.
- Adicionar na **Área 3** capacidade de geração igual ao acréscimo de pico de carga da Área 2. Alocar como VRE (eólica/solar, `p_max_pu` dos perfis existentes da área), nas barras que já têm VRE. Registrar MW adicionados por barra.
- Corredor VPL fixo: ramo(s) entre **N_318 e N_223**. Confirmar o UID em `branch.csv`; se houver circuitos paralelos, tratar o conjunto como corredor (métricas sobre a soma dos fluxos).
- Não há mais etapa de "identificar corredor"; `limit_corridor` fica disponível só como fallback documentado.

### 3.2 `scale_vre(n, target_share)`
- Métrica de penetração: Σ energia VRE **disponível** (p_max_pu × p_nom) / Σ carga, no conjunto de snapshots do caso, já com a configuração estressada aplicada.
- Escalar `p_nom` de WIND/PV/RTPV/CSP (incluindo a capacidade adicionada na Área 3) por fator único até 30 / 50 / 70 %. Registrar fatores.

**Critério de aceite F2:** no caso base 50% VRE, corredor N_318–N_223 saturado (|p0| ≥ 0,98·s_nom) em ≥ 6 h/dia em pelo menos 2 dos dias representativos e spread de LMP visível entre as barras 318 e 223. Se não saturar, aumentar a proporção VRE do acréscimo da Área 3 antes de recorrer a `limit_corridor`.

---

## 4. Fase 3 — Camada VPL: `add_vpl(n, corridor, p_nom, hours)`

- Dois `StorageUnit`, em **318** (montante) e **223** (jusante):
  - `p_nom` (MW) e `max_hours` (2–4 h) via config; sensibilidade 100/200/400/**650** MW (650 MW / 3.800 MWh é o dimensionamento do planejamento da tese — limite superior)
  - `efficiency_store = efficiency_dispatch = sqrt(0.85)` (round-trip 85%, mesmo valor da tese)
  - `cyclic_state_of_charge = True`
  - `marginal_cost` pequeno (ex.: 2 $/MWh) na descarga, representando degradação
  - `carrier = "VPL"`
- **Formulação padrão (emergente):** sem acoplamento explícito entre os dois BESS; o comportamento virtual emerge da localização e do spread de LMP.
- **Variante explícita (flag `vpl_mode: explicit`):** regra de chaveamento da tese (Tabela 4.3/5.2): estado de cada BESS fixado pelo sentido do fluxo no corredor e pelo estágio de demanda líquida (alto/baixo uso da rede). Implementar em `constraints.py`:
  - `sigma_t` parâmetro binário por hora: 1 se demanda líquida do sistema ≥ percentil 90 da curva de duração (alto uso), 0 se ≤ percentil 30 (baixo uso); horas intermediárias sem restrição (BESS livre para arbitragem — coerente com o *revenue stacking* da tese).
  - Binária `z_t` de sentido de fluxo em N_318→223 com big-M: `f_t ≤ M·z_t`, `f_t ≥ −M·(1−z_t)`.
  - Alto uso e fluxo a jusante (`sigma_t=1, z_t=1`): montante só carrega, jusante só descarrega. Baixo uso (`sigma_t=0`): inverso. Linearizar com `p_ch ≤ P·(1−w)`, `p_dis ≤ P·w` e `w` ligado a `z_t`/`sigma_t`.
  - Métrica adicional: horas em serviço VTL vs. horas em arbitragem.
- Métrica pós-processada: **capacidade virtual** = descarga do BESS a jusante nas horas em que o corredor está saturado (MW médio e MWh).

---

## 5. Fase 4 — Camada VDC: `add_vdc(n, sites, workloads)`

Modelagem nativa PyPSA, sem variáveis custom.

### 5.1 Sites
- Um site por área (3 sites), barras escolhidas em centros de carga. Config: `C_d` (MW elétrico total, 100–300), `PUE_d` (1,2–1,4), fração flexível `f_d` (base 0,5).
- Carga inflexível: `Load` na barra do site com perfil plano `(1 − f_d) · C_d`.

### 5.2 Workloads
Dois tipos, cada instância *j* com `E_j` (MWh de TI), janela `[a_j, b_j]`, sites viáveis `D_j`, custo de migração `c_{j,d}` (0 no site nativo, assimétrico entre sites, ex.: 5–20 $/MWh):
- **Batch (temporal):** janela 8–12 h, `D_j` = só o site nativo.
- **Migrável (espacial):** janela 2–4 h, `D_j` = todos os sites.
- A energia flexível total por site e dia deve ser `f_d · C_d · 24` distribuída entre workloads. Gerador de workloads em `layers.py`, determinístico por seed.

### 5.3 Componentes por workload *j*
- `Bus` virtual `compute_j`, `carrier="compute"`.
- Para cada `d ∈ D_j`: `Link` de `bus_d → compute_j` com
  - `efficiency = 1/PUE_d` (MW elétrico → MW de TI)
  - `p_nom = f_d · C_d`, `p_min_pu = 0`
  - `p_max_pu` série: 1 em `[a_j, b_j]`, 0 fora
  - `marginal_cost = c_{j,d}`
  - `ramp_limit_up = ramp_limit_down` configurável (ex.: 0,5)
- `Store` em `compute_j`: `e_nom = E_j`, `e_initial = 0`, `e_cyclic = False`, `standing_loss = 0`, `e_min_pu` série: 0 para t < b_j, 1 para t ≥ b_j (força conclusão até o deadline). `e_max_pu = 1`.

### 5.4 Restrição custom (única): capacidade por site
Em `constraints.py`, dentro de `extra_functionality(n, snapshots)`:

```
Σ_j Link-p[(j,d), t]  ≤  f_d · C_d       ∀ d, t
```
Implementar com linopy: `m = n.model; p = m["Link-p"]`; agrupar links por site via atributo `site` e `m.add_constraints(lhs <= rhs, name="site_capacity")`.

**Critério de aceite F3/F4:** caso 50% VRE com VPL+VDC resolve; toda energia de workload é concluída até o deadline (checar `stores_t.e` no snapshot `b_j` ≥ `E_j − ε`); nenhum site excede capacidade; VPL cicla ao menos uma vez nos dias com congestionamento.

---

## 6. Reserva girante (em `constraints.py`)

```
Σ_g (status_g,t · Pmax_g − p_g,t)  ≥  R_t
```
- `R_t` = max(3% da carga, maior unidade online) simplificado para `R_t = 0.03·load_t + 0.05·VRE_disponível_t` (configurável).
- linopy: `status = m["Generator-status"]`, `p = m["Generator-p"]` restritos aos committable; multiplicar status por `p_nom` (xarray alinhado na dimensão Generator).
- Opcional, flag no config: contar VDC (headroom de redução: `Link-p` corrente) e VPL (`StorageUnit-p_dispatch` headroom) como provedores de reserva. Default **desligado** no caso base; ligar como sensibilidade.

---

## 7. Armadilhas conhecidas

- Séries `p_max_pu`, `e_min_pu` etc. precisam ter índice **exatamente** `n.snapshots` (mesmos timestamps), senão o PyPSA ignora silenciosamente ou preenche com default.
- **Não** usar `linearized_unit_commitment=True` — perde o resultado de ciclagem, que é argumento central do artigo.
- Custo zero em VRE gera degenerescência entre curtailment e carga de BESS/VDC. Usar `marginal_cost = -0.1` em VRE (penaliza curtailment de forma interpretável) e reportar o efeito como desprezível no custo total. Alternativa: gerador-slack de curtailment com penalidade explícita.
- `shut_down_cost = 0` pode gerar despacho degenerado entre unidades idênticas (o RTS tem várias unidades gêmeas). Aceitável; não afeta métricas agregadas.
- Transformadores: se modelados como `Line`, garantir que a impedância convertida não distorça o fluxo. Validar com fluxo DC estático (`n.lpf()`) sobre um snapshot antes de rodar UC.
- MILP: fixar `mip_rel_gap = 0.005` em ambos os solvers para comparabilidade; reportar gap atingido em cada resultado.
- Salvar cada rede resolvida com `n.export_to_netcdf()` em `results/<cenario>.nc` para reprodutibilidade e re-processamento sem resolver de novo.

---

## 8. Fase 5 — Runner de cenários (`runner.py`)

Assinatura:

```python
run_case(day: str, vre_share: float, layers: set[str], vpl_mwh: float,
         dc_flex: float, solver: str, reserve_from_flex: bool) -> Path
```

- `layers ⊆ {"VPL", "VDC"}`. Casos: **A** base, **B** +VPL, **C** +VDC, **D** VPL+VDC.
- Clonar a rede base (`n.copy()`), aplicar camadas, resolver, exportar NetCDF, gravar linha em `results/metrics.csv`.
- Solver parametrizado:
  - `highs`: `solver_options={"mip_rel_gap": 0.005, "threads": N, "time_limit": 1800}`
  - `gurobi`: `solver_options={"MIPGap": 0.005, "Threads": N, "TimeLimit": 1800}`
- Registrar tempo de solução e gap em `metrics.csv`.

### 8.1 Dias representativos (config `days`)
Selecionar 3–4 dias do ano RTS-GMLC usando a caracterização de rampa da demanda líquida da tese (Seção 5.2.1.1: DFT da série anual + rampas máximas diárias) como critério automático, com confirmação manual:
1. Eólica alta + carga baixa (primavera) — curtailment máximo
2. Pico de carga de verão
3. Dia de rampa solar acentuada (outono/inverno)
4. Dia mediano de referência

### 8.2 Grade de sensibilidades (`scenarios.yaml`)
Caso base: 50% VRE, VPL 200 MW / 4 h por terminal, `f_d = 0,5`, janelas nominais. Variar um eixo por vez:
- VRE: 30 / 50 / 70 %
- VPL: 100 / 200 / 400 MW (4 h)
- `f_d`: 0,2 / 0,5 / 0,8
- Largura de janela batch: ×0,5 / ×1 / ×2
- Reserva de flex: off / on
- Representação do VPL: emergente / explícita

Total esperado: ~4 dias × 4 casos × ~12 variações ≈ 150–200 resoluções. Com HiGHS pode levar horas; **fazer grade reduzida em HiGHS para debug e grade completa em Gurobi**.

---

## 9. Fase 6 — Métricas (`metrics.py`)

Por resolução, extrair e gravar:

| Métrica | Fonte |
|---|---|
| Custo total e decomposição (combustível, partidas, migração, degradação, penalidade curtailment) | `n.objective`, `generators_t.p × marginal_cost`, `generators_t.start_up`, `links_t.p0 × marginal_cost`, `storage_units_t.p_dispatch × marginal_cost` |
| Curtailment VRE (MWh e %) | Σ(p_max_pu·p_nom − p) |
| Nº de partidas por combustível | `generators_t.status.diff().clip(lower=0).sum()` |
| FRUS / FRDS médios (eqs. 5.1–5.2 da tese) | FRUS_g,t = min(Pmax·u − p, RU − (p_t − p_{t−1})); FRDS_g,t = min(p − Pmin·u, RD − (p_{t−1} − p_t)); média sobre unidades ligadas e horas |
| Horas em serviço VTL vs. arbitragem (variante explícita) | `sigma_t` × operação do BESS |
| MWh operados em Pmin (ciclagem) | status·Pmin vs p com tolerância |
| Horas congestionadas do corredor e spread de LMP | `lines_t.p0`, `buses_t.marginal_price` |
| Capacidade virtual VPL (MW-eq, MWh) | descarga a jusante em horas saturadas |
| Energia VDC deslocada no espaço (fora do site nativo) e no tempo (fora da hora de chegada) | `links_t.p0` por workload |
| CO₂ (t) | p × fator por gerador |
| Tempo de solução, gap | log do solver |

Valor marginal: ΔCusto(B−A), ΔCusto(C−A), ΔCusto(D−A). Complementaridade: `ΔD − (ΔB + ΔC)` — negativo = substitutos, positivo = complementares. Esta é a tabela central do artigo.

---

## 10. Fase 7 — Figuras (`plots.py`)

1. Mapa do RTS-GMLC com corredor, sites de DC e VPL destacados.
2. Despacho empilhado por combustível, casos A e D, dia 1 (curtailment hachurado).
3. Fluxo no corredor N_318–N_223 vs limite + SOC dos dois BESS do VPL (mesmo eixo de tempo), com faixas de `sigma_t` sombreadas.
4. Heatmap de carga VDC por site × hora, casos C e D.
5. Spread de LMP nos terminais do corredor, casos A–D.
6. Sensibilidade: custo, curtailment e partidas vs penetração VRE, quatro casos.
7. Barra de complementaridade `ΔD − (ΔB + ΔC)` por dia e penetração.

Estilo IEEE: figuras de coluna única (3,5 in), fonte 8 pt, sem título dentro da figura, exportar PDF vetorial.

---

## 11. Entregáveis

- Código funcional com `make validate` (F1), `make corridor` (F2), `make grid SOLVER=highs|gurobi` (F5), `make metrics`, `make figures`.
- `results/metrics.csv` completo.
- `results/summary.md` com tabelas prontas para o artigo (valor marginal e complementaridade).
- Testes mínimos em `tests/`: parser gera rede consistente (balanço de potência no `lpf`), workloads concluem até deadline, capacidade de site respeitada.

## 12. Fora de escopo (não implementar)
- UC estocástico ou robusto.
- Reforço de transmissão / expansão.
- Rede AC não linear.
- Modelo detalhado de rede de dados/latência do data center — apenas o custo `c_{j,d}`.
- Real-time / redispatch intradiário.
