
import numpy as np

class TensorNetwork:
    @staticmethod
    def compute(matrix):
        m = np.array(matrix)
        corr = np.corrcoef(m)
        return {"tensor_shape": list(corr.shape), "market_link": float(np.mean(np.abs(corr)))}
