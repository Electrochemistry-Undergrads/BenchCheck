obs=lambda j:[h["observations"] for h in j["hypotheses"] if h["id"]=="concentration_or_area"]
print("n=0:", obs(analyze({**RS,"electrons_n":0}).json()))
print("c=-1 mM:", obs(analyze({**RS,"analyte_concentration":{"value":-1,"unit":"mM"}}).json()))
print("area=-1 + normalize:", analyze({**RS,"electrode_area_cm2":-1},normalize_by_area=True,normalize_by_area_confirmed=True).json()["notices"])