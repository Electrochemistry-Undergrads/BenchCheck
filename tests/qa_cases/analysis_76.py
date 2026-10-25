import numpy as np, json
# EC mechanism (as in r1) but scan STARTS at 0.0 V (e.g. OCP) going POSITIVE: 0->0.6->-0.2->0.6->-0.2->0.0
F,R,T=96485.33,8.314,298.15; f=F/(R*T); A,C,D,v,E0,kc=0.0707,1e-6,1e-5,0.1,0.2,1000.0
up=lambda a,b: np.arange(a,b,0.0005); dn=lambda a,b: np.arange(a,b,-0.0005)
E=np.r_[up(0,0.6),dn(0.6,-0.2),up(-0.2,0.6),dn(0.6,-0.2),up(-0.2,0.0+1e-9)]; h=0.0005/v; t=np.arange(len(E))*h; N=len(E)
w=np.ones(N)
for k in range(1,N): w[k]=w[k-1]*(k-0.5)/k
w*=np.sqrt(h); wo=w*np.exp(-kc*h*np.arange(N)); K=F*A*np.sqrt(D); I=np.zeros(N)
for j in range(1,N):
    hr=w[1:j+1]@I[j-1::-1]; ho=wo[1:j+1]@I[j-1::-1]; th=np.exp(f*(E[j]-E0)); I[j]=(th*(K*C-hr)-ho)/(w[0]*(1+th))
csv="t,E,I\n"+"\n".join(f"{a:.6f},{b:.5f},{c:.6e}" for a,b,c in zip(t,E,I))
for fd in ["auto","positive"]:
    cfg={"mapping":{"potential":"E","current":"I","time":"t"},"units":{"potential":"V","current":"A","time":"s"},"current_convention":"iupac","forward_direction":fd,"selected_cycle":None,"processing":{"smoothing_mv":10,"baseline":"flat_prewave"},"metadata":{"process_type":"dissolved_species","scan_rate":{"value":100,"unit":"mV/s"}},"reference_conversion":None,"normalize_by_area":False,"normalize_by_area_confirmed":False,"example_id":None}
    r=requests.post("http://127.0.0.1:8000/api/analyze",files={"file":("ocp.csv",csv)},data={"config":json.dumps(cfg)}).json(); s=r["selected"]
    print(f"forward_direction={fd}: detected forward={s['forward']['direction_label']}; fwd peaks={[p['label'] for p in s['forward']['peaks']]} ret peaks={[p['label'] for p in s['return']['peaks']]}; quality={[q['code'] for q in r['quality']]}")
    print("   triggered:", [(h["id"],h["observations"]) for h in r["hypotheses"] if h["triggered"] and h["id"]!="reference_uncertainty"])