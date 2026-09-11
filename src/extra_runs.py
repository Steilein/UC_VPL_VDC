"""
extra_runs.py — resoluções adicionais pedidas na revisão do artigo.

0. Condições iniciais herdadas (``--history``): o dia anterior a cada dia
   representativo é resolvido no caso A e o estado final das térmicas
   (ligada/desligada, potência, horas no estado) é usado como condição inicial
   dos quatro casos do dia de interesse, no lugar da regra "min_up >= 8 h começa
   ligada". Testa se as métricas de ciclagem dependem da condição de fronteira.
1. Sensibilidade ao custo de migração (``--migcost``): custo do VDC x0,5 e x2.
2. Decomposição do VPL (``--decomp``): caso B com apenas o BESS de montante
   (``vplup``) e apenas o de jusante (``vpldown``), nos quatro dias
   representativos. Valor do pareamento = ΔB − (ΔB_up + ΔB_down).
2. Dias mensais (``--monthly``): um dia útil por mês, o de energia de demanda
   líquida mais próxima da mediana mensal (excluídos os quatro dias já usados),
   casos A–D na variação base. Dá uma estimativa anual não viesada pela escolha
   dos dias extremos.

Os cenários entram em ``metrics.csv`` com ``axis = vpl_decomp`` e
``axis = monthly`` e ficam fora da tabela principal do ``summary.md``.

Uso::

    python src/extra_runs.py --decomp --monthly --solver gurobi
    python src/extra_runs.py --report          # só tabelas, a partir do metrics.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, load_config, results_dir  # noqa: E402

MONTHLY_DAYS = {
    1: "2020-01-03", 2: "2020-02-10", 3: "2020-03-18", 4: "2020-04-01", 5: "2020-05-26", 6: "2020-06-05",
    7: "2020-07-17", 8: "2020-08-24", 9: "2020-09-11", 10: "2020-10-09", 11: "2020-11-30", 12: "2020-12-07",
}
CASES = {"A": set(), "B": {"VPL"}, "C": {"VDC"}, "D": {"VPL", "VDC"}}


def _base_kw(cfg: dict) -> dict:
    return dict(vre_share=float(cfg["vre"]["target_share"]),
                vpl_mwh=float(cfg["vpl"]["p_nom_mw"]) * float(cfg["vpl"]["hours"]),
                dc_flex=float(cfg["vdc"]["flex_fraction"]),
                reserve_from_flex=bool(cfg["reserve"]["from_flex"]))


def run_decomp(cfg: dict, solver: str) -> None:
    from runner import run_case

    rdir = results_dir(cfg)
    for day in cfg["days"]:
        for label, term in (("vplup", "up"), ("vpldown", "down")):
            name = f"{day}__B__{label}"
            if (rdir / f"{name}.nc").exists():
                continue
            run_case(day, layers={"VPL"}, solver=solver, cfg=cfg, overrides={"vpl.terminals": term},
                     name=name, tags={"axis": "vpl_decomp", "variation": label}, **_base_kw(cfg))


def run_monthly(cfg: dict, solver: str) -> None:
    from runner import run_case

    rdir = results_dir(cfg)
    for m, date in MONTHLY_DAYS.items():
        key = f"m{m:02d}"
        for case, layers in CASES.items():
            name = f"{key}__{case}__base"
            if (rdir / f"{name}.nc").exists():
                continue
            cfg_m = dict(cfg)
            cfg_m["days"] = {**cfg["days"], key: date}
            run_case(key, layers=layers, solver=solver, cfg=cfg_m, name=name,
                     tags={"axis": "monthly", "variation": "base", "month": m}, **_base_kw(cfg))


def initial_state_from(nc_path: Path) -> dict:
    """Estado final das térmicas de uma rede resolvida: status, potência e
    quantas horas consecutivas cada unidade terminou o dia no mesmo estado."""
    import pypsa

    n = pypsa.Network(str(nc_path))
    st = n.generators_t.status
    p = n.generators_t.p
    out = {}
    for g in st.columns:
        v = (st[g].values > 0.5)
        last = bool(v[-1])
        streak = 1
        for k in range(len(v) - 2, -1, -1):
            if bool(v[k]) == last:
                streak += 1
            else:
                break
        out[g] = dict(on=last, streak=int(streak), p=float(p[g].iloc[-1]) if g in p else 0.0)
    return out


def apply_initial_state(state: dict):
    """Devolve um ``post_build(n, cfg)`` que injeta o estado inicial herdado."""

    def _hook(n, cfg):
        for g, s in state.items():
            if g not in n.generators.index:
                continue
            n.generators.loc[g, "up_time_before"] = s["streak"] if s["on"] else 0
            n.generators.loc[g, "down_time_before"] = 0 if s["on"] else s["streak"]
            n.generators.loc[g, "p_init"] = s["p"] if s["on"] else 0.0
        n.meta["initial_state"] = "inherited from previous day (case A)"

    return _hook


def run_history(cfg: dict, solver: str) -> None:
    """Resolve o dia anterior (caso A) e os quatro casos do dia com o estado herdado."""
    from datetime import datetime, timedelta

    from runner import run_case

    rdir = results_dir(cfg)
    for day, date in cfg["days"].items():
        prev = (datetime.fromisoformat(date) - timedelta(days=1)).date().isoformat()
        prev_name = f"{day}__A__prevday"
        prev_nc = rdir / f"{prev_name}.nc"
        if not prev_nc.exists():
            cfg_p = dict(cfg, days={**cfg["days"], f"{day}_prev": prev})
            run_case(f"{day}_prev", layers=set(), solver=solver, cfg=cfg_p, name=prev_name,
                     tags={"axis": "history", "variation": "prevday"}, **_base_kw(cfg))
        state = initial_state_from(prev_nc)
        for case, layers in CASES.items():
            name = f"{day}__{case}__hist"
            if (rdir / f"{name}.nc").exists():
                continue
            run_case(day, layers=layers, solver=solver, cfg=cfg, name=name,
                     tags={"axis": "history", "variation": "hist"},
                     post_build=apply_initial_state(state), **_base_kw(cfg))


def run_migcost(cfg: dict, solver: str) -> None:
    """Sensibilidade ao custo de migração do VDC (x0,5 e x2)."""
    from runner import run_case

    rdir = results_dir(cfg)
    lo, hi = cfg["vdc"]["workloads"]["migration_cost_range"]
    for label, k in (("mig05", 0.5), ("mig20", 2.0)):
        for day in cfg["days"]:
            for case, layers in (("C", {"VDC"}), ("D", {"VPL", "VDC"})):
                name = f"{day}__{case}__{label}"
                if (rdir / f"{name}.nc").exists():
                    continue
                run_case(day, layers=layers, solver=solver, cfg=cfg,
                         overrides={"vdc.workloads.migration_cost_range": [lo * k, hi * k]},
                         name=name, tags={"axis": "migration_cost", "variation": label}, **_base_kw(cfg))


def run_native(cfg: dict, solver: str) -> None:
    """A e B com o baseline 'native' (mesmos jobs no site nativo, EDF desde a chegada)."""
    from runner import run_case

    rdir = results_dir(cfg)
    for day in cfg["days"]:
        for case, layers in (("A", set()), ("B", {"VPL"})):
            name = f"{day}__{case}__native"
            if (rdir / f"{name}.nc").exists():
                continue
            run_case(day, layers=layers, solver=solver, cfg=cfg, overrides={"vdc.baseline": "native"},
                     name=name, tags={"axis": "baseline", "variation": "native"}, **_base_kw(cfg))


def run_soc(cfg: dict, solver: str) -> None:
    """B e D com o SOC inicial dos BESS ancorado em 50 % de e_nom."""
    from runner import run_case

    rdir = results_dir(cfg)
    for day in cfg["days"]:
        for case, layers in (("B", {"VPL"}), ("D", {"VPL", "VDC"})):
            name = f"{day}__{case}__soc50"
            if (rdir / f"{name}.nc").exists():
                continue
            run_case(day, layers=layers, solver=solver, cfg=cfg, overrides={"vpl.soc_initial": 0.5},
                     name=name, tags={"axis": "soc_initial", "variation": "soc50"}, **_base_kw(cfg))


def run_leituras400(cfg: dict, solver: str) -> None:
    """VPL de 400 MW sob as três leituras: emergente, explícita e dedicada.

    No porte base a interação fica dentro do ruído do gap nas três leituras, então
    a comparação só é informativa onde o sinal de competição é mensurável, isto é,
    com VPL grande. A leitura emergente de 400 MW já vem da grade (``vpl400``);
    aqui resolvem-se as duas variantes com regra de chaveamento.
    """
    from runner import run_case

    rdir = results_dir(cfg)
    hours = float(cfg["vpl"]["hours"])
    kw = _base_kw(cfg)
    kw["vpl_mwh"] = 400.0 * hours
    for day in cfg["days"]:
        for case, layers in (("B", {"VPL"}), ("D", {"VPL", "VDC"})):
            for tag, mode in (("vpl400dedic", "dedicated"), ("vpl400explic", "explicit")):
                name = f"{day}__{case}__{tag}"
                if (rdir / f"{name}.nc").exists():
                    continue
                run_case(day, layers=layers, solver=solver, cfg=cfg,
                         overrides={"vpl.mode": mode, "vpl.p_nom_mw": 400},
                         name=name, tags={"axis": "vpl_mode_size", "variation": tag}, **kw)


def report(cfg: dict) -> None:
    df = pd.read_csv(results_dir(cfg) / "metrics.csv").set_index("scenario")
    lines = ["# Resoluções adicionais — decomposição do VPL e dias mensais\n"]

    # 1. decomposição
    rows = []
    for day in cfg["days"]:
        try:
            A = df.loc[f"{day}__A__base", "cost_total"]
            B = df.loc[f"{day}__B__base", "cost_total"]
            up = df.loc[f"{day}__B__vplup", "cost_total"]
            dn = df.loc[f"{day}__B__vpldown", "cost_total"]
            vc_b = df.loc[f"{day}__B__base", "vpl_virtual_mwh"]
        except KeyError:
            continue
        dB, dUp, dDn = A - B, A - up, A - dn
        rows.append(dict(day=day, dB=dB, dB_up=dUp, dB_down=dDn, pairing=dB - (dUp + dDn),
                         pairing_pct=100 * (dB - (dUp + dDn)) / dB if dB else float("nan"), virtual_mwh=vc_b))
    dec = pd.DataFrame(rows)
    if not dec.empty:
        dec.loc["média"] = dec.drop(columns="day").mean(numeric_only=True)
        dec.loc["média", "day"] = "média"
        lines.append("## 1. Decomposição do benefício do VPL (caso B, 50 % VRE), $/dia\n")
        lines.append("ΔB = benefício do par; ΔB_up / ΔB_down = benefício de cada BESS sozinho (arbitragem nodal isolada); "
                     "pairing = ΔB − (ΔB_up + ΔB_down) = valor atribuível ao pareamento nos dois terminais.\n")
        lines.append(dec.round(0).to_markdown(index=False) + "\n")

    # 1b. baseline native
    rows = []
    for day in cfg["days"]:
        try:
            A, B = df.loc[f"{day}__A__base", "cost_total"], df.loc[f"{day}__B__base", "cost_total"]
            C, D = df.loc[f"{day}__C__base", "cost_total"], df.loc[f"{day}__D__base", "cost_total"]
            An, Bn = df.loc[f"{day}__A__native", "cost_total"], df.loc[f"{day}__B__native", "cost_total"]
            sA, sAn = df.loc[f"{day}__A__base", "startups_total"], df.loc[f"{day}__A__native", "startups_total"]
            sC = df.loc[f"{day}__C__base", "startups_total"]
        except KeyError:
            continue
        rows.append(dict(day=day, dC_flat=A - C, dC_native=An - C, dD_flat=A - D, dD_native=An - Bn + Bn - D,
                         I_flat=(A - D) - ((A - B) + (A - C)), I_native=(An - D) - ((An - Bn) + (An - C)),
                         startups_A_flat=sA, startups_A_native=sAn, startups_C=sC))
    nat = pd.DataFrame(rows)
    if not nat.empty:
        nat.loc["média"] = nat.drop(columns="day").mean(numeric_only=True)
        nat.loc["média", "day"] = "média"
        lines.append("## 1b. Sensibilidade ao baseline dos casos A/B: flat vs. native, $/dia\n")
        lines.append("flat = energia dos workloads distribuída uniformemente; native = mesmos jobs no site nativo, EDF desde a chegada.\n")
        lines.append(nat.round(0).to_markdown(index=False) + "\n")

    # 1c. condições iniciais herdadas
    rows = []
    for day in cfg["days"]:
        try:
            base = {c: df.loc[f"{day}__{c}__base"] for c in "ABCD"}
            hist = {c: df.loc[f"{day}__{c}__hist"] for c in "ABCD"}
        except KeyError:
            continue
        rows.append(dict(
            day=day,
            su_A=base["A"].startups_total, su_A_h=hist["A"].startups_total,
            su_D=base["D"].startups_total, su_D_h=hist["D"].startups_total,
            dsu_base=base["A"].startups_total - base["D"].startups_total,
            dsu_hist=hist["A"].startups_total - hist["D"].startups_total,
            I_base=(base["A"].cost_total - base["D"].cost_total)
            - ((base["A"].cost_total - base["B"].cost_total) + (base["A"].cost_total - base["C"].cost_total)),
            I_hist=(hist["A"].cost_total - hist["D"].cost_total)
            - ((hist["A"].cost_total - hist["B"].cost_total) + (hist["A"].cost_total - hist["C"].cost_total)),
        ))
    h = pd.DataFrame(rows)
    if not h.empty:
        h.loc["média"] = h.drop(columns="day").mean(numeric_only=True)
        h.loc["média", "day"] = "média"
        lines.append("## 1c. Condições iniciais: regra padrão vs. herdadas do dia anterior\n")
        lines.append("su = partidas; dsu = partidas evitadas por D; I = interação de custo ($/dia).\n")
        lines.append(h.round(1).to_markdown(index=False) + "\n")

    # 1d. custo de migração
    rows = []
    for day in cfg["days"]:
        r = {"day": day}
        ok = True
        for lbl, tag in (("base", "base"), ("x0,5", "mig05"), ("x2", "mig20")):
            try:
                A = df.loc[f"{day}__A__base", "cost_total"]
                r[f"dC {lbl}"] = A - df.loc[f"{day}__C__{tag}", "cost_total"]
                r[f"dD {lbl}"] = A - df.loc[f"{day}__D__{tag}", "cost_total"]
            except KeyError:
                ok = False
        if ok:
            rows.append(r)
    mg = pd.DataFrame(rows)
    if not mg.empty:
        mg.loc["média"] = mg.drop(columns="day").mean(numeric_only=True)
        mg.loc["média", "day"] = "média"
        lines.append("## 1d. Sensibilidade ao custo de migração do VDC ($/dia)\n")
        lines.append(mg.round(0).to_markdown(index=False) + "\n")

    # 1e. SOC inicial ancorado
    rows = []
    for day in cfg["days"]:
        try:
            A = df.loc[f"{day}__A__base", "cost_total"]
            B, D = df.loc[f"{day}__B__base", "cost_total"], df.loc[f"{day}__D__base", "cost_total"]
            Bs, Ds = df.loc[f"{day}__B__soc50", "cost_total"], df.loc[f"{day}__D__soc50", "cost_total"]
            C = df.loc[f"{day}__C__base", "cost_total"]
        except KeyError:
            continue
        rows.append(dict(day=day, dB_livre=A - B, dB_soc50=A - Bs, dD_livre=A - D, dD_soc50=A - Ds,
                         I_livre=(A - D) - ((A - B) + (A - C)),
                         I_soc50=(A - Ds) - ((A - Bs) + (A - C))))
    soc = pd.DataFrame(rows)
    if not soc.empty:
        soc.loc["média"] = soc.drop(columns="day").mean(numeric_only=True)
        soc.loc["média", "day"] = "média"
        lines.append("## 1e. SOC inicial do VPL: livre (ciclo fechado) vs. ancorado em 50 %\n")
        lines.append(soc.round(0).to_markdown(index=False) + "\n")

    # 2. dias mensais
    mon = df[df["axis"] == "monthly"] if "axis" in df else df.iloc[0:0]
    if not mon.empty:
        piv = mon.pivot_table(index="day_key", columns="case", values=["cost_total", "curtailment_mwh", "startups_total", "co2_t"])
        cost = piv["cost_total"]
        tab = pd.DataFrame({
            "A": cost["A"], "ΔB": cost["A"] - cost["B"], "ΔC": cost["A"] - cost["C"], "ΔD": cost["A"] - cost["D"],
        })
        tab["I"] = tab["ΔD"] - (tab["ΔB"] + tab["ΔC"])
        gaps = mon.pivot_table(index="day_key", columns="case", values="mip_gap")
        tab["ruído"] = (gaps * cost).sum(axis=1)
        tab["curt_A_MWh"] = piv["curtailment_mwh"]["A"]
        tab["curt_red_D_%"] = 100 * (1 - piv["curtailment_mwh"]["D"] / piv["curtailment_mwh"]["A"])
        tab["startups_A"] = piv["startups_total"]["A"]
        tab["startups_D"] = piv["startups_total"]["D"]
        tab.loc["média"] = tab.mean(numeric_only=True)
        lines.append("## 2. Dias mensais (um dia útil mediano por mês), variação base, $/dia\n")
        lines.append(tab.round(1).to_markdown() + "\n")
        a = cost["A"].sum(); d = cost["D"].sum()
        lines.append(f"Redução de custo D vs A, soma dos 12 dias: {100 * (a - d) / a:.1f} %; "
                     f"ΔB {100 * (a - cost['B'].sum()) / a:.1f} %; ΔC {100 * (a - cost['C'].sum()) / a:.1f} %. "
                     f"Curtailment D vs A: {100 * (1 - piv['curtailment_mwh']['D'].sum() / piv['curtailment_mwh']['A'].sum()):.1f} %; "
                     f"partidas D vs A: {100 * (1 - piv['startups_total']['D'].sum() / piv['startups_total']['A'].sum()):.1f} %. "
                     f"I médio {tab.loc['média', 'I']:.0f} $/dia; I < 0 em {(tab['I'].iloc[:-1] < 0).sum()} de {len(tab) - 1} dias; "
                     f"|I| > 2×ruído em {((tab['I'].iloc[:-1].abs()) > 2 * tab['ruído'].iloc[:-1]).sum()} dias.\n")
    out = results_dir(cfg) / "extra_runs.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--solver", default=None)
    ap.add_argument("--decomp", action="store_true")
    ap.add_argument("--monthly", action="store_true")
    ap.add_argument("--native", action="store_true")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--migcost", action="store_true")
    ap.add_argument("--soc", action="store_true")
    ap.add_argument("--leituras", action="store_true",
                    help="VPL 400 MW nas variantes explícita e dedicada")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config()
    solver = args.solver or cfg["solver"]["name"]
    if args.decomp:
        run_decomp(cfg, solver)
    if args.monthly:
        run_monthly(cfg, solver)
    if args.native:
        run_native(cfg, solver)
    if args.history:
        run_history(cfg, solver)
    if args.migcost:
        run_migcost(cfg, solver)
    if args.soc:
        run_soc(cfg, solver)
    if args.leituras:
        run_leituras400(cfg, solver)
    report(cfg)


if __name__ == "__main__":
    main()
