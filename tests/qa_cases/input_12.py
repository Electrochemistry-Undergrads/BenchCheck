t2,E2,I2=cv(step=0.002,rate=0.01)   # true 10 mV/s
hdr=["EXPLAIN","TAG\tCV","CURVE1\tTABLE","\tPt\tT\tVf\tIm\tVu\tSig\tAch\tIERange\tOver","\t#\ts\tV vs. Ref.\tA\tV\tV\tV\t#\tbits"]
rows=[f"\t{k}\t{a:.4f}\t{b:.5E}\t{c/1000:.5E}\t0\t{b:.5E}\t0\t9\t..." for k,(a,b,c) in enumerate(zip(t2,E2,I2))]
d="\n".join(hdr+rows)+"\n"; j=ins(d,"cv.DTA").json(); s=j["suggested"]
print("suggested:", {k:v["column"] for k,v in s.items()}, "| row:", j["preview_rows"][1][:4])
print("measured scan rate (V/s):", ana(d,cfg(s["potential"]["column"],s["current"]["column"],s["time"]["column"],ui="A"),"cv.DTA").json()["scan_rate_measured"], "(true 0.010)")