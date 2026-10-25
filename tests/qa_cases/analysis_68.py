import numpy as np, json
# ideal surface-confined (Langmuir/Nernst) couple, Q=10 uC, E0=-0.05 V, 10 mV/s, + constant double-layer current = 0.5*ip
f=96485.33/(8.314*298.15); v,Q,E0=0.01,1e-5,-0.05
E=np.r_[np.arange(-0.2,0.6,0.0005),np.arange(0.6,-0.2-1e-9,-0.0005)]; t=np.arange(len(E))*0.0005/v
th=1/(1+np.exp(-f*(E-E0))); I=Q*np.gradient(th,t); ip=f*v*Q/4
I+=0.5*ip*np.sign(np.gradient(E,t))
csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(t,E,I))
cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":"electrode_material","scan_rate":{"value":10,"unit":"mV/s"}},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("thin.csv",csv)},data={"config":json.dumps(cfg)}).json(); s=r["selected"]
print("true ip (A):", ip)
print("fwd baseline:", s["forward"]["baseline"]["method"], s["forward"]["baseline"]["note"]); print("ret baseline:", s["return"]["baseline"]["method"], s["return"]["baseline"]["intercept"])
print("heights fwd/ret:", s["forward"]["peaks"][0]["height"], s["return"]["peaks"][0]["height"])
print("pair:", {k:s["pairs"][0][k] for k in ("delta_ep","height_ratio","width_ratio")}, "charge_ratio:", s["charge_ratio"])
print([ (h["id"],h["observations"]) for h in r["hypotheses"] if h["triggered"] and h["id"]!="reference_uncertainty"])