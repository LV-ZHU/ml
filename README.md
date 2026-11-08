# 医疗费用预测课程项目

## 已完成结果

原始数据1338条，去除1条完全重复记录后1337条。固定开发集1069条、测试集268条，随机种子42；开发集五折验证。

按开发验证平均RMSE选择的模型为 **M3T 优化随机森林**：200棵树、最大深度5、叶节点最小样本数5。测试MAE为2142.17、RMSE为3398.01、R²为0.9199，费用单位为原始费用单位。全部8个模型及34个候选的真实结果见 `results/`。

## 环境与安装

实验环境：Windows 11、Python 3.13.12；准确依赖版本已固定在 `requirements.txt`，硬件及各阶段起止时间见 `results/environment.json` 与 `results/runs/*/environment.json`。训练和复现无需联网读取数据。

在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

报告生成另需 `requirements-report.txt` 中的依赖。`.venv` 不随提交包分发；在新电脑重新建立环境。

## 复现已冻结结果

```powershell
.\.venv\Scripts\python.exe -m src.run --stage reproduce --config config.json --output my_reproduction --reference-results results
```

该命令沿用保存的划分与冻结参数，在完整开发集重新拟合全部模型，生成测试预测，随后逐条比对原预测。通过后生成 `my_reproduction/reproduction_check.json`。验证容差为 `rtol=1e-9, atol=1e-6`。已实际在 `results_reproduced` 中复现，最大预测绝对差约2.18×10⁻¹¹。拟合耗时允许随机器负载变化。

## 重新运行完整开发流程

为保留已交付的实验历史，请指定新的输出目录：

```powershell
$env:MPLCONFIGDIR = Join-Path $PWD 'my_experiment\matplotlib_cache'
.\.venv\Scripts\python.exe -m src.run --stage all --config config.json --output my_experiment
```

也可运行 `./run_all.ps1 -OutputDir my_experiment`。依赖顺序为：

1. prepare：数据校验、审计、去重与固定划分。
2. baseline：一折试运行，再运行M0、M1、M2、M3的五折验证。
3. tune：六组岭回归与12组随机森林候选。
4. features：F0复用M2T，F1、F2各六个alpha候选，另存固定alpha对照。
5. diagnose：固定M1、M3的折外预测与分组误差。
6. freeze：保存参数、特征、指标、分组规则、源代码与划分校验值。
7. test：按冻结方案重训、保存逐条预测和测试指标。
8. plots：从已保存结果绘制六组图，不训练模型。

可将 `--stage all` 替换为单个阶段，所有命令使用同一个 `--output`。每一阶段检查上一阶段是否完成，并保存独立运行标识、配置、结果快照及交接文件；已经完成的阶段拒绝覆盖。失败后阅读对应 `runs/*/failure.json`、`failure_候选.json` 和 `run.log`，只重跑尚未完成的阶段。不要删除旧结果后重新选择划分。

## 使用已训练模型预测

```powershell
.\.venv\Scripts\python.exe scripts/predict.py --input data/example_inputs.csv --output predictions.csv
```

输入包含 `age,sex,bmi,children,smoker,region` 六列即可。默认读取 `results/models/M3T.joblib`，输出新增 `predicted_charges` 列；也可用 `--model` 指定其他保存的模型。类别使用数据字典中的取值。模型文件对应本项目依赖版本。

## 复核与报告生成

```powershell
.\.venv\Scripts\python.exe scripts/verify_results.py
.\.venv\Scripts\python.exe -m pip install -r requirements-report.txt
.\.venv\Scripts\python.exe scripts/build_report.py
```

复核脚本独立检查数据版本、去重规则、划分重建、五折互斥与覆盖、每条预测的真实值对齐、训练折标准化、特征构造、34个候选的验证统计、分组阈值以及测试指标重算。`results_reproduced` 是默认的已验证复现目录；保留该目录即可直接运行复核。报告生成只读取 `results` 与 `assets/报告模板.docx`，输出Word与可编辑正文，不重新训练。

补齐 `member_info.json` 后再运行报告生成脚本。例如：

```json
{"members": [{"name": "实际姓名", "student_id": "实际学号", "contribution": "实际完成的任务"}]}
```

贡献表沿用模板的三行容量，按实际成员填写。重新生成报告后，应使用Word重新检查分页和图表。当前交付稿已逐页核对；预览PDF与PNG属于内部检查文件。

## 数据与来源

数据随项目保存在 `data/raw/insurance.csv`，原样SHA256为：

```text
388eff679557d08ac19f463d025de5e0b4adc482537c8456d19934d78621fd47
```

发布页面：[Medical Cost Personal Datasets](https://www.kaggle.com/datasets/mirichoi0218/insurance)，发布者 Miri Choi，版本1。发布接口标注许可 `Database: Open Database, Contents: Database Contents`。数据卡致谢指向 [stedy 的数据仓库](https://github.com/stedy/Machine-Learning-with-R-datasets)。已下载公开副本逐记录比较，字段、形状、数值及行顺序完全一致；字节差异和校验值见 `results/source_verification.json`。源接口响应、README和公开对照CSV保存在 `qa/`。

charges按数据卡定义为向健康保险计费的个人医疗费用。数据卡未明确币种、费用统计周期、收集年份或抽样方式；这些待核实信息记录在工作记录与来源文件中。图表统一标注原始费用单位。

## 结果文件

| 文件 | 内容 |
|---|---|
| `config.json`、`requirements.txt` | 固定实验配置与准确依赖 |
| `results/data_audit.json`、`field_dictionary.csv` | 审计与术语定义 |
| `results/splits.csv` | 稳定行号、开发/测试划分、验证折与顺序 |
| `results/cv_fold_metrics.csv`、`cv_summary.csv` | 每折训练和验证指标、均值、样本标准差 |
| `results/search_results.csv` | 完整候选、参数、排名、状态与错误 |
| `results/candidate_predictions.csv` | 全部候选逐条开发验证预测 |
| `results/oof_predictions.csv` | 固定M1、M3折外诊断预测 |
| `results/feature_comparison.csv`、`feature_fixed_alpha.csv` | 独立选参与固定alpha特征对照 |
| `results/frozen_protocol.json`、`code_snapshot` | 冻结方案与实际训练代码 |
| `results/test_predictions.csv`、`test_metrics.csv` | 测试逐条预测、汇总指标与负预测数 |
| `results/group_metrics.csv` | 开发折外与测试分组指标 |
| `results/test_access_history.jsonl` | 冻结后的测试访问记录 |
| `results/verification.json` | 独立复核结果 |
| `results/figures`、`models` | 六组图与保存的完整模型流水线 |
| `results/runs`| 各阶段配置、结果快照、交接、错误修复与选参决定 |

五折平均RMSE使用每折RMSE的算术平均，折间标准差使用ddof=1；合并折外预测的RMSE另存于 `oof_metrics.csv`。F0与M2T共用结果。推荐依据保持为开发验证平均RMSE，测试结果用于最终评价。

## 提交


报告中的数据和方法来源在参考文献中列出。可选的从零实现、对数变换、学习曲线和额外模型未启用；本项目已完成特征工程与分组误差拓展。
