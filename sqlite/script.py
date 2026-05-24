"""
script.py — Benchmark do SQLite.

Uso (dentro do container 'benchmark'):
    python /app/sqlite/script.py --cenario A
    python /app/sqlite/script.py --cenario B
    python /app/sqlite/script.py --cenario C

Executa o cenário escolhido e grava um JSON em /app/results/.
O caminho do arquivo .db vem da variável de ambiente SQLITE_PATH (vide
docker-compose.yml).

Diferenças importantes em relação a Postgres/MySQL:
  * Não há servidor — cada conexão é direto contra um arquivo no disco.
  * Não há rede; a latência tende a ser menor no cenário A.
  * Escritas concorrentes (cenário C) costumam falhar com "database is locked"
    porque por padrão o SQLite usa rollback journal (não WAL).
    Mantemos essa configuração propositalmente — é exatamente o ponto do
    estudo: mostrar como SQLite se comporta sob alta concorrência.

Cenários:
    A) Carga isolada — 1 conexão, 100k INSERTs seguidos de 100k SELECTs.
    B) Leituras concorrentes — 100 conexões, cada uma faz 1000 SELECTs.
    C) Escritas concorrentes — 100 conexões, cada uma faz 500 INSERTs + 500 UPDATEs.
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from multiprocessing import Pool
from pathlib import Path

# Importa utilitários compartilhados
sys.path.insert(0, "/app/benchmark")
from common import (
    load_dataset,
    percentiles,
    save_results,
    now_timestamp,
    executar_repeticoes,
    selecionar_amostra,
    extrair_numericos,
    agregar_estatisticas,
)


# -----------------------------------------------------------------------------
# Configuração
# -----------------------------------------------------------------------------
DB_PATH = os.environ["SQLITE_PATH"]

# Parâmetros — mesmos valores dos outros scripts para a comparação ser justa.
NUM_INSERTS     = 100_000
NUM_SELECTS     = 100_000
NUM_WORKERS     = 100
OPS_POR_WORKER  = 1_000
NUM_REPETICOES  = 10        # cada experimento é repetido N vezes
DESCARTAR_PRIMEIRA = True  # descarta a primeira execução (aquecimento)

# -----------------------------------------------------------------------------
# SQL — parâmetros usam '?' no sqlite3 (estilo "qmark")
# -----------------------------------------------------------------------------
SQL_CREATE = """
    CREATE TABLE IF NOT EXISTS albums (
        id                INTEGER PRIMARY KEY,
        position          INTEGER,
        release_name      TEXT,
        artist_name       TEXT,
        release_date      TEXT,
        release_type      TEXT,
        primary_genres    TEXT,
        secondary_genres  TEXT,
        descriptors       TEXT,
        avg_rating        REAL,
        rating_count      INTEGER,
        review_count      INTEGER
    )
"""

SQL_INSERT = """
    INSERT INTO albums (id, position, release_name, artist_name, release_date,
                        release_type, primary_genres, secondary_genres, descriptors,
                        avg_rating, rating_count, review_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SQL_SELECT_BY_ID  = "SELECT * FROM albums WHERE id = ?"
SQL_UPDATE_RATING = "UPDATE albums SET avg_rating = ? WHERE id = ?"
SQL_COUNT         = "SELECT COUNT(*) FROM albums"
SQL_DELETE_ALL    = "DELETE FROM albums"


# -----------------------------------------------------------------------------
# Funções auxiliares
# -----------------------------------------------------------------------------
def conectar():
    """
    Abre uma conexão com o arquivo .db. Cria o arquivo (e a pasta-pai) caso
    ainda não exista. Mantemos a configuração padrão — sem WAL — para que
    o comportamento de "database is locked" no cenário C apareça.
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    # timeout=5 dá 5s antes de erroar com "database is locked"; sem isso o
    # erro seria imediato e o cenário C terminaria quase instantaneamente
    # com 100% de falhas — o que esconderia a métrica de latência.
    return sqlite3.connect(DB_PATH, timeout=5.0)


def garantir_schema():
    """Cria a tabela se não existir."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_CREATE)
    conn.commit()
    cur.close()
    conn.close()


def garantir_tabela_populada(resetar=False):
    """
    Garante que a tabela tenha exatamente NUM_INSERTS registros.
    Se resetar=True ou o tamanho for diferente, limpa e recarrega do CSV.
    """
    garantir_schema()
    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_COUNT)
    count = cur.fetchone()[0]

    if resetar or count != NUM_INSERTS:
        print(f"[setup] Tabela tem {count} linhas; recarregando para {NUM_INSERTS}...")
        cur.execute(SQL_DELETE_ALL)
        registros = load_dataset(NUM_INSERTS)
        cur.executemany(SQL_INSERT, registros)
        conn.commit()
        print("[setup] Tabela populada.")
    else:
        print(f"[setup] Tabela já tem {count} linhas; pulando carga inicial.")

    cur.close()
    conn.close()


