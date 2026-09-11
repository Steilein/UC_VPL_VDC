# Racional metodológico — UC day-ahead com Virtual Power Lines e Virtual Data Centers

Documento de rastreabilidade do experimento computacional do artigo destinado ao IEEE PES GTD Latin America (PPGEE-UFPR). Registra, item a item, o que foi feito, com que dados, com que código, com que solver, e o que se esperava e se obteve. Estado em 10/09/2026: grade HiGHS completa (116 cenários, gap 0,5 %) e grade Gurobi completa (116 cenários, gap 0,05 %), ambas com métricas, sumário, figuras e testes; sensibilidade cruzada VPL × f_d concluída (16 casos D adicionais).

---

## 1. Pergunta de pesquisa e tese

Sistemas termoelétricos com alta penetração de geração renovável variável (VRE) sofrem, simultaneamente, de congestionamento de transmissão, curtailment e ciclagem térmica. Dois recursos de flexibilidade atacam esse conjunto por caminhos opostos:

- **Virtual Power Line (VPL):** par de baterias (BESS) nos dois terminais de um corredor congestionado. Carrega a montante quando o corredor satura e descarrega a jusante no pico. Desloca **energia no tempo** dentro do corredor.
- **Virtual Data Center (VDC):** carga computacional com janela de execução e conjunto de sites viáveis. Desloca **carga no espaço e no tempo**.

A tese do artigo é quantificar o valor marginal de cada recurso e a interação entre eles, medida como a diferença entre o benefício conjunto e a soma dos benefícios isolados:

> Complementaridade = ΔBen(D) − [ΔBen(B) + ΔBen(C)],  com ΔBen(X) = Custo(A) − Custo(X)

onde A é o caso base, B inclui o VPL, C inclui o VDC e D inclui ambos, e Δ é o **benefício** (economia de custo em relação a A, positiva). Valor positivo indica complementaridade; valor negativo indica substituibilidade (os dois recursos disputam o mesmo alívio de congestionamento). Nas tabelas de `metrics.csv` as colunas `delta_*_A` são variações de custo (negativas quando há economia); por isso a coluna `complementarity` é calculada como (ΔCusto_B + ΔCusto_C) − ΔCusto_D, que equivale à expressão acima. Uma versão anterior do código usava o sinal oposto com o mesmo rótulo; foi corrigida em 10/09/2026 e todas as tabelas deste documento seguem a convenção de benefício.

## 2. Origem dos dados

### 2.1 RTS-GMLC (NREL / GridMod)

- Repositório público https://github.com/GridMod/RTS-GMLC, clonado em `data/RTS-GMLC`, commit `3ece0d3` de 22/10/2025.
- Topologia e parque: `bus.csv` (73 barras, 3 áreas), `branch.csv` (ramos CA com R, X, B em p.u. na base 100 MVA e limite contínuo), `dc_branch.csv` (elo CC 113–316), `gen.csv` (térmicas com curva de heat-rate por segmentos, custos de partida, tempos mínimos, rampas; hidro; eólica; PV; RTPV; CSP), `storage.csv` (313_STORAGE_1).
- Séries horárias do ano de 2020 em `timeseries_data_files`, sempre a versão **DAY_AHEAD**: carga por área, eólica, PV, RTPV, CSP e hidro. O ano completo alimenta a seleção dos dias representativos e o escalonamento anual do VRE.
- Referência: Barrows et al., "The IEEE Reliability Test System: A Proposed 2019 Update", IEEE Trans. Power Systems, 2020.

### 2.2 Phd_Files (Ferreira, tese PPGEE-UFPR)

- Repositório https://github.com/Falferreira/Phd_Files, clonado em `data/Phd_Files`, commit `d1d593e` de 18/05/2024.
- Quatro planilhas: custos de geração candidata, custos e comprimentos de linhas candidatas, custo de curtailment.
- Uso efetivo neste trabalho: os **nós candidatos de geração** da tese definem onde o acréscimo de VRE da Área 3 é alocado (eólica em 314, 316 e 319; PV em 320), no anel de 230 kV que alimenta a barra 318.

### 2.3 Premissas paramétricas sem arquivo externo

