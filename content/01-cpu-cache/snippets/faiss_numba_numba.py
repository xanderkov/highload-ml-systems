import numpy as np
from numba import njit

# Те же точки и запросы. Полный перебор, без приближений.
@njit
def compute(points, queries):
    indices = np.empty(len(queries), dtype=np.int64)
    for q in range(len(queries)):
        best_distance = np.inf
        best_index = -1
        for i in range(len(points)):
            dx = points[i, 0] - queries[q, 0]
            dy = points[i, 1] - queries[q, 1]
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best_distance = distance
                best_index = i
        indices[q] = best_index
    return indices
