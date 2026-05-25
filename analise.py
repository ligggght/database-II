"""
analise.py — Geração de tabelas e gráficos a partir dos resultados do benchmark.

Uso:
    python analise.py

O script detecta automaticamente os JSONs mais recentes em cada pasta
de resultados e gera:
  - Tabelas comparativas no terminal (e em CSV em resultados/tabelas/)
  - Gráficos PNG em resultados/graficos/

Não requer containers Docker — roda direto no host.
Dependências: matplotlib, pandas  (pip install matplotlib pandas)
"""

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # sem janela gráfica; salva em arquivo
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent
RESULT_DIR = BASE_DIR / "resultados"
TAB_DIR    = RESULT_DIR / "tabelas"
GRAF_DIR   = RESULT_DIR / "graficos"
TAB_DIR.mkdir(parents=True, exist_ok=True)
GRAF_DIR.mkdir(parents=True, exist_ok=True)

SGBDS    = ["sqlite", "mysql", "postgres"]
CENARIOS = ["A", "B", "C"]

# Cores e nomes de exibição por SGBD
COR = {
    "sqlite":   "#4C72B0",   # azul
    "mysql":    "#DD8452",   # laranja
    "postgres": "#55A868",   # verde
}
NOME = {
    "sqlite":   "SQLite",
    "mysql":    "MySQL",
    "postgres": "PostgreSQL",
}

# ---------------------------------------------------------------------------
# Carregamento dos JSONs
# ---------------------------------------------------------------------------

def ultimo_json(sgbd: str, cenario: str) -> Path | None:
    """Devolve o JSON mais recente de um SGBD/cenário, ou None se não houver."""
    pasta = BASE_DIR / sgbd / "results"
    if not pasta.exists():
        return None
    arquivos = sorted(pasta.glob(f"{sgbd}_{cenario}_*.json"))
    return arquivos[-1] if arquivos else None


def carregar_dados() -> dict:
    """Carrega todos os JSONs disponíveis em um dict dados[sgbd][cenario]."""
    dados = {}
    for sgbd in SGBDS:
        dados[sgbd] = {}
        for cenario in CENARIOS:
            caminho = ultimo_json(sgbd, cenario)
            if caminho:
                with open(caminho, encoding="utf-8") as f:
                    dados[sgbd][cenario] = json.load(f)
                print(f"  [ok] {sgbd}/{cenario} → {caminho.name}")
            else:
                print(f"  [--] {sgbd}/{cenario} → sem arquivo")
    return dados


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------

def fmt(valor, decimais=2):
    """Formata número para exibição, substituindo None por '—'."""
    if valor is None:
        return "—"
    return f"{valor:,.{decimais}f}"


def _get(d, *chaves):
    """Navega por um dict aninhado; devolve None se alguma chave faltar."""
    for k in chaves:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


# ---------------------------------------------------------------------------
# TABELAS
# ---------------------------------------------------------------------------

def tabela_cenario_a(dados: dict) -> pd.DataFrame:
    """
    Tabela comparativa do Cenário A:
    TPS e latência média de INSERTs e SELECTs por SGBD.
    """
    linhas = []
    for sgbd in SGBDS:
        d = dados.get(sgbd, {}).get("A")
        if not d:
            continue
        m = d["media"]
        linhas.append({
            "SGBD":                 NOME[sgbd],
            "INSERT — TPS":         _get(m, "inserts", "tps"),
            "INSERT — Tempo (s)":   _get(m, "inserts", "tempo_total_s"),
            "INSERT — Lat. Média (ms)": _get(m, "inserts", "latencia", "media_ms"),
            "INSERT — p50 (ms)":    _get(m, "inserts", "latencia", "p50_ms"),
            "INSERT — p95 (ms)":    _get(m, "inserts", "latencia", "p95_ms"),
            "INSERT — p99 (ms)":    _get(m, "inserts", "latencia", "p99_ms"),
            "SELECT — TPS":         _get(m, "selects", "tps"),
            "SELECT — Tempo (s)":   _get(m, "selects", "tempo_total_s"),
            "SELECT — Lat. Média (ms)": _get(m, "selects", "latencia", "media_ms"),
            "SELECT — p50 (ms)":    _get(m, "selects", "latencia", "p50_ms"),
            "SELECT — p95 (ms)":    _get(m, "selects", "latencia", "p95_ms"),
            "SELECT — p99 (ms)":    _get(m, "selects", "latencia", "p99_ms"),
        })
    return pd.DataFrame(linhas).set_index("SGBD")


