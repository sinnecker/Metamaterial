# ================================
# GEOMETRIA (forma da célula)
# ================================
GEOMETRY = {
    "H":1,
    "V":1,
    "sy/sx":2,
    "theta": 55,   # graus
    "widht/sx": 0.3,
    "thickness/sx": 0.3,
    "fillet": 0.1,
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
    "force": "TotalForce",#("ForceArea", "ForceDefArea", "TotalForce", "FollowerPressure", "Resultant")
    "force_value": [300,0,0]
}

# ================================
# EXPERIMENTO
# ================================
EXPERIMENT = {
    "type": "stiffness",      # "stiffness" ou "cyclic" ou "normal"
    "force": 1, #compresion ou expassion
    # --- Compressão Monotônica ---
    "max_strain":      0.7,  # deformação máxima em X (fração, ex: 0.30 = 30%)
    "min_strain":      0.3,  # deformação mínima em X (fração, ex: 0.30 = 30%)
    "n_steps":         100,    # número de passos da varredura paramétrica
    "displacement":    0.1, #displacement em X
    "NonLinear": False,
    "cuda": False,
    "output_plot": False,
}

# ================================
# OUTPUT
# ================================
PATHS = {
    "dxf": "outputs/dxf/unit_cell.dxf",
    "mph": "outputs/mph/model.mph"
}