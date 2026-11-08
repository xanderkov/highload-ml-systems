#!/bin/bash
# Вывод сервера — и в docker logs, и в общий том triton_log: runner показывает
# студенту ошибку загрузки его config.pbtxt. Текст ошибки разбора protobuf
# пишется только в stderr сервера, в ответ API загрузки он не попадает.
# Файл обнуляется при старте, чтобы не расти между перезапусками.
LOG=/var/log/triton/server.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1
exec tritonserver --model-repository=/models --model-control-mode=explicit "$@"
