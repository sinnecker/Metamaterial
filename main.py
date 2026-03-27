from Gridgen import generate_dxf
from COMSOL import comsol_model_unitcell
from config import GEOMETRY, SCALE, MATERIAL, SIMULATION, PATHS

import os

def main():

    os.makedirs("outputs/dxf", exist_ok=True)
    os.makedirs("outputs/mph", exist_ok=True)

    # ---------------------------
    # juntar parâmetros
    # ---------------------------
    scale = SCALE["scale"]
    h = GEOMETRY["h"]*scale
    l = GEOMETRY["l"]*scale
    theta = GEOMETRY["theta"]
    e = GEOMETRY["e"]*scale

    unit = SCALE["unit"]

    # ---------------------------
    # 1. gerar geometria
    # ---------------------------
    generate_dxf(
        h=h,
        l=l,
        theta=theta,
        e=e,
        filename=PATHS["dxf"]
    )

    # ---------------------------
    # 2. rodar COMSOL
    # ---------------------------
    model = comsol_model_unitcell(
        H=GEOMETRY["H"],
        V=GEOMETRY["V"],
        h=h,
        l=l,
        theta=theta,
        e=e,
        young_mod=MATERIAL["E"],
        poisson_ratio=MATERIAL["nu"],
        density=MATERIAL["rho"],
        extrude=SIMULATION["extrude"],
        fillet=SIMULATION["fillet"],
        metric=unit,
        geom_path=PATHS["dxf"],
        file_path=PATHS["mph"],
        array=True
    )

    print("Modelo salvo em:", PATHS["mph"])

    return model


if __name__ == "__main__":
    main()