#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/ec2-user/MarketAgent}"
CONDA_DIR="${CONDA_DIR:-/home/ec2-user/miniconda3}"
CONDA_ENV="${CONDA_ENV:-market_agent_env}"
BRANCH="${BRANCH:-main}"

cd "${REPO_DIR}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

source "${CONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
pip install -e .

cd "${REPO_DIR}/postgres"
if docker compose version >/dev/null 2>&1; then
  docker compose up -d
else
  docker-compose up -d
fi
cd "${REPO_DIR}"
bash postgres/init_db.sh

sudo cp deploy/systemd/marketagent-web.service /etc/systemd/system/marketagent-web.service
sudo cp deploy/systemd/marketagent-worker.service /etc/systemd/system/marketagent-worker.service
sudo cp deploy/systemd/marketagent-worker.timer /etc/systemd/system/marketagent-worker.timer
sudo systemctl daemon-reload

sudo systemctl restart marketagent-web.service
# Do not run the one-shot worker during deploy. It can take long enough to
# block the SSH action and fail an otherwise healthy release.
sudo systemctl restart marketagent-worker.timer

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/ >/dev/null; then
    echo "Deploy completed for ${BRANCH}."
    exit 0
  fi
  sleep 2
done

sudo systemctl status marketagent-web.service --no-pager -l || true
echo "Web health check failed after restart." >&2
exit 1
