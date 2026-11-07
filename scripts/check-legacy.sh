#!/bin/sh
# Ограждение от наследия CPU-курса: после отделения курса в коде платформы не
# должно остаться ни раздела про кэш, ни C-сборки, ни sweep-харнессов.
cd "$(dirname "$0")/.." || exit 2
hits=$(grep -rnE 'cpu-cache|cache-info|cache_info|bench\.c|\bsweep\b|build_c|compile_command' \
  web/app web/static runner/app runner/tests scripts Makefile docker-compose.yml README.txt \
  --exclude-dir=vendor --exclude=check-legacy.sh)
if [ -n "$hits" ]; then
  echo "Остатки CPU-курса:"
  echo "$hits"
  exit 1
fi
