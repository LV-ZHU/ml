import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def metrics(y, pred):
    return {"MAE": float(mean_absolute_error(y, pred)),
            "RMSE": float(np.sqrt(mean_squared_error(y, pred))),
            "R2": float(r2_score(y, pred))}


def group_metrics(predictions, partition):
    import pandas as pd
    rows = []
    for exp, data in predictions.groupby("experiment_id", sort=False):
        for variable in ("smoker", "cost_group"):
            for value, g in data.groupby(variable, sort=True):
                rows.append(dict(partition=partition, experiment_id=exp,
                                 group_variable=variable, group_value=value, n=len(g),
                                 **metrics(g.y_true, g.y_pred), mean_residual=float(g.residual.mean())))
    return pd.DataFrame(rows)
