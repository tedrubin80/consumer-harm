# Consumer Harm

**Evolution or the void?** A story-driven dashboard over the [CFPB Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/), focused on credit cards: where complaints go, fixed calendar study windows, and issuer patterns.

**Live demo:** [consumer-harm.vercel.app/app](https://consumer-harm.vercel.app/app) (Vercel landing → Railway dashboard) · [Railway direct](https://consumer-harm-production.up.railway.app)

Hosted on **Vercel** (static landing) and **Railway** (Streamlit). Local nginx/NPM is not used.

**Repository:** https://github.com/tedrubin80/consumer-harm

## Study period (fixed, not rolling)

Defaults are set in `period.env.example`:

| Window | Range |
|--------|--------|
| Study | 2011-01-01 → 2024-12-31 |
| Early comparison | 2011–2017 |
| Recent comparison | 2018–2024 |

Complaints outside the study window are excluded at build time.

## Quick start (Docker)

```bash
git clone https://github.com/tedrubin80/consumer-harm.git
cd consumer-harm

mkdir -p data
# First time: build summary (~30–60 min, ~8 GB CSV download)
docker compose --profile refresh run --rm refresh

docker compose up -d dashboard
open http://localhost:8502
```

Mount your data directory:

```bash
export OPPORTUNITY_HARM_DATA=/path/to/data
docker compose up -d
```

## Local dev (no Docker)

```bash
pip install streamlit pandas plotly
source period.env.example   # export vars
bash scripts/refresh-all.sh
streamlit run dashboard/app.py --server.port 8502
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/download_cfpb_complaints.py` | Bulk CSV/JSON from CFPB |
| `scripts/build_cfpb_summary.py` | SQLite aggregates for the dashboard |
| `scripts/refresh-all.sh` | Download + build (+ optional Docker restart) |

## Deploy elsewhere

| Surface | Role | Data |
|---------|------|------|
| **Railway** | Streamlit dashboard | `deploy/cfpb_summary.db` baked into Docker image; startup entrypoint seeds `/data/index/` if the mounted volume DB is empty |
| **Vercel** | Static landing page (`web/`) | No data — `/app` redirects to Railway |
| **Git** | Source + summary DB | `deploy/cfpb_summary.db` (~4 MB, 7.2M-complaint aggregates). Raw 8 GB CSV is **not** in git — download via `scripts/download_cfpb_complaints.py` or restore from backup |

- **Railway:** connect repo, root `.`, uses `railway.toml` + `docker/Dockerfile`. Optional volume at `/data` for rebuilds.
- **Vercel:** import repo, `vercel.json` at root; `/app` redirects to Railway.
- **GitHub Actions:** builds container on push (`.github/workflows/docker.yml`).
- **Backup:** Hetzner Storage Box `consumer-harm-corpus/` (CSV + summary DB).

## Legacy server layout

On the original host, data may live directly under `~/opportunity_harm/cfpb` and `~/opportunity_harm/index`. `paths.py` detects that automatically.

## License

MIT (data remains subject to CFPB terms of use.)
