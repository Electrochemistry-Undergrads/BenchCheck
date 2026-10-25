import numpy as np, json
# quasi-reversible n=2 couple (Butler-Volmer, k0=0.01 cm/s, alpha 0.5): dEp ~48 mV vs 29.6 mV reversible for n=2
F,R,T=96485.33,8.314,298.15; n=2; fn=n*F/(R*T); A,C,D,v,E0,k0,a=0.0707,1e-6,1e-5,0.1,0.2,0.01,0.5
E=np.r_[np.arange(-0.3,0.7,0.0005),np.arange(0.7,-0.3-1e-9,-0.0005)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-0.5)/k
w*=np.sqrt(h); K=n*F*A*np.sqrt(D); I=np.zeros(N)
for j in range(1,N):
    H=w[1:j+1]@I[j-1::-1]; kf=k0*np.exp((1-a)*fn*(E[j]-E0)); kb=k0*np.exp(-a*fn*(E[j]-E0))
    I[j]=(n*F*A*kf*C-n*F*A*(kf+kb)/K*H)/(1+n*F*A*(kf+kb)/K*w[0])
csv="t,E,I\n"+"\n".join(f"{x:.6f},{y:.5f},{z:.6e}" for x,y,z in zip(t,E,I))
cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":"dissolved_species","scan_rate":{"value":100,"unit":"mV/s"},"electrons_n":2},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("n2.csv",csv)},data={"config":json.dumps(cfg)}).json()
kl=[h for h in r["hypotheses"] if h["id"]=="kinetic_limitation"][0]
print("dEp:", r["selected"]["pairs"][0]["delta_ep"], "| kinetic_limitation:", kl["triggered"], "|", kl["trigger_rule"], "|", kl["not_triggered_reason"])