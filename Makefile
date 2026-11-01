.PHONY: up down test test-web test-runner verify-content smoke

up:
	python3 scripts/cache-info.py
	docker compose up --build

down:
	docker compose down -v

test: test-web test-runner

test-web:
	docker compose run --rm --build --no-deps web python -m pytest -q

test-runner:
	docker compose run --rm --build --no-deps runner python -m pytest -q

verify-content:
	docker compose run --rm --build web python -m pytest -q -m content

# Проверка страницы в браузере: pytest не исполняет модули страницы вовсе.
smoke:
	./scripts/smoke.sh