def tabela_cenario_b(dados: dict) -> pd.DataFrame:
    """
    Tabela comparativa do Cenário B:
    TPS e latência de SELECTs com 100 conexões concorrentes.
    """
    linhas = []
    for sgbd in SGBDS:
        d = dados.get(sgbd, {}).get("B")
        if not d:
            continue
        m = d["media"]
        linhas.append({
            "SGBD":              NOME[sgbd],
            "TPS Total":         _get(m, "tps"),
            "Tempo Total (s)":   _get(m, "tempo_total_s"),
            "Lat. Média (ms)":   _get(m, "latencia", "media_ms"),
            "p50 (ms)":          _get(m, "latencia", "p50_ms"),
            "p95 (ms)":          _get(m, "latencia", "p95_ms"),
            "p99 (ms)":          _get(m, "latencia", "p99_ms"),
            "Lat. Mín (ms)":     _get(m, "latencia", "min_ms"),
            "Lat. Máx (ms)":     _get(m, "latencia", "max_ms"),
        })
    return pd.DataFrame(linhas).set_index("SGBD")


def tabela_cenario_c(dados: dict) -> pd.DataFrame:
    """
    Tabela comparativa do Cenário C:
    TPS, taxa de falhas e latências de INSERTs/UPDATEs com 100 conexões.
    """
    linhas = []
    for sgbd in SGBDS:
        d = dados.get(sgbd, {}).get("C")
        if not d:
            continue
        m = d["media"]
        linhas.append({
            "SGBD":                     NOME[sgbd],
            "TPS Total":                _get(m, "tps"),
            "Tempo Total (s)":          _get(m, "tempo_total_s"),
            "Taxa de Falhas (%)":       (_get(m, "taxa_falhas") or 0) * 100,
            "INSERT — Lat. Média (ms)": _get(m, "latencia_inserts", "media_ms"),
            "INSERT — p50 (ms)":        _get(m, "latencia_inserts", "p50_ms"),
            "INSERT — p95 (ms)":        _get(m, "latencia_inserts", "p95_ms"),
            "INSERT — p99 (ms)":        _get(m, "latencia_inserts", "p99_ms"),
            "UPDATE — Lat. Média (ms)": _get(m, "latencia_updates", "media_ms"),
            "UPDATE — p50 (ms)":        _get(m, "latencia_updates", "p50_ms"),
            "UPDATE — p95 (ms)":        _get(m, "latencia_updates", "p95_ms"),
            "UPDATE — p99 (ms)":        _get(m, "latencia_updates", "p99_ms"),
        })
    return pd.DataFrame(linhas).set_index("SGBD")


def tabela_resumo(dados: dict) -> pd.DataFrame:
    """
    Tabela-resumo com os números mais relevantes de cada cenário em uma visão única.
    """
    linhas = []
    for sgbd in SGBDS:
        linha = {"SGBD": NOME[sgbd]}

        # Cenário A
        dA = dados.get(sgbd, {}).get("A")
        if dA:
            linha["A — INSERT TPS"]  = _get(dA, "media", "inserts", "tps")
            linha["A — SELECT TPS"]  = _get(dA, "media", "selects", "tps")
        else:
            linha["A — INSERT TPS"]  = None
            linha["A — SELECT TPS"]  = None

        # Cenário B
        dB = dados.get(sgbd, {}).get("B")
        linha["B — TPS (100 SELECTs)"] = _get(dB, "media", "tps") if dB else None

        # Cenário C
        dC = dados.get(sgbd, {}).get("C")
        if dC:
            linha["C — TPS (escrita)"]   = _get(dC, "media", "tps")
            linha["C — Falhas (%)"]      = (_get(dC, "media", "taxa_falhas") or 0) * 100
        else:
            linha["C — TPS (escrita)"]   = None
            linha["C — Falhas (%)"]      = None

        linhas.append(linha)
    return pd.DataFrame(linhas).set_index("SGBD")


