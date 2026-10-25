ctx={"metadata":{"electrode_material":"LiMn2O4"}}
for s in [{}, {"title":None,"link":None,"snippet":None}, {"source_id":"a","title":123,"snippet":["x"],"link":5}]:
    r=requests.post(B+"/api/evidence/select",json={"sources":[s],"context":ctx}); print(s, "->", r.status_code, r.text)