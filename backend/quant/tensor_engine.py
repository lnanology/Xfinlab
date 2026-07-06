
import numpy as np

class TensorEngine:
    @staticmethod
    def correlation_matrix(prices_matrix):
        matrix = np.array(prices_matrix)
        corr = np.corrcoef(matrix)
        strength = float(np.mean(np.abs(corr)))
        return {"correlation_strength": strength, "matrix_shape": list(corr.shape)}
