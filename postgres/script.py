"""
script.py — Benchmark do PostgreSQL.

Uso (dentro do container 'benchmark'):
    python /app/postgres/script.py --cenario A
    python /app/postgres/script.py --cenario B
    python /app/postgres/script.py --cenario C

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

import psycopg2

# Importa utilitários compartilhados (load_dataset, percentiles, save_results, ...)
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
# Configuração de conexão — lida do ambiente (vide docker-compose.yml)
# -----------------------------------------------------------------------------
DB_CONFIG = {
    "host":     os.environ["PG_HOST"],
    "port":     int(os.environ["PG_PORT"]),
    "user":     os.environ["PG_USER"],
    "password": os.environ["PG_PASSWORD"],
    "dbname":   os.environ["PG_DB"],
}

# -----------------------------------------------------------------------------
# Parâmetros dos cenários
# -----------------------------------------------------------------------------
NUM_INSERTS     = 100_000   # cenário A: inserts iniciais + popular tabela p/ B e C
NUM_SELECTS     = 100_000   # cenário A
NUM_WORKERS     = 100       # cenários B e C
OPS_POR_WORKER  = 1_000     # cenários B e C (total = 100k operações)
NUM_REPETICOES  = 61        # cada experimento é repetido N vezes
DESCARTAR_PRIMEIRA = True  # descarta a primeira execução (aquecimento)

# -----------------------------------------------------------------------------
# SQL — parâmetros usam %s no psycopg2 (estilo "format")
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

SQL_TRUNCATE = "TRUNCATE albums"


# -----------------------------------------------------------------------------
# Funções auxiliares
# -----------------------------------------------------------------------------
def conectar():
    """Abre uma conexão nova com o Postgres."""
    return psycopg2.connect(**DB_CONFIG)


def garantir_tabela_populada(resetar=False):
    """
    Garante que a tabela 'albums' tenha exatamente NUM_INSERTS registros.
    Se resetar=True ou o tamanho for diferente, limpa e recarrega do CSV.
    Usado nos cenários B e C, que precisam de dados pré-carregados para ler/atualizar.
    """
    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_COUNT)
    count = cur.fetchone()[0]

    if resetar or count != NUM_INSERTS:
        print(f"[setup] Tabela tem {count} linhas; recarregando para {NUM_INSERTS}...")
        cur.execute(SQL_TRUNCATE)
        registros = load_dataset(NUM_INSERTS)
        # executemany é mais eficiente que vários execute em loop para essa carga inicial
        cur.executemany(SQL_INSERT, registros)
        conn.commit()
        print("[setup] Tabela populada.")
    else:
        print(f"[setup] Tabela já tem {count} linhas; pulando carga inicial.")

    cur.close()
    conn.close()


def registro_sintetico(id_):
    """
    Gera um registro "fake" para os INSERTs do cenário C.
    Evita ter que carregar o CSV em cada worker (que custa caro com multiprocessing).
    """
    return (
        id_,
        id_ % 5000,                # position
        f"Album_{id_}",            # release_name
        f"Artist_{id_ % 1000}",    # artist_name
        "2020-01-01",              # release_date
        "album",                   # release_type
        "Rock, Electronic",        # primary_genres
        "",                        # secondary_genres
        "test, synthetic",         # descriptors
        4.0,                       # avg_rating
        1000,                      # rating_count
        50,                        # review_count
    )


def inicializar_aleatoriedade(worker_id):
    """Define uma semente distinta por processo para evitar padrões idênticos."""
    random.seed(time.time_ns() ^ (worker_id << 16))


# -----------------------------------------------------------------------------
# CENÁRIO A — 1 conexão, 100k INSERTs + 100k SELECTs
# -----------------------------------------------------------------------------
def cenario_a():
    """
    Mede a velocidade bruta de I/O com uma única conexão.
    Expectativa: tempos baixos pela ausência de contenção entre clientes;
    overhead de rede está presente (Postgres é client-server).
    """
    print(f"[A] Carregando {NUM_INSERTS} registros do CSV...")
    registros = load_dataset(NUM_INSERTS)

    # Limpa a tabela para começar do zero (mede tempo "puro" de inserção)
    conn = conectar()
    cur = conn.cursor()
    cur.execute(SQL_TRUNCATE)
    conn.commit()

    # --- Fase 1: INSERTs medidos um a um ----------------------------------
    print(f"[A] Executando {NUM_INSERTS} INSERTs...")
    latencias_insert = []
    inicio_insert = time.perf_counter()
    for r in registros:
        t0 = time.perf_counter()
        cur.execute(SQL_INSERT, r)
        latencias_insert.append(time.perf_counter() - t0)
    conn.commit()  # commit único no final — mede inserção, não sync de WAL por linha
    duracao_insert = time.perf_counter() - inicio_insert

    # --- Fase 2: SELECTs por id aleatório ---------------------------------
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
        "sgbd":    "postgres",
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
# CENÁRIO B — 100 conexões, todas só lendo
# -----------------------------------------------------------------------------
def worker_selects(args):
    """
    Função executada por cada processo no pool do cenário B.
    Abre 1 conexão, faz OPS_POR_WORKER SELECTs aleatórios, devolve as latências.
    """
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
    """
    100 processos lendo simultaneamente. Mede como o SGBD despacha leituras
    para múltiplos clientes concorrentes.
    """
    garantir_tabela_populada(resetar=resetar)
    ids_disponiveis = list(range(1, NUM_INSERTS + 1))

    # Cada worker recebe (id, lista_de_ids, num_ops) — multiprocessing serializa
    # esses argumentos via pickle, então mantemos pequenos.
    tarefas = [(i, ids_disponiveis, OPS_POR_WORKER) for i in range(NUM_WORKERS)]

    print(f"[B] Disparando {NUM_WORKERS} workers, {OPS_POR_WORKER} SELECTs cada...")
    inicio = time.perf_counter()
    with Pool(NUM_WORKERS) as pool:
        resultados = pool.map(worker_selects, tarefas)
    duracao = time.perf_counter() - inicio

    # Junta as latências de todos os workers em uma lista única para estatísticas
    todas_latencias = [lat for lista in resultados for lat in lista]
    total_ops = len(todas_latencias)

    return {
        "sgbd":    "postgres",
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
# CENÁRIO C — 100 conexões escrevendo (INSERT + UPDATE)
# -----------------------------------------------------------------------------
def worker_writes(args):
    """
    Função executada por cada processo no pool do cenário C.
    Faz metade INSERTs (com ids únicos por worker) e metade UPDATEs em ids
    já existentes.
    """
    worker_id, num_ops, id_base_insert, id_max_update = args
    inicializar_aleatoriedade(worker_id)
    conn = conectar()
    cur = conn.cursor()

    metade = num_ops // 2
    latencias_insert = []
    latencias_update = []
    falhas = 0

    # --- INSERTs ---------------------------------------------------------
    # Cada worker tem um range único de ids para inserir, evitando conflito
    # de chave primária entre workers.
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

    # --- UPDATEs ---------------------------------------------------------
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


def cenario_c(resetar=False):
    """
    100 processos escrevendo simultaneamente. Mede gerenciamento de locks
    e fila de escritas concorrentes.
    """
    garantir_tabela_populada(resetar=resetar)

    # Cada worker reserva um bloco de ids para INSERT, começando logo após
    # o último id existente (NUM_INSERTS).
    metade = OPS_POR_WORKER // 2
    tarefas = []
    for i in range(NUM_WORKERS):
        id_base = NUM_INSERTS + 1 + i * metade  # ex: 100001, 100501, 101001, ...
        tarefas.append((i, OPS_POR_WORKER, id_base, NUM_INSERTS))

    print(f"[C] Disparando {NUM_WORKERS} workers, {OPS_POR_WORKER} ops (50% INSERT, 50% UPDATE) cada...")
    inicio = time.perf_counter()
    with Pool(NUM_WORKERS) as pool:
        resultados = pool.map(worker_writes, tarefas)
    duracao = time.perf_counter() - inicio

    # Junta resultados de todos os workers
    todas_lat_insert = [lat for r in resultados for lat in r[0]]
    todas_lat_update = [lat for r in resultados for lat in r[1]]
    total_falhas     = sum(r[2] for r in resultados)
    total_ops        = len(todas_lat_insert) + len(todas_lat_update)
    total_planejadas = NUM_WORKERS * OPS_POR_WORKER

    return {
        "sgbd":    "postgres",
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
    parser = argparse.ArgumentParser(description="Benchmark do PostgreSQL")
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

    nome = f"postgres_{args.cenario}_{now_timestamp()}.json"
    save_results(nome, relatorio)
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))