- Configuração estressada de Ferreira & Unsihuay-Vila (Energies 2026): carga da Área 2 multiplicada por 1,40 e capacidade VRE equivalente ao acréscimo de pico (1 140 MW, 70 % eólica e 30 % PV) adicionada na Área 3.
- VPL: 200 MW por terminal, 4 h, eficiência ida-e-volta 85 %, custo de degradação 2 $/MWh.
- VDC: três sites de 200 MW elétricos (barras 118, 218 e 318), PUE 1,30, fração flexível 0,5, workloads sintéticos gerados com semente fixa 42.
- Reserva girante: 3 % da carga mais 5 % do VRE disponível.
- Todos os valores estão em `config/base.yaml`, com comentário justificando cada um.

## 3. Código-base utilizado e código escrito

### 3.1 Bibliotecas de terceiros (não escritas por nós)

| Componente | Versão | Papel |
|---|---|---|
| PyPSA | 1.3.0 | Estrutura da rede, formulação nativa do UC (status, partida, rampas, tempos mínimos), fluxo DC linear, armazenamentos, exportação NetCDF |
| linopy | 0.9.1 | Construção algébrica do MILP e interface com os solvers |
| HiGHS (highspy) | 1.15.1 | Solver MILP de código aberto para desenvolvimento e validação |
| Gurobi (gurobipy) | 13.0.3 | Solver MILP comercial, licença acadêmica UFPR, para a grade final |
| pandas, xarray, numpy, scipy | 3.0 / 2026.7 / 2.5 / 1.18 | Manipulação de dados e DFT |
| matplotlib, seaborn | 3.11 / 0.13 | Figuras em estilo IEEE |
| pytest | 9.1 | Testes automatizados |

O UC em si não foi reimplementado: PyPSA gera as restrições de commitment, balanço nodal, lei de Kirchhoff das tensões (fluxo DC via ciclos), limites de fluxo e balanço de armazenamento. Isso reduz o risco de erro de formulação e torna o modelo auditável por terceiros.

### 3.2 Código escrito neste projeto (`src/`, cerca de 2 640 linhas)

| Módulo | Linhas | Função |
|---|---|---|
| `rts_import.py` | 484 | Parser RTS-GMLC → `pypsa.Network`. Conversão de p.u. para ohms, transformadores, elo CC, linearização do heat-rate, condição inicial do UC, séries DAY_AHEAD |
| `layers.py` | 513 | `stress_system`, `scale_vre`, `limit_corridor`, `add_vpl`, `compute_sigma`, `add_dc_inflexible`, `add_vdc`, gerador de workloads |
| `constraints.py` | 174 | Restrições adicionais via `extra_functionality`: reserva girante, capacidade por site do VDC, regra de chaveamento explícita do VPL |
| `runner.py` | 330 | `run_case` e `run_grid`: MILP, fixação das binárias, LP de preços, exportação NetCDF, linha em `metrics.csv` |
| `metrics.py` | 420 | Métricas por cenário, tabela de valor marginal e complementaridade, `summary.md` |
| `select_days.py` | 168 | Seleção automática dos dias representativos (DFT e rampas da demanda líquida) |
| `validate.py` | 166 | Critérios de aceite F1 e F2 com relatórios |
| `plots.py` | 308 | Figuras 1 a 7 em PDF vetorial |
| `cross_sensitivity.py` | 190 | Sensibilidade cruzada VPL × f_d: resolve os casos D faltantes, tabela 3 × 3 e figura 8 |
| `common.py` | 78 | Configuração e tradução das opções de solver |
| `tests/test_model.py` | 128 | Cinco testes: topologia, balanço no `lpf`, escalonamento VRE, conclusão de workloads e capacidade de site, regra explícita do VPL |

Toda a parametrização está em `config/base.yaml` e `config/scenarios.yaml`. O `Makefile` encadeia as fases (`validate`, `days`, `corridor`, `grid`, `metrics`, `figures`, `test`).

## 4. Passos executados, na ordem

Cada fase seguiu o brief `UC_VPL_VDC_pypsa_brief.md`, que fixa um critério de aceite por fase. Nenhuma fase avançou sem cumprir o critério.

### Fase 1 — Importação e validação da rede original (F1)

