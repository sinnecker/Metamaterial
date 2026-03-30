# ================================
# GEOMETRIA (forma da célula)
# ================================
GEOMETRY = {
    "H":1,
    "V":1,
    "h": 3,
    "l": 2.5,
    "theta": 20,   # graus
    "e": 1
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
    "extrude": 1,
    "fillet": 0.2,
    "force": ["300", "0", "0"]
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