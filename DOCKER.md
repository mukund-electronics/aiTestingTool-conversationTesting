# Running conv-tester in Docker

This guide covers everything you need to run **conv-tester** in Docker: building the
image, starting the app, loading a pre-built image someone sent you, refreshing after a
code change, and the day-to-day commands for logs, restarts, and data.

The app runs as **two containers** from a single image:

| Service   | Process                       | Port (default) | URL                     |
|-----------|-------------------------------|----------------|-------------------------|
| `backend` | FastAPI (uvicorn)             | `8000`         | http://localhost:8000/docs |
| `ui`      | Streamlit                     | `8501`         | http://localhost:8501   |

The UI talks to the backend over Docker's internal network (`http://backend:8000`), so
you only ever open the **UI** in your browser (port `8501`). The SQLite database lives in
a named Docker volume (`conv_tester_data`) so your data survives restarts.

> **Prerequisite:** Docker Desktop (Windows/Mac) or Docker Engine + Compose plugin
> (Linux). Verify with `docker --version` and `docker compose version`.

---

## Which compose file do I use?

There are two compose files. Pick based on whether you have the source code:

| File                       | When to use                                                        | Image source         |
|----------------------------|--------------------------------------------------------------------|----------------------|
| `docker-compose.yml`       | You have the source and want Docker to **build** the image locally | `build: .` (Dockerfile) |
| `docker-compose.dist.yml`  | You were **sent a pre-built image** (`.tar` / `.tar.gz`), no source | `image: conv-tester:1.0.0` |

Everything below shows both where they differ. If a command omits `-f`, it uses
`docker-compose.yml`.

---

## A. Build & run from source

Use this when you have the repository checked out.

```powershell
# From the project root (where the Dockerfile lives)

# 1. (Optional) create your .env to override ports / settings
copy .env.example .env

# 2. Build the images and start both containers in the background
docker compose up -d --build

# 3. Open the UI
#    http://localhost:8501
```