def imprimir_tabela(df: pd.DataFrame, titulo: str):
    """Imprime uma tabela formatada no terminal."""
    sep = "─" * 80
    print(f"\n{sep}")
    print(f"  {titulo}")
    print(sep)
    # Formata colunas numéricas
    display = df.copy()
    for col in display.columns:
        display[col] = display[col].apply(
            lambda v: fmt(v, 0) if (v is not None and v >= 1000)
            else fmt(v, 2) if v is not None
            else "—"
        )
    print(display.to_string())
    print()


def salvar_tabelas(dados: dict):
    """Gera e salva todas as tabelas em CSV."""
    tabelas = {
        "cenario_A": (tabela_cenario_a(dados),  "Cenário A — Carga Isolada (1 conexão)"),
        "cenario_B": (tabela_cenario_b(dados),  "Cenário B — 100 SELECTs Concorrentes"),
        "cenario_C": (tabela_cenario_c(dados),  "Cenário C — 100 Escritas Concorrentes"),
        "resumo":    (tabela_resumo(dados),      "Resumo Geral — Todos os Cenários"),
    }
    for nome, (df, titulo) in tabelas.items():
        imprimir_tabela(df, titulo)
        caminho = TAB_DIR / f"{nome}.csv"
        df.to_csv(caminho)
        print(f"  [csv] → {caminho}")
    return tabelas


# ---------------------------------------------------------------------------
# GRÁFICOS — helpers
# ---------------------------------------------------------------------------

def _salvar(fig: plt.Figure, nome: str):
    caminho = GRAF_DIR / nome
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [png] → {caminho}")


def _barras(ax, sgbds_presentes, valores, erros=None, ylabel="", titulo="",
            fmt_y=None, cor_map=None):
    """
    Desenha um gráfico de barras simples em `ax`.
    sgbds_presentes: lista de chaves de SGBD na ordem de exibição
    valores: lista de valores correspondentes
    erros: lista de erros (semi-IC95), ou None
    """
    x = np.arange(len(sgbds_presentes))
    cores = [COR[s] for s in sgbds_presentes]
    nomes = [NOME[s] for s in sgbds_presentes]
    bars = ax.bar(x, valores, color=cores, width=0.5,
                  yerr=erros, capsize=6, error_kw={"linewidth": 1.5})
    ax.set_xticks(x)
    ax.set_xticklabels(nomes, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(titulo, fontsize=12, fontweight="bold", pad=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    # Rótulos nas barras
    for bar, val in zip(bars, valores):
        if val is None:
            continue
        texto = f"{val:,.0f}" if val >= 100 else f"{val:.2f}"
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.01,
                texto, ha="center", va="bottom", fontsize=9)
    if fmt_y:
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt_y))


def _semi_ic95(d, *caminho_media):
    """
    Calcula o semi-intervalo IC95 (superior - media) para barras de erro.
    Retorna None se o dado não existir.
    """
    media = _get(d, "media", *caminho_media)
    sup   = _get(d, "ic95", *caminho_media, "superior")
    if media is None or sup is None:
        return None
    return sup - media


# ---------------------------------------------------------------------------
# GRÁFICO 1 — Resumo TPS (todos os cenários, todos os SGBDs)
# ---------------------------------------------------------------------------

