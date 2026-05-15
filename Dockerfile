FROM python:3.11-slim

# ── System deps ───────────────────────────────────────────────────────────────
# unixodbc      : ODBC driver manager
# unixodbc-dev  : headers needed by pyodbc
# ksh           : required by the Plex driver installer script (unixpi.ksh)
# i386 libs     : rscshell (bundled in Plex 64-bit driver) is a 32-bit binary
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        unixodbc \
        unixodbc-dev \
        ksh \
        libc6:i386 \
        libncurses5:i386 \
        libstdc++6:i386 && \
    rm -rf /var/lib/apt/lists/*

# ── Plex ODBC driver ──────────────────────────────────────────────────────────
# The driver folder is gitignored — place the extracted Plex Linux driver
# files here before building. Expected layout:
#   driver/
#     lib64/
#       ivoa27.so       ← main driver shared object
#       ddtrc27.so      ← trace library
#     oaodbc64.sh       ← env setup script (not needed at runtime)
#     rscshell          ← 32-bit utility (needs i386 libs above)
COPY driver/ /usr/oaodbc81/

# ── ODBC config ───────────────────────────────────────────────────────────────
# odbcinst.ini  : registers the driver with unixODBC
# odbc.ini      : defines the Plex DSN (host, port, CompanyCode)
COPY config/odbcinst.ini /etc/odbcinst.ini
COPY config/odbc.ini     /etc/odbc.ini

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App ───────────────────────────────────────────────────────────────────────
WORKDIR /app
COPY main.py .

CMD ["python", "main.py"]