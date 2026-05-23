"""
common.py — utilitários compartilhados pelos scripts de benchmark.

Mantém em um lugar só tudo o que NÃO é específico de um SGBD:
- leitura do dataset CSV e geração das tuplas de INSERT;
- cálculo de estatísticas (média e percentis das latências);
- gravação dos resultados em JSON;
- timestamp para nomear arquivos.

Cada script (postgres/script.py, mysql/script.py, sqlite/script.py) importa
daqui as funções de uso geral e fica responsável apenas pela lógica de
conexão e dos cenários.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

# Caminhos dentro do container (montados pelo docker-compose.yml).
DATASET_PATH = Path("/app/rym-top-5000/rym_raw1.csv")
RESULTS_DIR = Path("/app/results")


def load_dataset(n):
    """
    Lê o CSV bruto e devolve uma lista de N tuplas prontas para INSERT na
    tabela 'albums'.

    O CSV bruto tem ~123k linhas, então 100k cabe sem problemas. Caso N seja
    maior que o número de linhas disponíveis, a função "dá a volta" e repete
    do começo — mas o 'id' continua sempre incrementando, evitando colisão de
    chave primária.

    Cada tupla tem 12 campos na ordem exata do INSERT_SQL definido nos
    scripts dos SGBDs.
    """
    # Carrega todo o CSV em memória — ~123k linhas é pequeno o bastante.
    with open(DATASET_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        linhas_csv = list(reader)

    if not linhas_csv:
        raise RuntimeError(f"Dataset vazio em {DATASET_PATH}")

    registros = []
    for i in range(n):
        # wrap-around: se N > linhas, reaproveita as linhas do começo
        linha = linhas_csv[i % len(linhas_csv)]
        registros.append((
            i + 1,                                       # id (sempre único)
            _to_int(linha.get("position")),
            (linha.get("release_name") or "")[:500],
            (linha.get("artist_name") or "")[:500],
            (linha.get("release_date") or "")[:50],
            (linha.get("release_type") or "")[:50],
            linha.get("primary_genres") or "",
            linha.get("secondary_genres") or "",
            linha.get("descriptors") or "",
            _to_float(linha.get("avg_rating")),
            _to_int(linha.get("rating_count")),
            _to_int(linha.get("review_count")),
        ))
    return registros


def _to_int(valor):
    """Converte string em int; devolve None se a conversão falhar."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _to_float(valor):
    """Converte string em float; devolve None se a conversão falhar."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def percentiles(latencias_seg):
    """
    Recebe uma lista de latências em SEGUNDOS e devolve um dict com média,
    mínimo, máximo e percentis p50/p95/p99, todos em MILISSEGUNDOS.

    Usamos o método "nearest-rank" (simples e suficiente para o tamanho de
    amostra que vamos coletar).
    """
    if not latencias_seg:
        return {
            "media_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0,
            "min_ms": 0.0, "max_ms": 0.0,
        }

    ordenadas = sorted(latencias_seg)
    n = len(ordenadas)

    def percentil(q):
        # índice "nearest-rank": q entre 0 e 1
        idx = max(0, min(n - 1, int(q * n)))
        return ordenadas[idx] * 1000  # segundos -> milissegundos

    return {
        "media_ms": (sum(ordenadas) / n) * 1000,
        "p50_ms":   percentil(0.50),
        "p95_ms":   percentil(0.95),
        "p99_ms":   percentil(0.99),
        "min_ms":   ordenadas[0] * 1000,
        "max_ms":   ordenadas[-1] * 1000,
    }


def save_results(nome_arquivo, dados):
    """
    Grava o dict 'dados' como JSON em /app/results/<nome_arquivo>.
    Cria a pasta se não existir e retorna o caminho do arquivo gerado.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = RESULTS_DIR / nome_arquivo
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
    print(f"[OK] Resultados salvos em {caminho}")
    return caminho


def now_timestamp():
    """Timestamp legível para nomear arquivos, ex: 20260523_143055."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
