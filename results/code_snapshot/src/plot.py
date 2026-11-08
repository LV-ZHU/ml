"""Figures read saved experiment results; plotting never fits a model."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .prepare import load_partitions

LABELS = {"M0":"均值预测", "M1":"线性回归", "M2":"岭回归", "M3":"随机森林",
          "M2T":"优化岭回归", "M3T":"优化随机森林", "F1":"平方项岭回归", "F2":"交互项岭回归"}
BLUE, ORANGE = "#29648a", "#cf6b37"


def make_plots(root, out, cfg):
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus":False, "font.size":10, "axes.spines.top":False,
                         "axes.spines.right":False, "savefig.dpi":220})
    figures = out / "figures"; figures.mkdir(exist_ok=True)
    made=[]
    def save(fig,name):
        fig.savefig(figures/name,bbox_inches="tight",facecolor="white"); plt.close(fig); made.append(name)
    d=load_partitions(root,out,cfg); dev=d[d.partition=="development"]
    fig, ax=plt.subplots(2,2,figsize=(9,6.2),layout="constrained")
    ax[0,0].hist(dev.charges,bins=30,color=BLUE,edgecolor="white")
    ax[0,0].set(xlabel="医疗费用（原始费用单位）",ylabel="样本数",title="开发集费用分布")
    ax[0,1].boxplot([dev[dev.smoker==s].charges for s in ["no","yes"]],tick_labels=["不吸烟","吸烟"],showfliers=True)
    ax[0,1].set(ylabel="医疗费用（原始费用单位）",title="开发集吸烟分组")
    ax[1,0].scatter(dev.age,dev.charges,s=9,alpha=.45,color=BLUE)
    ax[1,0].set(xlabel="年龄（岁）",ylabel="医疗费用（原始费用单位）",title="开发集年龄与费用")
    for s,c,label in [("no",BLUE,"不吸烟"),("yes",ORANGE,"吸烟")]:
        g=dev[dev.smoker==s]; ax[1,1].scatter(g.bmi,g.charges,s=10,alpha=.55,c=c,label=label)
    ax[1,1].set(xlabel="BMI（kg/m²）",ylabel="医疗费用（原始费用单位）",title="开发集 BMI 与费用"); ax[1,1].legend()
    save(fig,"01_development.png")
    summary=pd.read_csv(out/"cv_summary.csv"); s=summary[summary.selected].set_index("experiment_id")
    order=list(LABELS)
    test=pd.read_csv(out/"test_metrics.csv").set_index("experiment_id")
    fig,ax=plt.subplots(figsize=(9,4),layout="constrained"); x=np.arange(len(order))
    ax.bar(x-.19,s.loc[order].cv_mean_rmse,.37,yerr=s.loc[order].cv_std_rmse,label="五折验证均值 ± 标准差",color=BLUE,capsize=3)
    ax.bar(x+.19,test.loc[order].RMSE,.37,label="测试集",color=ORANGE)
    ax.set(xticks=x,xticklabels=[LABELS[e] for e in order],ylabel="RMSE（原始费用单位）")
    ax.tick_params(axis="x",labelrotation=24); ax.legend(); save(fig,"02_model_comparison.png")
    pred=pd.read_csv(out/"test_predictions.csv")
    selected=["M1","M3","M3T","F2"]
    limit=max(pred.y_true.max(),pred.y_pred.max())*1.03; low=min(0,pred.y_pred.min())-1000
    fig,axes=plt.subplots(2,2,figsize=(8.8,7.3),layout="constrained")
    for exp,ax in zip(selected,axes.flat):
        g=pred[pred.experiment_id==exp]; ax.scatter(g.y_true,g.y_pred,s=12,alpha=.6,color=BLUE)
        ax.plot([low,limit],[low,limit],"--",color=ORANGE,lw=1)
        ax.set(title=LABELS[exp],xlabel="真实费用（原始费用单位）",ylabel="预测费用（原始费用单位）",xlim=(low,limit),ylim=(low,limit))
    save(fig,"03_predictions.png")
    fig,axes=plt.subplots(1,2,figsize=(9,3.6),layout="constrained")
    for exp,ax in zip(["M3T","F2"],axes):
        g=pred[pred.experiment_id==exp]
        ax.scatter(g.y_pred,g.residual,s=12,alpha=.6,color=BLUE); ax.axhline(0,color=ORANGE,ls="--")
        ax.set(title=LABELS[exp],xlabel="预测费用（原始费用单位）",ylabel="残差 真实值−预测值",ylim=(pred.residual.min()-1000,pred.residual.max()+1000))
    save(fig,"04_residuals.png")
    fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout="constrained")
    r=summary[summary.experiment_id=="M2T"].copy(); r["alpha"]=r.params_json.map(lambda p:json.loads(p)["params"]["alpha"])
    axes[0].errorbar(r.alpha,r.cv_mean_rmse,yerr=r.cv_std_rmse,marker="o",capsize=3,color=BLUE)
    axes[0].set(xscale="log",xlabel="岭回归 alpha",ylabel="验证 RMSE（原始费用单位）",title="均值与折间标准差")
    r=summary[summary.experiment_id=="M3T"].copy()
    r["depth"]=r.params_json.map(lambda p:str(json.loads(p)["params"]["max_depth"]))
    r["leaf"]=r.params_json.map(lambda p:json.loads(p)["params"]["min_samples_leaf"])
    matrix=r.pivot(index="depth",columns="leaf",values="cv_mean_rmse").reindex(["3","5","10","None"])
    im=axes[1].imshow(matrix.values,cmap="Blues_r",aspect="auto")
    axes[1].set(xticks=[0,1,2],xticklabels=[1,3,5],yticks=[0,1,2,3],yticklabels=["3","5","10","不限"],xlabel="叶节点最小样本数",ylabel="最大树深度",title="随机森林五折平均 RMSE")
    for (i,j),value in np.ndenumerate(matrix.values): axes[1].text(j,i,f"{value:.0f}",ha="center",va="center",color="black")
    fig.colorbar(im,ax=axes[1],shrink=.8); save(fig,"05_tuning.png")
    fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout="constrained")
    f=pd.read_csv(out/"feature_comparison.csv").set_index("experiment_id").loc[["F0","F1","F2"]]
    axes[0].bar(f.index,f.cv_mean_rmse,yerr=f.cv_std_rmse,capsize=4,color=BLUE)
    axes[0].set(ylabel="验证 RMSE（原始费用单位）",title="各特征组独立选择 alpha")
    g=pd.read_csv(out/"test_group_metrics.csv"); g=g[(g.experiment_id=="M3T") & (g.group_variable=="cost_group")].set_index("group_value").loc[["other","high"]]
    axes[1].bar([f"其他费用 n={g.loc['other','n']}",f"高费用 n={g.loc['high','n']}"],g.MAE,color=[BLUE,ORANGE])
    axes[1].set(ylabel="测试 MAE（原始费用单位）",title="优化随机森林费用分组误差")
    save(fig,"06_features_groups.png")
    return made
