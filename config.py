# ================================
# GEOMETRIA (forma da célula)
# ================================
GEOMETRY = {
    "H":2,
    "V":2,
    "h": 2,
    "l": 1,
    "theta": 110,   # graus
    "e": 0.2
}

# ================================
# ESCALA FÍSICA
# ================================
SCALE = {
    "scale": 1.0,
    "unit": "mm"
}

# ================================
# MATERIAL
# ================================
MATERIAL = {
    "E": 1.124e12,     # Young (Pa)
    "nu": 0.28,      # Poisson
    "rho": 2329     # densidade
}

# ================================
# COMSOL / SIMULAÇÃO
# ================================
SIMULATION = {
    "extrude": 0.1,
    "fillet": 0.2,
    "force": "TotalForce",#("ForceArea", "ForceDefArea", "TotalForce", "FollowerPressure", "Resultant")
    "force_value": [300,0,0]
}

# ================================
# OUTPUT
# ================================
PATHS = {
    "dxf": "outputs/dxf/unit_cell.dxf",
    "mph": "outputs/mph/model.mph"
}