def registro_sintetico(id_):
    """Gera registro 'fake' para INSERTs do cenário C."""
    return (
        id_,
        id_ % 5000,
        f"Album_{id_}",
        f"Artist_{id_ % 1000}",
        "2020-01-01",
        "album",
        "Rock, Electronic",
        "",
        "test, synthetic",
        4.0,
        1000,
        50,
    )


def inicializar_aleatoriedade(worker_id):
    """Define uma semente distinta por processo para evitar padrões idênticos."""
    random.seed(time.time_ns() ^ (worker_id << 16))


# -----------------------------------------------------------------------------
# CENÁRIO A
# -----------------------------------------------------------------------------
def cenario_a():
    """1 conexão, 100k INSERTs seguidos de 100k SELECTs."""
    garantir_schema()
    print(f"[A] Carregando {NUM_INSERTS} registros do CSV...")
    registros = load_dataset(NUM_INSERTS)

    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_DELETE_ALL)
    conn.commit()

    # --- INSERTs ---------------------------------------------------------
    print(f"[A] Executando {NUM_INSERTS} INSERTs...")
    latencias_insert = []
    inicio_insert = time.perf_counter()
    for r in registros:
        t0 = time.perf_counter()
        cur.execute(SQL_INSERT, r)
        latencias_insert.append(time.perf_counter() - t0)
    conn.commit()
    duracao_insert = time.perf_counter() - inicio_insert

    # --- SELECTs ---------------------------------------------------------
    print(f"[A] Executando {NUM_SELECTS} SELECTs...")
    ids_disponiveis = [r[0] for r in registros]
    latencias_select = []
    inicio_select = time.perf_counter()
    for _ in range(NUM_SELECTS):
        id_ = random.choice(ids_disponiveis)
        t0 = time.perf_counter()
        cur.execute(SQL_SELECT_BY_ID, (id_,))
        cur.fetchone()
        latencias_select.append(time.perf_counter() - t0)
    duracao_select = time.perf_counter() - inicio_select

    cur.close()
    conn.close()

    return {
        "sgbd":    "sqlite",
        "cenario": "A",
        "descricao": "1 conexão, 100k INSERTs + 100k SELECTs",
        "inserts": {
            "total":          NUM_INSERTS,
            "tempo_total_s":  round(duracao_insert, 4),
            "tps":            round(NUM_INSERTS / duracao_insert, 2),
            "latencia":       percentiles(latencias_insert),
        },
        "selects": {
            "total":          NUM_SELECTS,
            "tempo_total_s":  round(duracao_select, 4),
            "tps":            round(NUM_SELECTS / duracao_select, 2),
            "latencia":       percentiles(latencias_select),
        },
    }


# -----------------------------------------------------------------------------
# CENÁRIO B
# -----------------------------------------------------------------------------
def worker_selects(args):
    """Cada processo abre 1 conexão e faz N SELECTs aleatórios."""
    worker_id, ids_disponiveis, num_ops = args
    inicializar_aleatoriedade(worker_id)
    conn = conectar()
    cur = conn.cursor()
    latencias = []
    for _ in range(num_ops):
        id_ = random.choice(ids_disponiveis)
        t0 = time.perf_counter()
        cur.execute(SQL_SELECT_BY_ID, (id_,))
        cur.fetchone()
        latencias.append(time.perf_counter() - t0)
    cur.close()
    conn.close()
    return latencias


def cenario_b(resetar=False):
    """100 processos lendo simultaneamente do mesmo arquivo .db."""
    garantir_tabela_populada(resetar=resetar)
    ids_disponiveis = list(range(1, NUM_INSERTS + 1))

    tarefas = [(i, ids_disponiveis, OPS_POR_WORKER) for i in range(NUM_WORKERS)]

    print(f"[B] Disparando {NUM_WORKERS} workers, {OPS_POR_WORKER} SELECTs cada...")
    inicio = time.perf_counter()
    with Pool(NUM_WORKERS) as pool:
        resultados = pool.map(worker_selects, tarefas)
    duracao = time.perf_counter() - inicio

    todas_latencias = [lat for lista in resultados for lat in lista]
    total_ops = len(todas_latencias)

    return {
        "sgbd":    "sqlite",
        "cenario": "B",
        "descricao": f"{NUM_WORKERS} conexões concorrentes, somente SELECTs",
        "num_workers":     NUM_WORKERS,
        "ops_por_worker":  OPS_POR_WORKER,
        "total_ops":       total_ops,
        "tempo_total_s":   round(duracao, 4),
        "tps":             round(total_ops / duracao, 2),
        "latencia":        percentiles(todas_latencias),
    }


