from Gridgen import generate_dxf
from COMSOL import build_geometry, apply_physics_compression
from config import GEOMETRY, SCALE, MATERIAL, SIMULATION, PATHS

import os
import numpy as np
import matplotlib.pyplot as plt

def plot_stress_strain(data_path, save_dir):
    print(f"Gerando gráfico Stress x Strain empírico de {data_path}...")
    # Lendo o arquivo numérico do COMSOL (descartando os cabeçalhos literais com '%')
    data = np.loadtxt(data_path, comments='%')
    
    # O COMSOL exporta as coordenadas de referência [X, Y, Z] por padrão nas colunas 0, 1 e 2.
    # Nossas expressões ["x", "y", "z", "solid.mises", "solid.disp", "solid.edeve"] começam no índice 3.
    # Portanto a estrutura é: [X, Y, Z, x, y, z, solid.mises, solid.disp, solid.edeve]
    stress = data[:, 6]
    strain = data[:, 8]
    
    plt.figure(figsize=(8, 6))
    # Scatter plot mostrando as variações nodais num único degrau de carga
    plt.scatter(strain, stress, c=stress, cmap='viridis', marker='.', s=2, alpha=0.6)
    
    plt.title("Curva de Estresse x Deformação (Distribuição Nodal)")
    plt.xlabel("Deformação Equivalente (solid.edeve)")
    plt.ylabel("Tensão de von Mises (Pa)")
    plt.grid(True, linestyle='--', alpha=0.7)
    
    cbar = plt.colorbar()
    cbar.set_label("Tensão (Pa)")
    
    plot_path = os.path.join(save_dir, "stress_strain_curve.png")
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Gráfico exportado com sucesso para {plot_path}")

def main():

    os.makedirs("outputs/dxf", exist_ok=True)
    os.makedirs("outputs/mph", exist_ok=True)
    os.makedirs("outputs/plots", exist_ok=True)

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
    # 2. Construir Geometria
    # ---------------------------
    model = build_geometry(
        H=GEOMETRY["H"],
        V=GEOMETRY["V"],
        h=h,
        l=l,
        theta=theta,
        e=e,
        extrude=SIMULATION["extrude"],
        fillet=SIMULATION["fillet"],
        metric=unit,
        geom_path=PATHS["dxf"],
        array=True
    )

    # ---------------------------
    # 3. Aplicar Física e Simular (Compressão Simples)
    # ---------------------------
    model = apply_physics_compression(
        model=model,
        young_mod=MATERIAL["E"],
        poisson_ratio=MATERIAL["nu"],
        density=MATERIAL["rho"],
        file_path=PATHS["mph"]
    )

    print("Modelo salvo em:", PATHS["mph"])
    print("Gráficos nativos do COMSOL (Estresse e Deslocamento) salvos em outputs/plots/")
    print("Dados para o gráfico Stress x Strain numéricos extraídos em outputs/mph/model_data.txt")

    # ---------------------------
    # 4. Gerar Curva Stress x Strain
    # ---------------------------
    data_path = PATHS["mph"].replace(".mph", "_data.txt")
    if os.path.exists(data_path):
        plot_stress_strain(data_path, "outputs/plots")

    return model


if __name__ == "__main__":
    main()