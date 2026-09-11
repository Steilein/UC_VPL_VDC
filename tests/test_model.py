"""
Testes mínimos exigidos pelo brief (§11):

1. O parser gera uma rede consistente (topologia íntegra; balanço de potência
   nodal no fluxo DC linear ``n.lpf``; fluxos do ``lpf`` coincidem com os do UC).
2. O escalonamento VRE atinge a penetração-alvo.
3. Os workloads do VDC concluem até o deadline e nenhum site excede a capacidade.
4. A variante explícita do VPL respeita a regra de chaveamento (sem carga e
   descarga simultâneas; modos coerentes com sigma_t e com o sentido do fluxo).

Os testes 3 e 4 resolvem o MILP de um dia com HiGHS (≈ 1 min cada); execute
``pytest -q`` a partir da raiz do repositório.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import load_config, set_by_path  # noqa: E402
from layers import VPL_DOWN, VPL_UP, corridor_flow, scale_vre, vre_share  # noqa: E402
from rts_import import build_network, load_rts_data, lpf_power_balance_error  # noqa: E402
from runner import apply_layers, build_stressed_network, solve  # noqa: E402

DAY = "2020-08-26"


@pytest.fixture(scope="module")
def cfg():
    c = load_config(ROOT / "config" / "base.yaml")
    c = set_by_path(c, "solver.name", "highs")
    c = set_by_path(c, "solver.time_limit", 600)
    return c


@pytest.fixture(scope="module")
def data(cfg):
    return load_rts_data(ROOT / cfg["paths"]["rts"])


def test_parser_topology(cfg, data):
    n = build_network(data, DAY, cfg)
    assert len(n.buses) == 73
    assert len(n.lines) + len(n.transformers) == 120          # branch.csv
    assert len(n.links) == 1                                   # dc_branch.csv
    assert int(n.generators["committable"].sum()) == 73        # Coal + NG + Oil + Nuclear
    assert len(n.snapshots) == 24
    # séries devem estar indexadas exatamente pelos snapshots (§7)
    assert n.generators_t.p_max_pu.index.equals(n.snapshots)
    assert n.loads_t.p_set.index.equals(n.snapshots)
    n.consistency_check()


def test_lpf_power_balance_and_flow_match(cfg, data):
    """Após o UC, fixa-se o despacho e roda-se ``lpf``: o balanço nodal deve
    fechar e os fluxos devem coincidir com os do problema de otimização."""
    n = build_network(data, DAY, cfg)
    solve(n, cfg)
    p0_opt = pd.concat([n.lines_t.p0, n.transformers_t.p0], axis=1).iloc[0].copy()
    n.optimize.fix_optimal_dispatch()
    err = lpf_power_balance_error(n, n.snapshots[0])
    assert err < 1e-3
    p0_lpf = pd.concat([n.lines_t.p0, n.transformers_t.p0], axis=1).iloc[0]
    assert float((p0_lpf - p0_opt).abs().max()) < 1.0       # MW


def test_scale_vre_reaches_target(cfg, data):
    n = build_network(data, DAY, cfg)
    from layers import stress_system

    stress_system(n, cfg)
    scale_vre(n, 0.7, basis="day")
    assert abs(vre_share(n) - 0.7) < 1e-6
    from layers import vre_share_annual

    scale_vre(n, 0.5, basis="annual")
    assert abs(vre_share_annual(n) - 0.5) < 1e-6


def test_vdc_workloads_complete_and_site_capacity(cfg):
    n = build_stressed_network(cfg, DAY)
    apply_layers(n, cfg, {"VDC"})
    solve(n, cfg)
    meta = n.meta["vdc"]
    links = n.links[n.links["carrier"] == "VDC"]
    eps = 1e-3
    for w in meta["workloads"]:
        e_end = float(n.stores_t.e[f"st_{w['id']}"].iloc[w["deadline"]])
        assert e_end >= w["E_it_mwh"] - eps, f"workload {w['id']} incompleto"
        # nada é consumido fora da janela
        wl = links.index[links["workload"] == w["id"]]
        outside = n.links_t.p0[wl].iloc[[t for t in range(24) if not (w["arrival"] <= t <= w["deadline"])]]
        assert float(outside.abs().max().max()) < eps
    for d, info in meta["sites"].items():
        idx = links.index[links["site"] == d]
        assert float(n.links_t.p0[idx].sum(axis=1).max()) <= info["flex_mw_elec"] + eps


def test_vpl_explicit_switching_rule(cfg):
    c = set_by_path(cfg, "vpl.mode", "explicit")
    n = build_stressed_network(c, DAY)
    apply_layers(n, c, {"VPL"})
    solve(n, c)
    dis, sto = n.storage_units_t.p_dispatch, n.storage_units_t.p_store
    eps = 1e-3
    # sem carga e descarga simultâneas em cada BESS
    for u in (VPL_UP, VPL_DOWN):
        assert float((dis[u] * sto[u]).max()) < eps
    sigma = pd.Series(n.meta["sigma"], index=n.snapshots, dtype="float")
    flow = corridor_flow(n, c)
    for t in n.snapshots:
        if pd.isna(sigma[t]):
            continue
        z = 1.0 if flow[t] > eps else (0.0 if flow[t] < -eps else None)
        if z is None:
            continue
        w_expected = z if sigma[t] == 1 else 1 - z
        if w_expected == 1:      # jusante descarrega, montante carrega
            assert sto[VPL_DOWN][t] < eps and dis[VPL_UP][t] < eps
        else:                    # inverso
            assert dis[VPL_DOWN][t] < eps and sto[VPL_UP][t] < eps
