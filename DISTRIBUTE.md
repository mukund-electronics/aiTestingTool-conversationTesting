# Distributing conv-tester (no source code)

Share just the Docker image — recipients need no Python, no build tools, no source code.

---

## Sender: build and export the image

Build images for **both CPU architectures** so Windows/Linux testers and Apple
Silicon Mac testers each get a native image (faster, no emulation warnings).

```powershell
# One-time: create a multi-platform builder (Docker Desktop required)
docker buildx create --name multibuilder --use
docker buildx inspect --bootstrap

# Build amd64 image  (Windows / Linux / Intel Mac)
docker buildx build --platform linux/amd64 -t conv-tester:2.0.0.2 --load conv-tester/
docker save conv-tester:2.0.0.2 -o conv-tester/conv-tester-2.0.0.2-amd64.tar

# Build arm64 image  (Apple Silicon Mac — M1/M2/M3/M4)
docker buildx build --platform linux/arm64 -t conv-tester:2.0.0.2 --load conv-tester/
docker save conv-tester:2.0.0.2 -o conv-tester/conv-tester-2.0.0.2-arm64.tar
```

> The arm64 build cross-compiles via QEMU and takes longer (~5–15 min). Run it
> once and keep both tars ready.

Give each recipient these **3 files** (pick the right tar for their machine):

| File | Who gets it |
|---|---|
| `conv-tester-2.0.0.2-amd64.tar` | Windows, Linux, Intel Mac |
| `conv-tester-2.0.0.2-arm64.tar` | Apple Silicon Mac (M1/M2/M3/M4) |
| `docker-compose.dist.yml` | everyone |
| `.env.example` | everyone |

---

## Recipient: load and run

**Requirements:** Docker Desktop (Windows/Mac) or Docker Engine (Linux). Nothing else.

```bash
# 1. Load the image into Docker
#    Use the tar that matches your machine (amd64 or arm64)
docker load -i conv-tester-2.0.0.2-arm64.tar   # Apple Silicon Mac
docker load -i conv-tester-2.0.0.2-amd64.tar   # Windows / Linux / Intel Mac

# 2. Create your .env from the example
cp .env.example .env
# Optionally edit .env to change ports (BACKEND_PORT, UI_PORT)

# 3. Start the app
docker compose -f docker-compose.dist.yml up -d

# 4. Open http://localhost:8501
```

> LLM API keys (OpenAI, Anthropic, etc.) are entered **inside the app** under Configs → LLMs.
> They are stored in the app's database — you do not put them in `.env`.

---

## Managing the app

```bash
# View logs
docker compose -f docker-compose.dist.yml logs -f

# Stop (data is preserved)
docker compose -f docker-compose.dist.yml down

# Stop and wipe all data
docker compose -f docker-compose.dist.yml down -v

# Restart
docker compose -f docker-compose.dist.yml up -d
```

## Updating to a newer image

When you receive a new image tar, stop the running containers first, load the
new image, then restart (the database volume is preserved):

```bash
# 1. Stop the currently running containers (keeps your data)
#    IMPORTANT: use the same compose file you used to start the app
docker compose -f docker-compose.dist.yml down

# 2. Load the new image (use the tar matching your architecture)
docker load -i conv-tester-2.0.0.2-arm64.tar   # Apple Silicon Mac
docker load -i conv-tester-2.0.0.2-amd64.tar   # Windows / Linux / Intel Mac

# 3. Start with the new image (same compose file as step 1)
docker compose -f docker-compose.dist.yml up -d --force-recreate
```

> **Always use the same compose filename for `down` and `up`.** Docker Compose
> identifies your deployment by the directory name + compose filename. If you
> switch filenames between commands, it treats them as separate deployments —
> the old containers keep running and new ones are created alongside them,
> causing "port already allocated" errors or duplicate instances.

> Skipping `down` will also cause a "port already allocated" error because the
> old containers are still holding the ports.

## Using local or other LLMs (LM Studio, Ollama, Groq, …)

You're not limited to OpenAI and Anthropic. In the app under **Configs → LLMs**,
set the **Base URL** to any OpenAI-compatible server and leave the API key blank
if it doesn't need one:

- LM Studio (local): `http://localhost:1234/v1`
- Ollama (local): `http://localhost:11434/v1`
- vLLM / LocalAI (local): `http://localhost:8000/v1`
- Groq / Together / OpenRouter / DeepSeek: their documented `/v1` URL (key required)

> Running the app in Docker and the model on your host machine? Use
> `http://host.docker.internal:1234/v1` instead of `localhost` so the container
> can reach the host.

## Changing ports

Edit `.env` before starting:
```
BACKEND_PORT=8010
UI_PORT=8511
```
Then open `http://localhost:8511`.