**O que foi feito.** Leitura dos CSVs e séries; construção da rede de um dia (24 snapshots horários). Decisões registradas: linhas em ohms via `Z_pu · v_nom² / 100`; ramos com relação de transformação ou níveis de tensão distintos como `Transformer` com reatância em p.u. sobre `s_nom`; elo CC como `Link` bidirecional; linhas CA nunca como `Link`, para não perder a física do congestionamento. Térmicas `committable` com custo marginal linearizado no ponto de 80 % de PMax e custo de partida a frio. Nuclear como must-run (168 h, p_min 0,9). Unidades com tempo mínimo ligado de 8 h ou mais iniciam ligadas, as demais desligadas, para não gerar partidas artificiais na hora 0.

**Critério de aceite.** UC converge com HiGHS; despacho por combustível e fluxos entre áreas plausíveis frente à literatura do RTS-GMLC; fluxo DC estático (`n.lpf`) com balanço nodal fechado.

**Resultado.** Dia 26/08/2020 (pico anual): ótimo em 39 s, custo 2 298 579 $, LMP médio 24,7 $/MWh, curtailment 2,9 %. Erro máximo de balanço nodal no `lpf` de 1,6·10⁻¹² MW e fluxos idênticos aos do UC. Mix (carvão 30 %, gás CC 31 %, nuclear 7 %, VRE 24 %) coerente com os resultados publicados de PCM para o RTS-GMLC. Relatório em `results/F1_validation.md`.

### Fase 1b — Seleção dos dias representativos

**O que foi feito.** Série anual da demanda líquida na configuração estressada; DFT para caracterizar as periodicidades (dominantes em 24 h, 12 h e sazonal); rampas máximas de 1 h e 3 h por dia; quatro critérios automáticos seguindo a Seção 5.2.1.1 da tese.

**Resultado.** `spring_wind` 12/03 (maior excedente VRE, 26 487 MWh), `summer_peak` 26/08 (pico anual, 9 282 MW), `solar_ramp` 14/01 (maior rampa de 3 h, 5 777 MW), `median` 16/03 (energia de demanda líquida mediana). Relatório em `results/days_report.md`; escolha confirmada em `config/base.yaml`.

### Fase 2 — Configuração estressada e saturação do corredor (F2)

**O que foi feito.** Carga da Área 2 × 1,40; acréscimo de 1 140 MW de VRE na Área 3; escalonamento do parque VRE por fator único até a penetração-alvo (30, 50 ou 70 %). Corredor de estudo: ramo CB-1 entre as barras 318 (Área 3) e 223 (Área 2), 500 MW.

**Decisões divergentes do brief.** (i) A alocação do acréscimo proporcional ao VRE existente concentrava tudo na barra 317 e congestionava a linha interna C29 antes do corredor; adotou-se a alocação nos nós candidatos da tese. (ii) O escalonamento VRE em base diária, leitura literal do brief, reduzia o parque a 55 % nos dias ventosos e impedia a saturação; adotou-se a base anual (penetração = energia disponível anual / carga anual, como na tese), com o parque idêntico em todos os dias.

**Critério de aceite.** Corredor saturado (|fluxo| ≥ 0,98 · limite) em pelo menos 6 h/dia em pelo menos 2 dos 4 dias, com spread de LMP visível entre 318 e 223.

**Resultado.** Horas saturadas: 8 (spring_wind), 17 (summer_peak), 6 (solar_ramp), 1 (median). Spread de LMP nas horas saturadas entre 16 e 22 $/MWh. Critério atendido em 3 dos 4 dias. Relatório em `results/F2_corridor.md`.

### Fase 3 — Camada VPL

**O que foi feito.** Dois `StorageUnit` em 318 e 223, eficiência de carga e descarga √0,85, estado de carga cíclico, custo de degradação na descarga. Formulação padrão **emergente**: sem acoplamento explícito entre os BESS; o comportamento de linha virtual emerge da localização e do spread de LMP. Variante **explícita**: binária z_t de sentido do fluxo (big-M) e binária w_t que fixa o modo de cada BESS conforme o estágio de uso da rede sigma_t (P90 e P30 da demanda líquida do dia), reproduzindo a regra de chaveamento da tese e deixando as horas intermediárias livres para arbitragem.

### Fase 4 — Camada VDC

