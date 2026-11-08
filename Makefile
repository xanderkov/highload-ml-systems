.PHONY: up down test test-repo test-web test-runner test-triton verify-content smoke

up:
	docker compose up --build

down:
	docker compose down -v

test: test-repo test-web test-runner

# Проверка всего репозитория с хоста: внутри контейнеров виден только свой сервис.
test-repo:
	./scripts/check-legacy.sh

test-web:
	docker compose run --rm --build --no-deps web python -m pytest -q

test-runner:
	docker compose run --rm --build --no-deps runner python -m pytest -q

# Тесты, которым нужен поднятый сервис triton (tritonlib, репозиторий моделей).
test-triton:
	docker compose run --rm --build runner python -m pytest -q -m triton

verify-content: test-triton
	docker compose run --rm --build web python -m pytest -q -m content

# Проверка страницы в браузере: pytest не исполняет модули страницы вовсе.
smoke:
	./scripts/smoke.sh
