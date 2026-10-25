a=analyze({"electrode_material":"<img src=x onerror=alert(1)>"}).json(); a.pop("data")
mdx=requests.post(B+"/api/report",json={"analysis":a,"evidence":{"sources":[{"title":"t","link":"javascript:alert(1)","passages":[]}]}}).json()["markdown"]
print([l for l in mdx.splitlines() if "onerror" in l or "javascript" in l])