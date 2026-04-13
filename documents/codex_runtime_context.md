# Codex Runtime Context

This file is the reusable operational context for new Codex threads working on `/Users/wenxina/Documents/MarketAgent`.

Use it when a new agent needs to understand:
- local environment setup
- deployment flow
- how to SSH into EC2
- how to check service status and logs
- where runtime credentials/config live
- how the app is exposed through Cloudflare

## Repository

- Local repo path: `/Users/wenxina/Documents/MarketAgent`
- Primary branch: `main`
- GitHub repo: `https://github.com/wx-a-oss/MarketAgent.git`

## Local Development Environment

### Python / Conda

- Conda env name: `market_agent_env`
- Python version target: `3.13`

Typical local setup:

```bash
cd /Users/wenxina/Documents/MarketAgent
conda create -n market_agent_env python=3.13 -y
conda activate market_agent_env
pip install -e .
```

### Local app run

```bash
cd /Users/wenxina/Documents/MarketAgent
conda activate market_agent_env
uvicorn frontend.web.server:app --reload --log-level info
```

App URL:

- `http://127.0.0.1:8000`

### Local database

Postgres runs through Docker Compose in `/Users/wenxina/Documents/MarketAgent/postgres`.

Start DB:

```bash
cd /Users/wenxina/Documents/MarketAgent/postgres
docker compose up -d
cd /Users/wenxina/Documents/MarketAgent
bash postgres/init_db.sh
```

## Required Runtime Credentials

These are runtime environment variables used by the app.

Required in most real environments:
- `FINNHUB_API_KEY`
- `OPENAI_API_KEY`

Optional depending on usage:
- `PERPLEXITY_API_KEY`
- `GEMINI_API_KEY`

### DB env vars

If `DATABASE_URL` is not set, the code falls back to:
- `PGHOST=localhost`
- `PGPORT=5432`
- `PGUSER=market_agent`
- `PGPASSWORD=market_agent_password`
- `PGDATABASE=market_agent`

## EC2 Runtime Layout

The deployed runtime on EC2 uses these paths:

- Repo path: `/home/ec2-user/MarketAgent`
- Conda install: `/home/ec2-user/miniconda3`
- Conda env: `market_agent_env`
- Runtime env file: `/etc/marketagent/marketagent.env`
- Web app local port: `8000`

### EC2 OS / architecture

- OS family: `Amazon Linux 2023`
- Architecture: `aarch64` / `arm64`

This matters for package installs like `cloudflared` and Docker Compose binaries.

## SSH Access To EC2

### Local SSH config

The working local SSH config entry is:

```sshconfig
Host ec2-54-159-76-176.compute-1.amazonaws.com
  HostName ec2-54-159-76-176.compute-1.amazonaws.com
  IdentityFile ~/.ssh/ec2_market_agent_keypair.pem
  User ec2-user
```

### SSH key path

- Private key: `/Users/wenxina/.ssh/ec2_market_agent_keypair.pem`

### Connect to EC2

```bash
ssh ec2-54-159-76-176.compute-1.amazonaws.com
```

If needed, the fully explicit form is:

```bash
ssh -i /Users/wenxina/.ssh/ec2_market_agent_keypair.pem ec2-user@ec2-54-159-76-176.compute-1.amazonaws.com
```

## EC2 Service Management

### systemd units

Deployed services:
- `marketagent-web.service`
- `marketagent-worker.service`
- `marketagent-worker.timer`

Repo source files:
- `/Users/wenxina/Documents/MarketAgent/deploy/systemd/marketagent-web.service`
- `/Users/wenxina/Documents/MarketAgent/deploy/systemd/marketagent-worker.service`
- `/Users/wenxina/Documents/MarketAgent/deploy/systemd/marketagent-worker.timer`

### Web service status

```bash
sudo systemctl status marketagent-web.service --no-pager -l
```

### Worker service status

```bash
sudo systemctl status marketagent-worker.service --no-pager -l
```

### Worker timer status

