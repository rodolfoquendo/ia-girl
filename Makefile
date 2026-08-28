.PHONY: help up down build logs shell restart ideas generate api

# Default target
help:
	@echo ""
	@echo "  ia-girl — AI persona content engine"
	@echo ""
	@echo "  Container commands:"
	@echo "    make up          Build and start the ia-girl container"
	@echo "    make down        Stop and remove the container"
	@echo "    make build       Rebuild the Docker image"
	@echo "    make restart     Restart the container"
	@echo "    make logs        Tail container logs"
	@echo "    make shell       Open a bash shell inside the container"
	@echo ""
	@echo "  Local dev (uses .venv):"
	@echo "    make install     Install Python dependencies into .venv"
	@echo "    make api         Run the API server locally (port 8000)"
	@echo "    make ideas       Generate 7 content ideas via Claude"
	@echo "    make generate    Generate one image + caption (no posting)"
	@echo "    make dms         Process pending Instagram DMs"
	@echo ""

# ── Container ─────────────────────────────────────────────────────────────────

up:
	docker compose up -d --build
	@echo "ia-girl API running at http://localhost:8082"
	@echo "Docs at http://localhost:8082/docs"

down:
	docker compose down

build:
	docker compose build --no-cache

restart:
	docker compose restart ia-girl

logs:
	docker compose logs -f ia-girl

shell:
	docker exec -ti ia-girl bash

# ── Local dev ────────────────────────────────────────────────────────────────

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

api:
	.venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8082 --reload

ideas:
	.venv/bin/python3 main.py ideas

generate:
	.venv/bin/python3 main.py generate

dms:
	.venv/bin/python3 main.py dms

renders:
	.venv/bin/python3 main.py renders

renders-room:
	.venv/bin/python3 main.py renders $(ROOM)

renders-fast:
	RENDER_MODEL=black-forest-labs/flux-schnell .venv/bin/python3 main.py renders

renders-fast-room:
	RENDER_MODEL=black-forest-labs/flux-schnell .venv/bin/python3 main.py renders $(ROOM)
