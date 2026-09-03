# ================================
# GEOMETRIA (forma da célula)
# ================================
GEOMETRY = {
    "array": False,
    "H":1,
    "V":1,
    "sx": 1,
    "sy/sx":1.2,
    "theta": 60,   # graus
    "widht/sx": 0.1,
    "extrude/sx": 5,
    "fillet/sx": 0,
}

# ================================
# ESCALA FÍSICA
# ================================
SCALE = {
    "scale": 10, 
    "unit": "um"
}

# ================================
# MATERIAL
# ================================
MATERIAL = {
    "E": 170e9,     # Young (Pa)
    "nu": 0.28,      # Poisson
    "rho": 2329     # densidade
}

# ================================
# COMSOL / SIMULAÇÃO
# ================================
SIMULATION = {
    "BC": 'force', # 'disp' ou 'force'
    "force_value": 500,
    "maxiter": 100,
    "disp":0.005, #porcentagem de displacement
    "axis":"x",
    "NonLinear": False,
}


