"""Fill a copy of the user template using saved results; no model training."""
from pathlib import Path
from copy import deepcopy
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json
import pandas as pd
from docx import Document
from docx.text.paragraph import Paragraph
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.style import WD_STYLE_TYPE

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'报告'; OUT.mkdir(exist_ok=True)
RESULT=ROOT/'results'
TEMPLATE=ROOT/'assets/报告模板.docx'
assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()=='4b6dccd77acfe138ec94b89c88e0ec1730d2e65c55b5b46c5f94cc1cafac1957'
doc=Document(TEMPLATE)
if 'Title' not in doc.styles:
    title_style=doc.styles.add_style('Title',WD_STYLE_TYPE.PARAGRAPH)
    title_style.base_style=doc.styles['Normal']
source=[deepcopy(p._p) for p in doc.paragraphs]
contribution=deepcopy(doc.tables[0]._tbl)
section=deepcopy(doc.sections[0]._sectPr)
body=doc._element.body
for child in list(body): body.remove(child)
body.append(section)
text_archive=[]
NEXT_PAGE=False

def font(run,size=12,bold=False):
    run.font.name='Times New Roman'; run.font.size=Pt(size); run.font.bold=bold; run.font.color.rgb=RGBColor(0,0,0)
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'宋体')

def para(text='',template=3,size=12,bold=False,align=None):
    global NEXT_PAGE
    element=deepcopy(source[template])
    for ch in list(element):
        if ch.tag!=qn('w:pPr'): element.remove(ch)
    body.insert(len(body)-1,element); p=Paragraph(element,doc._body)
    if NEXT_PAGE:
        p.paragraph_format.page_break_before=True
        NEXT_PAGE=False
    if template==3:
        p.paragraph_format.space_before=Pt(0); p.paragraph_format.space_after=Pt(6)
        p.paragraph_format.line_spacing=1.5
        p.paragraph_format.widow_control=True
    if align is not None: p.alignment=align
    if text: font(p.add_run(text),size,bold)
    text_archive.append(text)
    return p

def head(index,text=None):
    original=Paragraph(source[index],doc._body).text
    p=para(text or original,template=index,size=14 if index in [0,10] else 12,bold=True)
    p.paragraph_format.keep_with_next=True
    return p

def sub(text):
    p=para(text,bold=True); p.paragraph_format.first_line_indent=Pt(0); p.paragraph_format.keep_with_next=True
    return p

def page():
    global NEXT_PAGE
    NEXT_PAGE=True

def caption(text):
    p=para(text,size=10.5,align=WD_ALIGN_PARAGRAPH.CENTER)
    p.paragraph_format.first_line_indent=Pt(0); p.paragraph_format.line_spacing=1.15
    return p

def figure(name,label,width=5.7):
    p=para(align=WD_ALIGN_PARAGRAPH.CENTER); p.paragraph_format.first_line_indent=Pt(0)
    p.paragraph_format.line_spacing=1; p.paragraph_format.keep_with_next=True
    p.add_run().add_picture(str(RESULT/'figures'/name),width=Inches(width))
    # Alternative text is stored with the image for accessibility.
    for n in p._p.iter(qn('wp:docPr')): n.set('descr',label)
    caption(label)

