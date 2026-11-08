"""Independent acceptance checks of saved rows, splits, metrics, and preprocessing."""
import json
from pathlib import Path
import sys
import hashlib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, KFold
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluate import metrics
from src.models import make_model
from src.prepare import load_partitions

root = Path(__file__).resolve().parents[1]
cfg = json.loads((root/'config.json').read_text(encoding='utf-8'))
out = root/'results'
checks = {}
raw = pd.read_csv(root/cfg['data_path']); raw['row_id'] = raw.index
assert hashlib.sha256((root/cfg['data_path']).read_bytes()).hexdigest() == cfg['expected_sha256']
clean = raw.drop_duplicates(subset=[c for c in raw if c != 'row_id'])
assert len(clean) == 1337 and set(raw.row_id)-set(clean.row_id) == {581}
s = pd.read_csv(out/'splits.csv')
dev_ids,test_ids = train_test_split(clean.row_id.to_numpy(), test_size=.2,random_state=42,stratify=clean.smoker)
assert s[s.partition=='development'].row_id.tolist() == dev_ids.tolist()
assert s[s.partition=='test'].row_id.tolist() == test_ids.tolist()
for f,(_,v) in enumerate(KFold(5,shuffle=True,random_state=42).split(dev_ids)):
    assert set(dev_ids[v]) == set(s[(s.partition=='development') & (s.validation_fold==f)].row_id)
checks['data_and_splits'] = 'passed'
toy = metrics([1.,2.,3.], [2.,2.,2.])
assert np.isclose(toy['MAE'],2/3) and np.isclose(toy['RMSE'],np.sqrt(2/3)) and toy['R2']==0
assert np.array_equal(np.array([1,2,3])-np.array([2,2,2]),[-1,0,1])
checks['hand_calculated_metrics'] = toy
pred=pd.read_csv(out/'test_predictions.csv'); scores=pd.read_csv(out/'test_metrics.csv')
for exp,g in pred.groupby('experiment_id'):
    assert len(g)==268 and g.row_id.is_unique and set(g.row_id)==set(test_ids)
    target=raw.set_index('row_id').loc[g.row_id,'charges'].to_numpy()
    np.testing.assert_array_equal(g.y_true.to_numpy(),target)
    residual=target-g.y_pred.to_numpy(); expected={'MAE':abs(residual).mean(), 'RMSE':np.sqrt((residual**2).mean()), 'R2':1-(residual**2).sum()/((target-target.mean())**2).sum()}
    score=scores[scores.experiment_id==exp].iloc[0]
    for key,value in expected.items(): assert np.isclose(score[key],value,rtol=1e-12,atol=1e-9)
    np.testing.assert_allclose(g.residual,residual,rtol=1e-12,atol=1e-9)
checks['test_metrics_from_predictions']='passed for all 8 models'
fold=pd.read_csv(out/'cv_fold_metrics.csv'); summary=pd.read_csv(out/'cv_summary.csv')
candidate=pd.read_csv(out/'candidate_predictions.csv')
assert len(fold)==170 and len(summary)==34
for (exp,cid),g in candidate.groupby(['experiment_id','candidate_id']):
    assert g.row_id.is_unique and set(g.row_id)==set(dev_ids)
    for f,h in g.groupby('fold'):
        assert set(h.row_id)==set(s[(s.partition=='development') & (s.validation_fold==f)].row_id)
        train_y=raw[raw.row_id.isin(set(dev_ids)-set(h.row_id))].charges
        assert np.allclose(h.high_cost_threshold,train_y.quantile(.75))
    r=summary[(summary.experiment_id==exp)&(summary.candidate_id==cid)].iloc[0]
    f=fold[(fold.experiment_id==exp)&(fold.candidate_id==cid)]
    for key in ['MAE','RMSE','R2']:
        assert np.isclose(r['cv_mean_'+key.lower()],f[key].mean())
        assert np.isclose(r['cv_std_'+key.lower()],f[key].std(ddof=1))
for exp,g in summary.groupby('experiment_id'):
    assert np.isclose(g[g.selected].cv_mean_rmse.iloc[0],g.cv_mean_rmse.min())
checks['cv_candidates_and_thresholds']='passed: 34 candidates, 170 folds, 1069 rows each'
# Refit on fold 0 and verify learned means against precisely its training rows.
d=load_partitions(root,out,cfg); dev=d[d.partition=='development']; tr=dev[dev.validation_fold!=0]
cols=cfg['numeric']+cfg['categorical']; p=make_model('ridge',{'alpha':.1,'solver':'svd'},'F2')
p.fit(tr[cols],tr.charges); scaler=p.named_steps['preprocess'].named_transformers_['num']
assert scaler.n_samples_seen_==len(tr)==855
np.testing.assert_allclose(scaler.mean_[:3],tr[cfg['numeric']].mean().to_numpy(),rtol=1e-12)
from src.features import CostFeatures
transformed=CostFeatures('F2').transform(tr[cols]); assert (transformed.age_squared==tr.age**2).all()
assert (transformed.bmi_smoker==tr.bmi*(tr.smoker=='yes').astype(float)).all()
assert list(p.named_steps['preprocess'].feature_names_in_)==cols+['age_squared','bmi_squared','age_smoker','bmi_smoker']
assert len(p.named_steps['preprocess'].get_feature_names_out())==12
checks['fold_preprocessing_and_features']='passed'
groups=pd.read_csv(out/'group_metrics.csv')
for r in groups.itertuples():
    source=pred if r.partition=='test' else pd.read_csv(out/'oof_predictions.csv')
    g=source[(source.experiment_id==r.experiment_id)&(source[r.group_variable]==r.group_value)]
    assert len(g)==r.n
    residual=g.y_true-g.y_pred
    assert np.isclose(abs(residual).mean(),r.MAE) and np.isclose(residual.mean(),r.mean_residual)
checks['group_metrics']='passed'
checks['frozen_reproduction']=json.loads((root/'results_reproduced/reproduction_check.json').read_text())
assert checks['frozen_reproduction']['passed']
(out/'verification.json').write_text(json.dumps({'passed':True,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False,indent=2))
