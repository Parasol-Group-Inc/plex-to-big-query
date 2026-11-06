#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
: "${PLEX_ACCESS_TOKEN:?export PLEX_ACCESS_TOKEN first}"
: "${PLEX_ODBC_USER:=edominguez.parasol}"
export PLEX_ODBC_USER
SUDO=$([ "$(id -u)" = 0 ] || echo sudo)
{ command -v odbcinst >/dev/null && [ -e /usr/lib64/libpam.so.0 ]; } || $SUDO dnf install -y -q unixODBC pam
command -v pip3 >/dev/null || $SUDO dnf install -y -q python3-pip
python3 -c "import pyodbc" 2>/dev/null || pip3 install -q --user pyodbc
printf "[ODBC]\nInstallDir=%s\nIANAAppCodePage=4\nTrace=0\n" "$DIR/driver" > "$DIR/odbc.ini"
export ODBCINI="$DIR/odbc.ini"
export LD_LIBRARY_PATH="$DIR/driver/lib64" PLEX_DRIVER="$DIR/driver/lib64/ivoa27.so"
export PROBE_SOURCE="${PROBE_SOURCE:-AWS CloudShell $AWS_REGION}"
python3 "$DIR/plex_odbc_probe.py" "$@"