**O que foi feito.** Para cada workload j: um `Bus` virtual de computação; um `Link` de cada site viável até esse bus, com eficiência 1/PUE, janela de execução via `p_max_pu` e custo de migração como custo marginal; um `Store` cuja energia mínima salta para E_j no deadline, forçando a conclusão. Workloads batch (janela 8 a 12 h, só o site nativo) e migráveis (janela 2 a 4 h, todos os sites). Única restrição custom: soma dos Links por site limitada a f_d · C_d em cada hora. Carga inflexível dos DCs como `Load` plano.

**Decisões divergentes do brief.** (i) A energia flexível diária é u · f_d · C_d · 24 com u = 0,7: com u = 1 a carga flexível teria de operar a plena capacidade nas 24 h e não haveria flexibilidade alguma. (ii) Nos casos sem VDC (A e B) os DCs entram como carga plana com a mesma energia, de modo que a diferença de custo isola o valor da flexibilidade e não o valor de retirar carga.

**Critério de aceite (F3/F4).** Caso D a 50 % VRE resolve; toda energia de workload concluída até o deadline; nenhum site excede capacidade; VPL cicla nos dias congestionados. Verificado nos testes automatizados e nas métricas de cada cenário.

### Fase 5 — Runner e grade de sensibilidades

**O que foi feito.** `run_case` constrói, resolve e exporta um cenário; `run_grid` percorre 4 dias × 4 casos × variações de um eixo por vez. Eixos: penetração VRE (30/50/70 %), tamanho do VPL (100/200/400 MW), fração flexível f_d (0,2/0,5/0,8), largura da janela batch (×0,5/×1/×2), reserva provida por flexibilidade (off/on) e representação do VPL (emergente/explícita). Total: 116 resoluções. Cada rede resolvida é salva em NetCDF para reprocessamento sem re-resolver.

**Formação de preços.** Após o MILP, todas as binárias são fixadas na solução e o LP é re-resolvido, fornecendo LMPs e multiplicadores dos limites de fluxo com commitment fixo, procedimento padrão em mercados day-ahead.

### Fase 6 — Métricas

Por cenário: custo total decomposto (combustível, partidas, migração, degradação, penalidade de curtailment); curtailment em MWh e %; partidas por combustível; FRUS e FRDS médios (eqs. 5.1 e 5.2 da tese); MWh em mínimo técnico; horas congestionadas e spread de LMP do corredor; capacidade virtual do VPL (descarga a jusante em horas saturadas); horas em serviço de linha virtual versus arbitragem; energia VDC deslocada no espaço e no tempo; CO₂; tempo de solução e gap. A tabela central é a de valor marginal e complementaridade.

### Fase 7 — Figuras

Sete figuras em estilo IEEE, mais a figura 8 da sensibilidade cruzada, (coluna única, 3,5 in, 8 pt, PDF vetorial): mapa com corredor e sites; despacho empilhado A e D; fluxo no corredor e SOC dos BESS; heatmap de carga VDC por site e hora; spread de LMP; sensibilidade à penetração; barras de complementaridade.

## 5. Como a modelagem foi idealizada

1. **UC determinístico day-ahead com rede**, 24 snapshots horários, fluxo de potência linear (DC) via formulação de ciclos do PyPSA. Incerteza tratada por sensibilidade, não por programação estocástica (decisão do brief).
2. **Sem linearização do commitment.** A ciclagem térmica (partidas, operação em mínimo técnico) é argumento central do artigo, portanto as binárias de status são mantidas.
3. **Recursos de flexibilidade em componentes nativos do PyPSA**, sem variáveis customizadas: VPL como `StorageUnit`, VDC como `Bus` + `Link` + `Store`. Apenas três blocos de restrições adicionais (reserva, capacidade por site, chaveamento explícito) foram escritos em linopy.
4. **Comparabilidade entre casos.** Mesma rede, mesmos dados, mesma energia de DC em todos os casos; apenas as camadas de flexibilidade mudam. Custo marginal de −0,1 $/MWh no VRE como desempate interpretável do curtailment, com efeito desprezível no total.
5. **Um eixo por vez.** A grade varia um parâmetro de cada vez em torno do caso base, o que permite atribuir cada variação de resultado a uma causa.
6. **Rastreabilidade.** Cada decisão fica gravada em `n.meta` e é exportada com o NetCDF; o `metrics.csv` registra solver, gap e tempo de cada cenário.

## 6. Solver