`--build` forces a rebuild; on the first run it's required, and you should pass it any
time the source or dependencies changed (see [Refreshing](#refreshing-after-a-change)).

Check that both containers are healthy:

```powershell
docker compose ps
```

`backend` should report `healthy` (it has a `/healthz` healthcheck), and `ui` should be
`running`. The `ui` container waits for `backend` to become healthy before it starts.

---

## B. Load & run a pre-built image (no source)

Use this when someone gave you the image file plus the two support files. You need:

- `conv-tester-1.0.0.tar` (or `conv-tester-1.0.0.tar.gz`) — the Docker image
- `docker-compose.dist.yml` — compose file that references the image
- `.env.example` — template for environment overrides

```powershell
# 1. Load the image into your local Docker
docker load -i conv-tester-1.0.0.tar
#    If it was gzipped:
#    docker load -i conv-tester-1.0.0.tar.gz

# 2. Confirm the image is now present
docker image ls conv-tester

# 3. Create your .env (optional — only needed to change ports / SECRET_KEY)
copy .env.example .env

# 4. Start the app
docker compose -f docker-compose.dist.yml up -d

# 5. Open the UI
#    http://localhost:8501
```

> **API keys go in the app, not in `.env`.** LLM provider keys (OpenAI, Anthropic) are
> entered inside the UI under **Configs → LLMs** and stored in the database. `.env` is
> only for ports, the DB path, the encryption `SECRET_KEY`, and runner defaults.

---

## Refreshing after a change

How you "refresh" depends on what changed.

### You changed the source code (build-from-source workflow)

Rebuild and recreate the containers. Compose only rebuilds the layers that changed, so
this is fast unless `pyproject.toml` / `uv.lock` changed.

```powershell
docker compose up -d --build
```

To force a clean rebuild ignoring the layer cache:

```powershell
docker compose build --no-cache
docker compose up -d
```

### You only changed `.env` (ports, SECRET_KEY, runner defaults)

No rebuild needed — just recreate so the new environment is picked up:

```powershell
docker compose up -d
```

### You received a new image version (distribution workflow)

Load the new tar, then recreate the containers from it:

```powershell
docker load -i conv-tester-1.1.0.tar
# Edit docker-compose.dist.yml if the version tag changed (e.g. conv-tester:1.1.0)
docker compose -f docker-compose.dist.yml up -d
```

### Just restart (no changes, e.g. app got into a bad state)

```powershell
docker compose restart            # restart both services, keep containers
# or, to fully recreate containers:
docker compose up -d --force-recreate
```

> **Streamlit note:** there is no hot-reload inside the container. The UI is served with
> `--server.headless true`, so any source change requires a rebuild + recreate, not just
> a browser refresh.

---

## Managing the app

All commands below use `docker-compose.yml`. If you're on the distribution workflow, add
`-f docker-compose.dist.yml` to each command.

```powershell
# View live logs (both services)
docker compose logs -f

# Logs for just one service
docker compose logs -f backend
docker compose logs -f ui

# Show container status / health
docker compose ps

# Stop the app (containers removed, DATA PRESERVED in the volume)
docker compose down

# Start it again
docker compose up -d

# Restart without recreating
docker compose restart

# Open a shell inside a running container (debugging)
docker compose exec backend sh
```

---

## Data & the database

The SQLite database lives in the named volume `conv_tester_data`, mounted at `/data`
inside the backend container (`DATABASE_URL=sqlite+aiosqlite:////data/conv_tester.db`).

```powershell
# List volumes
docker volume ls

# Inspect the volume (shows its mount path on the host)
docker volume inspect conv_tester_data
```

- `docker compose down` **keeps** your data — the volume is untouched.
- `docker compose down -v` **deletes** the volume and **wipes all data** (configs, test
  cases, runs, results). Use this only for a clean reset.

```powershell
# DANGER: stop and erase all stored data
docker compose down -v
```

### Backing up the database

```powershell
# Copy the DB out of the running backend container to your host
docker compose cp backend:/data/conv_tester.db ./conv_tester_backup.db
```

---

## Configuration reference (`.env`)

These variables are read by the compose files. All are optional — defaults match the
in-app defaults.

| Variable               | Default                                  | Purpose                                            |
|------------------------|------------------------------------------|----------------------------------------------------|
| `BACKEND_PORT`         | `8000`                                   | Host port mapped to the backend                    |
| `UI_PORT`              | `8501`                                   | Host port mapped to the Streamlit UI               |
| `SECRET_KEY`           | *(empty)*                                | Fernet key to encrypt stored API keys (see below)  |
| `DEFAULT_MAX_TURNS`    | `10`                                     | Runner default max turns                           |
| `DEFAULT_HTTP_TIMEOUT` | `30`                                     | Runner default HTTP timeout (s)                    |
| `DEFAULT_HTTP_RETRIES` | `3`                                      | Runner default HTTP retries                        |

> `DATABASE_URL` and `BACKEND_URL` are set explicitly inside the compose files for the
> container network — don't override them in `.env` unless you know what you're doing.

### Encrypting stored API keys (recommended for shared deployments)

If `SECRET_KEY` is empty, LLM API keys are stored in the database as plaintext. To
encrypt them, generate a Fernet key and put it in `.env`:

```powershell
# Generate a key (needs Python + the cryptography package locally)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```
# .env
SECRET_KEY=<paste the generated key here>
```

Then recreate: `docker compose up -d`.

### Changing ports

Edit `.env` before (re)starting:

```
BACKEND_PORT=8010
UI_PORT=8511
```

Then `docker compose up -d` and open `http://localhost:8511`.

---

## Distributing the image to someone else

If you want to hand the app to a colleague who has no source code, see
[DISTRIBUTE.md](DISTRIBUTE.md). In short:

```powershell
# Build, then export to a single compressed file
docker build -t conv-tester:1.0.0 .
docker save conv-tester:1.0.0 | gzip > conv-tester-1.0.0.tar.gz
```

Send them `conv-tester-1.0.0.tar.gz`, `docker-compose.dist.yml`, and `.env.example`, then
point them at section **B** above.

---

## Troubleshooting

| Symptom                                            | Fix                                                                                  |
|----------------------------------------------------|--------------------------------------------------------------------------------------|
| UI loads but shows connection errors to backend    | Check `docker compose ps` — `backend` must be `healthy`. View `docker compose logs backend`. |
| `port is already allocated`                        | Another process is using 8000/8501. Set `BACKEND_PORT` / `UI_PORT` in `.env` and recreate. |
| Changes don't appear after editing source          | You must rebuild: `docker compose up -d --build`. There is no in-container hot-reload. |
| Want a totally clean slate                          | `docker compose down -v` (erases data), then `docker compose up -d --build`.         |
| `docker load` says "no such file"                  | Run it from the directory containing the `.tar`, or pass the full path to `-i`.      |
| Backend stuck `starting` / never `healthy`         | `docker compose logs backend` — usually a bad `.env` value or DB permission issue.   |

---

## Quick command cheat-sheet

```powershell
# Build from source
docker compose up -d --build

# Load a sent image and run
docker load -i conv-tester-1.0.0.tar
docker compose -f docker-compose.dist.yml up -d

# Refresh after a code change
docker compose up -d --build

# Logs / status
docker compose logs -f
docker compose ps

# Stop (keep data) / wipe (delete data)
docker compose down
docker compose down -v
```
