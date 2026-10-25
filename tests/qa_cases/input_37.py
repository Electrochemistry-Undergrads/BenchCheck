print(preview(**{"from":"she","target":"RHE","ph":100}).json()["explanation"])
ps=analyze({"reference_electrode":"ag_agcl_3m_kcl","ph":100},reference_conversion={"target":"RHE","confirmed":True}).json()
print({k:ps[k] for k in ("notices",)}, ps["potential_scale"])