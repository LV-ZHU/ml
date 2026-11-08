from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.dummy import DummyRegressor
from .features import CostFeatures, numeric_columns


def make_model(kind, params, scheme="F0"):
    """Always return a fresh pipeline; no fitted state crosses folds."""
    estimators = {"mean": DummyRegressor, "linear": LinearRegression,
                  "ridge": Ridge, "forest": RandomForestRegressor}
    pre = ColumnTransformer([
        ("num", "passthrough" if kind == "forest" else StandardScaler(), numeric_columns(scheme)),
        ("cat", OneHotEncoder(drop="first", handle_unknown="ignore", sparse_output=False),
         ["sex", "smoker", "region"])
    ], sparse_threshold=0)
    return Pipeline([("features", CostFeatures(scheme)), ("preprocess", pre),
                     ("model", estimators[kind](**params))])
