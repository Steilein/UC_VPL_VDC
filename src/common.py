"""
common.py — utilidades compartilhadas: leitura de configuração, sobrescrita
de parâmetros por caminho pontilhado e opções de solver.

Mantido propositalmente pequeno para que os demais módulos permaneçam
legíveis e autocontidos.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Garante UTF-8 no console do Windows (cp1252 não representa "≥", "→", etc.)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def load_config(path: str | Path = ROOT / "config" / "base.yaml") -> dict:
    """Lê um YAML de configuração e devolve um ``dict`` aninhado."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def set_by_path(cfg: dict, dotted: str, value: Any) -> dict:
    """Sobrescreve ``cfg["a"]["b"]["c"]`` a partir de ``"a.b.c"`` (cópia profunda)."""
    out = copy.deepcopy(cfg)
    node = out
    keys = dotted.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return out


def solver_options(cfg: dict, mip: bool = True) -> tuple[str, dict]:
    """Traduz o bloco ``solver`` do YAML nas opções específicas de cada solver.

    O gap relativo (config: 0,5 % na depuração, 0,05 % na grade final) e o
    limite de tempo são idênticos em HiGHS e Gurobi
    para garantir comparabilidade dos resultados (§7 do brief). Para a
    re-solução LP (obtenção dos LMPs) os parâmetros de MIP são omitidos.
    """
    s = cfg["solver"]
    name = str(s["name"]).lower()
    threads = int(s.get("threads", 4))
    if name == "highs":
        opts = {"threads": threads, "time_limit": float(s["time_limit"])}
        if mip:
            opts["mip_rel_gap"] = float(s["mip_rel_gap"])
    elif name == "gurobi":
        opts = {"Threads": threads, "TimeLimit": float(s["time_limit"])}
        if mip:
            opts["MIPGap"] = float(s["mip_rel_gap"])
    else:
        raise ValueError(f"Solver não suportado: {name}")
    return name, opts


def results_dir(cfg: dict) -> Path:
    p = ROOT / cfg["paths"]["results"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def figures_dir(cfg: dict) -> Path:
    p = ROOT / cfg["paths"]["figures"]
    p.mkdir(parents=True, exist_ok=True)
    return p