def table(headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.autofit=False
    for i,w in enumerate(widths): t.columns[i].width=Inches(w)
    for row,vals in [(t.rows[0],headers)]+[(t.add_row(),x) for x in rows]:
        for i,value in enumerate(vals):
            c=row.cells[i]; c.width=Inches(widths[i]); c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p=c.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.LEFT if i==0 else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(3); p.paragraph_format.line_spacing=1.1
            font(p.add_run(str(value)),10.5,row is t.rows[0])
            tcPr=c._tc.get_or_add_tcPr(); margins=OxmlElement('w:tcMar')
            for side in ['top','left','bottom','right']:
                e=OxmlElement('w:'+side); e.set(qn('w:w'),'70'); e.set(qn('w:type'),'dxa'); margins.append(e)
            tcPr.append(margins)
        cant=OxmlElement('w:cantSplit'); row._tr.get_or_add_trPr().append(cant)
    borders=OxmlElement('w:tblBorders')
    for side in ['top','left','bottom','right','insideH','insideV']:
        e=OxmlElement('w:'+side); e.set(qn('w:val'),'single'); e.set(qn('w:sz'),'4'); e.set(qn('w:color'),'000000'); borders.append(e)
    t._tbl.tblPr.append(borders)
    repeat=OxmlElement('w:tblHeader'); t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for c in t.rows[0].cells:
        for r in c.paragraphs[0].runs: r.bold=True
    body.remove(t._tbl); body.insert(len(body)-1,t._tbl)
    text_archive.extend([' | '.join(map(str,headers))]+[' | '.join(map(str,x)) for x in rows])
    return t

summary=pd.read_csv(RESULT/'cv_summary.csv'); S=summary[summary.selected].set_index('experiment_id')
T=pd.read_csv(RESULT/'test_metrics.csv').set_index('experiment_id')
G=pd.read_csv(RESULT/'group_metrics.csv')
env=json.loads((RESULT/'environment.json').read_text(encoding='utf-8'))
audit=json.loads((RESULT/'data_audit.json').read_text(encoding='utf-8'))
protocol=json.loads((RESULT/'frozen_protocol.json').read_text(encoding='utf-8'))
names={'M0':'均值预测','M1':'线性回归','M2':'岭回归','M3':'随机森林','M2T':'优化岭回归','M3T':'优化随机森林','F1':'平方项岭回归','F2':'交互项岭回归'}
def n(x): return f'{float(x):.2f}'
def pct(a,b): return f'{(float(a)-float(b))/float(a)*100:.2f}%'
def group(part,exp,var,value):
    return G[(G.partition==part)&(G.experiment_id==exp)&(G.group_variable==var)&(G.group_value==value)].iloc[0]

# Page 1: source contribution table, overview and purpose.
p=para('基于个人特征的医疗费用预测',size=18,bold=True,align=WD_ALIGN_PARAGRAPH.CENTER)
p.style=doc.styles['Title']; p.paragraph_format.first_line_indent=Pt(0); p.paragraph_format.space_after=Pt(12)
body.insert(len(body)-1,contribution)
from docx.table import Table
ct=Table(contribution,doc._body)
members=json.loads((ROOT/'member_info.json').read_text(encoding='utf-8'))['members']
for i in range(1,4):
    vals=(f"{members[i-1]['name']} / {members[i-1]['student_id']}",members[i-1]['contribution']) if i<=len(members) else (('姓名待填 / 学号待填','实际任务与贡献待填') if i==1 else ('',''))
    for c,value in zip(ct.rows[i].cells,vals):
        c.text=value
        for p in c.paragraphs:
            for r in p.runs: font(r,12)
head(0); head(1)
para('医疗费用预测以个人特征为输入，估计连续数值型的医疗费用。本文使用年龄、性别、身体质量指数、受抚养人数、吸烟状态和地区，比较线性回归、岭回归与随机森林，并分析参数优化和交互特征对误差的影响。')
para(f'按开发集五折验证结果选择的模型为优化随机森林。该模型在268条测试样本上的平均绝对误差为{n(T.loc["M3T","MAE"])}，均方根误差为{n(T.loc["M3T","RMSE"])}，决定系数为{T.loc["M3T","R2"]:.4f}。高费用样本仍有较大的预测偏差。')
head(4)
para('研究围绕三个问题展开：三种回归方法在统一评价条件下的误差有何差异；年龄与身体质量指数的平方项及吸烟交互项能否改善岭回归；不同吸烟状态和费用水平样本的误差有何差异。')
para('实验以均值预测为参照，依次完成基础模型比较、岭回归和随机森林参数搜索、三组特征对照以及分组误差分析。最终模型依据开发集验证误差确定，并在预留测试集上统一评价。')

# Page 2: dataset and complete original field definitions.
page(); head(7)
para('数据采用 Miri Choi 发布的 Medical Cost Personal Datasets，第1版包含1338条记录、7个字段[1]。数据卡将其与 Brett Lantz 的 Machine Learning with R 教材数据关联，并给出公开数据仓库[2]。每条样本对应一条个人受益人记录，预测目标 charges 表示向健康保险计费的个人医疗费用。')
para('身体质量指数（Body Mass Index，BMI）等于体重除以身高的平方，单位为kg/m²。children统一称为受抚养人数，表示医保覆盖的子女或受抚养人数。表1列出全部字段及其用途。')
caption('表1 数据字段与模型输入')
table(['字段','统一名称','类型与取值','用途'],[
 ['age','年龄','18—64岁','输入'],['sex','性别','female、male','输入'],
 ['bmi','身体质量指数 BMI','15.96—53.13 kg/m²','输入'],['children','受抚养人数','0—5人','输入'],
 ['smoker','吸烟状态','no、yes','输入'],['region','地区','美国东北、西北、东南、西南','输入'],
 ['charges','医疗费用','1121.87—63770.43','目标']], [1.0,1.25,2.45,.9])
para('费用数值均按原始费用单位报告。性别、吸烟状态和地区作为类别输入；年龄、BMI和受抚养人数作为数值输入。原始行号 row_id 用于追踪样本与预测结果。')
para('主样本为去除完全重复记录后的1337条记录，其中1069条进入开发集，268条进入测试集。开发集承担数据探索、参数选择和特征比较，测试集用于最终评价。')

# Page 3: preprocessing and development-only exploration.
page(); head(10); head(11)
para('数据含零缺失值、零无穷值和1条完全重复记录。按顺序保留首次出现的记录，得到1337条主样本。数值范围检查后保留高费用与高BMI样本。')
para('为稳定吸烟样本比例，按吸烟状态分层作80%/20%随机划分，随机种子为42。开发集含219条吸烟、850条不吸烟样本；测试集分别为55条、213条。开发集采用打乱顺序的五折交叉验证，验证折依次含214、214、214、214、213条样本。')
para('类别采用独热编码，转成0或1的指示列，并删除一个参考类别。线性回归和岭回归的数值输入减去训练均值，再除以训练标准差；随机森林保留原尺度。处理流水线（Pipeline）在各训练折内独立拟合预处理与模型[3]。')
figure('01_development.png','图1 开发集费用分布及其与年龄 BMI 吸烟状态的关系',5.3)
para('开发集费用分布右偏，少数样本形成较长的高费用尾部。吸烟样本的费用中位数为34254.05，不吸烟样本为7351.95；BMI与费用的散点关系也随吸烟状态变化。这一分组差异为后续吸烟交互项实验提供依据。')

# Page 4: model principles, exact objectives and baseline settings.
page(); head(14)
sub('线性回归与岭回归')
para('为建立可解释的加性预测关系，线性回归对编码后的输入加权求和，并选择使训练平方误差之和最小的系数[4]。设 xᵢ 为第i条样本的输入向量，yᵢ为真实费用，β₀为截距，β为系数向量，则预测为 ŷᵢ＝β₀＋xᵢᵀβ。')
para('为控制相关输入所对应系数的大小，岭回归在平方误差之和上增加系数平方惩罚[5,8]。正则化强度α越大，对较大系数的惩罚越强。本文同时拟合截距，并使用奇异值分解（Singular Value Decomposition，SVD）求解。')
caption('线性回归目标  min Σᵢ(yᵢ−β₀−xᵢᵀβ)²')
caption('岭回归目标  min [Σᵢ(yᵢ−β₀−xᵢᵀβ)²＋αΣⱼβⱼ²]')
sub('随机森林')
para('为表达分段关系与变量交互，随机森林对训练样本进行有放回抽样，分别拟合多棵回归树，再对各树预测取平均[6]。每棵树通过输入条件将样本分组，并用叶节点训练费用的均值给出预测。树深度和叶节点最小样本数控制模型复杂度。')
para('本文设置200棵树，固定随机种子42，bootstrap=True，max_features=1.0，即每次分裂可考察全部编码后输入[7]。因此，本实验的树之间随机性主要来自样本抽样。')
caption('表2 基础模型设置')
table(['编号','方法','主要设置'],[
 ['M0','均值预测','训练部分费用均值'],['M1','线性回归','拟合截距，最小二乘'],
 ['M2','岭回归','α＝1，拟合截距，SVD'],['M3','随机森林','200棵树，深度不限，叶节点最少1条']], [.55,1.25,3.8])
para('均值预测为常数参照。M1、M2与M3均使用六个原始字段；独热编码后共有8列输入。模型比较由相同样本和相同验证折构成。')

# Page 5: training and metrics.
page(); head(17)
para('开发集采用五折交叉验证：每次使用四折拟合全部预处理步骤和模型，以剩余一折计算指标，重复五次。每个候选保存训练误差、验证误差与拟合时间。对每组候选，以五个验证RMSE的算术平均值最小者为该组方案，同时报告指标均值及样本标准差。')
para('为同时衡量一般偏差与较大误差，采用平均绝对误差（Mean Absolute Error，MAE）和均方根误差（Root Mean Squared Error，RMSE）。决定系数R²衡量模型相对该评价集合真实费用均值预测的改进程度[4]。设评价集合包含n条样本，ȳ为真实费用均值，各指标定义如下。')
caption('MAE＝(1/n) Σᵢ |yᵢ−ŷᵢ|')
caption('RMSE＝√[(1/n) Σᵢ (yᵢ−ŷᵢ)²]')
caption('R²＝1−Σᵢ(yᵢ−ŷᵢ)² / Σᵢ(yᵢ−ȳ)²')
para('MAE与RMSE越小越好，R²越大越好。所有指标均在原始费用尺度计算。残差定义为真实费用减预测费用，正值表示低估；分组平均残差用于观察偏差方向。')
sub('参数选择与最终评价流程')
para('流程为开发集五折选参与特征比较、冻结方案、完整开发集重训和测试集统一评价。')
para('参数搜索外层采用单进程，随机森林最多使用4个线程。推荐模型由开发验证平均RMSE确定。最终评价包含M0—M3、优化岭回归M2T、优化随机森林M3T及F1、F2。')
caption('表3 实验运行环境')
table(['项目','实际配置'],[['操作系统 / Python',f'Windows 11 / {env["python"]}'],['NumPy / pandas',f'{env["packages"]["numpy"]} / {env["packages"]["pandas"]}'],['scikit-learn / SciPy',f'{env["packages"]["scikit-learn"]} / {env["packages"]["scipy"]}']], [2.2,3.4])

# Page 6: principal comparison.
page(); head(20)
para(f'优化随机森林在开发验证中的平均RMSE最低，为{n(S.loc["M3T","cv_mean_rmse"])}±{n(S.loc["M3T","cv_std_rmse"])}，据此选为推荐模型。表4给出全部方案在同一测试集上的表现，费用误差均采用原始费用单位。')
caption('表4 测试集模型性能  n＝268')
table(['编号','模型','MAE','RMSE','R²'],[[e,names[e],n(T.loc[e,'MAE']),n(T.loc[e,'RMSE']),f'{T.loc[e,"R2"]:.4f}'] for e in names],[.5,1.75,1.1,1.1,1.15])
figure('02_model_comparison.png','图2 各模型五折验证与测试 RMSE 误差线为折间标准差')
para(f'基础随机森林相较线性回归的测试RMSE下降{pct(T.loc["M1","RMSE"],T.loc["M3","RMSE"])}。优化随机森林进一步降至{n(T.loc["M3T","RMSE"])}，其MAE和R²也同时改善。交互项岭回归的测试RMSE为{n(T.loc["F2","RMSE"])}，优于M1、M2、M2T和F1。')

# Page 7: same coordinate prediction plots.
page(); sub('真实费用与预测费用的对应关系')
figure('03_predictions.png','图3 测试集真实费用与预测费用 虚线为 y＝x',5.65)
para('线性回归在高费用区出现较宽的点带，部分样本明显偏离等值线。随机森林能够形成不同的费用区间，优化后散点更集中在等值线附近。交互项岭回归也减少了高费用区的整体偏离。')
para(f'线性回归与优化岭回归的测试RMSE分别为{n(T.loc["M1","RMSE"])}和{n(T.loc["M2T","RMSE"])}，表现接近。它们共享相同的加性输入结构，小幅调整正则化强度对预测关系的改变较小。增加吸烟交互项后误差明显下降，说明在本实验中，表达输入关系比微调原始特征岭回归的系数惩罚更有效。')

# Page 8: residuals, explanation grounded in groups.
page(); sub('残差分布与误差结构')
figure('04_residuals.png','图4 测试集残差 正值表示真实费用高于预测费用')
para('优化随机森林和交互项岭回归都存在正向的大残差。部分费用处于中低预测区间的样本，其真实费用明显更高，形成散点图上方的偏差。多数预测较准确与少数大误差并存，使RMSE明显高于MAE。')
para(f'优化随机森林的测试MAE为{n(T.loc["M3T","MAE"])}，RMSE为{n(T.loc["M3T","RMSE"])}。在高费用组中，其平均残差为{n(group("test","M3T","cost_group","high").mean_residual)}，呈低估方向；其他费用组为{n(group("test","M3T","cost_group","other").mean_residual)}，呈高估方向。分组结果表明，费用两端仍有向中间收缩的预测现象。')
para('一种解释是叶节点平均会平滑同组样本间的差异，而输入仅包含六个个人特征。对于年龄、BMI等输入相近但费用差异较大的记录，模型会给出相近预测。后续可增加诊疗项目、既往病史等与实际费用形成直接相关的输入，检验能否减少这一类大残差。')
para(f'测试集中，线性回归、原始岭回归和优化岭回归各有3条负费用预测，平方项岭回归有2条。本文按冻结时的原始预测计算各项指标。随机森林和交互项岭回归的测试预测均为非负。')

# Page 9: fixed budgets and optimization evidence.
page(); head(23)
para('为检验正则化强度与树复杂度的作用，岭回归对α＝0.01、0.1、1、10、100、1000进行六组搜索。随机森林对最大深度3、5、10、不限和叶节点最小样本数1、3、5进行12组搜索，树数等其他设置保持不变。两组网格均包含基础模型参数。')
figure('05_tuning.png','图5 开发集参数优化 岭回归误差线为折间标准差')
caption('表5 优化前后五折验证结果')
table(['方案','选定参数','训练RMSE','验证RMSE'],[
 ['M2','α＝1',n(S.loc['M2','train_mean_rmse']),n(S.loc['M2','cv_mean_rmse'])],
 ['M2T','α＝0.1',n(S.loc['M2T','train_mean_rmse']),n(S.loc['M2T','cv_mean_rmse'])],
 ['M3','深度不限，叶1',n(S.loc['M3','train_mean_rmse']),n(S.loc['M3','cv_mean_rmse'])],
 ['M3T','深度5，叶5',n(S.loc['M3T','train_mean_rmse']),n(S.loc['M3T','cv_mean_rmse'])]], [.65,2.05,1.45,1.45])
para(f'岭回归的最佳α为0.1，验证RMSE较α＝1仅下降{n(S.loc["M2","cv_mean_rmse"]-S.loc["M2T","cv_mean_rmse"])}，提升幅度很小；α达到100和1000时误差明显上升，较强惩罚削弱了拟合。随机森林将最大深度限制为5、叶节点最小样本数设为5后，验证RMSE下降{pct(S.loc["M3","cv_mean_rmse"],S.loc["M3T","cv_mean_rmse"])}。训练与验证RMSE的差距由{n(S.loc["M3","cv_mean_rmse"]-S.loc["M3","train_mean_rmse"])}缩至{n(S.loc["M3T","cv_mean_rmse"]-S.loc["M3T","train_mean_rmse"])}，说明限制树复杂度减少了对训练样本细节的拟合。')

# Page 10: feature comparisons, including less favorable MAE.
page(); head(26)
sub('平方项与吸烟交互项')
para('为使岭回归表达曲线关系，F1在原始六个输入F0上增加年龄平方与BMI平方；为表达吸烟状态下不同的年龄和BMI关系，F2进一步增加年龄×吸烟指示变量、BMI×吸烟指示变量，吸烟记为1、不吸烟记为0。平方与乘积均由原始数值构造，再在训练折内统一标准化，吸烟类别输入继续保留。')
para('三个特征组分别在相同六个α候选、相同样本与相同五折上独立选参。F0复用M2T结果；编码后F0、F1、F2分别含8、10、12列输入。')
caption('表6 特征方案的五折验证结果')
table(['组别','最佳α','MAE','RMSE均值±标准差','R²'],[[label,json.loads(S.loc[e,'params_json'])['params']['alpha'],n(S.loc[e,'cv_mean_mae']),f'{n(S.loc[e,"cv_mean_rmse"])}±{n(S.loc[e,"cv_std_rmse"])}',f'{S.loc[e,"cv_mean_r2"]:.4f}'] for label,e in [('F0','M2T'),('F1','F1'),('F2','F2')]],[.5,.65,1.0,2.35,1.1])
figure('06_features_groups.png','图6 特征方案验证 RMSE 与优化随机森林测试分组 MAE')
para(f'F1的平均RMSE较F0下降{pct(S.loc["M2T","cv_mean_rmse"],S.loc["F1","cv_mean_rmse"])}，同时MAE由{n(S.loc["M2T","cv_mean_mae"])}升至{n(S.loc["F1","cv_mean_mae"])}，说明仅增加平方项对一般偏差的改善有限。F2使平均RMSE下降{pct(S.loc["M2T","cv_mean_rmse"],S.loc["F2","cv_mean_rmse"])}，MAE与R²同步改善。')
fixed=pd.read_csv(RESULT/'feature_fixed_alpha.csv').set_index('experiment_id')
para(f'固定α＝0.1的补充对照中，F0、F1、F2的平均RMSE依次为{n(fixed.loc["F0","cv_mean_rmse"])}、{n(fixed.loc["F1","cv_mean_rmse"])}、{n(fixed.loc["F2","cv_mean_rmse"])}。这一排序与独立选参一致，支持吸烟交互项对误差下降的贡献。')

# Page 11: predefined independent group analyses.
page(); sub('吸烟状态与高费用样本的分组误差')
para('为观察不同样本的误差，先对固定参数M1、M3产生折外预测，即每条开发样本的预测来自未包含该样本的训练折。高费用组定义为真实费用高于相应训练部分第75百分位数的样本。测试分组使用完整开发集阈值17178.68；残差沿用真实费用减预测费用。')
caption('表7 固定模型的开发集折外分组误差')
rows=[]
for var,val,label in [('smoker','no','不吸烟'),('smoker','yes','吸烟'),('cost_group','other','其他费用'),('cost_group','high','高费用')]:
    a=group('development','M1',var,val); b=group('development','M3',var,val)
    rows.append([label,int(a.n),n(a.MAE),n(b.MAE),n(a.mean_residual),n(b.mean_residual)])
table(['分组','n','M1 MAE','M3 MAE','M1平均残差','M3平均残差'],rows,[.85,.45,1.0,1.0,1.15,1.15])
para('基础随机森林对吸烟样本的MAE明显低于线性回归，表明树模型对该组费用关系的表达更充分。高费用组仍有较大的正向平均残差，是总体大误差的重要来源。')
caption('表8 优化随机森林的测试集分组结果')
rows=[]
for var,val,label in [('smoker','no','不吸烟'),('smoker','yes','吸烟'),('cost_group','other','其他费用'),('cost_group','high','高费用')]:
    a=group('test','M3T',var,val); rows.append([label,int(a.n),n(a.MAE),n(a.RMSE),n(a.mean_residual)])
table(['分组','n','MAE','RMSE','平均残差'],rows,[1.1,.5,1.3,1.3,1.5])
para(f'优化随机森林在吸烟与不吸烟测试样本上的MAE分别为{n(group("test","M3T","smoker","yes").MAE)}和{n(group("test","M3T","smoker","no").MAE)}，两组接近；高费用组MAE为{n(group("test","M3T","cost_group","high").MAE)}，约为其他费用组的{group("test","M3T","cost_group","high").MAE/group("test","M3T","cost_group","other").MAE:.2f}倍。因此，总体误差下降之后，进一步减少高费用样本的大偏差仍是主要改进方向。')
para('费用分组按照真实费用定义，用于描述预测完成后的误差分布。吸烟状态与费用水平分别分组，分组数值与总体指标一并报告。')

# Page 12: direct answers and references.
page(); head(0,'三、总结')
para(f'本实验在1337条主样本上完成了三种回归方法的比较。随机森林的开发验证与测试误差均低于采用原始输入的线性回归和岭回归。通过限制树深度和增大叶节点最小样本数，优化随机森林的五折平均RMSE由{n(S.loc["M3","cv_mean_rmse"])}降至{n(S.loc["M3T","cv_mean_rmse"])}，测试RMSE为{n(T.loc["M3T","RMSE"])}，R²为{T.loc["M3T","R2"]:.4f}。')
para(f'特征对照表明，仅加入年龄和BMI平方项的改进较小；进一步加入吸烟交互项后，岭回归的五折平均RMSE较原始特征方案下降{pct(S.loc["M2T","cv_mean_rmse"],S.loc["F2","cv_mean_rmse"])}，固定α对照保持同样排序。这说明结合分布分析构造少量交互项，能够改善简单模型对费用差异的表达。')
para('分组分析显示，优化随机森林在两类吸烟状态样本上的MAE接近，高费用样本误差仍明显高于其他费用样本，并存在平均低估。后续研究可围绕这些大残差样本补充诊疗与病史信息，检验新增输入带来的误差变化。')
sub('参考文献')
references=[
 '[1] CHOI M. Medical Cost Personal Datasets[DB/OL]. Version 1, 2018[2026-11-05]. https://www.kaggle.com/datasets/mirichoi0218/insurance.',
 '[2] STEDY. Data for Machine Learning with R[DB/OL]. [2026-11-05]. https://github.com/stedy/Machine-Learning-with-R-datasets.',
 '[3] Scikit-learn developers. Common pitfalls and recommended practices[EB/OL]. Version 1.9.1[2026-11-05]. https://scikit-learn.org/1.9/common_pitfalls.html.',
 '[4] JAMES G, WITTEN D, HASTIE T, et al. An Introduction to Statistical Learning with Applications in Python[M]. Cham: Springer, 2023. DOI:10.1007/978-3-031-38747-0.',
 '[5] HOERL A E, KENNARD R W. Ridge regression: Biased estimation for nonorthogonal problems[J]. Technometrics, 1970, 12(1):55-67. DOI:10.1080/00401706.1970.10488634.',
 '[6] BREIMAN L. Random forests[J]. Machine Learning, 2001, 45:5-32. DOI:10.1023/A:1010933404324.',
 '[7] Scikit-learn developers. RandomForestRegressor[EB/OL]. Version 1.9.1[2026-11-05]. https://scikit-learn.org/1.9/modules/generated/sklearn.ensemble.RandomForestRegressor.html.',
 '[8] Scikit-learn developers. Ridge[EB/OL]. Version 1.9.1[2026-11-05]. https://scikit-learn.org/1.9/modules/generated/sklearn.linear_model.Ridge.html.'
]
for ref in references:
    p=para(ref,size=10.5,align=WD_ALIGN_PARAGRAPH.LEFT); p.paragraph_format.first_line_indent=Pt(0); p.paragraph_format.line_spacing=1.15; p.paragraph_format.space_after=Pt(6)

# Keep all original opaque/style/numbering parts byte-for-byte unchanged.
intermediate=OUT/'build.docx'; final=OUT/'医疗费用预测报告.docx'
doc.save(intermediate)
allowed={'word/document.xml','word/_rels/document.xml.rels','[Content_Types].xml','word/styles.xml'}
with ZipFile(TEMPLATE) as original, ZipFile(intermediate) as made, ZipFile(final,'w',ZIP_DEFLATED) as result:
    for name in made.namelist():
        if name=='word/styles.xml':
            # Append only Title; retain all source style definitions as original bytes.
            xml=original.read(name)
            title=b'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="a"/><w:rPr><w:color w:val="000000"/></w:rPr></w:style>'
            result.writestr(name,xml.replace(b'</w:styles>',title+b'</w:styles>'))
        else:
            result.writestr(name,made.read(name) if name in allowed or name not in original.namelist() else original.read(name))
with ZipFile(TEMPLATE) as original,ZipFile(final) as result:
    preserved={name:original.read(name)==result.read(name) for name in original.namelist() if name not in allowed}
    assert all(preserved.values())
assert Document(final).sections[0]._sectPr.xml==Document(TEMPLATE).sections[0]._sectPr.xml
(ROOT/'qa/template-fidelity.json').write_text(json.dumps({'passed':True,'preserved_parts':preserved,'section_geometry_identical':True},ensure_ascii=False,indent=2),encoding='utf-8')
intermediate.unlink()
(OUT/'报告正文.md').write_text('\n\n'.join(x for x in text_archive if x),encoding='utf-8')
dump={'template_sha256':hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
      'result_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RESULT.glob('*.csv')},
      'report_sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'member_info_provided':bool(members)}
(RESULT/'report_provenance.json').write_text(json.dumps(dump,ensure_ascii=False,indent=2),encoding='utf-8')
print(final)
