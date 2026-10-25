d=GOOD.replace("\n"," # ok\n").replace("I/mA # ok","I/mA")
j=ins(d).json(); print("inspect notes:", j["table"]["notes"], "| suggested:", j["suggested"]["current"]["column"], "| preview:", j["preview_rows"][0])
print("analyze:", ana(d,cfg("E/V","I/mA","time/s")).json())