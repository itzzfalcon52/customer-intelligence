# Deploying to AWS Lightsail

One Linux server runs everything with Docker Compose:

- **web:** Caddy serves the React app, terminates HTTPS and routes `/api/*`.
- **backend:** the Better Auth account service.
- **api:** FastAPI and the training and monitoring worker, sharing the `app-data` volume.

Accounts stay in Neon. Nothing here has been deployed. These files were checked for syntax but
not built, because Docker isn't installed on the development machine, so expect to fix small
issues on the first `docker compose build`.

## Cost

- **Lightsail, 4 GB RAM / 2 vCPU** (enough for training on a few hundred thousand rows): about
  $24 a month. New AWS accounts get $100–200 in credits for up to 6–12 months, which covers this
  at first. Check the AWS Free Tier page for your account.
- **Neon:** the free tier is enough to start.
- **Backups:** Cloudflare R2's free tier (10 GB, no egress fees) or S3.
- **Nebius AI:** billed per use, and capped by each workspace's daily token limit.

## 1. Create the server

1. In Lightsail, create an instance with **Linux/Unix → OS only → Ubuntu 24.04** on the **4 GB**
   plan.
2. In **Networking**, attach a **static IP** and allow **HTTPS (443)** next to the default SSH
   (22) and HTTP (80).
3. At your DNS provider, point an `A` record for your domain (for example `app.example.com`) at
   the static IP.

## 2. Install Docker and get the code

```sh
ssh ubuntu@<static-ip>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit   # log back in afterwards
# Private repository: give the server a read-only deploy key.
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 && cat ~/.ssh/id_ed25519.pub
# GitHub → repository → Settings → Deploy keys → Add deploy key (leave "Allow write access" off)
git clone git@github.com:<owner>/customer-intelligence.git && cd customer-intelligence
```

## 3. Configure

```sh
cp deploy/.env.production.example deploy/.env
nano deploy/.env    # DOMAIN, DATABASE_URL, both secrets (openssl rand -hex 32), Nebius key,
                    # CI_CREDENTIALS_KEY (openssl rand -base64 32 | tr '+/' '-_'), optional Resend
chmod 600 deploy/.env
```

`INTERNAL_API_SECRET` must be identical for the backend and the API; compose passes the same
value to both. Use a new `BETTER_AUTH_SECRET` for production.

## 4. Start

```sh
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm backend \
  ./node_modules/.bin/prisma migrate deploy
docker compose -f deploy/docker-compose.yml --env-file deploy/.env ps
```

Caddy requests the HTTPS certificate automatically once DNS points at the server. Open
`https://<your-domain>`, sign up, and run the demo from Home.

## 5. Check it works

- `https://<domain>/api/v1/health` returns `{"status": "ok", ...}`.
- Settings → Service status shows the ML API connected and the worker online.
- Check AI connection (Settings) succeeds.
- Logs: `docker compose -f deploy/docker-compose.yml logs -f api` (and `backend`, `web`).

## 6. Backups

The simplest safety net is Lightsail's **automatic snapshots** (instance → Snapshots tab), which
copy the whole disk daily, Docker volumes included, for a few cents a month. For an off-server
copy, create a bucket (R2 or S3), fill the `BACKUP_*` and access-key lines in `deploy/.env`, install
the AWS CLI (`sudo snap install aws-cli --classic`; Ubuntu 24.04 has no `awscli` apt package)
and schedule the nightly script:

```sh
crontab -e
15 3 * * * /home/ubuntu/customer-intelligence/deploy/backup.sh >> /home/ubuntu/ci-backup.log 2>&1
```

The script stops the API for a few seconds so the SQLite files are copied consistently. To
restore, stop the stack, extract an archive into the `customer-intelligence_app-data` volume and
start it again. Test a restore once before relying on it.

## Updating

```sh
git pull
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm backend \
  ./node_modules/.bin/prisma migrate deploy
```

## Security notes

- Only ports 22, 80 and 443 are open. The backend and API are reachable only through Caddy.
- `NODE_ENV=production` turns on secure cookies, and the backend refuses a non-HTTPS
  `APP_ORIGIN`.
- `TRUST_PROXY=true` makes the backend's sign-in rate limits use the client address that Caddy
  writes. Caddy ignores client-supplied `X-Forwarded-For`, so this can't be spoofed through it.
- Secrets live only in `deploy/.env` on the server (ignored by git and Docker builds).
- Customer data stays in the `app-data` volume and your backups; the AI provider only receives
  aggregates and pseudonymous labels.

## When one server is no longer enough

Move metadata to Postgres and artifacts to object storage, then run several API and worker
containers. That redesign is planned work.