| | HiGHS 1.15.1 | Gurobi 13.0.3 |
|---|---|---|
| Papel | Desenvolvimento, validação, primeira grade completa | Grade final |
| Licença | Código aberto | Acadêmica UFPR, ativada em 10/09/2026, válida até 10/09/2027 |
| Gap MIP relativo | 0,5 % | 0,05 % |
| Limite de tempo | 1 800 s | 1 800 s |
| Threads | 8 | 8 |
| Tempo de MILP | média 40 s, máx. 421 s | média 60 s, mediana 17 s, máx. 1 834 s |
| Gap atingido | médio 0,32 %, máx. 0,50 % | médio 0,038 %, máx. 0,056 % |

Por que reduzir o gap. Com gap de 0,5 %, o erro absoluto admitido no ótimo é de 3 a 14 k$ por cenário, da mesma ordem da complementaridade medida (0,3 a 17 k$/dia). A grade HiGHS serviu para depurar o pipeline e obter a ordem de grandeza, mas não permitia concluir sobre o sinal da interação. Com gap de 0,05 % o erro cai para cerca de 1 k$ e o sinal passa a ser mensurável.

Um cenário da grade Gurobi (summer_peak, caso A, 70 % VRE) atingiu o limite de 1 800 s com gap de 0,056 %, ligeiramente acima da meta e ainda uma ordem de grandeza abaixo do gap HiGHS. Esse valor fica registrado no `metrics.csv`. O objetivo do caso A base melhorou entre 0,00 % e 0,15 % em relação ao HiGHS, o que confirma que as soluções HiGHS já estavam próximas do ótimo, mas não com precisão suficiente para medir a interação.

## 7. Resultados esperados e obtidos

> **Nota (10/09/2026, noite):** as seções 7.2 a 7.5 refletem a grade anterior à correção do baseline dos data centers. Os números válidos estão na seção 7.6.

### 7.1 O que se esperava

- Valor marginal do VPL crescente com a penetração VRE e com o tamanho da bateria.
- Valor marginal do VDC crescente com a fração flexível f_d e decrescente com janelas mais estreitas.
- Redução de curtailment e de partidas em B, C e D frente a A.
- Hipótese do brief: complementaridade positiva, ou seja, os dois recursos somam mais juntos do que separados.

### 7.2 Grade HiGHS (116 cenários, gap 0,5 %): papel de depuração

A grade HiGHS reproduziu as tendências esperadas (VPL vale cerca de 1,7 vez o VDC; ambos reduzem curtailment e partidas; D reduz o custo em 7,5 %). Porém a complementaridade medida ficou entre −18 e +4 k$/dia com ruído de gap de 3 a 14 k$ por combinação, de modo que nenhum valor era distinguível de zero. A grade fica arquivada em `results_highs_gap05/` e não é usada no artigo.

### 7.3 Grade Gurobi completa (116 cenários, gap 0,05 %)

Métricas operacionais por caso, médias entre os quatro dias, variação base:

| Caso | Custo total ($) | Redução vs. A | Curtailment (%) | Partidas | Horas congestionadas | CO₂ (t) |
|---|---|---|---|---|---|---|
| A base | 1 630 710 | — | 21,2 | 17,0 | 8,8 | 43 425 |
| B +VPL | 1 553 050 | −4,8 % | 19,0 | 12,8 | 11,3 | 42 942 |
| C +VDC | 1 585 920 | −2,7 % | 20,6 | 12,5 | 10,8 | 42 623 |
| D ambos | 1 510 380 | −7,4 % | 18,4 | 9,5 | 11,8 | 42 008 |

Leituras confirmadas: o VPL vale cerca de 1,8 vez o VDC na configuração base; ambos reduzem curtailment, partidas e CO₂; o VDC desloca 13 % da energia flexível no espaço e 49 % no tempo. As horas congestionadas do corredor **aumentam** com os recursos, o que é esperado: eles exploram o corredor até o limite em mais horas, deslocando energia para dentro dele. Sensibilidades: ΔB vai de −39 k$ (VPL 100 MW) a −142 k$ (400 MW); ΔC vai de +7 k$ (f_d = 0,2, quando o VDC quase não flexibiliza e paga custo de migração) a −96 k$ (f_d = 0,8). A variante explícita do VPL vale 57 % da emergente, porque a regra de chaveamento retira graus de liberdade da arbitragem.

