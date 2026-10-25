for k,v in [("temperature_c",-273.15),("temperature_c",-300),("electrons_n",-2),("diffusion_coefficient_cm2_s",-1e-5)]:
    r=analyze({**RS,k:v}); print(f"{k}={v}: ->", r.status_code, r.text[:80])