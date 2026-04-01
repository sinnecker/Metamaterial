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
    "extrude": 1,
    "fillet": 0.2,
    "force": "TotalForce",#("ForceArea", "ForceDefArea", "TotalForce", "FollowerPressure", "Resultant")
    "force_value": [300,0,0]
}

# ================================
# EXPERIMENTO
# ================================
EXPERIMENT = {
    "type": "monotonic",      # "monotonic" ou "cyclic"
    "force": 1, #compresion ou expassion
    # --- Compressão Monotônica ---
    "max_strain":      0.6,  # deformação máxima em X (fração, ex: 0.30 = 30%)
    "min_strain":      0.45,  # deformação mínima em X (fração, ex: 0.30 = 30%)
    "n_steps":         100,    # número de passos da varredura paramétrica
    "NonLinear": True,
}

# ================================
# OUTPUT
# ================================
PATHS = {
    "dxf": "outputs/dxf/unit_cell.dxf",
    "mph": "outputs/mph/model.mph"
}