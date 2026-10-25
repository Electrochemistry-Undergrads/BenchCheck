print("inspect:", ins(GOOD).json()["suggested"]["current"])
a=ana(GOOD,json.dumps({"mapping":{"potential":"E/V","current":"I/mA"}})).json(); print("analyze:", a["processing"][0]["detail"])