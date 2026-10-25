import numpy as np, json
F,R,T=96485.33,8.314,298.15; f=F/(R*T); A,C,D,v,E0,kc=0.0707,1e-6,1e-5,0.1,0.2,1000.0
E=np.r_[np.arange(-0.2,0.6,0.0005),np.arange(0.6,-0.2-1e-9,-0.0005)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-0.5)/k
w*=np.sqrt(h); wo=w*np.exp(-kc*h*np.arange(N)); K=F*A*np.sqrt(D); I=np.zeros(N)
for j in range(1,N):  # R -> O + e (Nernstian), O -> inactive (k=1000/s); semi-integral solution
    hr=w[1:j+1]@I[j-1::-1]; ho=wo[1:j+1]@I[j-1::-1]; th=np.exp(f*(E[j]-E0))
    I[j]=(th*(K*C-hr)-ho)/(w[0]*(1+th))
csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(t,E,I))
cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":"dissolved_species","scan_rate":{"value":100,"unit":"mV/s"}},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("ec.csv",csv)},data={"config":json.dumps(cfg)}).json()
print("current at return sweep start / last 30 mV (A):", I[N//2], I[-61::20])
print("return vertex:", r["selected"]["return"]["vertex"])
for h in r["hypotheses"]:
    if h["triggered"]: print(h["id"], h["observations"])