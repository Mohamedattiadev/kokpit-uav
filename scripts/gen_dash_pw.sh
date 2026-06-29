#!/usr/bin/env bash
# N8 — dashboard auth secret üret. systemd EnvironmentFile için.
# Sudo gerekir (/etc/kokpit/ write).
set -e
DIR=/etc/kokpit
FILE=$DIR/dash_pw
if [[ -f "$FILE" ]]; then
  echo "Var: $FILE (üzerine yazmak için önce sil)"
  exit 0
fi
sudo mkdir -p "$DIR"
PW=$(openssl rand -hex 16)
echo "KOKPIT_DASH_PW=$PW" | sudo tee "$FILE" >/dev/null
sudo chmod 600 "$FILE"
echo "OK: $FILE (chmod 600)"
echo "Tarayıcı user: kokpit  password: $PW"
