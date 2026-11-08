"""Predict from six input columns using a saved frozen pipeline."""
import argparse
from pathlib import Path
import sys
import joblib
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--model',default='results/models/M3T.joblib')
    a=p.parse_args(); data=pd.read_csv(a.input)
    cols=['age','bmi','children','sex','smoker','region']
    if not set(cols).issubset(data): raise ValueError('CSV must include: '+','.join(cols))
    if data[cols].isna().any().any(): raise ValueError('Missing input: resolve field meanings before prediction')
    model=joblib.load(a.model)
    result=data.copy(); result['predicted_charges']=model.predict(data[cols]); result.to_csv(a.output,index=False)

if __name__=='__main__': main()
