from itertools import batched
import numpy as np

# records — поток обычных словарей, например после разбора JSON:
# {"id": 101, "score": -0.2}, {"id": 102, "score": 0.7}, ...
# Результат: [0.0, 0.7, ...], в порядке входных записей.
BATCH_SIZE = 1024

def compute(records):
    result = []
    for batch in batched(records, BATCH_SIZE):
        # Собираем числа из записей и преобразуем в массив NumPy.
        scores = np.array([record["score"] for record in batch])
        np.clip(scores, 0, 1, out=scores)
        result.extend(scores.tolist())
    return result