```bash
sudo systemctl status marketagent-worker.timer --no-pager -l
systemctl list-timers --all | grep marketagent-worker
```

### Restart services

```bash
sudo systemctl restart marketagent-web.service
sudo systemctl restart marketagent-worker.service
sudo systemctl restart marketagent-worker.timer
```

### Enable services

```bash
sudo systemctl enable --now marketagent-web.service
sudo systemctl enable --now marketagent-worker.timer
```

### Logs

Web logs:

```bash
journalctl -u marketagent-web.service -n 200 --no-pager
journalctl -u marketagent-web.service -f
```

Worker logs:

```bash
journalctl -u marketagent-worker.service -n 200 --no-pager
journalctl -u marketagent-worker.service -f
```

Timer logs:

```bash
journalctl -u marketagent-worker.timer -n 100 --no-pager
```

## Deployed Commands / Behavior

### Web service command

The web service runs:

```bash
/home/ec2-user/miniconda3/bin/conda run --no-capture-output -n market_agent_env \
  uvicorn frontend.web.server:app --host 0.0.0.0 --port 8000 --log-level info
```

### Worker command

The worker service runs:

```bash
/home/ec2-user/miniconda3/bin/conda run --no-capture-output -n market_agent_env \
  marketagent-company-worker --source finnhub --provider openai \
  --market-model gpt-5.4 --prompt-style simple --output-language zh-CN \
  --timezone America/Los_Angeles
```

### Worker schedule

Current timer definition:

- intended schedule: daily at `23:00:00` America/Los_Angeles
- service unit: `marketagent-worker.service`

Note: the timer file currently uses `Timezone=America/Los_Angeles`. Systemd on the EC2 host has previously warned that `Timezone` is an unknown key. If schedule behavior is questioned, inspect the actual timer state with `systemctl list-timers` and logs.

## Deploy Flow

### Automatic deploy trigger

Pushes to `main` trigger GitHub Actions deploy.

Workflow file:
- `/Users/wenxina/Documents/MarketAgent/.github/workflows/deploy-ec2.yml`

Workflow behavior:
1. checkout repo
2. install package
3. run syntax checks
4. SSH into EC2
5. run `/home/ec2-user/MarketAgent/deploy/ec2/deploy.sh`

### GitHub Actions secrets required

- `EC2_HOST`
- `EC2_USER`
- `EC2_SSH_PRIVATE_KEY`

### Manual deploy on EC2

```bash
ssh ec2-54-159-76-176.compute-1.amazonaws.com
cd /home/ec2-user/MarketAgent
bash deploy/ec2/deploy.sh
```

### What `deploy.sh` does

Repo file:
- `/Users/wenxina/Documents/MarketAgent/deploy/ec2/deploy.sh`

Key behavior:
1. fetch `origin/main`
2. hard reset EC2 repo to `origin/main`
3. activate `market_agent_env`
4. `pip install -e .`
5. start Postgres Docker Compose in `/home/ec2-user/MarketAgent/postgres`
6. run `bash postgres/init_db.sh`
7. copy systemd unit files into `/etc/systemd/system`
8. `systemctl daemon-reload`
9. restart web, worker, timer
10. health-check `http://127.0.0.1:8000/`

Important consequence:
- manual edits made directly on EC2 inside `/home/ec2-user/MarketAgent` will be overwritten by deploy because the script runs `git reset --hard origin/main`.

## First-Time EC2 Bootstrap

Repo bootstrap script:
- `/Users/wenxina/Documents/MarketAgent/deploy/ec2/setup_ec2.sh`

This script:
- installs git/docker/wget/tar/gzip/postgresql client
- installs Docker Compose if missing
- installs Miniconda for Linux ARM64
- clones repo
- creates `market_agent_env`
- installs package
- writes `/etc/marketagent/marketagent.env`
- starts Postgres via Docker Compose
- runs migrations/bootstrap
- installs and enables systemd units

## Runtime Environment File On EC2

Path:
- `/etc/marketagent/marketagent.env`

