rows=['"time/s","E/V","I/mA"']+[",".join('"%s"'%x.replace(".",",") for x in (f"{a:.4f}",f"{b:.5f}",f"{c:.6g}")) for a,b,c in zip(t,E,I)]
d="\n".join(rows)+"\n"; j=ins(d).json(); s=j["suggested"]
print("columns:", j["table"]["columns"]); print("first row:", j["preview_rows"][0]); print("suggested:", {k:v["column"] for k,v in s.items()})
a=ana(d,cfg(s["potential"]["column"],s["current"]["column"],s["time"]["column"],ui="A")).json()
print("analyze -> cycles:", len(a["cycle_list"]), "| measured scan rate (V/s):", a["scan_rate_measured"])