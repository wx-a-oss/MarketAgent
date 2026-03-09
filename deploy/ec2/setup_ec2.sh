#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/wx-a-oss/MarketAgent.git}"
REPO_DIR="${REPO_DIR:-/home/ec2-user/MarketAgent}"
CONDA_DIR="${CONDA_DIR:-/home/ec2-user/miniconda3}"
CONDA_ENV="${CONDA_ENV:-market_agent_env}"
ENV_FILE="${ENV_FILE:-/etc/marketagent/marketagent.env}"
SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"

sudo dnf install -y git docker wget tar gzip postgresql15
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user || true

if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  sudo curl -fsSL https://github.com/docker/compose/releases/download/v2.39.0/docker-compose-linux-aarch64 \
    -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
fi

if [ ! -d "${CONDA_DIR}" ]; then
  curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh -o /tmp/miniconda.sh
  bash /tmp/miniconda.sh -b -p "${CONDA_DIR}"
fi

if [ ! -d "${REPO_DIR}" ]; then
  git clone "${REPO_URL}" "${REPO_DIR}"
fi

source "${CONDA_DIR}/etc/profile.d/conda.sh"
if ! conda env list | awk '{print $1}' | grep -qx "${CONDA_ENV}"; then
  conda create -n "${CONDA_ENV}" python=3.13 -y
fi

cd "${REPO_DIR}"
git fetch origin main
git checkout main
git pull --ff-only origin main

conda activate "${CONDA_ENV}"
pip install -e .

sudo install -d -m 0755 /etc/marketagent
sudo tee "${ENV_FILE}" >/dev/null <<EOF
FINNHUB_API_KEY=${FINNHUB_API_KEY:-}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY:-}
GEMINI_API_KEY=${GEMINI_API_KEY:-}
PGHOST=localhost
PGPORT=5432
PGUSER=market_agent
PGPASSWORD=market_agent_password
PGDATABASE=market_agent
COMPANY_STORY_WARMUP_DAYS=${COMPANY_STORY_WARMUP_DAYS:-10}
COMPANY_STORY_WARMUP_SLICE_DAYS=${COMPANY_STORY_WARMUP_SLICE_DAYS:-10}
EOF
sudo chmod 600 "${ENV_FILE}"

cd "${REPO_DIR}/postgres"
if docker compose version >/dev/null 2>&1; then
  docker compose up -d
else
  docker-compose up -d
fi
cd "${REPO_DIR}"
bash postgres/init_db.sh

sudo cp deploy/systemd/marketagent-web.service "${SERVICE_DIR}/marketagent-web.service"
sudo cp deploy/systemd/marketagent-worker.service "${SERVICE_DIR}/marketagent-worker.service"
sudo cp deploy/systemd/marketagent-worker.timer "${SERVICE_DIR}/marketagent-worker.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now marketagent-web.service
sudo systemctl enable --now marketagent-worker.timer

curl -fsS http://127.0.0.1:8000/ >/dev/null || true
echo "EC2 setup completed."
