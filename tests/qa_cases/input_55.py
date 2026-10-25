a=analyze({}).json(); a.pop("data"); a["selected"]["pairs"][0]["delta_ep"]=0.5
mdx=requests.post(B+"/api/report",json={"analysis":a,"evidence":{}}).json()["markdown"]
print([l.strip()[:120] for l in mdx.splitlines() if "ΔEp" in l][:4])
print(requests.post(B+"/api/report",json={"analysis":{}}).status_code)