def grafico_resumo_tps(dados: dict):
    """
    Gráfico agrupado: TPS por cenário e SGBD.
    Cada cenário é um grupo de 3 barras (uma por SGBD).
    """
    # Cenário A tem dois TPS (INSERT e SELECT); usamos a média deles
    cen_labels = ["A (INSERT)", "A (SELECT)", "B (SELECTs\nconcorrentes)", "C (Escritas\nconcorrentes)"]

    tps_por_sgbd = {sgbd: [] for sgbd in SGBDS}
    for sgbd in SGBDS:
        dA = dados.get(sgbd, {}).get("A")
        dB = dados.get(sgbd, {}).get("B")
        dC = dados.get(sgbd, {}).get("C")
        tps_por_sgbd[sgbd] = [
            _get(dA, "media", "inserts", "tps")  if dA else None,
            _get(dA, "media", "selects", "tps")  if dA else None,
            _get(dB, "media", "tps")              if dB else None,
            _get(dC, "media", "tps")              if dC else None,
        ]

    n_grupos = len(cen_labels)
    n_sgbds  = len(SGBDS)
    width    = 0.25
    x        = np.arange(n_grupos)

    fig, ax = plt.subplots(figsize=(13, 6))

    for i, sgbd in enumerate(SGBDS):
        vals = tps_por_sgbd[sgbd]
        offset = (i - 1) * width
        bars = ax.bar(x + offset,
                      [v if v is not None else 0 for v in vals],
                      width, label=NOME[sgbd], color=COR[sgbd], alpha=0.9)
        for bar, val in zip(bars, vals):
            if val and val > 0:
                txt = f"{val:,.0f}"
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() * 1.01,
                        txt, ha="center", va="bottom", fontsize=7.5, rotation=45)

    ax.set_xticks(x)
    ax.set_xticklabels(cen_labels, fontsize=11)
    ax.set_ylabel("Transações por Segundo (TPS)", fontsize=11)
    ax.set_title("Comparativo de Vazão (TPS) — Todos os Cenários", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    # Escala log para visualizar SQLite (350k) junto com PostgreSQL (~10k) no cenário A
    ax.set_yscale("log")
    ax.set_ylabel("Transações por Segundo (TPS) — escala log", fontsize=11)

    fig.tight_layout()
    _salvar(fig, "00_resumo_tps.png")


# ---------------------------------------------------------------------------
# GRÁFICO 2 — Cenário A: TPS (INSERTs e SELECTs)
# ---------------------------------------------------------------------------

def grafico_a_tps(dados: dict):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Cenário A — Carga Isolada (1 Conexão, 100k ops)", fontsize=13, fontweight="bold")

    for ax, op in [(ax1, "inserts"), (ax2, "selects")]:
        sgbds_ok = [s for s in SGBDS if _get(dados.get(s, {}).get("A"), "media", op, "tps") is not None]
        vals  = [_get(dados[s]["A"], "media", op, "tps") for s in sgbds_ok]
        erros = [_semi_ic95(dados[s]["A"], op, "tps") for s in sgbds_ok]
        _barras(ax, sgbds_ok, vals, erros=erros,
                ylabel="TPS",
                titulo=f"{'INSERTs' if op == 'inserts' else 'SELECTs'} — TPS (média ± IC95)")

    fig.tight_layout()
    _salvar(fig, "01_cenario_A_tps.png")


# ---------------------------------------------------------------------------
# GRÁFICO 3 — Cenário A: Latência (p50 / p95 / p99)
# ---------------------------------------------------------------------------

def grafico_a_latencia(dados: dict):
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.suptitle("Cenário A — Perfil de Latência por Operação (ms)", fontsize=13, fontweight="bold")

    percentis = ["p50_ms", "p95_ms", "p99_ms"]
    rotulos   = ["p50 (mediana)", "p95", "p99"]
    ops       = [("inserts", "INSERT"), ("selects", "SELECT")]

    for row, (op, op_label) in enumerate(ops):
        for col, (perc, perc_label) in enumerate(zip(percentis, rotulos)):
            ax = axes[row][col]
            sgbds_ok = [s for s in SGBDS if _get(dados.get(s, {}).get("A"), "media", op, "latencia", perc) is not None]
            vals  = [_get(dados[s]["A"], "media", op, "latencia", perc) for s in sgbds_ok]
            erros = [_semi_ic95(dados[s]["A"], op, "latencia", perc) for s in sgbds_ok]
            _barras(ax, sgbds_ok, vals, erros=erros,
                    ylabel="ms",
                    titulo=f"{op_label} — {perc_label}")

    fig.tight_layout()
    _salvar(fig, "02_cenario_A_latencia.png")


# ---------------------------------------------------------------------------
# GRÁFICO 4 — Cenário B: TPS e Latência
# ---------------------------------------------------------------------------

def grafico_b(dados: dict):
    fig, axes = plt.subplots(1, 4, figsize=(16, 5))
    fig.suptitle("Cenário B — 100 Conexões Concorrentes (somente SELECTs)", fontsize=13, fontweight="bold")

    metricas = [
        ("tps",       None,         "TPS Total",    "TPS"),
        ("latencia",  "media_ms",   "Lat. Média",   "ms"),
        ("latencia",  "p95_ms",     "Lat. p95",     "ms"),
        ("latencia",  "p99_ms",     "Lat. p99",     "ms"),
    ]

    for ax, (chave1, chave2, titulo, ylabel) in zip(axes, metricas):
        sgbds_ok = []
        vals     = []
        erros    = []
        for s in SGBDS:
            d = dados.get(s, {}).get("B")
            if not d:
                continue
            if chave2:
                v = _get(d, "media", chave1, chave2)
                e = _semi_ic95(d, chave1, chave2)
            else:
                v = _get(d, "media", chave1)
                e = _semi_ic95(d, chave1)
            if v is not None:
                sgbds_ok.append(s)
                vals.append(v)
                erros.append(e)
        _barras(ax, sgbds_ok, vals, erros=erros, ylabel=ylabel, titulo=titulo)

    fig.tight_layout()
    _salvar(fig, "03_cenario_B.png")


# ---------------------------------------------------------------------------
# GRÁFICO 5 — Cenário C: TPS, falhas e latências
# ---------------------------------------------------------------------------

def grafico_c_tps_falhas(dados: dict):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Cenário C — 100 Conexões Concorrentes (Escritas: 50% INSERT + 50% UPDATE)",
                 fontsize=13, fontweight="bold")

    # TPS
    sgbds_tps = [s for s in SGBDS if _get(dados.get(s, {}).get("C"), "media", "tps") is not None]
    vals_tps  = [_get(dados[s]["C"], "media", "tps") for s in sgbds_tps]
    erros_tps = [_semi_ic95(dados[s]["C"], "tps") for s in sgbds_tps]
    _barras(ax1, sgbds_tps, vals_tps, erros=erros_tps, ylabel="TPS", titulo="Vazão (TPS)")

    # Taxa de falhas
    sgbds_f = [s for s in SGBDS if _get(dados.get(s, {}).get("C"), "media", "taxa_falhas") is not None]
    vals_f  = [(_get(dados[s]["C"], "media", "taxa_falhas") or 0) * 100 for s in sgbds_f]
    _barras(ax2, sgbds_f, vals_f, ylabel="% de operações com falha",
            titulo="Taxa de Falhas (%)\n(database is locked / deadlock)")

    fig.tight_layout()
    _salvar(fig, "04_cenario_C_tps_falhas.png")


