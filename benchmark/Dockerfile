# =============================================================================
# Dockerfile do container "benchmark" (cliente).
# -----------------------------------------------------------------------------
# Esta imagem contém apenas o Python e os drivers para conectar aos SGBDs.
# Os scripts em si NÃO são copiados para a imagem — eles entram via bind mount
# definido no docker-compose.yml, para que possamos editar no host e a mudança
# já reflita dentro do container sem precisar de rebuild.
# =============================================================================

FROM python:3.12-slim

# Evita buffer no stdout/stderr (mensagens aparecem em tempo real nos logs)
# e desliga avisos do pip que poluem a saída.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instala apenas as dependências Python. Usamos pacotes "binary" (wheels
# pré-compilados) para psycopg2 e mysql-connector, evitando precisar de gcc,
# libpq-dev, etc. dentro da imagem.
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Nada de CMD/ENTRYPOINT: o docker-compose.yml define 'sleep infinity' para
# manter o container vivo e nós executamos os cenários via 'docker compose exec'.
