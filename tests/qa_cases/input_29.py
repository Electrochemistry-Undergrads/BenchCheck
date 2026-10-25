# Section setup: reversible 2-cycle CV, 50 mV/s, with a time column; RS = complete Randles–Ševčík metadata
import json, numpy as np
B = "http://127.0.0.1:8000"
E=np.r_[np.linspace(0,.8,401),np.linspace(.8,0,401)]; up=np.arange(802)<401
I=np.where(up,1e-3*np.exp(-((E-.45)/.04)**2),-1e-3*np.exp(-((E-.39)/.04)**2))
E,I=np.tile(E,2),np.tile(I,2); t=np.arange(E.size)*0.04
CSV="time/s,Ewe/V,I/A\n"+"\n".join(f"{a:.3f},{b:.4f},{c:.4e}" for a,b,c in zip(t,E,I))
def analyze(meta, **cfg): return requests.post(B+"/api/analyze",files={"file":("s.csv",CSV)},data={"config":json.dumps({"mapping":{"potential":"Ewe/V","current":"I/A","time":"time/s"},"metadata":meta,**cfg})})
preview=lambda **kw: requests.post(B+"/api/conversion-preview",json=kw)
RS={"process_type":"dissolved_species","analyte_concentration":{"value":1,"unit":"mM"},"electrode_area_cm2":0.07,"diffusion_coefficient_cm2_s":1e-5,"electrons_n":1,"scan_rate":{"value":50,"unit":"mV/s"}}