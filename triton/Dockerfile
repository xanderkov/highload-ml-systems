# Triton Inference Server на CPU: образ NGC только с python и pytorch backend
# (спайк, спека §7.1). nvcr.io из некоторых стран отдаёт 403 — см. README.
FROM nvcr.io/nvidia/tritonserver:26.10-pyt-python-py3
# Python backend исполняет model.py в интерпретаторе образа, а torch в нём нет.
# CPU-сборка, как в runner: колесо по умолчанию тянет гигабайты CUDA.
RUN pip install --no-cache-dir --break-system-packages \
      --index-url https://download.pytorch.org/whl/cpu "torch~=2.15" "numpy<2"
CMD ["tritonserver", "--model-repository=/models", "--model-control-mode=explicit"]
