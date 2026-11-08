"""model.py python backend Triton: widemodel из раздела 30 тем же torch-кодом.

Харнесс кладёт этот файл в репозиторий модели как <имя>/1/model.py, рядом —
widemodel.py. Студенческого кода здесь нет: студент пишет только config.pbtxt.

parameters TORCH_THREADS в config.pbtxt — потоки torch на экземпляр модели
(по умолчанию 1). Вход, у которого первый элемент равен BAD_INPUT, — «битый»
(глава 5): ошибку получает только его запрос, остальные запросы батча — ответ.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import triton_python_backend_utils as pb_utils  # noqa: E402
import widemodel  # noqa: E402

BAD_INPUT = -1e9


class TritonPythonModel:
    def initialize(self, args):
        config = json.loads(args["model_config"])
        threads = config.get("parameters", {}).get("TORCH_THREADS", {}).get("string_value", "1")
        torch.set_num_threads(int(threads))
        self.model = widemodel.make_model()

    def execute(self, requests):
        inputs, responses = [], [None] * len(requests)
        for k, request in enumerate(requests):
            x = pb_utils.get_input_tensor_by_name(request, "INPUT__0").as_numpy()
            if x.size and x.flat[0] == BAD_INPUT:
                responses[k] = pb_utils.InferenceResponse(error=pb_utils.TritonError(
                    "битый вход: первый элемент равен BAD_INPUT", pb_utils.TritonError.INVALID_ARG))
            else:
                inputs.append((k, x))
        if inputs:
            with torch.inference_mode():
                out = self.model(torch.from_numpy(np.concatenate([x for _, x in inputs]))).numpy()
            start = 0
            for k, x in inputs:
                part = out[start:start + len(x)]
                start += len(x)
                responses[k] = pb_utils.InferenceResponse([pb_utils.Tensor("OUTPUT__0", part)])
        return responses
