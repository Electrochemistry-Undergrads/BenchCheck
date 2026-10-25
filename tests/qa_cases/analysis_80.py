import numpy as np, json
from math import sqrt
F=96485.33; f=F/(8.314*298.15); A,C,D,v,E0=0.0707,1e-6,1e-5,0.1,0.2
E=np.r_[np.arange(-0.1,0.5,0.0005),np.arange(0.5,-0.1-1e-9,-0.0005)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
m=F*A*sqrt(D)*C/(1+np.exp(-f*(E-E0))); w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-1.5)/k
I=np.convolve(m-m[0],w)[:N]/sqrt(h)
def go(tcol, meta, ref=None, title=""):
    csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(tcol,E,I))
    cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":dict({"process_type":"dissolved_species"},**meta),"reference_conversion":ref,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
    return requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("x.csv",csv)},data={"config":json.dumps(cfg)}).json()
rs={"analyte_concentration":{"value":1,"unit":"mM"},"electrode_area_cm2":A,"diffusion_coefficient_cm2_s":D,"electrons_n":1}
# (a) 1000x scan-rate mismatch worded as "100% difference"; (b) time column actually ms -> RS hypothesis blames concentration/area
r=go(t,{"scan_rate":{"value":100,"unit":"V/s"}}); print("(a)",[q["message"] for q in r["quality"] if q["code"]=="scan_rate_mismatch"])
r=go(t*1000,dict(scan_rate={"value":100,"unit":"mV/s"},**rs)); print("(b)",[q["message"] for q in r["quality"] if q["code"]=="scan_rate_mismatch"], r["selected"]["forward"]["charge"], [h["observations"] for h in r["hypotheses"] if h["id"]=="concentration_or_area"])
# (c) 10 s gap in the time column right after the vertex (no samples) -> silently integrated
t2=t.copy(); t2[N//2+1:]+=10; r=go(t2,{"scan_rate":{"value":100,"unit":"mV/s"}}); s=r["selected"]
print("(c) charges", s["forward"]["charge"], s["return"]["charge"], "ratio", s["charge_ratio"], "quality", [q["code"] for q in r["quality"]])
# (d) custom offset: description becomes the scale name and replaces the 'cannot verify' caveat
r=go(t,{"scan_rate":{"value":100,"unit":"mV/s"},"reference_electrode":"ag_agcl_3m_kcl"},{"target":"custom","offset_v":0.1,"description":"measured vs master Ag/AgCl","confirmed":True})
print("(d)", r["potential_scale"]["label"], r["potential_scale"]["caveats"])
print("    preview:", requests.post("http://127.0.0.1:8000/api/conversion-preview",json={"from":"ag_agcl_3m_kcl","target":"custom","offset_v":0.1,"description":"measured vs master Ag/AgCl"}).json())