This is the main runtime credential/config file for systemd-managed app processes.

Typical inspection command:

```bash
sudo cat /etc/marketagent/marketagent.env
```

Edit carefully:

```bash
sudo vi /etc/marketagent/marketagent.env
sudo systemctl restart marketagent-web.service
sudo systemctl restart marketagent-worker.service
sudo systemctl restart marketagent-worker.timer
```

Expected contents include keys like:
- `FINNHUB_API_KEY`
- `OPENAI_API_KEY`
- `PERPLEXITY_API_KEY`
- `GEMINI_API_KEY`
- `PGHOST`
- `PGPORT`
- `PGUSER`
- `PGPASSWORD`
- `PGDATABASE`
- `COMPANY_STORY_WARMUP_DAYS`
- `COMPANY_STORY_WARMUP_SLICE_DAYS`

## Cloudflare / Private Access

The app is exposed through Cloudflare Tunnel + Access, not by relying on a directly open app port.

Known live hostname:
- `https://marketagent.xwawx.com`

Known domain:
- `xwawx.com`

Operational model:
- Cloudflare Access protects the app
- `cloudflared` runs on EC2
- origin app remains on local EC2 port `8000`
- browser traffic goes through Cloudflare to `http://localhost:8000` on EC2

### EC2-side tunnel checks

```bash
sudo systemctl status cloudflared --no-pager -l
journalctl -u cloudflared -n 200 --no-pager
journalctl -u cloudflared -f
```

### Local origin check on EC2

```bash
curl -I http://127.0.0.1:8000/
```

If Cloudflare URL fails but localhost works, the problem is likely in:
- `cloudflared`
- Cloudflare Access policy
- Cloudflare Tunnel hostname config

## Current Model Defaults

Code file:
- `/Users/wenxina/Documents/MarketAgent/market_agent/config/models.py`

Current defaults:
- market OpenAI default: `gpt-5.4`
- company OpenAI default: `gpt-5.4-mini`

Important deployment behavior:
- scheduled market analysis stays on `gpt-5.4`
- scheduled company analysis defaults to `gpt-5.4-mini`
- per-company model may be saved in the watchlist and override company default

## Common Cloud Debug Commands

### Confirm deployed commit on EC2

```bash
ssh ec2-54-159-76-176.compute-1.amazonaws.com
cd /home/ec2-user/MarketAgent
git rev-parse HEAD
git log -1 --oneline
```

### Check web health locally on EC2

```bash
curl -fsS http://127.0.0.1:8000/ >/dev/null && echo ok
```

### Check worker next run and last result

```bash
systemctl list-timers --all | grep marketagent-worker
sudo systemctl status marketagent-worker.service --no-pager -l
journalctl -u marketagent-worker.service -n 200 --no-pager
```

### Run worker manually once

```bash
cd /home/ec2-user/MarketAgent
source /home/ec2-user/miniconda3/etc/profile.d/conda.sh
conda activate market_agent_env
marketagent-company-worker --source finnhub --provider openai --market-model gpt-5.4 --prompt-style simple --output-language zh-CN --timezone America/Los_Angeles
```

### Open psql on EC2

```bash
psql -h localhost -U market_agent -d market_agent
```

If prompted for password, use the value from `/etc/marketagent/marketagent.env`.

Or export it first:

```bash
export PGPASSWORD=$(sudo awk -F= '/^PGPASSWORD=/{print $2}' /etc/marketagent/marketagent.env)
psql -h localhost -U market_agent -d market_agent
```

## Local Test / Validation Commands

Common quick checks from local repo:

```bash
cd /Users/wenxina/Documents/MarketAgent
python3 -m py_compile frontend/web/server.py market_agent/analysis/company/news/service.py market_agent/jobs/company_updates.py
```

Repo test command used often in this project:

```bash
/opt/miniconda3/envs/market_agent_env/bin/pytest -q /Users/wenxina/Documents/MarketAgent/tests/test_market_story_and_earnings_endpoints.py
```