# umbreld sources this file before running docker compose for the app, with
# EXPORTS_APP_DIR = this app's app-data dir. It does NOT pass an env-file to
# compose, so optional settings in app-data/.env (LAYA_DEVICE=cpu, ...) only
# reach the compose file when exported here. No .env = shipped defaults.
if [ -f "${EXPORTS_APP_DIR}/.env" ]; then
  set -a
  . "${EXPORTS_APP_DIR}/.env"
  set +a
fi
