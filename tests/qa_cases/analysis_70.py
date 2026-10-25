import numpy as np, json
from math import sqrt
# reversible Nernstian diffusion CV (semi-integral solution), E0=0.20 V, 100 mV/s; switching 300 mV past E0, end vertex 250 mV below E0
F=96485.33; A,C,D,v,E0=0.0707,1e-6,1e-5,0.1,0.2
def run(lo,T=25.0):
    f=F/(8.314*(T+273.15))
    E=np.r_[np.arange(lo,0.5,0.0005),np.arange(0.5,lo-1e-9,-0.0005)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
    m=F*A*sqrt(D)*C/(1+np.exp(-f*(E-E0))); w=np.ones(N)
    for k in range(1,N): w[k]=w[k-1]*(k-1.5)/k
    I=np.convolve(m-m[0],w)[:N]/sqrt(h)   # semi-derivative
    csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(t,E,I))
    cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":"auto","selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":"dissolved_species","scan_rate":{"value":100,"unit":"mV/s"},"temperature_c":T},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
    r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("rev.csv",csv)},data={"config":json.dumps(cfg)}).json(); s=r["selected"]
    c=s["return"]["peaks"][0]; tr=[h for h in r["hypotheses"] if h["id"]=="truncated_return"][0]
    print(f"window {lo}..0.5 V, {T} C: C1 at {c['potential']:.4f} V (distance to end vertex {c['potential']-lo:.3f} V), width_v={c['width_v']}, near_vertex={c['near_vertex']}, dEp={s['pairs'][0]['delta_ep']*1000:.0f} mV -> truncated_return={tr['triggered']} {tr['observations']}")
run(-0.10); run(-0.05); run(0.0); run(-0.10,T=60.0)