#!/bin/bash
# Вывод сервера — и в docker logs, и в общий том triton_log: runner показывает
# студенту ошибку загрузки его config.pbtxt. Текст ошибки разбора protobuf
# пишется только в stderr сервера, в ответ API загрузки он не попадает.
# Файл обнуляется при старте, чтобы не расти между перезапусками.
LOG=/var/log/triton/server.log
LOG_MAX_BYTES=$((64 * 1024 * 1024))
: > "$LOG"
# Сторож размера: tee пишет с O_APPEND, поэтому обрезка безопасна. Харнессу
# нужен только свежий вывод (ошибки загрузки модели), старый не нужен.
( while sleep 5; do
    [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ] && : > "$LOG"
  done ) &
exec > >(tee -a "$LOG") 2>&1
exec tritonserver --model-repository=/models --model-control-mode=explicit "$@"
