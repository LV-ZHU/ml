"""Deterministic, stateless feature construction before fold-wise scaling."""
from sklearn.base import BaseEstimator, TransformerMixin


class CostFeatures(TransformerMixin, BaseEstimator):
    def __init__(self, scheme="F0"):
        self.scheme = scheme

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        out = X.copy()
        if self.scheme in ("F1", "F2"):
            out["age_squared"] = out.age ** 2
            out["bmi_squared"] = out.bmi ** 2
        if self.scheme == "F2":
            s = (out.smoker == "yes").astype(float)
            out["age_smoker"] = out.age * s
            out["bmi_smoker"] = out.bmi * s
        return out


def numeric_columns(scheme):
    cols = ["age", "bmi", "children"]
    if scheme in ("F1", "F2"):
        cols += ["age_squared", "bmi_squared"]
    if scheme == "F2":
        cols += ["age_smoker", "bmi_smoker"]
    return cols
