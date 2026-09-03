from Gridgen import generate_dxf
from COMSOL import build_geometry, create_physics_disp, create_physics_force, create_solver_iterative
from config import GEOMETRY, SCALE, MATERIAL, SIMULATION

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import mph
import time

# Inicia o cliente (usa o binário em /usr/local/bin/comsol automaticamente)
client = mph.start()

BASE_DIR = "newdataset"
DXF_DIR  = os.path.join(BASE_DIR, "dxf_g1")
MPH_DIR  = os.path.join(BASE_DIR, "mph_g1")

os.makedirs(DXF_DIR,   exist_ok=True)
os.makedirs(MPH_DIR,   exist_ok=True)


def main():

    dxf_path = os.path.join(DXF_DIR, "unit_cell.dxf")
    mph_path = os.path.join(MPH_DIR, "model.mph")

    # ---------------------------
    # Parâmetros
    # ---------------------------
    H = GEOMETRY["H"]
    V = GEOMETRY["V"]
    scale = SCALE["scale"]
    l = GEOMETRY["sx"] * scale
    h = GEOMETRY["sy/sx"] * l
    theta = GEOMETRY["theta"]
    e = GEOMETRY["widht/sx"] * l
    unit = SCALE["unit"]
    extrude = GEOMETRY["extrude/sx"] * l
    fillet = GEOMETRY["fillet/sx"] * l
    array = GEOMETRY["array"]
    young_mod = MATERIAL["E"]
    poisson_ratio = MATERIAL["nu"]
    density = MATERIAL["rho"]
    axis = SIMULATION["axis"]
    BC = SIMULATION["BC"]
    disp = SIMULATION["disp"]
    force_value = SIMULATION["force_value"]
    NonLinear = SIMULATION["NonLinear"]
    maxiter = SIMULATION["maxiter"]

    t1 = time.time()
    # ---------------------------
    # 1. Gerar DXF
    # ---------------------------
    generate_dxf(h, l, theta, e, dxf_path)

    # ---------------------------
    # 2. Construir Geometria 3D
    # ---------------------------
    model = build_geometry(client, H, V, h, l, theta, e, extrude, fillet, unit, dxf_path, mph_path, array)

    # ---------------------------
    # 3. Física e Simulação
    # ---------------------------
    if BC == "force":
        model = create_physics_force(model, e, h, unit, young_mod, poisson_ratio, density, axis, mph_path)
        model = create_solver_iterative(model, BC, force_value, NonLinear, maxiter, mph_path)
    elif BC == "disp":
        model = create_physics_disp(model, e, h, unit, young_mod, poisson_ratio, density, axis, mph_path)
        model = create_solver_iterative(model, BC, disp, NonLinear, maxiter, mph_path)

    model.java.sol("sol1").runAll()
    t2 = time.time()

    p_vec = model.evaluate("poisson")
    ep_x= model.evaluate("ep_x")
    ep_y = model.evaluate("ep_y")
    Von_mises = model.evaluate("solid.misesGp")

    client.remove(model)
    client.clear()
    print(f"Tempo total: {t2 - t1} segundos")
    print(f"Poisson: {p_vec}")
    print(f"Deformação X: {ep_x}")
    print(f"Deformação Y: {ep_y}")
    print(f"Von Mises max: {np.max(Von_mises)}")
if __name__ == "__main__":
    main()