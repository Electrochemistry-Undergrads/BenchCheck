# Section setup: a clean 3-cycle simulated CV in mA (true peak A1 at 0.82 V, 0.5 mA)
import json, numpy as np
B = "http://127.0.0.1:8000"
def cv(n_cyc=3, lo=0.3, hi=1.1, step=0.001, rate=0.001):
    up=np.arange(lo,hi,step); one=np.r_[up, up[::-1]+step]
    E=np.tile(one,n_cyc); sgn=np.tile(np.r_[np.ones(len(up)),-np.ones(len(up))],n_cyc)
    I=0.04*sgn+sgn*0.5*np.exp(-((E-0.8-0.02*sgn)/0.03)**2)
    t=np.arange(len(E))*step/rate; return t,E,I
def cfg(p,i,t,up="V",ui="mA",ut="s"):
    return json.dumps({"mapping":{"potential":p,"current":i,"time":t},"units":{"potential":up,"current":ui,"time":ut},
      "current_convention":"iupac","forward_direction":"auto","selected_cycle":None,
      "processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{},
      "reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False})
ins=lambda d,n="x.csv": requests.post(B+"/api/inspect",files={"file":(n,d)})
ana=lambda d,c,n="x.csv": requests.post(B+"/api/analyze",files={"file":(n,d)},data={"config":c})
t,E,I=cv(); GOOD="time/s,E/V,I/mA\n"+"\n".join(f"{a:.4f},{b:.5f},{c:.6g}" for a,b,c in zip(t,E,I))+"\n"
print("GOOD:", len(GOOD.splitlines())-1, "rows")