d=GOOD.replace("-","−").encode()
print("inspect:", {k:ins(d).json()["table"][k] for k in ("n_rows","malformed_rows","notes")})
a=ana(d,cfg("E/V","I/mA","time/s")).json()
print("analyze: rows_used", a["rows_used"], "rows_excluded", a["rows_excluded"], "notices", a["notices"], "quality", [q["code"] for q in a["quality"]])