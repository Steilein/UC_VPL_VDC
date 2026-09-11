# =============================================================================
# UC day-ahead com Virtual Power Lines e Virtual Data Centers (PyPSA / RTS-GMLC)
# -----------------------------------------------------------------------------
# Alvos (§11 do brief):
#   make validate                 -> Fase 1: rede original resolvida + results/F1_validation.md
#   make days                     -> seleção dos dias representativos (results/days_report.md)
#   make corridor                 -> Fase 2: verificação de saturação do corredor (results/F2_corridor.md)
#   make grid SOLVER=highs QUICK=1-> Fase 5: grade reduzida (depuração)
#   make grid SOLVER=gurobi       -> Fase 5: grade completa
#   make cross SOLVER=gurobi      -> sensibilidade cruzada VPL x f_d (results/cross_vpl_fd.md, fig8)
#   make extra SOLVER=gurobi      -> decomposicao do VPL, dias mensais, cond. iniciais, baseline, migracao
#   make leituras SOLVER=gurobi   -> VPL 400 MW nas tres leituras (emergente / explicita / dedicada)
#   make resref SOLVER=gurobi     -> C e D com o mesmo requisito de reserva de A e B
#   make relatorio                -> relatorio em portugues (docs/relatorio/relatorio.pdf)
#   make metrics                  -> Fase 6: recalcula metrics.csv e summary.md a partir dos .nc
#   make figures                  -> Fase 7: figuras em PDF (figures/)
#   make test                     -> testes mínimos (pytest)
# =============================================================================

# Interpretador do venv: Windows usa .venv/Scripts, Linux/macOS usa .venv/bin
ifeq ($(OS),Windows_NT)
  PY    ?= .venv/Scripts/python.exe
else
  PY    ?= .venv/bin/python
endif
SOLVER  ?= highs
QUICK   ?= 0
DAYS    ?=

ifeq ($(QUICK),1)
  QUICKFLAG = --quick
endif
ifneq ($(DAYS),)
  DAYSFLAG = --days $(DAYS)
endif

.PHONY: validate days corridor grid cross extra leituras resref relatorio metrics figures test all clean

validate:
	$(PY) src/validate.py --phase F1

days:
	$(PY) src/select_days.py

corridor:
	$(PY) src/validate.py --phase F2 --solver $(SOLVER)

grid:
	$(PY) src/runner.py --grid --solver $(SOLVER) $(QUICKFLAG) $(DAYSFLAG)

# Gera tabelas.tex e numeros.tex a partir de results/metrics.csv e compila o
# relatorio em portugues.
relatorio:
	$(PY) src/report_pt.py
	cd docs/relatorio && pdflatex -interaction=nonstopmode relatorio.tex && pdflatex -interaction=nonstopmode relatorio.tex

cross:
	$(PY) src/cross_sensitivity.py --solver $(SOLVER)

extra:
	$(PY) src/extra_runs.py --decomp --monthly --solver $(SOLVER)

leituras:
	$(PY) src/extra_runs.py --leituras --solver $(SOLVER)

resref:
	$(PY) src/extra_runs.py --resref --solver $(SOLVER)

metrics:
	$(PY) src/metrics.py

figures:
	$(PY) src/plots.py

test:
	$(PY) -m pytest -q tests

all: validate corridor grid metrics figures

clean:
	rm -f results/*.nc results/metrics.csv results/summary.md figures/*.pdf figures/*.png
