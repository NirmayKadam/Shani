FROM python:3.11-slim-bookworm

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN echo "tzdata tzdata/Areas select Etc" | debconf-set-selections && \
    echo "tzdata tzdata/Zones/Etc select UTC" | debconf-set-selections

# Install system deps for DB, Redis, and Supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg lsb-release supervisor redis-server tzdata locales \
    && echo "en_US.UTF-8 UTF-8" > /etc/core/locale.gen || echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && echo "deb http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && wget --quiet -O /etc/apt/trusted.gpg.d/pgdg.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb https://packagecloud.io/timescale/timescaledb/debian/ bookworm main" > /etc/apt/sources.list.d/timescaledb.list \
    && wget --quiet -O /etc/apt/trusted.gpg.d/timescaledb.asc https://packagecloud.io/timescale/timescaledb/gpgkey \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-15 postgresql-client-15 timescaledb-2-postgresql-15 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8

# Install python deps sequentially to save RAM/Space
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source and configs
COPY . .
COPY supervisord.conf /supervisord.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose FastAPI port
EXPOSE 8000

# Start supervisor via wrapper script
CMD ["/start.sh"]
