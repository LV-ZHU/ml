"""Ordered, checkpointed experiments. Run `python -m src.run --help`."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import time
import traceback
import uuid
import numpy as np
import pandas as pd
import psutil
import joblib
from .prepare import prepare, sha256, load_partitions
from .models import make_model
from .evaluate import metrics, group_metrics

STAGES = ["prepare", "baseline", "tune", "features", "diagnose", "freeze", "test", "plots"]


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def code_manifest(root):
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted((root / "src").glob("*.py"))}


def experiment_specs(cfg):
    return {
        "M0": dict(kind="mean", scheme="F0", params={"strategy": "mean"}),
        "M1": dict(kind="linear", scheme="F0", params={"fit_intercept": True}),
        "M2": dict(kind="ridge", scheme="F0", params={"alpha": 1.0, "fit_intercept": True, "solver": "svd"}),
        "M3": dict(kind="forest", scheme="F0", params=cfg["forest"]),
    }


def check_preprocessor(pipe, train):
    pre = pipe.named_steps["preprocess"]
    scaler = pre.named_transformers_["num"]
    if pipe.named_steps["model"].__class__.__name__ != "RandomForestRegressor":
        assert scaler.n_samples_seen_ == len(train)
        transformed = pipe.named_steps["features"].transform(train)
        from .features import numeric_columns
        assert np.allclose(scaler.mean_, transformed[numeric_columns(pipe.named_steps["features"].scheme)].mean())
    assert "charges" not in pre.feature_names_in_ and "row_id" not in pre.feature_names_in_
    return dict(n_samples_seen=len(train), input_columns=pre.feature_names_in_.tolist(),
                output_features=pre.get_feature_names_out().tolist())


def evaluate_candidate(dev, cfg, exp, cid, spec, run_id, only_fold=None):
    rows, preds, checks = [], [], []
    columns = cfg["numeric"] + cfg["categorical"]
    for fold in range(cfg["folds"]):
        if only_fold is not None and fold != only_fold:
            continue
        train, valid = dev[dev.validation_fold != fold], dev[dev.validation_fold == fold]
        pipe = make_model(**spec)
        t = time.perf_counter()
        pipe.fit(train[columns], train.charges)
        elapsed = time.perf_counter() - t
        check = check_preprocessor(pipe, train[columns])
        checks.append(dict(experiment_id=exp, candidate_id=cid, fold=fold, **check))
        pred = pipe.predict(valid[columns])
        row = dict(run_id=run_id, experiment_id=exp, candidate_id=cid, fold=fold,
                   n_train=len(train), n_valid=len(valid), **metrics(valid.charges, pred),
                   train_RMSE=metrics(train.charges, pipe.predict(train[columns]))["RMSE"],
                   fit_seconds=elapsed, params_json=json.dumps(spec, sort_keys=True))
        rows.append(row)
        q = float(train.charges.quantile(.75))
        for r, p in zip(valid.itertuples(), pred):
            preds.append(dict(row_id=r.row_id, experiment_id=exp, candidate_id=cid, fold=fold,
                              y_true=r.charges, y_pred=float(p), residual=float(r.charges-p), smoker=r.smoker,
                              high_cost_threshold=q, cost_group="high" if r.charges > q else "other"))
    return rows, preds, checks


def load_csv(path):
    return pd.read_csv(path) if Path(path).exists() else pd.DataFrame()


def run_candidates(dev, cfg, out, exp, specs, run_id):
    records, predictions, checks, search = [], [], [], []
    for i, spec in enumerate(specs):
        cid = f"{exp}_{i:02d}"
        try:
            r, p, c = evaluate_candidate(dev, cfg, exp, cid, spec, run_id)
            records.extend(r); predictions.extend(p); checks.extend(c)
            search.append(dict(experiment_id=exp, candidate_id=cid, params_json=json.dumps(spec, sort_keys=True),
                               cv_mean_rmse=float(np.mean([x["RMSE"] for x in r])), status="ok", error_message=""))
            logging.info("%s %s CV RMSE %.6f", exp, cid, search[-1]["cv_mean_rmse"])
        except Exception as e:
            search.append(dict(experiment_id=exp, candidate_id=cid, params_json=json.dumps(spec, sort_keys=True),
                               cv_mean_rmse=None, status="failed", error_message=repr(e)))
            dump(out / f"failure_{cid}.json", dict(time=now(), traceback=traceback.format_exc(), spec=spec))
    s = pd.DataFrame(search)
    s["rank"] = s.cv_mean_rmse.rank(method="min", na_option="bottom")
    for filename, new in [("cv_fold_metrics.csv", pd.DataFrame(records)), ("candidate_predictions.csv", pd.DataFrame(predictions)),
                          ("search_results.csv", s)]:
        old = load_csv(out / filename)
        if len(old):
            old = old[old.experiment_id != exp]
        pd.concat([old, new], ignore_index=True).to_csv(out / filename, index=False)
    dump(out / f"preprocessing_checks_{exp}.json", checks)
    if not records:
        raise RuntimeError(f"All candidates failed: {exp}; see failure files")
    refresh_summary(out, cfg)


def refresh_summary(out, cfg):
    folds = pd.read_csv(out / "cv_fold_metrics.csv")
    rows = []
    for (exp, cid), g in folds.groupby(["experiment_id", "candidate_id"], sort=False):
        row = dict(experiment_id=exp, candidate_id=cid, params_json=g.params_json.iloc[0],
                   mean_fit_seconds=float(g.fit_seconds.mean()), train_mean_rmse=float(g.train_RMSE.mean()))
        for m in ["MAE", "RMSE", "R2"]:
            row[f"cv_mean_{m.lower()}"] = float(g[m].mean())
            row[f"cv_std_{m.lower()}"] = float(g[m].std(ddof=1))
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary["selected"] = False
    for exp, g in summary.groupby("experiment_id", sort=False):
        best = g.cv_mean_rmse.min()
        ties = g[g.cv_mean_rmse <= best + cfg["tie_tolerance"]]
        def key(idx):
            spec = json.loads(summary.loc[idx, "params_json"]); p = spec["params"]
            return ({"F0": 0, "F1": 1, "F2": 2}[spec["scheme"]],
                    p.get("max_depth") or 100000, -p.get("min_samples_leaf", 1), idx)
        summary.loc[min(ties.index, key=key), "selected"] = True
    summary.to_csv(out / "cv_summary.csv", index=False)


def selected(out, exp):
    s = pd.read_csv(out / "cv_summary.csv")
    return s[(s.experiment_id == exp) & s.selected].iloc[0]


def predict_test(root, out, cfg, protocol):
    assert sha256(root / cfg["data_path"]) == protocol["data_sha256"]
    assert sha256(out / "splits.csv") == protocol["splits_sha256"]
    assert code_manifest(root) == protocol["code_manifest"], "Code changed since freeze"
    all_data = load_partitions(root, out, cfg)
    dev = all_data[all_data.partition == "development"]
    test = all_data[all_data.partition == "test"]
    cols = cfg["numeric"] + cfg["categorical"]
    # Log access before reading test targets for metrics.
    with (out / "test_access_history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(time=now(), purpose="frozen final evaluation", experiments=list(protocol["models"])), ensure_ascii=False) + "\n")
    cached, predictions, scores = {}, [], []
    (out / "models").mkdir(exist_ok=True)
    for exp, spec in protocol["models"].items():
        signature = json.dumps(spec, sort_keys=True)
        if signature not in cached:
            pipe = make_model(**spec); t = time.perf_counter()
            pipe.fit(dev[cols], dev.charges); fit_time = time.perf_counter()-t
            check_preprocessor(pipe, dev[cols]); t = time.perf_counter()
            pred = pipe.predict(test[cols]); predict_time = time.perf_counter()-t
            joblib.dump(pipe, out / "models" / f"{exp}.joblib")
            cached[signature] = (pred, fit_time, predict_time, exp)
        pred, fit_time, predict_time, canonical = cached[signature]
        scores.append(dict(experiment_id=exp, canonical_model=canonical, n=len(test),
                           **metrics(test.charges, pred), fit_seconds=fit_time, predict_seconds=predict_time,
                           negative_predictions=int((pred < 0).sum())))
        q = float(dev.charges.quantile(.75))
        for r, p in zip(test.itertuples(), pred):
            predictions.append(dict(row_id=r.row_id, experiment_id=exp, y_true=r.charges, y_pred=float(p),
                                    residual=float(r.charges-p), smoker=r.smoker, high_cost_threshold=q,
                                    cost_group="high" if r.charges > q else "other"))
    pd.DataFrame(scores).to_csv(out / "test_metrics.csv", index=False)
    p = pd.DataFrame(predictions); p.to_csv(out / "test_predictions.csv", index=False)
    group_metrics(p, "test").to_csv(out / "test_group_metrics.csv", index=False)
    old = load_csv(out / "development_group_metrics.csv")
    pd.concat([old, group_metrics(p, "test")], ignore_index=True).to_csv(out / "group_metrics.csv", index=False)
    return scores


def run_stage(stage, root, out, cfg, run_id):
    if stage == "prepare":
        return prepare(root, out, cfg)
    if stage == "plots":
        from .plot import make_plots
        return make_plots(root, out, cfg)
    all_data = load_partitions(root, out, cfg)
    dev = all_data[all_data.partition == "development"]
    base = experiment_specs(cfg)
    if stage == "baseline":
        smoke = evaluate_candidate(dev, cfg, "M1", "smoke", base["M1"], run_id, only_fold=0)
        dump(out / "smoke_test.json", dict(metrics=smoke[0], preprocessing=smoke[2]))
        for exp, spec in base.items():
            run_candidates(dev, cfg, out, exp, [spec], run_id)
        return {"completed": list(base)}
    if stage == "tune":
        ridge = [dict(kind="ridge", scheme="F0", params=dict(alpha=a, fit_intercept=True, solver="svd")) for a in cfg["alpha_grid"]]
        forest = [dict(kind="forest", scheme="F0", params={**cfg["forest"], "max_depth":d, "min_samples_leaf":l})
                  for d in cfg["depth_grid"] for l in cfg["leaf_grid"]]
        run_candidates(dev, cfg, out, "M2T", ridge, run_id)
        run_candidates(dev, cfg, out, "M3T", forest, run_id)
        return {exp: selected(out, exp).to_dict() for exp in ["M2T", "M3T"]}
    if stage == "features":
        alpha = json.loads(selected(out, "M2T").params_json)["params"]["alpha"]
        for scheme in ["F1", "F2"]:
            specs = [dict(kind="ridge", scheme=scheme, params=dict(alpha=a, fit_intercept=True, solver="svd")) for a in cfg["alpha_grid"]]
            run_candidates(dev, cfg, out, scheme, specs, run_id)
        summary = pd.read_csv(out / "cv_summary.csv")
        s = summary[summary.selected & summary.experiment_id.isin(["M2T", "F1", "F2"])].copy()
        s.loc[s.experiment_id == "M2T", "experiment_id"] = "F0"
        s.to_csv(out / "feature_comparison.csv", index=False)
        fixed = []
        for exp, original in [("F0", "M2T"), ("F1", "F1"), ("F2", "F2")]:
            match = summary[summary.experiment_id == original]
            row = match[match.params_json.map(lambda x: json.loads(x)["params"]["alpha"] == alpha)].iloc[0].to_dict()
            row.update(experiment_id=exp, fixed_alpha=alpha); fixed.append(row)
        pd.DataFrame(fixed).to_csv(out / "feature_fixed_alpha.csv", index=False)
        return {"fixed_alpha":alpha, "completed":["F0", "F1", "F2"]}
    if stage == "diagnose":
        p = pd.read_csv(out / "candidate_predictions.csv")
        p = p[p.experiment_id.isin(["M1", "M3"])].copy()
        assert p.groupby("experiment_id").size().eq(len(dev)).all()
        p.to_csv(out / "oof_predictions.csv", index=False)
        group_metrics(p, "development").to_csv(out / "development_group_metrics.csv", index=False)
        rows = [dict(experiment_id=e, n=len(g), oof_rmse=metrics(g.y_true, g.y_pred)["RMSE"],
                     negative_predictions=int((g.y_pred < 0).sum())) for e,g in p.groupby("experiment_id")]
        pd.DataFrame(rows).to_csv(out / "oof_metrics.csv", index=False)
        return rows
    if stage == "freeze":
        s = pd.read_csv(out / "cv_summary.csv"); s = s[s.selected]
        best = s.cv_mean_rmse.min()
        order = ["M0", "M1", "M2", "M3", "M2T", "M3T", "F1", "F2"]
        eligible = s[s.cv_mean_rmse <= best + cfg["tie_tolerance"]]
        winner = min(eligible.experiment_id, key=lambda e: order.index(e))
        protocol = dict(frozen_at=now(), run_id=run_id, data_sha256=sha256(root/cfg["data_path"]),
                        splits_sha256=sha256(out/"splits.csv"), code_manifest=code_manifest(root),
                        config_sha256=sha256(root/"config.json"), models={r.experiment_id:json.loads(r.params_json) for r in s.itertuples()},
                        selection="minimum arithmetic mean of five validation RMSE; ddof=1 for SD", recommended_model=winner,
                        metrics={"MAE":"mean(abs(y-p))", "RMSE":"sqrt(mean((y-p)^2))", "R2":"1-SSE/SST"},
                        postprocess=cfg["postprocess"], feature_schemes={"F0":"six original inputs", "F1":"F0+age^2+bmi^2", "F2":"F1+age*smoker+bmi*smoker"},
                        test_groups={"smoker":["no","yes"], "cost_group":"y > development q75; descriptive if n < 30"},
                        optional_extension="none; predefined features and error diagnostics completed",
                        test_history="Whole-table quality audit available before splitting; no test metrics before freeze")
        dump(out / "frozen_protocol.json", protocol)
        shutil.copytree(root/"src", out/"code_snapshot"/"src", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
        shutil.copyfile(root/"config.json", out/"code_snapshot"/"config.json")
        return {"recommended_model":winner, "cv_mean_rmse":float(best)}
    if stage == "test":
        return predict_test(root, out, cfg, json.loads((out / "frozen_protocol.json").read_text(encoding="utf-8")))
    raise ValueError(stage)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=STAGES+["all", "reproduce"], required=True)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--output", help="New output directory relative to project root")
    parser.add_argument("--reference-results", default="results")
    args = parser.parse_args()
    root = Path(args.config).resolve().parent
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out = root / (args.output or cfg["results_dir"]); out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    run_dir = out / "runs" / run_id; run_dir.mkdir(parents=True)
    dump(run_dir / "config.json", cfg)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(out/"run.log", encoding="utf-8"), logging.StreamHandler()])
    env = dict(python=platform.python_version(), executable=os.sys.executable, platform=platform.platform(),
               cpu=platform.processor(), logical_cpus=os.cpu_count(), memory_bytes=psutil.virtual_memory().total,
               packages={p:importlib.metadata.version(p) for p in ["numpy","pandas","scipy","scikit-learn","matplotlib","joblib","psutil"]},
               threads={"search_outer_jobs":1,"forest_n_jobs":cfg["forest"]["n_jobs"]}, started_at=now(), run_id=run_id)
    dump(out / "environment.json", env)
    try:
        if args.stage == "reproduce":
            ref = root / args.reference_results
            if out.resolve() == ref.resolve():
                raise ValueError("Reproduction requires a separate output directory")
            protocol = json.loads((ref/"frozen_protocol.json").read_text(encoding="utf-8"))
            shutil.copyfile(ref/"splits.csv", out/"splits.csv")
            dump(out/"frozen_protocol.json", protocol)
            predict_test(root, out, cfg, protocol)
            a = pd.read_csv(ref/"test_predictions.csv").sort_values(["experiment_id","row_id"])
            b = pd.read_csv(out/"test_predictions.csv").sort_values(["experiment_id","row_id"])
            assert a[["experiment_id","row_id"]].equals(b[["experiment_id","row_id"]])
            assert np.allclose(a.y_pred,b.y_pred,rtol=1e-9,atol=1e-6)
            dump(out/"reproduction_check.json",dict(passed=True,max_absolute_prediction_difference=float(np.max(abs(a.y_pred-b.y_pred))),rtol=1e-9,atol=1e-6))
        else:
            stages = STAGES if args.stage == "all" else [args.stage]
            state_path = out/"stage_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
            for stage in stages:
                if stage in state and state[stage]["status"] == "complete":
                    raise RuntimeError(f"Stage {stage} already complete: use a new --output to preserve existing records")
                if STAGES.index(stage) > 0:
                    previous = STAGES[STAGES.index(stage)-1]
                    assert state.get(previous,{}).get("status") == "complete", f"Dependency not complete: {previous}"
                logging.info("Starting stage %s", stage)
                started = now()
                result = run_stage(stage, root, out, cfg, run_id)
                handoff = dict(stage=stage,status="complete",started_at=started,finished_at=now(),run_id=run_id,
                               result=result, data_sha256=cfg["expected_sha256"], code_manifest=code_manifest(root),
                               test_metrics_viewed=STAGES.index(stage)>=STAGES.index("test"),
                               next_stage=STAGES[STAGES.index(stage)+1] if stage != "plots" else "report_and_verify")
                dump(run_dir / f"{stage}_handoff.json",handoff)
                shutil.copyfile(root/"config.json",run_dir/f"{stage}_config.json")
                state[stage] = handoff; dump(state_path,state)
                with (root/"工作记录.md").open("a",encoding="utf-8") as f:
                    f.write(f"\n### {stage} {now()}\n\n运行标识 `{run_id}`；状态：完成。配置与交接：`{run_dir.relative_to(root).as_posix()}/{stage}_handoff.json`。测试指标已查看：{handoff['test_metrics_viewed']}。下一阶段：{handoff['next_stage']}。\n")
        env["status"]="complete"
    except Exception:
        env["status"]="failed"
        dump(run_dir/"failure.json", dict(time=now(),stage=args.stage,traceback=traceback.format_exc()))
        logging.exception("Run failed; evidence saved")
        raise
    finally:
        env["finished_at"]=now(); dump(out/"environment.json",env); dump(run_dir/"environment.json",env)
        snapshot = run_dir/"results_snapshot"
        snapshot.mkdir(exist_ok=True)
        for p in out.iterdir():
            if p.is_file() and p.suffix in [".csv", ".json", ".jsonl"]:
                shutil.copyfile(p,snapshot/p.name)


if __name__ == "__main__":
    main()
