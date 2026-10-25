for unit in ["uM","bananas"]:
    j=analyze({**RS,"analyte_concentration":{"value":1000 if unit=="uM" else 1,"unit":unit}}).json()
    print(unit, [h["observations"] for h in j["hypotheses"] if h["id"]=="concentration_or_area"])