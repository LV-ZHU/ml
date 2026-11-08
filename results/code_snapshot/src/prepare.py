import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, KFold


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_data(path):
    d = pd.read_csv(path, encoding="utf-8")
    d.insert(0, "row_id", np.arange(len(d)))
    return d


def prepare(root, out, cfg):
    path = root / cfg["data_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        source = Path(cfg["source_path"])
        if not source.exists():
            source = root / "insurance.csv"
        if not source.exists():
            raise FileNotFoundError("No original or verified local CSV is available")
        shutil.copyfile(source, path)
    if sha256(path) != cfg["expected_sha256"]:
        raise ValueError("CSV version changed: audit differences before rebuilding splits")
    d = read_data(path)
    cols = ["age", "sex", "bmi", "children", "smoker", "region", "charges"]
    assert d.columns.tolist() == ["row_id"] + cols
    assert d.shape == (1338, 8)
    stats = {}
    for c in cols:
        x = d[c]
        stats[c] = dict(dtype=str(x.dtype), missing=int(x.isna().sum()))
        if pd.api.types.is_numeric_dtype(x):
            stats[c].update(infinite=int(np.isinf(x).sum()), minimum=float(x.min()),
                            median=float(x.median()), maximum=float(x.max()))
        else:
            stats[c]["categories"] = sorted(x.unique().tolist())
    assert not d[cols].isna().any().any(), "Input missing values require an audited imputation config"
    assert np.isfinite(d[["age", "bmi", "children", "charges"]]).all().all()
    assert (d.age > 0).all() and (d.bmi > 0).all() and (d.children >= 0).all() and (d.charges >= 0).all()
    assert set(d.smoker) == {"yes", "no"} and set(d.sex) == {"female", "male"}
    duplicate = d.duplicated(cols, keep="first")
    removed = []
    for _, r in d[duplicate].iterrows():
        first = d[(d[cols] == r[cols]).all(axis=1)].iloc[0]
        removed.append(dict(removed_row_id=int(r.row_id), kept_row_id=int(first.row_id)))
    clean = d[~duplicate].copy()
    dev, test = train_test_split(clean.row_id.to_numpy(), test_size=cfg["test_size"],
                                 random_state=cfg["seed"], stratify=clean.smoker)
    # Preserve train_test_split output order when assigning KFold; save for full reconstruction.
    rows = []
    folds = {}
    for fold, (_, valid) in enumerate(KFold(cfg["folds"], shuffle=True, random_state=cfg["seed"]).split(dev)):
        folds.update({int(dev[k]): fold for k in valid})
    for i, row_id in enumerate(dev):
        rows.append(dict(row_id=int(row_id), partition="development", validation_fold=folds[int(row_id)], partition_order=i))
    for i, row_id in enumerate(test):
        rows.append(dict(row_id=int(row_id), partition="test", validation_fold=None, partition_order=i))
    splits = pd.DataFrame(rows)
    assert splits.row_id.is_unique and set(dev).isdisjoint(test)
    assert set(splits.row_id) == set(clean.row_id)
    splits.to_csv(out / "splits.csv", index=False, encoding="utf-8")
    audit = dict(raw_sha256=sha256(path), source_path=cfg["source_path"], local_path=cfg["data_path"],
                 raw_rows=len(d), clean_rows=len(clean), columns=stats, duplicates_removed=removed,
                 development_rows=len(dev), test_rows=len(test),
                 fold_sizes=pd.Series(list(folds.values())).value_counts().sort_index().to_dict(),
                 input_missing_policy="stop_and_update_audit_before_imputation",
                 test_history="Whole-table quality statistics previously inspected; detailed exploration uses development data")
    (out / "data_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    meanings = [("age", "年龄", "岁", "主要受益人的年龄"), ("sex", "性别", "类别", "female/male"),
                ("bmi", "身体质量指数 BMI", "kg/m²", "体重除以身高的平方"),
                ("children", "受抚养人数", "人", "医保覆盖的子女或受抚养人数"),
                ("smoker", "吸烟状态", "类别", "yes/no"), ("region", "地区", "类别", "美国四个居住地区"),
                ("charges", "医疗费用", cfg["cost_unit"], "向健康保险计费的个人医疗费用")]
    pd.DataFrame(meanings, columns=["field", "name", "unit", "definition"]).to_csv(out / "field_dictionary.csv", index=False)
    return audit


def load_partitions(root, out, cfg):
    raw = read_data(root / cfg["data_path"]).set_index("row_id", drop=False)
    s = pd.read_csv(out / "splits.csv")
    return raw.loc[s.row_id].reset_index(drop=True).merge(s, on="row_id", validate="one_to_one").sort_values(["partition", "partition_order"])
