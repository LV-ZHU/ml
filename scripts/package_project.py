"""Package deliverables, including results and provenance, excluding local environments and previews."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
qa_keep={'artifact.md','kaggle-view.json','kaggle-list.json','public-insurance.csv','public-readme.md',
         'template-parts.json','template-style.json','template-fidelity.json','report-style.json','delivery_qa.json'}
top={'执行计划.md','工作记录.md','README.md','config.json','requirements.txt','requirements-report.txt','member_info.json','run_all.ps1'}
folders={'src','scripts','assets','data','报告','results','results_reproduced'}
files=[]
for p in sorted(ROOT.rglob('*')):
    if not p.is_file(): continue
    rel=p.relative_to(ROOT)
    if '__pycache__' in rel.parts or 'matplotlib_cache' in rel.parts: continue
    if rel.parts[0]=='qa':
        if len(rel.parts)!=2 or p.name not in qa_keep: continue
    elif rel.parts[0] not in folders and rel.as_posix() not in top: continue
    if rel.parts[0]=='results_reproduced' and 'models' in rel.parts: continue
    files.append(p)
manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
manifest_path=ROOT/'交付文件校验.json'
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
archive=ROOT/'回归作业_姓名待填_学号待填.zip'
with ZipFile(archive,'w',ZIP_DEFLATED,compresslevel=6) as z:
    for p in files+[manifest_path]: z.write(p,'医疗费用预测/'+p.relative_to(ROOT).as_posix())
with ZipFile(archive) as z:
    assert z.testzip() is None
    for rel,digest in manifest.items(): assert hashlib.sha256(z.read('医疗费用预测/'+rel)).hexdigest()==digest
print(json.dumps({'archive':str(archive),'files':len(files)+1,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
