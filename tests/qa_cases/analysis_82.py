import numpy as np, json
# totally irreversible ET (k0=1e-7 cm/s): wave starts but no peak inside -0.4..0.8 V
F,R,T=96485.33,8.314,298.15; f=F/(R*T); A,C,D,v,E0,k0,a=0.0707,1e-6,1e-5,0.1,0.2,1e-7,0.5
E=np.r_[np.arange(-0.4,0.8,0.001),np.arange(0.8,-0.4-1e-9,-0.001)]; h=0.001/v; t=np.arange(len(E))*h; N=len(E)
w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-0.5)/k
w*=np.sqrt(h); K=F*A*np.sqrt(D); I=np.zeros(N)
for j in range(1,N):
    H=w[1:j+1]@I[j-1::-1]; kf=k0*np.exp((1-a)*f*(E[j]-E0)); kb=k0*np.exp(-a*f*(E[j]-E0))
    I[j]=(F*A*kf*C-F*A*(kf+kb)/K*H)/(1+F*A*(kf+kb)/K*w[0])
csv="t,E,I\n"+"\n".join(f"{x:.6f},{y:.4f},{z:.6e}" for x,y,z in zip(t,E,I))
cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":"dissolved_species","scan_rate":{"value":100,"unit":"mV/s"}},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("irr.csv",csv)},data={"config":json.dumps(cfg)}).json()
print("fwd peaks:", r["selected"]["forward"]["peaks"], "ret peaks:", r["selected"]["return"]["peaks"])
for h in r["hypotheses"]:
    if h["id"] in ("side_reaction_vertex","ec_chemical_step"): print(h["id"], h["triggered"], h["observations"], h["not_triggered_reason"])