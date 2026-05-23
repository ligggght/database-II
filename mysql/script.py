"""
script.py — Benchmark do MySQL (InnoDB).

Uso (dentro do container 'benchmark'):
    python /app/mysql/script.py --cenario A
    python /app/mysql/script.py --cenario B
    python /app/mysql/script.py --cenario C

Executa o cenário escolhido e grava um JSON em /app/results/.
A conexão usa as variáveis de ambiente definidas no docker-compose.yml.

Cenários:
    A) Carga isolada — 1 conexão, 100k INSERTs seguidos de 100k SELECTs.
    B) Leituras concorrentes — 100 conexões, cada uma faz 1000 SELECTs.
    C) Escritas concorrentes — 100 conexões, cada uma faz 500 INSERTs + 500 UPDATEs.
"""

import argparse
import json
import os
import random
import sys
import time
from multiprocessing import Pool

import mysql.connector

# Importa utilitários compartilhados
sys.path.insert(0, "/app/benchmark")
from common import load_dataset, percentiles, save_results, now_timestamp


# -----------------------------------------------------------------------------
# Configuração de conexão
# -----------------------------------------------------------------------------
DB_CONFIG = {
    "host":     os.environ["MYSQL_HOST"],
    "port":     int(os.environ["MYSQL_PORT"]),
    "user":     os.environ["MYSQL_USER"],
    "password": os.environ["MYSQL_PASSWORD"],
    "database": os.environ["MYSQL_DB"],
    # Desabilita o autocommit para controlarmos os commits manualmente,
    # igual aos outros scripts.
    "autocommit": False,
}

# -----------------------------------------------------------------------------
# Parâmetros dos cenários — mesmos valores dos outros scripts
# -----------------------------------------------------------------------------
NUM_INSERTS     = 100_000
NUM_SELECTS     = 100_000
NUM_WORKERS     = 100
OPS_POR_WORKER  = 1_000

# -----------------------------------------------------------------------------
# SQL — parâmetros usam %s no mysql-connector (mesma sintaxe do psycopg2)
# -----------------------------------------------------------------------------
SQL_INSERT = """
    INSERT INTO albums (id, position, release_name, artist_name, release_date,
                        release_type, primary_genres, secondary_genres, descriptors,
                        avg_rating, rating_count, review_count)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

SQL_SELECT_BY_ID = "SELECT * FROM albums WHERE id = %s"

SQL_UPDATE_RATING = "UPDATE albums SET avg_rating = %s WHERE id = %s"

SQL_COUNT = "SELECT COUNT(*) FROM albums"

SQL_TRUNCATE = "TRUNCATE TABLE albums"


# -----------------------------------------------------------------------------
# Funções auxiliares
# -----------------------------------------------------------------------------
def conectar():
    """Abre uma conexão nova com o MySQL."""
    return mysql.connector.connect(**DB_CONFIG)


def garantir_tabela_populada():
    """
    Garante que a tabela 'albums' tenha pelo menos NUM_INSERTS registros.
    Se estiver vazia/menor, limpa e popula.
    """
    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_COUNT)
    count = cur.fetchone()[0]

    if count < NUM_INSERTS:
        print(f"[setup] Tabela tem {count} linhas; populando com {NUM_INSERTS}...")
        cur.execute(SQL_TRUNCATE)
        registros = load_dataset(NUM_INSERTS)
        cur.executemany(SQL_INSERT, registros)
        conn.commit()
        print(f"[setup] Tabela populada.")
    else:
        print(f"[setup] Tabela já tem {count} linhas; pulando carga inicial.")

    cur.close()
    conn.close()


def registro_sintetico(id_):
    """Gera registro "fake" para os INSERTs do cenário C (mesmo formato dos outros scripts)."""
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


# -----------------------------------------------------------------------------
# CENÁRIO A
# -----------------------------------------------------------------------------
def cenario_a():
    """
    1 conexão, 100k INSERTs seguidos de 100k SELECTs.
    """
    print(f"[A] Carregando {NUM_INSERTS} registros do CSV...")
    registros = load_dataset(NUM_INSERTS)

    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_TRUNCATE)
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
        "sgbd":    "mysql",
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


def cenario_b():
    """100 processos lendo simultaneamente."""
    garantir_tabela_populada()
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
        "sgbd":    "mysql",
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
    """Cada processo faz metade INSERTs (ids únicos) e metade UPDATEs (ids existentes)."""
    worker_id, num_ops, id_base_insert, id_max_update = args
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
        except Exception:
            conn.rollback()
            falhas += 1

    for _ in range(metade):
        id_ = random.randint(1, id_max_update)
        novo_rating = round(random.uniform(0.0, 5.0), 2)
        try:
            t0 = time.perf_counter()
            cur.execute(SQL_UPDATE_RATING, (novo_rating, id_))
            conn.commit()
            latencias_update.append(time.perf_counter() - t0)
        except Exception:
            conn.rollback()
            falhas += 1

    cur.close()
    conn.close()
    return latencias_insert, latencias_update, falhas


def cenario_c():
    """100 processos escrevendo simultaneamente."""
    garantir_tabela_populada()

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

    return {
        "sgbd":    "mysql",
        "cenario": "C",
        "descricao": f"{NUM_WORKERS} conexões concorrentes, 50% INSERT + 50% UPDATE",
        "num_workers":     NUM_WORKERS,
        "ops_por_worker":  OPS_POR_WORKER,
        "total_ops":       total_ops,
        "total_falhas":    total_falhas,
        "tempo_total_s":   round(duracao, 4),
        "tps":             round(total_ops / duracao, 2) if duracao > 0 else 0,
        "latencia_inserts": percentiles(todas_lat_insert),
        "latencia_updates": percentiles(todas_lat_update),
    }


# -----------------------------------------------------------------------------
# Entrada
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark do MySQL/InnoDB")
    parser.add_argument("--cenario", required=True, choices=["A", "B", "C"])
    args = parser.parse_args()

    if args.cenario == "A":
        resultado = cenario_a()
    elif args.cenario == "B":
        resultado = cenario_b()
    else:
        resultado = cenario_c()

    nome = f"mysql_{args.cenario}_{now_timestamp()}.json"
    save_results(nome, resultado)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
