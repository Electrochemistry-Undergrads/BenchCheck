d="Time,Potential,Current\n"+"\n".join(f"{a:.1f},{b*1000:.1f},{c*1000:.2f}" for a,b,c in zip(t,E,I))+"\n"
print("suggested units:", {k:v["unit"] for k,v in ins(d).json()["suggested"].items()})
a=ana(d,cfg("Potential","Current","Time",up="V",ui="A")).json(); print(a["observations"][1]["text"], "| notices:", a["notices"])