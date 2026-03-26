# ================================
# GEOMETRIA (forma da célula)
# ================================
GEOMETRY = {
    "h": 2.0,
    "l": 1.2,
    "theta": 30,   # graus
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
    "E": 200e9,     # Young (Pa)
    "nu": 0.3,      # Poisson
    "rho": 7800     # densidade
}

# ================================
# COMSOL / SIMULAÇÃO
# ================================
SIMULATION = {
    "extrude": 0.4,
    "fillet": 0.1,
    "force": 300
}

# ================================
# OUTPUT
# ================================
PATHS = {
    "dxf": "outputs/dxf/unit_cell.dxf",
    "mph": "outputs/mph/model.mph"
}