Complementaridade (ΔB + ΔC) − ΔD em $/dia, convenção de benefício (positivo = complementares), por dia e variação:

| Dia | base | vre30 | vre70 | vpl100 | vpl400 | explicit | f02 | f08 | w05 | w20 | reson |
|---|---|---|---|---|---|---|---|---|---|---|---|
| median | −614 | **−12 275** | −2 819 | **+6 574** | −1 041 | **+5 842** | −2 025 | −869 | −1 158 | −1 010 | −670 |
| solar_ramp | **−6 173** | **−6 751** | −3 406 | −3 923 | **−9 983** | −77 | +824 | **−7 190** | **−6 817** | **−6 880** | **−5 031** |
| spring_wind | +1 290 | **−8 442** | **−5 652** | +1 796 | −1 346 | **+2 988** | +1 | +589 | +737 | +526 | **+2 079** |
| summer_peak | −2 960 | −4 801 | −314 | −2 067 | **−18 358** | −3 252 | −779 | −7 487 | −5 285 | −3 818 | −2 579 |
| Média | −2 114 | −8 067 | −3 048 | +595 | −7 682 | +1 375 | −495 | −3 739 | −3 131 | −2 796 | −1 550 |
| Ruído do gap | 2 387 | 2 567 | 2 647 | 2 528 | 2 158 | 2 566 | 2 597 | 2 302 | 2 410 | 2 562 | 2 851 |

Em negrito os valores com módulo maior que duas vezes o ruído do gap da combinação (soma dos gaps absolutos dos quatro casos). Ruído médio por dia: 1,0 k$ (spring_wind), 2,1 k$ (solar_ramp), 2,5 k$ (median), 4,5 k$ (summer_peak).

O que a tabela diz:

- **A interação é predominantemente negativa.** Média geral de −2,8 k$/dia sobre as 44 combinações. Das 14 combinações em que o sinal supera duas vezes o ruído, 11 indicam substituição e 3 indicam complementaridade.
- **A substituição cresce com a força do VPL.** Com VPL de 400 MW a perda de sinergia chega a −18,4 k$/dia no pico de verão e −10,0 k$/dia no dia de rampa solar, ou seja, 10 a 12 % do benefício do VDC desaparece quando o VPL grande já aliviou o corredor. Com VPL de 100 MW ou com a regra de chaveamento explícita, que restringe o VPL, a interação passa a ser positiva no dia mediano (+6,6 e +5,8 k$/dia).
- **A substituição é maior com baixa penetração VRE.** A 30 % de VRE o corredor congestiona menos horas, os dois recursos competem pelas mesmas poucas horas de spread e a interação é negativa em todos os dias (−4,8 a −12,3 k$/dia). A 70 % o excedente de VRE é grande o bastante para que os dois trabalhem em horas distintas e a interação se aproxima de zero.
- **O dia importa mais do que o eixo.** solar_ramp é sistematicamente substitutivo; spring_wind é o único dia com sinais positivos fora dos casos de VPL fraco.

Comparação com a grade HiGHS: o sinal concordou em 89 % das combinações, mas com HiGHS nenhuma delas superava o ruído. Para spring_wind a 30 % de VRE o HiGHS indicava −8,5 k$ com ruído de 8,5 k$; o Gurobi indica −8,4 k$ com ruído de 0,9 k$. A conclusão só existe na grade de alta precisão.

### 7.4 Interpretação para o artigo

A hipótese inicial de complementaridade positiva não se confirma. O resultado é mais informativo do que a hipótese: quando duas fontes de flexibilidade aliviam a mesma restrição de transmissão, o benefício marginal da segunda cai, e a queda é tanto maior quanto mais dimensionada estiver a primeira. A implicação para planejamento é direta: dimensionar VPL e VDC de forma independente superestima o benefício conjunto em até 12 % do valor do VDC. A complementaridade só aparece quando o VPL é pequeno ou operado por regra fixa, situação em que o VDC preenche horas que o VPL não alcança. A magnitude da substituição e sua dependência do tamanho do VPL e da penetração VRE são os achados a reportar.

### 7.5 Sensibilidade cruzada: tamanho do VPL × fração flexível f_d

