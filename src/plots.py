"""
plots.py — Fase 7: figuras do artigo (estilo IEEE).

Convenções gráficas:
* coluna única = 3,5 in de largura (dupla = 7,16 in), fonte 8 pt, sem título
  dentro da figura (a legenda vai no caption do artigo), exportação em PDF
  vetorial (+ PNG de conferência);
* um único eixo y por painel (nunca eixo duplo): grandezas diferentes vão em
  painéis empilhados que compartilham o eixo do tempo;
* paleta categórica fixa e validada para daltonismo (8 posições, ordem fixa);
  os combustíveis são agrupados em 8 séries de despacho e os casos A–D usam as
  quatro primeiras posições;
* curtailment desenhado com hachura (textura), redundante à cor.

Figuras (§10 do brief):
1. Mapa do RTS-GMLC com corredor, sites de DC e VPL destacados.
2. Despacho empilhado por combustível, casos A e D, dia 1 (curtailment hachurado).
3. Fluxo no corredor vs. limite + SOC dos dois BESS do VPL, faixas de sigma_t.
4. Heatmap da carga VDC por site × hora, casos C e D.
5. Spread de LMP nos terminais do corredor, casos A–D.
6. Sensibilidade: custo, curtailment e partidas vs. penetração VRE, quatro casos.
7. Barras de complementaridade (ΔB + ΔC) − ΔD (benefício conjunto − soma) por dia e penetração.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pypsa

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import figures_dir, load_config, results_dir  # noqa: E402
from layers import VPL_DOWN, VPL_UP, corridor_flow, corridor_limit  # noqa: E402
from metrics import marginal_value_table  # noqa: E402

# --- Idioma dos rótulos: PLOTS_LANG=pt (padrão) | en (figuras do artigo, gravadas em figures/en/)
import os

LANG = os.environ.get("PLOTS_LANG", "pt").lower()
_TR = {
    "Nuclear": "Nuclear", "Carvão": "Coal", "Gás CC": "Gas CC", "Gás CT": "Gas CT", "Óleo": "Oil",
    "Hidro": "Hydro", "Eólica": "Wind", "Solar": "Solar",
    "Área": "Area", "Corredor N_318–N_223": "Corridor 318–223", "Terminais do VPL": "VPL terminals",
    "Sites de data center": "Data-center sites", "Longitude (°)": "Longitude (°)", "Latitude (°)": "Latitude (°)",
    "(a) Caso A": "(a) Case A", "(b) Caso D": "(b) Case D", "(a) Caso C": "(a) Case C",
    "Armazenamento": "Storage", "Curtailment": "Curtailment", "Carga": "Load", "Hora": "Hour",
    "Potência (MW)": "Power (MW)", "Fluxo 318→223": "Flow 318→223", "Limite térmico": "Thermal limit",
    "Fluxo (MW)": "Flow (MW)", "BESS 318 (montante)": "BESS 318 (upstream)", "BESS 223 (jusante)": "BESS 223 (downstream)",
    "faixas: σ=1 (laranja), σ=0 (azul)": "bands: σ=1 (orange), σ=0 (blue)", "Carga do site (MW)": "Site load (MW)",
    "Penetração VRE (%)": "VRE penetration (%)", "Partidas térmicas (n/dia)": "Thermal start-ups (per day)",
    "(ΔB + ΔC) − ΔD  (k$/dia)": "I = ΔD − (ΔB + ΔC)  (k$/day)", "< 0: substitutos   > 0: complementares": "< 0: substitutes   > 0: complements",
    "custo (k$/dia)": "cost (k$/day)", "curtailment (%)": "curtailment (%)", "partidas": "start-ups",
    "VPL (MW/terminal)": "VPL (MW per terminal)", "fração flexível $f_d$": "flexible fraction $f_d$",
    "largura da janela batch (×)": "batch window width (×)", "caso": "case", "média": "mean",
    "custo (k$)": "cost (k$)", "curtailment (%)": "curtailment (%)",
    "A: base": "A: base", "B: +VPL": "B: +VPL", "C: +VDC": "C: +VDC", "D: VPL+VDC": "D: VPL+VDC",
}


def T(s: str) -> str:
    """Traduz um rótulo quando PLOTS_LANG=en; devolve o original caso contrário."""
    return _TR.get(s, s) if LANG == "en" else s


# --- Paleta categórica validada (ordem fixa; ver skill dataviz / palette.md)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CASE_COLORS = dict(zip("ABCD", PALETTE[:4]))
CASE_LABELS = {"A": "A: base", "B": "B: +VPL", "C": "C: +VDC", "D": "D: VPL+VDC"}
# Grupos de despacho em ordem de mérito (base → ponta → renováveis)
DISPATCH_GROUPS = {
    "Nuclear": ["Nuclear"], "Carvão": ["Coal"], "Gás CC": ["Gas CC"], "Gás CT": ["Gas CT"],
    "Óleo": ["Oil CT", "Oil ST"], "Hidro": ["Hydro"], "Eólica": ["Wind"], "Solar": ["Solar PV", "Solar RTPV", "CSP"],
}
GROUP_COLORS = dict(zip(DISPATCH_GROUPS, PALETTE))
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
W1, W2 = 3.5, 7.16   # polegadas


def ieee_style() -> None:
    plt.rcParams.update({
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8, "legend.fontsize": 7,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"], "axes.edgecolor": INK2, "axes.linewidth": 0.6,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
        "xtick.color": INK2, "ytick.color": INK2, "axes.labelcolor": INK, "text.color": INK,
        "legend.frameon": False, "lines.linewidth": 1.2, "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.spines.top": False, "axes.spines.right": False,
    })


def save(fig, fdir: Path, name: str) -> None:
    if LANG == "en":
        fdir = fdir / "en"
        fdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fdir / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(fdir / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}.pdf")


def load_net(rdir: Path, name: str) -> pypsa.Network | None:
    p = rdir / f"{name}.nc"
    return pypsa.Network(str(p)) if p.exists() else None


# -----------------------------------------------------------------------------
# 1. Mapa
# -----------------------------------------------------------------------------
def fig1_map(n: pypsa.Network, cfg: dict, fdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(W1, 3.2))
    b = n.buses[n.buses["carrier"] == "AC"]
    segs = [[(b.at[r.bus0, "x"], b.at[r.bus0, "y"]), (b.at[r.bus1, "x"], b.at[r.bus1, "y"])]
            for r in pd.concat([n.lines, n.transformers]).itertuples()]
    ax.add_collection(LineCollection(segs, colors="#b8b7b1", linewidths=0.5, zorder=1))
    for area, col in zip((1, 2, 3), PALETTE[:3]):
        sel = b[b["area"] == area]
        ax.scatter(sel["x"], sel["y"], s=8, color=col, label=f"{T('Área')} {area}", zorder=3, linewidths=0)
    # corredor
    c = cfg["corridor"]
    for uid in c["branches"]:
        r = n.lines.loc[uid]
        ax.plot([b.at[r.bus0, "x"], b.at[r.bus1, "x"]], [b.at[r.bus0, "y"], b.at[r.bus1, "y"]],
                color=PALETTE[7], lw=2.2, zorder=2, label=T("Corredor N_318–N_223") if uid == c["branches"][0] else None)
    for bus, tag in ((c["bus_up"], "318 (VPL↑)"), (c["bus_down"], "223 (VPL↓)")):
        ax.scatter(b.at[str(bus), "x"], b.at[str(bus), "y"], marker="^", s=45, facecolor="white",
                   edgecolor=PALETTE[7], linewidths=1.2, zorder=4)
        ax.annotate(tag, (b.at[str(bus), "x"], b.at[str(bus), "y"]), xytext=(-6, 7), textcoords="offset points",
                    fontsize=6, ha="right" if str(bus) == str(c["bus_up"]) else "left")
    for s in cfg["vdc"]["sites"]:
        ax.scatter(b.at[str(s["bus"]), "x"], b.at[str(s["bus"]), "y"], marker="s", s=40, facecolor="white",
                   edgecolor=INK, linewidths=1.0, zorder=4)
        ax.annotate(s["name"], (b.at[str(s["bus"]), "x"], b.at[str(s["bus"]), "y"]), xytext=(4, -8),
                    textcoords="offset points", fontsize=6)
    ax.scatter([], [], marker="^", facecolor="white", edgecolor=PALETTE[7], label=T("Terminais do VPL"))
    ax.scatter([], [], marker="s", facecolor="white", edgecolor=INK, label=T("Sites de data center"))
    ax.set_xlabel(T("Longitude (°)")); ax.set_ylabel(T("Latitude (°)"))
    ax.grid(False)
    ax.legend(loc="lower left", fontsize=6, ncol=2, handletextpad=0.3, columnspacing=0.8)
    save(fig, fdir, "fig1_map")


# -----------------------------------------------------------------------------
# 2. Despacho empilhado
# -----------------------------------------------------------------------------
def _dispatch_frame(n: pypsa.Network) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    p = n.generators_t.p
    df = pd.DataFrame({g: p[n.generators.index[n.generators["carrier"].isin(c)]].sum(axis=1)
                       for g, c in DISPATCH_GROUPS.items()})
    su = n.storage_units_t.p if not n.storage_units.empty else pd.DataFrame(index=n.snapshots)
    storage = su.sum(axis=1) if not su.empty else pd.Series(0.0, index=n.snapshots)
    vre = n.generators.index[n.generators["is_vre"]]
    avail = (n.get_switchable_as_dense("Generator", "p_max_pu")[vre] * n.generators.loc[vre, "p_nom"]).sum(axis=1)
    curt = (avail - p[vre].sum(axis=1)).clip(lower=0)
    load = n.get_switchable_as_dense("Load", "p_set").sum(axis=1)
    return df, storage, curt, load


def fig2_dispatch(nA: pypsa.Network, nD: pypsa.Network, fdir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(W2, 2.6), sharey=True)
    for ax, n, tag in zip(axes, (nA, nD), (T("(a) Caso A"), T("(b) Caso D"))):
        df, storage, curt, load = _dispatch_frame(n)
        h = np.arange(24)
        bottom = np.zeros(24)
        for g in DISPATCH_GROUPS:
            ax.fill_between(h, bottom, bottom + df[g].values, step="mid", color=GROUP_COLORS[g], lw=0, label=T(g))
            bottom += df[g].values
        # descarga de armazenamento (positiva) empilhada por cima; carga como linha
        dis = storage.clip(lower=0).values
        ax.fill_between(h, bottom, bottom + dis, step="mid", facecolor="none", edgecolor=INK2, hatch="....", lw=0.3, label=T("Armazenamento"))
        top = bottom + dis
        ax.fill_between(h, top, top + curt.values, step="mid", facecolor="none", edgecolor=PALETTE[6], hatch="////", lw=0.3, label=T("Curtailment"))
        ax.step(h, load.values, where="mid", color=INK, lw=1.0, label=T("Carga"))
        ax.set_xlim(-0.5, 23.5); ax.set_xticks([0, 6, 12, 18, 23]); ax.set_xlabel(T("Hora"))
        ax.text(0.02, 0.97, tag, transform=ax.transAxes, va="top", fontsize=7)
        # O total precisa estar escrito: a diferenca de curtailment entre A e D e de
        # ~8 %, pequena demais para ser lida na area hachurada.
        vre_disp = float(df["Eólica"].sum() + df["Solar"].sum())
        avail = float(curt.sum()) + vre_disp
        pct = 100 * float(curt.sum()) / avail if avail > 0 else float("nan")
        ax.text(0.98, 0.97, T("curtailment") + f": {curt.sum()/1e3:.1f} GWh ({pct:.0f} %)",
                transform=ax.transAxes, va="top", ha="right", fontsize=6.5,
                color=PALETTE[6])
    axes[0].set_ylabel(T("Potência (MW)"))
    axes[0].set_ylim(0, None)
    axes[1].legend(loc="upper center", bbox_to_anchor=(-0.1, -0.22), ncol=6, fontsize=6, handlelength=1.4)
    save(fig, fdir, "fig2_dispatch")


# -----------------------------------------------------------------------------
# 3. Corredor + SOC do VPL
# -----------------------------------------------------------------------------
def fig3_corridor(n: pypsa.Network, cfg: dict, fdir: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(W1, 3.4), sharex=True, gridspec_kw={"hspace": 0.12})
    h = np.arange(24)
    flow = corridor_flow(n, cfg); lim = corridor_limit(n, cfg)
    sigma = n.meta.get("sigma")
    if sigma is not None:
        s = pd.Series(sigma, index=n.snapshots, dtype="float").values
        for ax in (ax1, ax2):
            for t in h:
                if s[t] == 1:
                    ax.axvspan(t - 0.5, t + 0.5, color=PALETTE[1], alpha=0.12, lw=0)
                elif s[t] == 0:
                    ax.axvspan(t - 0.5, t + 0.5, color=PALETTE[0], alpha=0.12, lw=0)
    ax1.step(h, flow.values, where="mid", color=INK, label=T("Fluxo 318→223"))
    ax1.axhline(lim, color=PALETTE[7], ls="--", lw=0.8, label=T("Limite térmico"))
    ax1.axhline(-lim, color=PALETTE[7], ls="--", lw=0.8)
    ax1.set_ylabel(T("Fluxo (MW)"))
    ax1.legend(loc="center left", fontsize=6, ncol=2)
    soc = n.storage_units_t.state_of_charge
    e_cap = n.storage_units.loc[VPL_UP, "p_nom"] * n.storage_units.loc[VPL_UP, "max_hours"]
    ax2.step(h, 100 * soc[VPL_UP].values / e_cap, where="mid", color=PALETTE[2], label=T("BESS 318 (montante)"))
    ax2.step(h, 100 * soc[VPL_DOWN].values / e_cap, where="mid", color=PALETTE[6], label=T("BESS 223 (jusante)"))
    ax2.set_ylabel("SOC (%)"); ax2.set_ylim(0, 105); ax2.set_xlabel(T("Hora"))
    ax2.set_xlim(-0.5, 23.5); ax2.set_xticks([0, 6, 12, 18, 23])
    ax2.legend(loc="upper left", fontsize=6, ncol=1)
    if sigma is not None:
        ax1.text(0.99, 0.10, T("faixas: σ=1 (laranja), σ=0 (azul)"), transform=ax1.transAxes, ha="right", va="bottom", fontsize=6, color=INK2)
    save(fig, fdir, "fig3_corridor_vpl")


# -----------------------------------------------------------------------------
# 4. Heatmap VDC
# -----------------------------------------------------------------------------
def _vdc_site_load(n: pypsa.Network) -> pd.DataFrame:
    meta = n.meta["vdc"]
    links = n.links[n.links["carrier"] == "VDC"]
    out = {}
    for d, info in meta["sites"].items():
        idx = links.index[links["site"] == d]
        inflex = n.loads_t.p_set.get(f"L_{d}_inflex", pd.Series(0.0, index=n.snapshots))
        out[d] = n.links_t.p0[idx].sum(axis=1) + inflex
    return pd.DataFrame(out).T


def fig4_vdc_heatmap(nC: pypsa.Network, nD: pypsa.Network, fdir: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(W1, 2.6), sharex=True, gridspec_kw={"hspace": 0.35})
    mats = [_vdc_site_load(nC), _vdc_site_load(nD)]
    vmax = max(m.values.max() for m in mats)
    for ax, m, tag in zip(axes, mats, (T("(a) Caso C"), T("(b) Caso D"))):
        im = ax.imshow(m.values, aspect="auto", cmap="Blues", vmin=0, vmax=vmax)
        ax.set_yticks(range(len(m.index))); ax.set_yticklabels(m.index)
        ax.set_title(tag, loc="left", fontsize=7, pad=2); ax.grid(False)
    axes[1].set_xticks([0, 6, 12, 18, 23]); axes[1].set_xlabel(T("Hora"))
    cb = fig.colorbar(im, ax=axes, fraction=0.04, pad=0.02); cb.set_label(T("Carga do site (MW)"))
    save(fig, fdir, "fig4_vdc_heatmap")


# -----------------------------------------------------------------------------
# 5. Spread de LMP
# -----------------------------------------------------------------------------
def fig5_lmp_spread(nets: dict[str, pypsa.Network], cfg: dict, fdir: Path) -> None:
    fig, ax = plt.subplots(figsize=(W1, 2.2))
    c = cfg["corridor"]; h = np.arange(24)
    for case, n in nets.items():
        mp = n.buses_t.marginal_price
        ax.step(h, (mp[str(c["bus_down"])] - mp[str(c["bus_up"])]).values, where="mid",
                color=CASE_COLORS[case], label=CASE_LABELS[case])
    ax.axhline(0, color=INK2, lw=0.5)
    ax.set_xlim(-0.5, 23.5); ax.set_xticks([0, 6, 12, 18, 23]); ax.set_xlabel(T("Hora"))
    ax.set_ylabel("LMP$_{223}$ − LMP$_{318}$ (\\$/MWh)")
    ax.legend(ncol=4, fontsize=6, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    save(fig, fdir, "fig5_lmp_spread")


# -----------------------------------------------------------------------------
# 6. Sensibilidade à penetração VRE
# -----------------------------------------------------------------------------
def fig6_sensitivity(df: pd.DataFrame, fdir: Path) -> None:
    sub = df[df["axis"].isin(["base", "vre_share"])]
    agg = sub.groupby(["case", "vre_share"])[["cost_total", "curtailment_pct", "startups_total"]].mean().reset_index()
    fig, axes = plt.subplots(1, 3, figsize=(W2, 2.0))
    specs = [("cost_total", "Custo total (M$/dia)", 1e-6), ("curtailment_pct", "Curtailment VRE (%)", 1),
             ("startups_total", T("Partidas térmicas (n/dia)"), 1)]
    for ax, (col, lab, k) in zip(axes, specs):
        for case in "ABCD":
            d = agg[agg["case"] == case].sort_values("vre_share")
            ax.plot(100 * d["vre_share"], k * d[col], marker="o", ms=3.5, color=CASE_COLORS[case], label=CASE_LABELS[case])
        ax.set_xlabel(T("Penetração VRE (%)")); ax.set_ylabel(T(lab)); ax.set_xticks([30, 50, 70])
    axes[0].legend(fontsize=6, loc="best")
    save(fig, fdir, "fig6_vre_sensitivity")


# -----------------------------------------------------------------------------
# 7. Complementaridade
# -----------------------------------------------------------------------------
def fig7_complementarity(df: pd.DataFrame, fdir: Path, scenarios: dict | None = None) -> None:
    mv = marginal_value_table(df, scenarios=scenarios).dropna(subset=["complementarity"])
    mv = mv[mv["axis"].isin(["base", "vre_share"])].copy()
    label = {"vre30": "30 %", "base": "50 %", "vre70": "70 %"}
    mv["pen"] = mv["variation"].map(label)
    days = list(dict.fromkeys(mv["day_key"]))
    pens = [p for p in ("30 %", "50 %", "70 %") if p in set(mv["pen"])]
    fig, ax = plt.subplots(figsize=(W1, 2.2))
    x = np.arange(len(days)); wbar = 0.8 / max(len(pens), 1)
    for i, p in enumerate(pens):
        vals = [mv[(mv["day_key"] == d) & (mv["pen"] == p)]["complementarity"].sum() / 1e3 for d in days]
        ax.bar(x + (i - (len(pens) - 1) / 2) * wbar, vals, width=wbar * 0.92, color=PALETTE[i], label=f"VRE {p}", lw=0)
    ax.axhline(0, color=INK2, lw=0.6)
    ax.set_xticks(x); ax.set_xticklabels([d.replace("_", "\n") for d in days], fontsize=6)
    ax.set_ylabel(T("(ΔB + ΔC) − ΔD  (k$/dia)"))
    ax.text(0.01, 0.02, T("< 0: substitutos   > 0: complementares"), transform=ax.transAxes, fontsize=6, color=INK2)
    ax.legend(fontsize=6, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.12))
    save(fig, fdir, "fig7_complementarity")


# -----------------------------------------------------------------------------
# 9. Sensibilidade ao dimensionamento (Fig. 5 do artigo)
# -----------------------------------------------------------------------------
def fig9_sizing(df: pd.DataFrame, fdir: Path) -> None:
    """Custo, curtailment e partidas (média entre dias) vs. potência do VPL,
    fração flexível f_d e largura da janela batch; uma linha por caso."""
    axes_spec = [
        ("vpl_size", "vpl_mwh", T("VPL (MW/terminal)"), lambda v: v / 4.0, ["B", "D"]),
        ("dc_flex", "dc_flex", T("fração flexível $f_d$"), lambda v: v, ["C", "D"]),
        ("window_scale", "window_scale", T("largura da janela batch (×)"), lambda v: v, ["C", "D"]),
    ]
    metrics = [("cost_total", T("custo (k$/dia)"), 1e-3), ("curtailment_pct", T("curtailment (%)"), 1.0),
               ("startups_total", T("partidas"), 1.0)]
    fig, axs = plt.subplots(len(metrics), len(axes_spec), figsize=(W2, 4.2), sharex="col")
    for j, (axis, xcol, xlabel, xf, cases) in enumerate(axes_spec):
        sub = df[df["axis"].isin([axis, "base"])]
        for c in "ABCD":
            g = sub[sub["case"] == c]
            if g.empty:
                continue
            if c not in cases:            # eixo não se aplica: valor base constante (linha de referência)
                g = g[g["variation"] == "base"]
            agg = g.groupby("variation")[[xcol] + [m for m, _, _ in metrics]].mean()
            if c not in cases:
                xs = sorted(set(xf(v) for v in sub[sub["case"].isin(cases)][xcol].dropna()))
                for i, (m, _, k) in enumerate(metrics):
                    axs[i, j].plot(xs, [agg[m].iloc[0] * k] * len(xs), color=CASE_COLORS[c], ls=":", lw=0.9,
                                   label=f"{T('caso')} {c}" if (i == 0 and j == 0) else None)
                continue
            agg = agg.assign(x=agg[xcol].map(xf)).sort_values("x")
            for i, (m, _, k) in enumerate(metrics):
                axs[i, j].plot(agg["x"], agg[m] * k, marker="o", ms=3, color=CASE_COLORS[c],
                               label=f"{T('caso')} {c}" if (i == 0 and j == 0) else None)
        axs[-1, j].set_xlabel(T(xlabel))
        if axis == "vpl_size":
            axs[-1, j].set_xticks([100, 200, 400, 650])
    for i, (_, ylabel, _) in enumerate(metrics):
        axs[i, 0].set_ylabel(T(ylabel))
    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.02), fontsize=6)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    save(fig, fdir, "fig9_sizing")


# -----------------------------------------------------------------------------
def main():
    ieee_style()
    cfg = load_config()
    rdir, fdir = results_dir(cfg), figures_dir(cfg)
    day1 = list(cfg["days"])[0]           # dia 1 = eólica alta + carga baixa
    print("Gerando figuras em", fdir)

    nets = {c: load_net(rdir, f"{day1}__{c}__base") for c in "ABCD"}
    if nets["A"] is not None:
        fig1_map(nets["A"], cfg, fdir)
    if nets["A"] is not None and nets["D"] is not None:
        fig2_dispatch(nets["A"], nets["D"], fdir)
    n_exp = load_net(rdir, f"{day1}__D__explicit") or load_net(rdir, f"{day1}__B__explicit") or nets["D"]
    if n_exp is not None and VPL_UP in n_exp.storage_units.index:
        fig3_corridor(n_exp, cfg, fdir)
    if nets["C"] is not None and nets["D"] is not None:
        fig4_vdc_heatmap(nets["C"], nets["D"], fdir)
    if all(v is not None for v in nets.values()):
        fig5_lmp_spread(nets, cfg, fdir)
    mpath = rdir / "metrics.csv"
    if mpath.exists():
        df = pd.read_csv(mpath)
        df = df[~df["scenario"].str.startswith("_")]
        if (df["axis"] == "vre_share").any():
            fig6_sensitivity(df, fdir)
        from common import ROOT

        fig7_complementarity(df, fdir, scenarios=load_config(ROOT / "config" / "scenarios.yaml"))
        if df["axis"].isin(["vpl_size", "dc_flex", "window_scale"]).any():
            fig9_sizing(df[~df["axis"].eq("vpl_x_fd")], fdir)


if __name__ == "__main__":
    main()
