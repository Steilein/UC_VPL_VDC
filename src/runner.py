"""
runner.py — Fase 5: construção, resolução e exportação dos cenários.

Fluxo de um caso (``run_case``):

1. ``rts_import.build_network``  → rede RTS-GMLC original do dia;
2. ``layers.stress_system``      → configuração estressada (tese / Energies 2026);
3. ``layers.scale_vre``          → penetração VRE alvo;
4. camadas: ``add_vpl`` e/ou ``add_vdc`` (ou ``add_dc_inflexible`` nos casos sem VDC);
5. ``n.optimize`` (MILP) com as restrições de ``constraints.py``;
6. re-solução LP com as binárias fixadas → preços nodais (LMP) e multiplicadores;
7. ``n.export_to_netcdf`` em ``results/<cenario>.nc`` e linha em ``results/metrics.csv``.

Casos: A (base), B (+VPL), C (+VDC), D (VPL+VDC). A grade de sensibilidades é
lida de ``config/scenarios.yaml`` (``run_grid``). O solver é parametrizado
(HiGHS para depuração, gap 0,5 %; Gurobi para a grade final, gap 0,05 %).

Uso pela linha de comando::

    python src/runner.py --day summer_peak --case D            # um caso
    python src/runner.py --grid --solver highs --quick         # grade reduzida
    python src/runner.py --grid --solver gurobi                # grade completa
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, load_config, results_dir, set_by_path, solver_options  # noqa: E402
from constraints import make_extra_functionality  # noqa: E402
from layers import add_dc_inflexible, add_vdc, add_vpl, limit_corridor, scale_vre, stress_system  # noqa: E402
from metrics import append_metrics_row, compute_metrics  # noqa: E402
from rts_import import RTSData, build_network, load_rts_data  # noqa: E402

_DATA_CACHE: dict[str, RTSData] = {}


def get_data(cfg: dict) -> RTSData:
    """Carrega os CSVs do RTS uma única vez por processo."""
    key = str(cfg["paths"]["rts"])
    if key not in _DATA_CACHE:
        _DATA_CACHE[key] = load_rts_data(ROOT / key)
    return _DATA_CACHE[key]


# -----------------------------------------------------------------------------
# Construção
# -----------------------------------------------------------------------------
def build_stressed_network(cfg: dict, day: str) -> pypsa.Network:
    """Rede estressada e escalonada para a penetração VRE alvo (Fases 1 e 2)."""
    n = build_network(get_data(cfg), day, cfg)
    stress_system(n, cfg)
    scale_vre(n, float(cfg["vre"]["target_share"]), basis=cfg["vre"].get("scaling_basis", "annual"))
    factor = cfg["corridor"].get("limit_corridor_factor")
    if factor:
        limit_corridor(n, cfg, float(factor))
    return n


def apply_layers(n: pypsa.Network, cfg: dict, layers: set[str]) -> None:
    """Aplica as camadas de flexibilidade; DCs viram carga plana quando não há VDC."""
    layers = {s.upper() for s in layers}
    if "VPL" in layers:
        add_vpl(n, cfg)
    if "VDC" in layers:
        add_vdc(n, cfg)
    else:
        add_dc_inflexible(n, cfg)
    n.meta["layers"] = sorted(layers)


# -----------------------------------------------------------------------------
# Resolução: MILP + LP para preços
# -----------------------------------------------------------------------------
def _mip_gap(n: pypsa.Network) -> float | None:
    """Gap relativo reportado pelo solver após o MILP (HiGHS ou Gurobi)."""
    sm = n.model.solver_model
    try:
        return float(sm.getInfo().mip_gap)          # HiGHS
    except Exception:
        pass
    try:
        return float(sm.MIPGap)                     # Gurobi
    except Exception:
        return None


def _fix_binaries(n: pypsa.Network) -> None:
    """Fixa todas as variáveis binárias na solução MILP e as torna contínuas.

    Com isso o modelo vira um LP cuja solução dual fornece os preços nodais
    (LMPs) e os multiplicadores dos limites de fluxo — procedimento padrão em
    mercados day-ahead (formação de preço com o commitment fixo).
    """
    m = n.model
    for name in list(m.binaries):
        var = m.variables[name]
        sol = var.solution.round()
        var.lower = sol
        var.upper = sol
        var.attrs["binary"] = False


def solve(n: pypsa.Network, cfg: dict) -> dict:
    """Resolve o UC (MILP) e a re-solução LP; devolve um dicionário de log."""
    name, mip_opts = solver_options(cfg, mip=True)
    _, lp_opts = solver_options(cfg, mip=False)
    log = bool(cfg["solver"].get("log_to_console", False))
    ef = make_extra_functionality(cfg)

    t0 = time.perf_counter()
    status, cond = n.optimize(solver_name=name, solver_options=mip_opts, extra_functionality=ef,
                              log_to_console=log)
    t_milp = time.perf_counter() - t0
    if status != "ok":
        raise RuntimeError(f"MILP não convergiu: status={status}, condição={cond}")
    info = {
        "solver": name,
        "status_milp": cond,
        "objective_milp": float(n.objective),
        "mip_gap": _mip_gap(n),
        "time_milp_s": round(t_milp, 1),
    }

    t0 = time.perf_counter()
    _fix_binaries(n)
    status_lp, cond_lp = n.optimize.solve_model(solver_name=name, solver_options=lp_opts, log_to_console=log)
    info.update({"status_lp": cond_lp, "objective_lp": float(n.objective),
                 "time_lp_s": round(time.perf_counter() - t0, 1)})
    if status_lp != "ok":
        raise RuntimeError(f"LP de preços não convergiu: {cond_lp}")

    # O solver model não é serializável nem copiável; libera memória
    n.model.solver_model = None
    n.meta["solve"] = info
    return info


# -----------------------------------------------------------------------------
# Um caso
# -----------------------------------------------------------------------------
def run_case(
    day: str,
    vre_share: float,
    layers: set[str],
    vpl_mwh: float,
    dc_flex: float,
    solver: str,
    reserve_from_flex: bool,
    cfg: dict | None = None,
    overrides: dict | None = None,
    name: str | None = None,
    tags: dict | None = None,
    post_build=None,
) -> Path:
    """Constrói, resolve e exporta um cenário; devolve o caminho do NetCDF.

    ``post_build(n, cfg)``, se dado, é chamado depois de montar a rede e aplicar
    as camadas, antes de resolver: usado para injetar condições iniciais das
    térmicas herdadas do dia anterior (ver ``extra_runs.py``).

    Parameters
    ----------
    day : str
        Data ``YYYY-MM-DD`` ou chave de ``cfg["days"]`` (ex.: ``"summer_peak"``).
    vre_share : float
        Penetração VRE alvo (0,30 / 0,50 / 0,70).
    layers : set[str]
        Subconjunto de ``{"VPL", "VDC"}``.
    vpl_mwh : float
        Energia por terminal do VPL (MWh); potência = vpl_mwh / horas.
    dc_flex : float
        Fração flexível f_d dos data centers.
    solver : str
        ``"highs"`` ou ``"gurobi"``.
    reserve_from_flex : bool
        Se VDC/VPL contam como provedores de reserva.
    overrides : dict, opcional
        Sobrescritas adicionais ``{"caminho.pontilhado": valor}`` (eixos da grade).
    """
    cfg = copy.deepcopy(cfg or load_config())
    day_key, day_date = _resolve_day(cfg, day)
    cfg = set_by_path(cfg, "vre.target_share", float(vre_share))
    cfg = set_by_path(cfg, "vpl.p_nom_mw", float(vpl_mwh) / float(cfg["vpl"]["hours"]))
    cfg = set_by_path(cfg, "vdc.flex_fraction", float(dc_flex))
    cfg = set_by_path(cfg, "solver.name", solver)
    cfg = set_by_path(cfg, "reserve.from_flex", bool(reserve_from_flex))
    for k, v in (overrides or {}).items():
        cfg = set_by_path(cfg, k, v)

    layers = {s.upper() for s in layers}
    case = {frozenset(): "A", frozenset({"VPL"}): "B", frozenset({"VDC"}): "C",
            frozenset({"VPL", "VDC"}): "D"}[frozenset(layers)]
    name = name or f"{day_key}__{case}__base"

    n = build_stressed_network(cfg, day_date)
    apply_layers(n, cfg, layers)
    if post_build is not None:      # gancho para condições iniciais herdadas (extra_runs.py)
        post_build(n, cfg)
    n.meta["scenario"] = {"name": name, "day_key": day_key, "day": day_date, "case": case,
                          "vre_share": float(vre_share), "vpl_mwh": float(vpl_mwh),
                          "dc_flex": float(dc_flex), "reserve_from_flex": bool(reserve_from_flex),
                          "vpl_mode": cfg["vpl"]["mode"],
                          "window_scale": float(cfg["vdc"]["workloads"]["window_scale"]),
                          **(tags or {})}
    n.meta["config"] = json.loads(json.dumps(cfg, default=str))

    info = solve(n, cfg)
    print(f"[{name}] obj={info['objective_milp']:,.0f} $  gap={info['mip_gap']:.2e}  "
          f"t={info['time_milp_s']}s(+{info['time_lp_s']}s LP)", flush=True)

    out = results_dir(cfg) / f"{name}.nc"
    n.export_to_netcdf(out)
    append_metrics_row(compute_metrics(n, cfg), results_dir(cfg) / "metrics.csv")
    return out


def _resolve_day(cfg: dict, day: str) -> tuple[str, str]:
    """Aceita chave (``summer_peak``) ou data (``2020-07-18``)."""
    if day in cfg["days"]:
        return day, cfg["days"][day]
    for k, v in cfg["days"].items():
        if v == day:
            return k, v
    return day.replace("-", ""), day


# -----------------------------------------------------------------------------
# Grade de sensibilidades
# -----------------------------------------------------------------------------
def run_grid(cfg: dict, scen: dict, solver: str, quick: bool = False, days: list[str] | None = None,
             skip_existing: bool = True) -> list[Path]:
    """Executa dias × casos × variações (um eixo por vez) conforme ``scenarios.yaml``.

    Variações de um eixo que não se aplicam a um caso (ex.: tamanho do VPL no
    caso A) não são re-resolvidas: a tabela de valor marginal usa a linha base.
    """
    day_keys = days or (scen["quick"]["days"] if quick else list(cfg["days"]))
    axes = {k: v for k, v in scen["axes"].items() if (not quick or k in scen["quick"]["axes"])}
    cases = scen["cases"]
    base = {
        "vre_share": float(cfg["vre"]["target_share"]),
        "vpl_mwh": float(cfg["vpl"]["p_nom_mw"]) * float(cfg["vpl"]["hours"]),
        "dc_flex": float(cfg["vdc"]["flex_fraction"]),
        "reserve_from_flex": bool(cfg["reserve"]["from_flex"]),
    }
    hours = float(cfg["vpl"]["hours"])

    # Lista de (rótulo da variação, overrides)
    variations: list[tuple[str, str, dict]] = [("base", "base", {})]
    for axis, spec in axes.items():
        for label, value in spec["values"].items():
            if label == spec["base"]:
                continue
            variations.append((axis, label, {spec["param"]: value}))

    outputs = []
    for day_key in day_keys:
        for axis, label, over in variations:
            for case, layers in cases.items():
                if axis != "base" and case not in axes[axis].get("applies_to", list(cases)):
                    continue
                name = f"{day_key}__{case}__{label}"
                out = results_dir(cfg) / f"{name}.nc"
                if skip_existing and out.exists():
                    print(f"[{name}] já existe — pulando", flush=True)
                    outputs.append(out)
                    continue
                kw = dict(base)
                # Cópia por caso: a variação original não pode ser consumida (pop)
                # pelo primeiro caso, senão os casos seguintes rodariam no valor base.
                over_case = dict(over)
                # Eixos que coincidem com argumentos explícitos de run_case
                if "vre.target_share" in over_case:
                    kw["vre_share"] = over_case.pop("vre.target_share")
                if "vpl.p_nom_mw" in over_case:
                    kw["vpl_mwh"] = float(over_case.pop("vpl.p_nom_mw")) * hours
                if "vdc.flex_fraction" in over_case:
                    kw["dc_flex"] = over_case.pop("vdc.flex_fraction")
                if "reserve.from_flex" in over_case:
                    kw["reserve_from_flex"] = over_case.pop("reserve.from_flex")
                try:
                    outputs.append(run_case(day_key, layers=set(layers), solver=solver, cfg=cfg, overrides=over_case,
                                            name=name, tags={"axis": axis, "variation": label}, **kw))
                except Exception as exc:  # registra e segue para o próximo cenário
                    print(f"[{name}] FALHOU: {exc}", flush=True)
    return outputs


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description="UC day-ahead com VPL e VDC — runner de cenários")
    p.add_argument("--config", default=str(ROOT / "config" / "base.yaml"))
    p.add_argument("--scenarios", default=str(ROOT / "config" / "scenarios.yaml"))
    p.add_argument("--solver", default=None, help="highs | gurobi (padrão: config)")
    p.add_argument("--grid", action="store_true", help="executa a grade de sensibilidades")
    p.add_argument("--quick", action="store_true", help="grade reduzida (depuração)")
    p.add_argument("--days", nargs="*", default=None, help="chaves de dias a executar")
    p.add_argument("--day", default=None, help="chave ou data de um único dia")
    p.add_argument("--case", default="A", choices=["A", "B", "C", "D"])
    p.add_argument("--vre", type=float, default=None)
    p.add_argument("--force", action="store_true", help="re-resolve mesmo se o .nc existir")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    solver = args.solver or cfg["solver"]["name"]
    if args.grid:
        scen = load_config(args.scenarios)
        run_grid(cfg, scen, solver, quick=args.quick, days=args.days, skip_existing=not args.force)
        return
    layers = {"A": set(), "B": {"VPL"}, "C": {"VDC"}, "D": {"VPL", "VDC"}}[args.case]
    run_case(
        day=args.day or list(cfg["days"])[0],
        vre_share=args.vre if args.vre is not None else float(cfg["vre"]["target_share"]),
        layers=layers,
        vpl_mwh=float(cfg["vpl"]["p_nom_mw"]) * float(cfg["vpl"]["hours"]),
        dc_flex=float(cfg["vdc"]["flex_fraction"]),
        solver=solver,
        reserve_from_flex=bool(cfg["reserve"]["from_flex"]),
        cfg=cfg,
    )


if __name__ == "__main__":
    main()
