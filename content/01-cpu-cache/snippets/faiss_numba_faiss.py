# 262 144 точки (x, y), float32. Нужно найти ближайшую
# точку для каждого из 64 запросов по евклидову расстоянию.
# index = faiss.IndexFlatL2(2), точки добавлены до замера.
def compute(index, queries):
    distances, indices = index.search(queries, 1)
    return indices[:, 0]