Para mapear a fronteira entre substituição e complementaridade, os dois eixos de dimensionamento foram cruzados: P_VPL ∈ {100, 200, 400} MW por terminal × f_d ∈ {0,2; 0,5; 0,8}. Dos nove casos D por dia, cinco já existiam na grade principal; os 16 restantes foram resolvidos por `src/cross_sensitivity.py` com Gurobi (10 a 170 s cada, gap ≤ 0,05 %). A, B(P) e C(f) vêm da grade principal. Relatório em `results/cross_vpl_fd.md`; figura 8 em `figures/fig8_cross_vpl_fd`.

Complementaridade média entre os quatro dias, em $/dia:

| VPL por terminal | f_d = 0,2 | f_d = 0,5 | f_d = 0,8 |
|---|---|---|---|
| 100 MW | −823 | +595 | −1 572 |
| 200 MW | −495 | −2 114 | −3 739 |
| 400 MW | −3 933 | −7 682 | −10 583 |

Ruído médio do gap entre 2,2 e 2,7 k$ em todas as células. Em relação ao benefício isolado do VDC, a perda de sinergia é de 4 a 5 % com VPL de 200 MW e de 11 a 17 % com VPL de 400 MW.

O que a superfície mostra:

- **A substituição é monótona nos dois eixos.** Quanto maior o VPL e quanto mais flexível o data center, mais negativa a interação. A única célula positiva na média é VPL 100 MW com f_d = 0,5, e ela fica dentro do ruído.
- **O pico de verão domina a magnitude.** Em summer_peak a célula VPL 400 MW × f_d = 0,8 chega a −26,9 k$/dia, o que equivale a cerca de um quarto do benefício isolado do VDC nesse dia. Em solar_ramp a substituição é forte já com VPL de 400 MW e f_d = 0,2 (−8,0 k$/dia).
- **spring_wind é a exceção parcial.** Com VPL de 100 ou 200 MW a interação é levemente positiva (+0,6 a +1,9 k$/dia, dentro do ruído de 1 k$); só com 400 MW e f_d = 0,8 aparece substituição forte (−8,4 k$/dia). No dia de maior excedente eólico há horas de curtailment suficientes para os dois recursos trabalharem sem competir, até que o VPL grande esgote o corredor.
- **O dia mediano é quase aditivo**, exceto pela célula VPL 100 MW × f_d = 0,5 (+6,6 k$/dia, 2,8 vezes o ruído), que se repete da grade principal: um VPL pequeno deixa horas de spread para o VDC preencher.

Leitura para o artigo: a interação VPL–VDC é uma superfície côncava em (P_VPL, f_d), aproximadamente aditiva quando ambos os recursos são pequenos e crescentemente substitutiva quando qualquer um deles cresce. Isso quantifica a regra de planejamento: o benefício conjunto deve ser avaliado em co-otimização, e o dimensionamento sequencial (primeiro o VPL, depois o VDC, ou vice-versa) superestima o valor da segunda camada em até um quarto no dia crítico.


## 7.6 Correção do baseline dos data centers e números finais (10/09/2026, noite)

**Erro encontrado.** A revisão externa questionou o baseline plano dos casos A/B. Ao verificar, constatou-se um erro de implementação: a carga plana usava a fórmula 0,7·f_d·C_d·24 (12 240 MWh/dia nos três sites), enquanto os workloads de C/D, após os cortes de factibilidade do gerador, somavam 11 336 MWh/dia. Os casos flexíveis tinham 904 MWh/dia a menos de carga, o que inflava o valor do VDC. O mesmo desalinhamento existia nos eixos f_d e janela, em que A e B não eram recalculados.

**Correção.** `add_dc_inflexible` passou a derivar a carga plana dos workloads efetivamente gerados para a mesma configuração; os eixos `dc_flex` e `window_scale` passaram a incluir A e B; a sensibilidade cruzada passou a usar A(f) e B(P, f). Foram refeitas 132 resoluções (A e B da grade, decomposição, dias mensais, baseline alternativo "native" e cruzamentos). Os resultados anteriores ficaram em `results_ab_prebugfix/`.

**Números finais (Gurobi, gap 0,05 %, médias dos quatro dias, variação base):**

