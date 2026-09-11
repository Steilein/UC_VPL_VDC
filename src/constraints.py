"""
constraints.py — restrições adicionais ao UC nativo do PyPSA (``extra_functionality``).

O PyPSA/linopy constrói o MILP do Unit Commitment (balanço nodal, fluxo DC,
status/partida/parada, rampas, tempos mínimos, armazenamentos). Este módulo
acrescenta, via ``extra_functionality(n, snapshots)``, três blocos de
restrições descritos no brief:

1. **Reserva girante** (§6):
       Σ_g (status_{g,t} · Pmax_g − p_{g,t}) ≥ R_t,
   com R_t = a·carga_t + b·VRE_disponível_t. Opcionalmente (``reserve.from_flex``)
   a folga do VDC (carga corrente dos Links, redutível) e do VPL (folga de
   descarga do BESS) também contam como reserva.

2. **Capacidade e rampa por site do VDC** (§5.4):
       Σ_j Link-p[(j,d), t] ≤ f_d · C_d                    ∀ d, t;
       | Σ_j Link-p[(j,d),t] − Σ_j Link-p[(j,d),t−1] | ≤ Δ_d.
   A rampa agregada complementa o ``ramp_limit`` nativo do ``Link``, que só
   limita cada par tarefa-site isoladamente.

3. **Regra de chaveamento explícita do VPL** (§4, variante ``vpl.mode = explicit``):
   binária z_t de sentido do fluxo no corredor (big-M) e binária w_t que fixa o
   modo (carga/descarga) de cada BESS conforme sigma_t (estágio de uso da rede).

Convenções do linopy/PyPSA ≥ 1.0 usadas aqui: as variáveis chamam-se
``"Generator-status"``, ``"Generator-p"``, ``"Link-p"``, ``"Line-s"``,
``"StorageUnit-p_dispatch"``, ``"StorageUnit-p_store"``; a dimensão dos
componentes chama-se ``"name"`` e a temporal ``"snapshot"``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pypsa
import xarray as xr

from layers import VPL_DOWN, VPL_UP, corridor_lines, vre_available


def _by_name(values: pd.Series) -> xr.DataArray:
    """Série pandas indexada por componente → DataArray alinhado na dimensão ``name``."""
    return xr.DataArray(values.values, coords={"name": values.index.values}, dims="name")


def _by_snapshot(values: pd.Series, sns: pd.Index) -> xr.DataArray:
    """Série pandas indexada por snapshot → DataArray na dimensão ``snapshot``."""
    return xr.DataArray(values.reindex(sns).values, coords={"snapshot": sns.values}, dims="snapshot")


# -----------------------------------------------------------------------------
# 1. Reserva girante
# -----------------------------------------------------------------------------
def add_spinning_reserve(n: pypsa.Network, sns: pd.Index, cfg: dict) -> None:
    r = cfg["reserve"]
    m = n.model
    g = n.generators
    com = g.index[g["committable"].astype(bool)]

    status = m["Generator-status"].sel(name=com)
    p = m["Generator-p"].sel(name=com)
    p_nom = _by_name(g.loc[com, "p_nom"])

    # Lado esquerdo: folga total das unidades térmicas ligadas
    lhs = (status * p_nom - p).sum("name")

    # Requisito R_t
    load_t = n.get_switchable_as_dense("Load", "p_set", sns).sum(axis=1)
    vre_t = vre_available(n).reindex(sns).sum(axis=1)
    req = float(r["load_fraction"]) * load_t + float(r["vre_fraction"]) * vre_t
    rhs = _by_snapshot(req, sns)

    # Provedores flexíveis (sensibilidade): VDC e VPL
    if r.get("from_flex", False):
        vdc_links = n.links.index[n.links["carrier"] == "VDC"]
        if len(vdc_links):
            # Carga corrente do VDC pode ser reduzida → headroom de reserva
            lhs = lhs + m["Link-p"].sel(name=vdc_links).sum("name")
        vpl = [u for u in (VPL_UP, VPL_DOWN) if u in n.storage_units.index]
        if vpl:
            p_dis = m["StorageUnit-p_dispatch"].sel(name=vpl)
            p_sto = m["StorageUnit-p_store"].sel(name=vpl)
            p_nom_vpl = _by_name(n.storage_units.loc[vpl, "p_nom"])
            # Folga de descarga + carga corrente interrompível (ignora limite de SOC)
            lhs = lhs + (p_nom_vpl - p_dis + p_sto).sum("name")

    m.add_constraints(lhs >= rhs, name="spinning_reserve")


# -----------------------------------------------------------------------------
# 2. Capacidade por site do VDC
# -----------------------------------------------------------------------------
def add_site_capacity(n: pypsa.Network, sns: pd.Index, cfg: dict) -> None:
    links = n.links[n.links["carrier"] == "VDC"]
    if links.empty:
        return
    m = n.model
    sites = n.meta["vdc"]["sites"]
    for site, info in sites.items():
        idx = links.index[links["site"] == site]
        if idx.empty:
            continue
        lhs = m["Link-p"].sel(name=idx).sum("name")
        m.add_constraints(lhs <= float(info["flex_mw_elec"]), name=f"site_capacity-{site}")


def add_site_ramp(n: pypsa.Network, sns: pd.Index, cfg: dict) -> None:
    """Limite de rampa da carga de TI **agregada** por site (§5.4):

        | Σ_j Link-p[(j,d),t] − Σ_j Link-p[(j,d),t−1] | ≤ Δ_d,
        Δ_d = ramp_limit_pu · f_d · C_d   (MW elétricos por hora).

    O ``ramp_limit`` nativo do ``Link`` limita cada par tarefa-site
    isoladamente; sem esta restrição a soma no site pode variar até a
    capacidade flexível inteira em uma hora.
    """
    links = n.links[n.links["carrier"] == "VDC"]
    if links.empty or len(sns) < 2:
        return
    m = n.model
    rl = float(cfg["vdc"]["ramp_limit_pu"])
    p = m["Link-p"]
    cur = sns[1:]
    prev = sns[:-1]
    for site, info in n.meta["vdc"]["sites"].items():
        idx = links.index[links["site"] == site]
        if idx.empty:
            continue
        delta = rl * float(info["flex_mw_elec"])
        agg = p.sel(name=idx).sum("name")
        diff = agg.sel(snapshot=cur) - agg.sel(snapshot=prev).rename(snapshot="snapshot").assign_coords(snapshot=cur)
        m.add_constraints(diff <= delta, name=f"site_ramp_up-{site}")
        m.add_constraints(diff >= -delta, name=f"site_ramp_down-{site}")


def add_vpl_soc_initial(n: pypsa.Network, sns: pd.Index, cfg: dict) -> None:
    """Fixa o estado de carga inicial dos BESS do VPL (``vpl.soc_initial``).

    Com ``cyclic_state_of_charge`` o PyPSA só impõe e_final = e_inicial, deixando
    o nível livre: o otimizador escolhe o SOC de partida mais conveniente de cada
    dia. Com esta opção o ciclo continua fechado, mas ancorado numa fração fixa
    de ``e_nom`` (tipicamente 0,5), o que é o contrafactual de um operador que
    começa o dia num estado pré-definido.
    """
    frac = cfg["vpl"].get("soc_initial")
    if frac is None:
        return
    units = [u for u in (VPL_UP, VPL_DOWN) if u in n.storage_units.index]
    if not units:
        return
    m = n.model
    soc = m["StorageUnit-state_of_charge"]
    for u in units:
        e_nom = float(n.storage_units.at[u, "p_nom"] * n.storage_units.at[u, "max_hours"])
        m.add_constraints(soc.sel(name=u, snapshot=sns[-1]) == float(frac) * e_nom,
                          name=f"VPL-soc_initial-{u}")


# -----------------------------------------------------------------------------
# 3. Variante explícita do VPL (regra de chaveamento da tese)
# -----------------------------------------------------------------------------
def add_explicit_vpl(n: pypsa.Network, sns: pd.Index, cfg: dict) -> None:
    """Impõe o modo de operação dos BESS pelo sentido do fluxo e por sigma_t.

    * z_t = 1 ⇔ fluxo montante → jusante (f_t ≤ M·z_t ; f_t ≥ −M·(1 − z_t)).
    * w_t = 1 ⇔ BESS a jusante em modo descarga (e o de montante em modo carga);
      w_t = 0 ⇔ inverso. Linearização: p_dis ≤ P·w, p_ch ≤ P·(1 − w).
    * Alto uso (sigma_t = 1): w_t = z_t  → com fluxo a jusante, montante carrega
      e jusante descarrega (alívio do corredor).
    * Baixo uso (sigma_t = 0): w_t = 1 − z_t → inverso (recarga do terminal a
      jusante usando a folga do corredor).
    * Horas intermediárias: em ``explicit`` w_t fica livre (arbitragem /
      *revenue stacking*, como na versão inter-área do cap. 5 da tese); em
      ``dedicated`` vale w_t = z_t, ou seja, o par emula transferência no
      sentido do fluxo em toda hora que não seja de baixo uso. O modo
      ``dedicated`` é a leitura estrita da seção 4.2.3 da tese, em que o ESS
      alocado a uma VTL opera permanentemente em carga ou descarga e não
      presta nenhum outro serviço.
    """
    if VPL_UP not in n.storage_units.index:
        return
    v = cfg["vpl"]
    m = n.model
    big_m = float(v["big_m"])
    P = float(n.storage_units.at[VPL_UP, "p_nom"])

    # Fluxo agregado no corredor como expressão linear (orientação montante→jusante)
    lines = corridor_lines(n, cfg)
    flow = None
    for name, sign in lines["sign"].items():
        term = sign * m["Line-s"].sel(name=name)
        flow = term if flow is None else flow + term

    # linopy espera um pd.Index nomeado para criar a dimensão "snapshot"
    snap_idx = pd.Index(sns, name="snapshot")
    z = m.add_variables(binary=True, coords=[snap_idx], name="VPL-z")
    w = m.add_variables(binary=True, coords=[snap_idx], name="VPL-w")

    m.add_constraints(flow - big_m * z <= 0, name="VPL-flow_direction-upper")
    m.add_constraints(flow + big_m * (1 - z) >= 0, name="VPL-flow_direction-lower")

    dis_up = m["StorageUnit-p_dispatch"].sel(name=VPL_UP)
    sto_up = m["StorageUnit-p_store"].sel(name=VPL_UP)
    dis_dn = m["StorageUnit-p_dispatch"].sel(name=VPL_DOWN)
    sto_dn = m["StorageUnit-p_store"].sel(name=VPL_DOWN)

    m.add_constraints(dis_dn - P * w <= 0, name="VPL-down-dispatch_mode")
    m.add_constraints(sto_dn + P * w <= P, name="VPL-down-store_mode")
    m.add_constraints(dis_up + P * w <= P, name="VPL-up-dispatch_mode")
    m.add_constraints(sto_up - P * w <= 0, name="VPL-up-store_mode")

    sigma = pd.Series(n.meta["sigma"], index=n.snapshots, dtype="float").reindex(sns)
    dedicated = str(v.get("mode", "emergent")).lower() == "dedicated"
    # em 'dedicated' nao existe hora livre: tudo que nao e baixo uso segue w_t = z_t
    hi = (sigma != 0.0) if dedicated else (sigma == 1.0)
    mask_hi = xr.DataArray(hi.values, coords={"snapshot": sns.values}, dims="snapshot")
    mask_lo = xr.DataArray((sigma == 0.0).values, coords={"snapshot": sns.values}, dims="snapshot")
    if bool(mask_hi.any()):
        m.add_constraints(w - z == 0, name="VPL-sigma_high", mask=mask_hi)
    if bool(mask_lo.any()):
        m.add_constraints(w + z == 1, name="VPL-sigma_low", mask=mask_lo)


# -----------------------------------------------------------------------------
# Fábrica da extra_functionality
# -----------------------------------------------------------------------------
def make_extra_functionality(cfg: dict):
    """Devolve a função ``extra_functionality(n, snapshots)`` para ``n.optimize``."""

    def extra_functionality(n: pypsa.Network, sns: pd.Index) -> None:
        if cfg["reserve"].get("enabled", True):
            add_spinning_reserve(n, sns, cfg)
        add_site_capacity(n, sns, cfg)
        add_site_ramp(n, sns, cfg)
        add_vpl_soc_initial(n, sns, cfg)
        if str(cfg["vpl"]["mode"]).lower() in ("explicit", "dedicated"):
            add_explicit_vpl(n, sns, cfg)

    return extra_functionality
