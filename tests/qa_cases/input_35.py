for T in [-300,-273.15,1e6]:
    print(T, preview(**{"from":"ag_agcl_3m_kcl","target":"RHE","ph":7,"temperature_c":T}).json()["explanation"])