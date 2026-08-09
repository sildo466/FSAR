.PHONY: dev build stop test wsl-test clean help

help:
	@echo "FSAR make targets:"
	@echo "  make dev       - run start.sh (full launcher)"
	@echo "  make build     - frontend build only"
	@echo "  make stop      - kill running backend"
	@echo "  make test      - run pytest"
	@echo "  make wsl-test  - print WSL2 launcher command"
	@echo "  make clean     - remove build artifacts"

dev:
	bash start.sh

build:
	bash scripts/_frontend.sh

stop:
	pkill -f "src.server.ws_server" || true
	@echo "Backend stopped"

test:
	pytest tests/ -x -q

wsl-test:
	@echo "Run inside WSL2: cd /mnt/c/WinTool/FSAR && bash start.sh"

clean:
	rm -rf frontend/dist
	rm -rf data/logs/*.log
	rm -rf __pycache__ */__pycache__ */*/__pycache__ */*/*/__pycache__
	@echo "Cleaned"
