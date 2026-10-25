import numpy as np, json
from math import sqrt
F=96485.33; f=F/(8.314*298.15); A,C,D,v,E0=0.0707,1e-6,1e-5,0.1,0.2
E=np.r_[np.arange(-0.1,0.5,0.0005),np.arange(0.5,-0.1-1e-9,-0.0005)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
m=F*A*sqrt(D)*C/(1+np.exp(-f*(E-E0))); w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-1.5)/k
I=np.convolve(m-m[0],w)[:N]/sqrt(h) + np.random.default_rng(3).normal(0,1e-6,N)   # ip=19 uA, white noise sigma=1 uA
csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(t,E,I))
for sm in [0,5]:
    cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":sm,"baseline":"flat_prewave"},"metadata":{"process_type":"dissolved_species","scan_rate":{"value":100,"unit":"mV/s"}},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
    r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("noisy.csv",csv)},data={"config":json.dumps(cfg)}).json(); s=r["selected"]
    print(f"smoothing_mv={sm}: noise_sigma={r['noise_sigma']:.3g} fwd peaks={[(p['label'],p['potential']) for p in s['forward']['peaks']]} ret peaks={[(p['label'],p['potential']) for p in s['return']['peaks']]}")
    print("   triggered:", [(h["id"],h["observations"]) for h in r["hypotheses"] if h["triggered"] and h["id"]!="reference_uncertainty"])