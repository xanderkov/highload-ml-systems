import sys
import time

# Фикстура: пишет в stderr и зависает — runner должен вернуть этот вывод с таймаутом.
print("сервер Triton занят другим замером, ждём…", file=sys.stderr, flush=True)
time.sleep(60)