| Caso | Custo (k$) | Redução vs. A | Curtailment (MWh) | Partidas | Horas congest. |
|---|---|---|---|---|---|
| A | 1 612,3 | — | 20 464 | 17,25 | 9,5 |
| B (+VPL) | 1 535,7 | −4,7 % | 18 907 | 11,75 | 12,75 |
| C (+VDC) | 1 585,9 | −1,6 % | 19 641 | 12,50 | 10,75 |
| D (ambos) | 1 510,4 | −6,3 % | 17 998 | 9,50 | 11,75 |

O valor do VDC caiu de 44,8 para 26,4 k$/dia (−41 %); o do VPL ficou em 76,6 k$/dia. A interação de custo permaneceu negativa nos três níveis de penetração: −9,0 k$ (30 %), −1,0 k$ (50 %) e −3,7 k$ (70 %), ou seja, benefício conjunto 11,7 %, 1,0 % e 3,3 % menor que a soma. Nas 48 combinações da grade, I < 0 em 33 e |I| > 2×ruído em 22 (16 substituição, 6 complementaridade). Nos 12 dias mensais: −4,7 % de custo, −15 % de curtailment, −49 % de partidas, I < 0 em 9 de 12.

**Decomposição do VPL:** 37,6 + 35,9 = 73,5 k$ contra 76,6 k$ do par; o pareamento vale 4 % (1 a 9 % por dia).

**Baseline alternativo (native):** com os mesmos jobs no site nativo executados por EDF desde a chegada, o valor do VDC cai de 26,4 para 18,0 k$ e o conjunto de 101,9 para 93,5 k$; a interação permanece negativa (−2,2 contra −1,0 k$). O baseline plano superestima o VDC em cerca de um terço, mas não altera a conclusão sobre a interação.

**Superfície VPL × f_d (médias, k$/dia):** 100 MW: −1,8 / +1,6 / −1,8; 200 MW: −1,4 / −1,0 / −1,7; 400 MW: −3,1 / −6,8 / −7,9 para f_d = 0,2 / 0,5 / 0,8. Para VPL de 100 a 200 MW a interação fica dentro do ruído (~2,5 k$); a 400 MW é claramente negativa (19 a 26 % do benefício do VDC); a 650 MW e f_d = 0,5 chega a −16,9 k$.

**Sensibilidades:** VPL 38 / 77 / 142 / 186 k$ a 100 / 200 / 400 / 650 MW (retorno marginal decrescente: 38, 32 e 18 k$ por 100 MW); VDC 12 / 26 / 41 k$ para f_d 0,2 / 0,5 / 0,8 e 9 / 26 / 35 k$ para janela ×0,5 / ×1 / ×2 (a janela é restrição de primeira ordem); regra explícita custa 32 dos 77 k$ do VPL (+2,1 %).

**Mensagem central mantida e reforçada:** duas flexibilidades que aliviam o mesmo corredor competem economicamente mesmo prestando serviços distintos, VPL sobre curtailment e VDC sobre ciclagem térmica. A competição se dá pela capacidade do corredor nas mesmas horas saturadas, não pelo colapso de um sinal de preço (o spread é deslocado, não eliminado).

## 8. Limitações e próximos passos

- Determinístico: sem incerteza de previsão de VRE; sensibilidade em vez de programação estocástica.
- Rede CA não linear, expansão de transmissão e rede de dados dos data centers estão fora de escopo (brief §12).
- DCs de 200 MW por área e workloads sintéticos são premissas nossas, a declarar na seção de dados do artigo.
- O RTS-GMLC não fornece custos de partida em base monetária diretamente comparável a mercados reais; usam-se os do próprio `gen.csv`.
- A significância foi avaliada pelo ruído do gap MIP, não por replicação; os dias representativos são quatro, o que limita a generalização sazonal.
- Próximos passos: reescrever a seção de resultados e as conclusões do artigo com a grade Gurobi e a superfície VPL × f_d (figuras 7 e 8); avaliar se o dia mediano com VPL fraco justifica uma figura própria; considerar um quinto dia de outono para reforçar a generalização sazonal.

## 9. Reprodução

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
git clone --depth 1 https://github.com/GridMod/RTS-GMLC data/RTS-GMLC
git clone --depth 1 https://github.com/Falferreira/Phd_Files data/Phd_Files
make validate && make days && make corridor
make grid SOLVER=gurobi
make metrics && make figures && make test
```
