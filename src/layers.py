"""
layers.py — Fases 2, 3 e 4: configuração estressada, escalonamento VRE e as
camadas de flexibilidade (Virtual Power Line e Virtual Data Center).

Todas as funções operam *in place* sobre um ``pypsa.Network`` já construído
por ``rts_import.build_network`` e registram suas decisões em ``n.meta`` para
rastreabilidade (o dicionário é exportado junto com o NetCDF).

Resumo das funções públicas
---------------------------
stress_system(n, cfg)      +40 % de carga na Área 2 e VRE equivalente na Área 3 (§3.1)
scale_vre(n, share)        escala a capacidade VRE até a penetração-alvo (§3.2)
limit_corridor(n, factor)  fallback documentado: reduz s_nom do corredor (§3.1)
add_vpl(n, cfg)            par de BESS nos terminais do corredor (§4)
compute_sigma(n, cfg)      estágio de uso da rede sigma_t para a variante explícita (§4)
add_dc_inflexible(n, cfg)  data centers como carga plana (casos sem camada VDC)
add_vdc(n, cfg)            workloads com janela, sites viáveis e custo de migração (§5)
corridor_flow(n)           série do fluxo no corredor (positivo = montante -> jusante)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pypsa


# =============================================================================
# Utilidades do corredor
# =============================================================================
def corridor_lines(n: pypsa.Network, cfg: dict) -> pd.DataFrame:
    """Devolve as linhas do corredor com uma coluna ``sign`` de orientação.

    ``sign = +1`` quando ``bus0`` é o terminal a montante (p0 > 0 significa
    fluxo montante → jusante); ``-1`` caso contrário.
    """
    c = cfg["corridor"]
    lines = n.lines.loc[c["branches"]].copy()
    lines["sign"] = np.where(lines["bus0"] == str(c["bus_up"]), 1.0, -1.0)
    return lines


def corridor_flow(n: pypsa.Network, cfg: dict) -> pd.Series:
    """Fluxo agregado no corredor (MW), positivo no sentido montante → jusante."""
    lines = corridor_lines(n, cfg)
    return (n.lines_t.p0[lines.index] * lines["sign"]).sum(axis=1)


def corridor_limit(n: pypsa.Network, cfg: dict) -> float:
    """Capacidade agregada do corredor (soma de ``s_nom`` dos circuitos)."""
    return float(corridor_lines(n, cfg)["s_nom"].sum())


def vre_available(n: pypsa.Network) -> pd.DataFrame:
    """Potência VRE disponível por gerador e snapshot (MW) = p_max_pu × p_nom."""
    g = n.generators[n.generators["is_vre"]]
    pmax_pu = n.get_switchable_as_dense("Generator", "p_max_pu")[g.index]
    return pmax_pu * g["p_nom"]


def net_demand(n: pypsa.Network) -> pd.Series:
    """Demanda líquida do sistema (MW) = carga total − VRE disponível."""
    load = n.get_switchable_as_dense("Load", "p_set").sum(axis=1)
    return load - vre_available(n).sum(axis=1)


# =============================================================================
# Fase 2 — Configuração estressada e escalonamento VRE
# =============================================================================
def plan_added_vre(cfg: dict, gens: pd.DataFrame, mw_total: float) -> list[dict]:
    """Plano de alocação do acréscimo VRE na Área 3 (§3.1).

    Duas políticas (``stress.allocation``):

    * ``"candidates"`` (padrão): o acréscimo é distribuído pelos **nós
      candidatos da tese** (``Phd_Files/Network_RTS_Candidate_Gen_Costs.xlsx``:
      eólica em N_314/N_316/N_319, PV em N_320), com pesos iguais às
      capacidades candidatas e perfis ``p_max_pu`` de unidades existentes
      vizinhas da mesma tecnologia (``profile_from``). Estes nós ficam no anel
      de 230 kV que alimenta N_318, o que preserva o corredor N_318–N_223 como
      caminho de exportação.
    * ``"existing"``: proporcional à capacidade VRE já instalada nas barras da
      Área 3. Concentra o acréscimo em N_317 e provoca congestionamento na
      linha interna C29 (317–318) antes do corredor — documentado no F2.

    A repartição eólica/PV segue ``added_wind_share``. Devolve uma lista de
    dicionários ``{name, bus, carrier, p_nom_mw, profile_from}``.
    """
    s = cfg["stress"]
    gen_area = int(s["gen_area"])
    split = {"Wind": float(s["added_wind_share"]), "Solar PV": 1.0 - float(s["added_wind_share"])}
    base = gens[~gens.index.str.endswith("_ADD")]
    plan: list[dict] = []

    if s.get("allocation", "candidates") == "candidates":
        sites = pd.DataFrame(s["candidate_sites"])
        sites["bus"] = sites["bus"].astype(str)
        for carrier, share in split.items():
            sub = sites[sites["carrier"] == carrier]
            if sub.empty or share <= 0:
                continue
            w = sub["weight_mw"] / sub["weight_mw"].sum()
            for (_, row), wi in zip(sub.iterrows(), w):
                plan.append(dict(name=f"{row['bus']}_{carrier.replace(' ', '')}_ADD", bus=row["bus"], carrier=carrier,
                                 p_nom_mw=mw_total * share * float(wi), profile_from=str(row["profile_from"])))
    else:
        for carrier, share in split.items():
            existing = base[(base["carrier"] == carrier) & (base["area"] == gen_area)]
            if existing.empty or share <= 0:
                continue
            w = existing["p_nom"] / existing["p_nom"].sum()
            for uid, wi in w.items():
                plan.append(dict(name=f"{uid}_ADD", bus=existing.at[uid, "bus"], carrier=carrier,
                                 p_nom_mw=mw_total * share * float(wi), profile_from=uid))
    return plan


def stress_system(n: pypsa.Network, cfg: dict) -> pypsa.Network:
    """Replica a configuração da tese / Energies 2026 (§3.1).

    1. Multiplica por ``load_factor`` (1,40) todas as cargas da Área 2.
    2. Adiciona na Área 3 capacidade VRE igual ao acréscimo do pico anual de
       carga da Área 2, repartida entre eólica e PV (``added_wind_share``) e
       alocada nas barras que já possuem VRE, proporcionalmente à capacidade
       existente. Cada nova unidade herda o perfil ``p_max_pu`` da unidade
       existente correspondente.
    """
    s = cfg["stress"]
    load_area, gen_area = int(s["load_area"]), int(s["gen_area"])
    factor = float(s["load_factor"])

    # --- 1. Carga da Área 2
    loads = n.loads.index[n.loads["area"] == load_area]
    n.loads_t.p_set[loads] *= factor

    # --- 2. Acréscimo de capacidade = (fator − 1) × pico anual da Área 2
    peak = float(n.meta["area_peak_load_mw"][str(load_area)])
    mw_added_total = (factor - 1.0) * peak

    g = n.generators
    added = {}
    for item in plan_added_vre(cfg, g, mw_added_total):
        src = item["profile_from"]
        n.add(
            "Generator",
            item["name"],
            bus=item["bus"],
            carrier=item["carrier"],
            fuel=g.at[src, "fuel"],
            unit_type=g.at[src, "unit_type"],
            p_nom=item["p_nom_mw"],
            p_max_pu=n.generators_t.p_max_pu[src],
            marginal_cost=g.at[src, "marginal_cost"],
            area=gen_area,
            is_vre=True,
            is_thermal=False,
            cf_annual=g.at[src, "cf_annual"],
            added_stress=True,
        )
        added[item["name"]] = {"bus": item["bus"], "carrier": item["carrier"], "p_nom_mw": round(item["p_nom_mw"], 2),
                               "profile_from": src}

    n.generators["added_stress"] = n.generators["added_stress"].fillna(False).astype(bool)
    # Carga anual estressada (para o escalonamento VRE em base anual)
    annual = n.meta["annual_load_mwh_by_area"]
    n.meta["annual_load_mwh_stressed"] = float(
        sum(v * (factor if int(a) == load_area else 1.0) for a, v in annual.items())
    )
    n.meta["stress"] = {
        "load_area": load_area,
        "load_factor": factor,
        "area2_annual_peak_mw": peak,
        "mw_added_area3": round(mw_added_total, 2),
        "added_units": added,
    }
    n.meta["system"] = "RTS-GMLC estressado (tese / Energies 2026)"
    return n


def vre_share(n: pypsa.Network) -> float:
    """Penetração VRE diária = Σ energia VRE disponível / Σ carga, nos snapshots da rede."""
    load = n.get_switchable_as_dense("Load", "p_set").sum().sum()
    return float(vre_available(n).sum().sum() / load)


def vre_share_annual(n: pypsa.Network) -> float:
    """Penetração VRE anual = Σ_g p_nom_g · CF_g · 8784 / carga anual estressada.

    Usa o fator de capacidade anual de cada unidade (``cf_annual``, calculado no
    parser a partir da série DAY_AHEAD do ano inteiro) e a carga anual já com o
    fator de estresse da Área 2.
    """
    g = n.generators[n.generators["is_vre"]]
    energy = float((g["p_nom"] * g["cf_annual"]).sum() * n.meta["annual_hours"])
    load = float(n.meta.get("annual_load_mwh_stressed", sum(n.meta["annual_load_mwh_by_area"].values())))
    return energy / load


def scale_vre(n: pypsa.Network, target_share: float, basis: str = "annual") -> float:
    """Escala ``p_nom`` de todas as unidades VRE por um fator único (§3.2).

    A métrica de penetração é a energia VRE *disponível* (não a despachada)
    dividida pela carga, com a configuração estressada já aplicada. Duas bases:

    * ``"annual"`` (padrão): fator único para o ano — o parque instalado é o
      mesmo em todos os dias representativos e a penetração é a anual, como na
      tese. Dias de vento forte têm share diário > alvo (curtailment máximo) e o
      dia de pico tem share < alvo. Foi a base necessária para atender ao
      critério F2 (saturação do corredor).
    * ``"day"``: fator calculado sobre os 24 snapshots do caso (leitura literal
      do brief); reduz o parque nos dias ventosos e o amplia nos dias de pico.

    Devolve o fator aplicado (também registrado em ``n.meta``).
    """
    current = vre_share_annual(n) if basis == "annual" else vre_share(n)
    factor = float(target_share) / current
    vre = n.generators.index[n.generators["is_vre"]]
    n.generators.loc[vre, "p_nom"] *= factor
    n.meta["vre_scaling"] = {
        "basis": basis,
        "share_before": round(current, 4),
        "target_share": float(target_share),
        "factor": round(factor, 4),
        "share_after_annual": round(vre_share_annual(n), 4),
        "share_after_day": round(vre_share(n), 4),
    }
    return factor


def limit_corridor(n: pypsa.Network, cfg: dict, factor: float) -> None:
    """Fallback documentado (§3.1): reduz ``s_nom`` das linhas do corredor.

    Só deve ser usado se o corredor não saturar mesmo após aumentar a fração
    VRE do acréscimo da Área 3.
    """
    lines = corridor_lines(n, cfg).index
    n.lines.loc[lines, "s_nom"] *= float(factor)
    n.meta["corridor_limit_factor"] = float(factor)


# =============================================================================
# Fase 3 — Virtual Power Line
# =============================================================================
VPL_UP, VPL_DOWN = "VPL_up", "VPL_down"


def add_vpl(n: pypsa.Network, cfg: dict) -> None:
    """Adiciona o par de BESS do VPL nos terminais do corredor (§4).

    Formulação padrão (*emergente*): nenhum acoplamento explícito entre os dois
    BESS; o comportamento de "linha virtual" emerge do spread de LMP entre os
    terminais. A variante *explícita* (regra de chaveamento da tese) é imposta
    em ``constraints.py`` quando ``cfg["vpl"]["mode"] == "explicit"``; aqui só
    se pré-calcula ``sigma_t`` para ela.

    ``cfg["vpl"]["terminals"]`` (padrão ``"both"``) permite instalar apenas o
    BESS de montante (``"up"``) ou de jusante (``"down"``). Serve à decomposição
    do benefício do VPL em *arbitragem de bateria isolada* (soma dos dois casos
    com um terminal) e *valor do pareamento* (diferença para o caso completo).
    """
    v, c = cfg["vpl"], cfg["corridor"]
    eta = np.sqrt(float(v["roundtrip_efficiency"]))
    terminals = str(v.get("terminals", "both")).lower()
    if "VPL" not in n.carriers.index:
        n.add("Carrier", "VPL")
    pairs = ((VPL_UP, str(c["bus_up"])), (VPL_DOWN, str(c["bus_down"])))
    if terminals == "up":
        pairs = pairs[:1]
    elif terminals == "down":
        pairs = pairs[1:]
    for name, bus in pairs:
        n.add(
            "StorageUnit",
            name,
            bus=bus,
            carrier="VPL",
            p_nom=float(v["p_nom_mw"]),
            max_hours=float(v["hours"]),
            efficiency_store=eta,
            efficiency_dispatch=eta,
            cyclic_state_of_charge=True,
            marginal_cost=float(v["marginal_cost"]),   # degradação, cobrado na descarga
        )
    n.meta["vpl"] = {
        "p_nom_mw": float(v["p_nom_mw"]),
        "hours": float(v["hours"]),
        "mwh_per_terminal": float(v["p_nom_mw"]) * float(v["hours"]),
        "mode": v["mode"],
        "terminals": terminals,
    }
    if str(v["mode"]).lower() in ("explicit", "dedicated"):
        sigma = compute_sigma(n, cfg)
        # NaN (hora intermediária) vira None para ser serializável em JSON
        n.meta["sigma"] = [None if pd.isna(x) else int(x) for x in sigma]


def compute_sigma(n: pypsa.Network, cfg: dict) -> pd.Series:
    """Estágio de uso da rede por hora para a variante explícita (§4).

    ``sigma_t = 1`` se a demanda líquida ≥ percentil alto (alto uso),
    ``sigma_t = 0`` se ≤ percentil baixo (baixo uso) e ``NaN`` nas horas
    intermediárias (BESS livre para arbitragem — *revenue stacking*).
    Os percentis são tomados sobre a curva de duração do horizonte resolvido
    (24 h), coerentes com o caráter day-ahead do problema.
    """
    v = cfg["vpl"]
    nd = net_demand(n)
    hi = np.percentile(nd, float(v["sigma_high_percentile"]))
    lo = np.percentile(nd, float(v["sigma_low_percentile"]))
    sigma = pd.Series(np.nan, index=n.snapshots, name="sigma")
    sigma[nd >= hi] = 1.0
    sigma[nd <= lo] = 0.0
    return sigma


# =============================================================================
# Fase 4 — Virtual Data Center
# =============================================================================
def _site_table(cfg: dict) -> pd.DataFrame:
    """Tabela de sites com capacidade flexível derivada de f_d e PUE_d."""
    v = cfg["vdc"]
    sites = pd.DataFrame(v["sites"]).set_index("name")
    sites["bus"] = sites["bus"].astype(str)
    sites["flex_fraction"] = float(v["flex_fraction"])
    sites["flex_mw_elec"] = sites["flex_fraction"] * sites["capacity_mw"]        # f_d · C_d
    sites["flex_mw_it"] = sites["flex_mw_elec"] / sites["pue"]                   # em MW de TI
    sites["inflex_mw_elec"] = (1.0 - sites["flex_fraction"]) * sites["capacity_mw"]
    return sites


def _edf_schedule(workloads: list[dict], cap_it_mw: float, horizon: int = 24) -> np.ndarray:
    """Cronograma EDF (MW de TI por hora) de um site: cada job executa no site
    nativo a partir da chegada, à máxima potência disponível, prioridade por
    prazo. É o *baseline* "native" (jobs inflexíveis no tempo e no espaço)."""
    remaining = {w["id"]: w["E_it_mwh"] for w in workloads}
    sched = np.zeros(horizon)
    for t in range(horizon):
        active = [w for w in workloads if w["arrival"] <= t <= w["deadline"] and remaining[w["id"]] > 1e-9]
        active.sort(key=lambda w: w["deadline"])
        cap = cap_it_mw
        for w in active:
            p_max = cap_it_mw * (0.5 if t in (w["arrival"], w["deadline"]) else 1.0)
            served = min(p_max, remaining[w["id"]], cap)
            remaining[w["id"]] -= served
            cap -= served
            sched[t] += served
            if cap <= 1e-9:
                break
    return sched


def add_dc_inflexible(n: pypsa.Network, cfg: dict) -> None:
    """Data centers como carga inflexível, para os casos SEM camada VDC (A e B).

    A energia diária de cada site é **exatamente** a dos workloads gerados por
    ``generate_workloads`` para a mesma configuração (f_d, janela, semente),
    incluindo os cortes de factibilidade. Assim A/B e C/D consomem a mesma
    energia e a diferença de custo isola o valor da flexibilidade.

    ``cfg["vdc"]["baseline"]``:
    * ``"flat"`` (padrão): energia flexível distribuída uniformemente nas 24 h
      (perfil plano) mais a parte inflexível ``(1 − f_d)·C_d``;
    * ``"native"``: os mesmos jobs executados no site nativo a partir da chegada
      (cronograma EDF, sem deslocamento temporal nem espacial) — contrafactual
      operacional mais estrito, usado como sensibilidade.
    """
    sites = _site_table(cfg)
    mode = str(cfg["vdc"].get("baseline", "flat")).lower()
    workloads, _ = generate_workloads(cfg)
    if "datacenter" not in n.carriers.index:
        n.add("Carrier", "datacenter")
    energy = {}
    for name, s in sites.iterrows():
        site_wl = [w for w in workloads if w["native"] == name]
        e_it = float(sum(w["E_it_mwh"] for w in site_wl))
        energy[name] = e_it * float(s["pue"])
        if mode == "native":
            prof_it = _edf_schedule(site_wl, float(s["flex_mw_it"]))
            p_set = pd.Series(s["inflex_mw_elec"] + float(s["pue"]) * prof_it, index=n.snapshots)
        else:
            p_set = s["inflex_mw_elec"] + energy[name] / 24.0
        n.add("Load", f"L_{name}_flat", bus=s["bus"], p_set=p_set, carrier="datacenter", area=int(s["area"]))
    n.meta["vdc"] = {"mode": f"inflexible-{mode}", "flex_energy_elec_mwh": energy,
                     "flat_mw": {k: float(sites.loc[k, "inflex_mw_elec"] + energy[k] / 24.0) for k in sites.index}}


def _edf_feasible(workloads: list[dict], cap_it_mw: float, horizon: int = 24) -> bool:
    """Verifica por simulação EDF (*earliest deadline first*) se um conjunto de
    workloads cabe na capacidade ``cap_it_mw`` de um único site.

    Usa-se a capacidade efetiva ``(L_j − 1)`` horas por workload, que é exata
    para rampa de 0,5 p.u./h (primeira e última hora a meia potência).
    """
    remaining = {w["id"]: w["E_it_mwh"] for w in workloads}
    for t in range(horizon):
        active = [w for w in workloads if w["arrival"] <= t <= w["deadline"] and remaining[w["id"]] > 1e-9]
        active.sort(key=lambda w: w["deadline"])
        cap = cap_it_mw
        for w in active:
            # meia potência nas horas de borda da janela (efeito da rampa)
            p_max = cap_it_mw * (0.5 if t in (w["arrival"], w["deadline"]) else 1.0)
            served = min(p_max, remaining[w["id"]], cap)
            remaining[w["id"]] -= served
            cap -= served
            if cap <= 1e-9:
                break
    return all(r <= 1e-6 for r in remaining.values())


def generate_workloads(cfg: dict) -> tuple[list[dict], pd.DataFrame]:
    """Gera o conjunto determinístico (por *seed*) de workloads (§5.2).

    Por site *d*: energia flexível diária ``u·f_d·C_d·24`` MWh elétricos, ou
    seja ``u·f_d·C_d·24 / PUE_d`` MWh de TI, repartida entre workloads
    **batch** (janela 8–12 h, só o site nativo) e **migráveis** (janela 2–4 h,
    todos os sites). A factibilidade de cada site é checada por EDF; se
    necessário as energias do site são reduzidas por bissecção e o fator é
    registrado.

    Devolve a lista de workloads e a matriz de custos de migração
    ``c[nativo][destino]`` ($/MWh de TI), assimétrica, 0 na diagonal.
    """
    v = cfg["vdc"]
    wcfg = v["workloads"]
    rng = np.random.default_rng(int(wcfg["seed"]))
    sites = _site_table(cfg)
    u = float(v["flex_utilization"])
    scale = float(wcfg["window_scale"])
    lo_c, hi_c = wcfg["migration_cost_range"]

    # Matriz assimétrica de custo de migração (sorteada uma vez, por par de sites)
    names = list(sites.index)
    cost = pd.DataFrame(0.0, index=names, columns=names)
    for a in names:
        for b in names:
            if a != b:
                cost.loc[a, b] = float(rng.uniform(lo_c, hi_c))

    workloads: list[dict] = []
    for d, s in sites.iterrows():
        e_it_total = u * s["flex_mw_elec"] * 24.0 / s["pue"]
        e_batch = float(wcfg["batch_share"]) * e_it_total
        e_migr = e_it_total - e_batch

        def _split(total: float, k: int) -> np.ndarray:
            return total * rng.dirichlet(np.full(k, 4.0))   # partes semelhantes, não idênticas

        site_wl: list[dict] = []
        # --- batch (temporal)
        for i, e in enumerate(_split(e_batch, int(wcfg["n_batch_per_site"]))):
            L = int(np.clip(round(rng.uniform(*wcfg["batch_window_h"]) * scale), 2, 24))
            a = int(rng.integers(0, 24 - L + 1))
            site_wl.append(dict(id=f"{d}_B{i+1}", type="batch", native=d, sites=[d],
                                arrival=a, deadline=a + L - 1, E_it_mwh=float(e)))
        # --- migráveis (espacial)
        for i, e in enumerate(_split(e_migr, int(wcfg["n_migratable_per_site"]))):
            L = int(np.clip(round(rng.uniform(*wcfg["migratable_window_h"])), 2, 24))
            a = int(rng.integers(0, 24 - L + 1))
            site_wl.append(dict(id=f"{d}_M{i+1}", type="migratable", native=d, sites=names,
                                arrival=a, deadline=a + L - 1, E_it_mwh=float(e)))

        # --- limite individual: E_j ≤ (L_j − 1)·capacidade de TI do site
        for w in site_wl:
            cap_j = (w["deadline"] - w["arrival"]) * s["flex_mw_it"]
            w["E_it_mwh"] = min(w["E_it_mwh"], cap_j)

        # --- factibilidade conjunta no site nativo (conservadora: ignora migração)
        f_scale = 1.0
        if not _edf_feasible(site_wl, s["flex_mw_it"]):
            lo, hi = 0.0, 1.0
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                trial = [dict(w, E_it_mwh=w["E_it_mwh"] * mid) for w in site_wl]
                if _edf_feasible(trial, s["flex_mw_it"]):
                    lo = mid
                else:
                    hi = mid
            f_scale = lo
            for w in site_wl:
                w["E_it_mwh"] *= f_scale
        for w in site_wl:
            w["feasibility_scale"] = f_scale
            w["pue"] = float(s["pue"])
        workloads.extend(site_wl)

    return workloads, cost


def add_vdc(n: pypsa.Network, cfg: dict) -> None:
    """Adiciona a camada VDC com componentes nativos do PyPSA (§5.3).

    Por workload *j*: uma barra virtual ``compute_j``; um ``Link`` de cada site
    viável *d* até ``compute_j`` (eficiência 1/PUE_d, ``p_max_pu`` = 1 dentro da
    janela, custo de migração ``c_{j,d}``); e um ``Store`` em ``compute_j`` cujo
    ``e_min_pu`` salta para 1 no deadline, forçando a conclusão. A única
    restrição custom (capacidade por site) fica em ``constraints.py``.
    """
    v = cfg["vdc"]
    sites = _site_table(cfg)
    workloads, cost = generate_workloads(cfg)
    sns = n.snapshots
    hours = np.arange(len(sns))

    # Carga inflexível plana por site
    for d, s in sites.iterrows():
        n.add("Load", f"L_{d}_inflex", bus=s["bus"], p_set=float(s["inflex_mw_elec"]),
              carrier="datacenter", area=int(s["area"]))

    if "compute" not in n.carriers.index:
        n.add("Carrier", ["compute", "VDC", "datacenter"])

    for w in workloads:
        cbus = f"compute_{w['id']}"
        n.add("Bus", cbus, carrier="compute")
        window = pd.Series(((hours >= w["arrival"]) & (hours <= w["deadline"])).astype(float), index=sns)
        for d in w["sites"]:
            s = sites.loc[d]
            n.add(
                "Link",
                f"{w['id']}@{d}",
                bus0=s["bus"],
                bus1=cbus,
                carrier="VDC",
                efficiency=1.0 / float(s["pue"]),
                p_nom=float(s["flex_mw_elec"]),
                p_min_pu=0.0,
                p_max_pu=window,
                marginal_cost=float(cost.loc[w["native"], d]),
                ramp_limit_up=float(v["ramp_limit_pu"]),
                ramp_limit_down=float(v["ramp_limit_pu"]),
                site=d,
                workload=w["id"],
                native_site=w["native"],
                is_native=(d == w["native"]),
                arrival=int(w["arrival"]),
                deadline=int(w["deadline"]),
            )
        e_min = pd.Series((hours >= w["deadline"]).astype(float), index=sns)
        n.add(
            "Store",
            f"st_{w['id']}",
            bus=cbus,
            carrier="compute",
            e_nom=float(w["E_it_mwh"]),
            e_initial=0.0,
            e_cyclic=False,
            standing_loss=0.0,
            e_min_pu=e_min,
            e_max_pu=1.0,
            workload=w["id"],
        )

    n.meta["vdc"] = {
        "mode": "flexible",
        "flex_fraction": float(v["flex_fraction"]),
        "flex_utilization": float(v["flex_utilization"]),
        "window_scale": float(v["workloads"]["window_scale"]),
        "sites": {d: {"bus": s["bus"], "capacity_mw": float(s["capacity_mw"]), "pue": float(s["pue"]),
                      "flex_mw_elec": float(s["flex_mw_elec"])} for d, s in sites.iterrows()},
        "workloads": workloads,
        "migration_cost": cost.round(3).to_dict(),
    }
