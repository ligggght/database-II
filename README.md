# Benchmark de SGBDs — Banco de Dados II

Comparação de desempenho entre **PostgreSQL**, **MySQL (InnoDB)** e **SQLite**
em três cenários: carga isolada, alta concorrência de leituras e alta
concorrência de escritas.

## Estrutura

```
postgres/, mysql/, sqlite/   scripts dos cenários (+ schema SQL nos dois primeiros)
benchmark/                   imagem do cliente Python e utilitários compartilhados
rym-top-5000/                dataset
results/                     JSONs gerados a cada execução
```

## Pré-requisitos

- Docker e Docker Compose
- Python 3.10+ no host (só para baixar o dataset)

## Como rodar

### 1. Subir os containers

```bash
docker compose up -d
```

Esse comando constrói a imagem do `benchmark`, sobe os containers do
PostgreSQL e do MySQL (com as tabelas já criadas pelos scripts em
`postgres/init/` e `mysql/init/`) e deixa o container do cliente vivo
aguardando comandos.

### 2. Executar um cenário

```bash
docker compose exec benchmark python /app/<sgbd>/script.py --cenario <A|B|C>
```

Exemplos:

```bash
docker compose exec benchmark python /app/postgres/script.py --cenario A
docker compose exec benchmark python /app/mysql/script.py    --cenario B
docker compose exec benchmark python /app/sqlite/script.py   --cenario C
```

Para garantir uma base sempre igual entre execucoes (mesmo com volumes persistentes),
use a flag `--resetar`:

```bash
docker compose exec benchmark python /app/postgres/script.py --cenario B --resetar
```

Cenários:

| | Descrição |
|---|---|
| **A** | 1 conexão; 100k INSERTs seguidos de 100k SELECTs |
| **B** | 100 conexões concorrentes, somente SELECTs |
| **C** | 100 conexões concorrentes, 50% INSERTs + 50% UPDATEs |

### 3. Ver os resultados

Cada execução gera um JSON em `results/<sgbd>_<cenario>_<timestamp>.json`.
O experimento roda 31 vezes, descarta a primeira (aquecimento) e reporta
média e desvio padrão das métricas (tempo, TPS e latências).

### 4. Encerrar

```bash
docker compose down       # mantém os dados dos volumes
docker compose down -v    # apaga os volumes (reseta os bancos)
```
