L=GOOD.splitlines(); L[901]="900.0,1.0,nan"; d="\n".join(L)+"\n"
j=ins(d).json(); print("columns:", j["table"]["columns"], "| n_rows:", j["table"]["n_rows"], "(file has 4800)")
r=ana(d,cfg("E/V","I/mA","time/s")); print("analyze with header names ->", r.status_code, r.json())