# Consumer Harm

**Evolution or the void?** A story-driven dashboard over the [CFPB Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/), focused on credit cards: where complaints go, fixed calendar study windows, and issuer patterns.

**Live demo:** [consumer-harm.vercel.app/app](https://consumer-harm.vercel.app/app) (Vercel → Railway) · [Railway direct](https://consumer-harm-production.up.railway.app)

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

- **Railway (Streamlit app):** connect repo, root directory `.`, uses `railway.toml` + `docker/Dockerfile`. Mount volume at `/data` with `index/cfpb_summary.db`. See `railway.env.example`.
- **Vercel (landing page):** import repo, root `web` via `vercel.json`; `/app` rewrites to your Railway URL (update `vercel.json` after deploy).
- **GitHub Actions:** builds container image on push (see `.github/workflows/docker.yml`).
- **GitLab CI:** see `.gitlab-ci.yml` for the same pattern.
- Data is **not** in git — ship a volume, object storage, or run the `refresh` profile once on deploy.

## Legacy server layout

On the original host, data may live directly under `~/opportunity_harm/cfpb` and `~/opportunity_harm/index`. `paths.py` detects that automatically.

## License

MIT (data remains subject to CFPB terms of use.)
