print(analyze({"ph":"seven"}).json())
print(requests.post(B+"/api/analyze",files={"file":("s.csv",CSV)},data={"config":"{}"}).json())