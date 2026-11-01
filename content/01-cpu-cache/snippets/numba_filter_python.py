# data = [1.0, 0.0, 0.0, ...]
# state: 0.1, затем 0.09, затем 0.081, ...
def compute(data):
    state = 0.0
    for x in data:
        state = 0.9 * state + 0.1 * x
    return state