# -----------------------------------------------------------------------------
# CENÁRIO C
# -----------------------------------------------------------------------------
def worker_writes(args):
    """
    Cada processo faz metade INSERTs e metade UPDATEs.
    No SQLite, espera-se que apareçam muitos erros "database is locked" —
    contamos esses erros em 'falhas' para mostrar no relatório.
    """
    worker_id, num_ops, id_base_insert, id_max_update = args
    inicializar_aleatoriedade(worker_id)
    conn = conectar()
    cur = conn.cursor()

    metade = num_ops // 2
    latencias_insert = []
    latencias_update = []
    falhas = 0

    for j in range(metade):
        novo_id = id_base_insert + j
        try:
            t0 = time.perf_counter()
            cur.execute(SQL_INSERT, registro_sintetico(novo_id))
            conn.commit()
            latencias_insert.append(time.perf_counter() - t0)
        except sqlite3.Error:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            falhas += 1

    for _ in range(metade):
        id_ = random.randint(1, id_max_update)
        novo_rating = round(random.uniform(0.0, 5.0), 2)
        try:
            t0 = time.perf_counter()
            cur.execute(SQL_UPDATE_RATING, (novo_rating, id_))
            conn.commit()
            latencias_update.append(time.perf_counter() - t0)
        except sqlite3.Error:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            falhas += 1

    cur.close()
    conn.close()
    return latencias_insert, latencias_update, falhas


def cenario_c(resetar=False):
    """100 processos escrevendo simultaneamente no mesmo arquivo .db."""
    garantir_tabela_populada(resetar=resetar)

    metade = OPS_POR_WORKER // 2
    tarefas = []
    for i in range(NUM_WORKERS):
        id_base = NUM_INSERTS + 1 + i * metade
        tarefas.append((i, OPS_POR_WORKER, id_base, NUM_INSERTS))

    print(f"[C] Disparando {NUM_WORKERS} workers, {OPS_POR_WORKER} ops (50% INSERT, 50% UPDATE) cada...")
    inicio = time.perf_counter()
    with Pool(NUM_WORKERS) as pool:
        resultados = pool.map(worker_writes, tarefas)
    duracao = time.perf_counter() - inicio

    todas_lat_insert = [lat for r in resultados for lat in r[0]]
    todas_lat_update = [lat for r in resultados for lat in r[1]]
    total_falhas     = sum(r[2] for r in resultados)
    total_ops        = len(todas_lat_insert) + len(todas_lat_update)
    total_planejadas = NUM_WORKERS * OPS_POR_WORKER

    return {
        "sgbd":    "sqlite",
        "cenario": "C",
        "descricao": f"{NUM_WORKERS} conexões concorrentes, 50% INSERT + 50% UPDATE",
        "num_workers":     NUM_WORKERS,
        "ops_por_worker":  OPS_POR_WORKER,
        "total_ops":       total_ops,
        "total_ops_planejadas": total_planejadas,
        "total_falhas":    total_falhas,
        "taxa_falhas":     round((total_falhas / total_planejadas), 4) if total_planejadas else 0,
        "tempo_total_s":   round(duracao, 4),
        "tps":             round(total_ops / duracao, 2) if duracao > 0 else 0,
        "latencia_inserts": percentiles(todas_lat_insert),
        "latencia_updates": percentiles(todas_lat_update),
    }


# -----------------------------------------------------------------------------
# Entrada
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark do SQLite")
    parser.add_argument("--cenario", required=True, choices=["A", "B", "C"])
    parser.add_argument(
        "--resetar",
        action="store_true",
        help="Recarrega a tabela para exatamente 100k linhas antes de rodar o cenario",
    )
    args = parser.parse_args()

    if args.cenario == "A":
        func_cenario = cenario_a
    elif args.cenario == "B":
        func_cenario = lambda: cenario_b(resetar=args.resetar)
    else:
        func_cenario = lambda: cenario_c(resetar=args.resetar)

    resultados = executar_repeticoes(func_cenario, NUM_REPETICOES)
    usados = selecionar_amostra(resultados, descartar_primeira=DESCARTAR_PRIMEIRA)
    numericos = [extrair_numericos(r) for r in usados]
    media, desvio, percentual, erro_padrao, ic95 = agregar_estatisticas(numericos)

    base = resultados[0]
    relatorio = {
        "sgbd": base["sgbd"],
        "cenario": base["cenario"],
        "descricao": base["descricao"],
        "runs": {
            "total": NUM_REPETICOES,
            "descartadas": 1 if DESCARTAR_PRIMEIRA and len(resultados) > 1 else 0,
            "consideradas": len(usados),
        },
        "media": media,
        "desvio_padrao": desvio,
        "percentual_desvio": percentual,
        "erro_padrao": erro_padrao,
        "ic95": ic95,
    }

    nome = f"sqlite_{args.cenario}_{now_timestamp()}.json"
    save_results(nome, relatorio, subdir="sqlite")
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))
