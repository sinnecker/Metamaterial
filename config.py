# ================================
# GEOMETRIA (forma da célula)
# ================================
GEOMETRY = {
    "H":3,
    "V":1,
    "h": 3.0,
    "l": 1.5,
    "theta": 40,   # graus
    "e": 0.4
}

# ================================
# ESCALA FÍSICA
# ================================
SCALE = {
    "scale": 1.0,
    "unit": "um"
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
    "force": 300
}

# ================================
# OUTPUT
# ================================
PATHS = {
    "dxf": "outputs/dxf/unit_cell.dxf",
    "mph": "outputs/mph/model.mph"
}