def grafico_c_latencia(dados: dict):
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.suptitle("Cenário C — Perfil de Latência por Operação (ms)", fontsize=13, fontweight="bold")

    percentis = ["p50_ms", "p95_ms", "p99_ms"]
    rotulos   = ["p50 (mediana)", "p95", "p99"]
    ops       = [("latencia_inserts", "INSERT"), ("latencia_updates", "UPDATE")]

    for row, (op, op_label) in enumerate(ops):
        for col, (perc, perc_label) in enumerate(zip(percentis, rotulos)):
            ax = axes[row][col]
            sgbds_ok = [s for s in SGBDS if _get(dados.get(s, {}).get("C"), "media", op, perc) is not None]
            vals  = [_get(dados[s]["C"], "media", op, perc) for s in sgbds_ok]
            erros = [_semi_ic95(dados[s]["C"], op, perc) for s in sgbds_ok]
            _barras(ax, sgbds_ok, vals, erros=erros,
                    ylabel="ms",
                    titulo=f"{op_label} — {perc_label}")

    fig.tight_layout()
    _salvar(fig, "05_cenario_C_latencia.png")


# ---------------------------------------------------------------------------
# GRÁFICO 6 — Tempo total por cenário (visão de custo de execução)
# ---------------------------------------------------------------------------

