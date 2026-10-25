for p,i in [("E/V","E/V"),("E/V","time/s")]:
    r=ana(GOOD,cfg(p,i,"time/s")); print(p, i, "->", r.status_code, [o["text"][:80] for o in r.json()["observations"]][:1])