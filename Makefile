.DEFAULT_GOAL := help

COMPOSE     := docker compose
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help up down dev logs migrate seed openapi test lint format typecheck bootstrap build

help: ## Показать список доступных команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Первичная настройка окружения (scripts/bootstrap.sh)
	./scripts/bootstrap.sh

up: ## Запустить весь стек в фоне (со сборкой образов)
	$(COMPOSE) up -d --build

down: ## Остановить стек
	$(COMPOSE) down

dev: ## Запустить стек с hot reload (foreground)
	./scripts/dev.sh

logs: ## Логи всех сервисов (follow)
	$(COMPOSE) logs -f --tail=100

build: ## Собрать образ backend
	$(COMPOSE) build

migrate: ## Применить миграции Alembic
	cd backend && uv run alembic upgrade head

seed: ## Загрузить демо-данные
	cd backend && uv run python ../scripts/seed_demo.py

openapi: ## Экспортировать OpenAPI-схему
	cd backend && uv run python ../scripts/export_openapi.py

test: ## Запустить тесты (scripts/test.sh)
	./scripts/test.sh

lint: ## Линтеры и проверка типов (scripts/lint.sh)
	./scripts/lint.sh

format: ## Автоформатирование кода (ruff format + fix)
	cd backend && uv run ruff format . && uv run ruff check --fix .

typecheck: ## Проверка типов (mypy)
	cd backend && uv run mypy app