def grafico_tempo_total(dados: dict):
    """
    Comparativo do tempo total (em segundos) de cada cenário.
    Cenário A: INSERT + SELECT somados.
    Cenários B e C: tempo da execução paralela.
    """
    cen_labels  = ["A (INSERT)", "A (SELECT)", "B", "C"]
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle("Tempo Total de Execução por Cenário (s) — menor é melhor",
                 fontsize=13, fontweight="bold")

    n_grupos = len(cen_labels)
    width    = 0.25
    x        = np.arange(n_grupos)

    for i, sgbd in enumerate(SGBDS):
        dA = dados.get(sgbd, {}).get("A")
        dB = dados.get(sgbd, {}).get("B")
        dC = dados.get(sgbd, {}).get("C")
        vals = [
            _get(dA, "media", "inserts", "tempo_total_s") if dA else None,
            _get(dA, "media", "selects", "tempo_total_s") if dA else None,
            _get(dB, "media", "tempo_total_s")            if dB else None,
            _get(dC, "media", "tempo_total_s")            if dC else None,
        ]
        offset = (i - 1) * width
        bars = ax.bar(x + offset,
                      [v if v is not None else 0 for v in vals],
                      width, label=NOME[sgbd], color=COR[sgbd], alpha=0.9)
        for bar, val in zip(bars, vals):
            if val and val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() * 1.02,
                        f"{val:.1f}s", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(cen_labels, fontsize=11)
    ax.set_ylabel("Tempo Total (s)", fontsize=11)
    ax.legend(fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.tight_layout()
    _salvar(fig, "06_tempo_total.png")


# ---------------------------------------------------------------------------
# GRÁFICO 7 — Heatmap de latência p99 (visão compacta para slides)
# ---------------------------------------------------------------------------

def grafico_heatmap_latencia(dados: dict):
    """
    Heatmap: eixo X = cenário/operação, eixo Y = SGBD, célula = p99 em ms.
    Útil para identificar rapidamente os piores casos de cada banco.
    """
    colunas = [
        ("A — INSERT p99",  "A",  "inserts",         "p99_ms"),
        ("A — SELECT p99",  "A",  "selects",          "p99_ms"),
        ("B — SELECT p99",  "B",  "latencia",         "p99_ms"),
        ("C — INSERT p99",  "C",  "latencia_inserts", "p99_ms"),
        ("C — UPDATE p99",  "C",  "latencia_updates", "p99_ms"),
    ]

    matrix = []
    linhas = []
    for sgbd in SGBDS:
        linha = []
        for _, cenario, campo1, campo2 in colunas:
            d = dados.get(sgbd, {}).get(cenario)
            v = _get(d, "media", campo1, campo2) if d else None
            linha.append(v if v is not None else 0)
        matrix.append(linha)
        linhas.append(NOME[sgbd])

    df = pd.DataFrame(matrix, index=linhas, columns=[c[0] for c in colunas])

    fig, ax = plt.subplots(figsize=(11, 4))
    # Usa log para não deixar o SQLite Cenário C dominar completamente
    log_matrix = np.log10(np.array(df.values, dtype=float) + 1)
    im = ax.imshow(log_matrix, aspect="auto", cmap="RdYlGn_r")

    ax.set_xticks(range(len(df.columns)))
    ax.set_xticklabels(df.columns, fontsize=10, rotation=20, ha="right")
    ax.set_yticks(range(len(linhas)))
    ax.set_yticklabels(linhas, fontsize=11)

    for i in range(len(linhas)):
        for j in range(len(df.columns)):
            val = df.values[i][j]
            txt = f"{val:.0f}" if val >= 1 else f"{val:.2f}"
            ax.text(j, i, txt, ha="center", va="center",
                    fontsize=9, color="black" if log_matrix[i, j] < 2 else "white")

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("log10(p99 ms + 1)", fontsize=9)
    ax.set_title("Heatmap — Latência p99 por Cenário/Operação (ms, escala log)", fontsize=12, fontweight="bold")
    fig.tight_layout()
    _salvar(fig, "07_heatmap_latencia_p99.png")


# ---------------------------------------------------------------------------
# GRÁFICO 8 — Barras de erro (IC95) para TPS nos cenários B e C
# ---------------------------------------------------------------------------

def grafico_ic95_bc(dados: dict):
    """
    Gráfico de barras com IC95 explícito para TPS nos cenários B e C,
    mostrando a estabilidade das medições.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Vazão (TPS) com Intervalo de Confiança 95%", fontsize=13, fontweight="bold")

    for ax, cenario, titulo in [(ax1, "B", "Cenário B — SELECTs Concorrentes"),
                                 (ax2, "C", "Cenário C — Escritas Concorrentes")]:
        sgbds_ok, vals, erros = [], [], []
        for s in SGBDS:
            d = dados.get(s, {}).get(cenario)
            if not d:
                continue
            media = _get(d, "media", "tps")
            inf   = _get(d, "ic95", "tps", "inferior")
            sup   = _get(d, "ic95", "tps", "superior")
            if media is None:
                continue
            sgbds_ok.append(s)
            vals.append(media)
            erros.append([media - (inf or media), (sup or media) - media])

        if not vals:
            continue

        erros_T = np.array(erros).T  # shape (2, n)
        x = np.arange(len(sgbds_ok))
        cores = [COR[s] for s in sgbds_ok]
        bars = ax.bar(x, vals, color=cores, width=0.5,
                      yerr=erros_T, capsize=8, error_kw={"linewidth": 2})
        ax.set_xticks(x)
        ax.set_xticklabels([NOME[s] for s in sgbds_ok], fontsize=11)
        ax.set_ylabel("TPS", fontsize=10)
        ax.set_title(titulo, fontsize=11, fontweight="bold")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() * 1.02,
                    f"{val:,.0f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    _salvar(fig, "08_ic95_tps_BC.png")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  ANÁLISE DE BENCHMARK — SGBDs Relacionais")
    print("=" * 60)

    print("\n[1/3] Carregando resultados...")
    dados = carregar_dados()

    # Verifica se há dados suficientes
    faltando = [(s, c) for s in SGBDS for c in CENARIOS
                if not dados.get(s, {}).get(c)]
    if faltando:
        print(f"\n  AVISO: os seguintes resultados estão ausentes:")
        for s, c in faltando:
            print(f"    • {NOME[s]} / Cenário {c}")
        print("  Os gráficos e tabelas serão gerados apenas com os dados disponíveis.\n")

    print("\n[2/3] Gerando tabelas...")
    salvar_tabelas(dados)

    print("\n[3/3] Gerando gráficos...")
    grafico_resumo_tps(dados)
    grafico_a_tps(dados)
    grafico_a_latencia(dados)
    grafico_b(dados)
    grafico_c_tps_falhas(dados)
    grafico_c_latencia(dados)
    grafico_tempo_total(dados)
    grafico_heatmap_latencia(dados)
    grafico_ic95_bc(dados)

    print("\n" + "=" * 60)
    print(f"  Tabelas → {TAB_DIR}")
    print(f"  Gráficos → {GRAF_DIR}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
