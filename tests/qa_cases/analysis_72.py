import numpy as np, json
from math import sqrt
F=96485.33; f=F/(8.314*298.15); A,C,D,v,E0=0.0707,1e-6,1e-5,0.1,0.2
E=np.r_[np.arange(-0.1,0.5,0.0005),np.arange(0.5,-0.1-1e-9,-0.0005)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
m=F*A*sqrt(D)*C/(1+np.exp(-f*(E-E0))); w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-1.5)/k
I=np.convolve(m-m[0],w)[:N]/sqrt(h)   # textbook reversible diffusion CV: dEp 58 mV, ipc/ipa 1
csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(t,E,I))
for meta in [{"process_type":"unknown"},{"process_type":"dissolved_species"}]:
    cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":meta,"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
    r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("rev.csv",csv)},data={"config":json.dumps(cfg)}).json()
    print(meta, "notices:", r["notices"], "| triggered:", [(h["id"],h["title"],h["observations"]) for h in r["hypotheses"] if h["triggered"] and h["id"]!="reference_uncertainty"])