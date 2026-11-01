#!/usr/bin/env bash
# Проверка страницы в браузере: поднимает стек, исполняет JS и смотрит на
# итоговый DOM.
#
# Зачем отдельно от make test: pytest проверяет сервер, а модули страницы он не
# исполняет вовсе. Ошибка вроде повторного объявления переменной в модуле не
# видна ни одному питоновскому тесту и не ловится `node --check` — она
# проявляется только тем, что блок не смонтировался. Ровно так один раз и
# уехало в коммит.

set -euo pipefail

URL="${1:-http://localhost:18080/section/cpu-cache}"

CHROME=""
for candidate in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium" \
  "$(command -v chromium 2>/dev/null || true)" \
  "$(command -v google-chrome 2>/dev/null || true)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then CHROME="$candidate"; break; fi
done

if [ -z "$CHROME" ]; then
  echo "smoke: браузер не найден — проверку выполнить нечем" >&2
  exit 2
fi

docker compose up -d --build >/dev/null
# Сервер поднимается не мгновенно; ждём health, а не спим наугад.
for _ in $(seq 1 30); do
  if curl -sf localhost:18080/health >/dev/null; then break; fi
  sleep 1
done

DOM=$("$CHROME" --headless=new --disable-gpu --virtual-time-budget=6000 \
      --dump-dom "$URL" 2>/dev/null)

fail=0

if broken=$(printf '%s' "$DOM" | grep -o 'не запустился[^<]*'); then
  echo "smoke: блок не смонтировался:" >&2
  printf '  %s\n' "$broken" >&2
  fail=1
fi

if printf '%s' "$DOM" | grep -q 'Ошибка в материалах курса'; then
  echo "smoke: страница отдала ошибку материалов" >&2
  fail=1
fi

# Виджеты, без которых раздел бессмысленен. Число — минимум, а не точное
# значение: материалы растут, и тест не должен ломаться от нового блока.
check() {
  local name="$1" min="$2"
  local got
  got=$(printf '%s' "$DOM" | grep -o "class=\"[^\"]*$name" | wc -l | tr -d ' ')
  if [ "$got" -lt "$min" ]; then
    echo "smoke: $name — найдено $got, ожидалось не меньше $min" >&2
    fail=1
  else
    printf '  %-14s %s\n' "$name" "$got"
  fi
}

echo "smoke: смонтировано"
check editor 1
check chart 1
check cache-walk 1
check cs-memory-cell 64
check cs-cache-cell 16

if [ "$fail" -ne 0 ]; then
  echo "smoke: провалено" >&2
  exit 1
fi
echo "smoke: страница жива"
