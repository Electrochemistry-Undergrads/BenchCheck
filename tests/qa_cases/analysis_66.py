import numpy as np, json
# ideal capacitor 100 uF + 50 ohm (tau 5 ms), 50 mV/s, -0.2..0.6 V, 1 cycle, tiny noise. No faradaic process at all.
v,Cdl,tau=0.05,1e-4,0.005
E=np.r_[np.arange(-0.2,0.6,0.001),np.arange(0.6,-0.2-1e-9,-0.001)]; t=np.arange(len(E))*0.001/v; dt=t[1]
s=np.gradient(E,t); I=np.zeros(len(E))
for k in range(1,len(E)): I[k]=I[k-1]+(Cdl*s[k]-I[k-1])*(1-np.exp(-dt/tau))
I+=np.random.default_rng(1).normal(0,2e-8,len(I))
csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.4f},{c:.6e}" for a,b,c in zip(t,E,I))
for pt in ["electrode_material","dissolved_species"]:
    cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":pt,"scan_rate":{"value":50,"unit":"mV/s"}},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
    r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("cap.csv",csv)},data={"config":json.dumps(cfg)}).json()
    s=r["selected"]
    print(pt, "| fwd peaks:", [(p["label"],p["potential"],p["height"],p["near_vertex"]) for p in s["forward"]["peaks"]], "| charge_ratio:", round(s["charge_ratio"],3))
    print("   triggered:", [(h["id"],h["title"],h["observations"]) for h in r["hypotheses"] if h["triggered"] and h["id"]!="reference_uncertainty"])