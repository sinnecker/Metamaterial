from Gridgen import generate_dxf
from COMSOL import build_geometry, apply_physics_compression, apply_physics_monotonic
from config import GEOMETRY, SCALE, MATERIAL, SIMULATION, EXPERIMENT, PATHS

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


# ============================================================
# Plot helpers
# ============================================================

def plot_stress_strain(data_path, save_dir):
    """Curva nodal stress-strain (modo legado — compressão estática única)."""
    print(f"Gerando gráfico Stress x Strain empírico de {data_path}...")
    data = np.loadtxt(data_path, comments='%')

    stress = data[:, 6]
    strain = data[:, 8]

    plt.figure(figsize=(8, 6))
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


def plot_monotonic_curve(data_path, save_dir, A0, Lx, fracture_stress, geom_unit="um"):
    """
    Gera a curva de compressão monotônica nominal (stress vs strain).

    Lê a tabela exportada pelo COMSOL com colunas:
        para_disp | F_rx | u_x | sigma_max

    Calcula:
        strain_nominal = u_x / Lx_m
        stress_nominal = F_rx / A0_m2

    Marca o ponto de falha onde sigma_max ≥ fracture_stress.
    """
    print(f"Gerando curva de compressão monotônica de {data_path}...")

    # Lê os dados — o COMSOL exporta com cabeçalho comentado com '%'
    data = np.loadtxt(data_path, comments='%')

    # Colunas: [para_disp_value, F_rx, u_x, sigma_max]
    # (a primeira coluna é o índice paramétrico; o mapeamento depende do COMSOL)
    # Assumindo exportação colunar: col0=param_val, col1=F_rx, col2=u_x, col3=sigma_max
    if data.ndim == 1:
        data = data.reshape(1, -1)

    u_x       = data[:, 0]          # deslocamento prescrito (unidade da geometria)
    F_rx      = data[:, 1]          # força de reação em X (N, sinal negativo = compressão)
    sigma_max = data[:, 2]          # von Mises máxima por passo (Pa)

    # ------------------------------------------------------------------
    # Conversão de dimensões para o SI (metros) para o cálculo
    # (Pois F_rx vem em N, u_x em m, e precisamos de área em m² e compr em m)
    # ------------------------------------------------------------------
    if geom_unit == "um":
        Lx_m = Lx * 1e-6
        A0_m2 = A0 * 1e-12
    elif geom_unit == "mm":
        Lx_m = Lx * 1e-3
        A0_m2 = A0 * 1e-6
    else:
        Lx_m = Lx
        A0_m2 = A0

    # Stress e strain nominais calculados coerentemente
    strain = np.abs(u_x) / Lx_m         # adimensional (fração)
    stress = np.abs(F_rx) / A0_m2       # Pa (stress nominal de compressão)

    # Ponto de falha: primeiro passo onde sigma_max ≥ fracture_stress
    fail_mask = sigma_max >= fracture_stress
    fail_idx  = np.argmax(fail_mask) if fail_mask.any() else None

    # ------------------------------------------------------------------
    # Figura
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Compressão Monotônica — Metamaterial Auxético", fontsize=13, fontweight='bold')

    # Painel 1: Curva Stress × Strain nominal
    ax1 = axes[0]
    ax1.plot(strain * 100, stress / 1e6, 'o-', color='#2E86AB', linewidth=2,
             markersize=5, label='Stress nominal')

    if fail_idx is not None:
        ax1.axvline(strain[fail_idx] * 100, color='crimson', linestyle='--',
                    linewidth=1.5, label=f'Falha (ε = {strain[fail_idx]*100:.1f}%)')
        ax1.scatter([strain[fail_idx] * 100], [stress[fail_idx] / 1e6],
                    color='crimson', s=80, zorder=5)

    ax1.set_xlabel("Deformação Nominal ε [%]",   fontsize=11)
    ax1.set_ylabel("Tensão Nominal σ [MPa]",      fontsize=11)
    ax1.set_title("Curva Stress × Strain",        fontsize=11)
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend()

    # Painel 2: Tensão de von Mises máxima × Strain (critério de falha)
    ax2 = axes[1]
    ax2.plot(strain * 100, sigma_max / 1e9, 's-', color='#E76F51', linewidth=2,
             markersize=5, label='σ_max (von Mises)')
    ax2.axhline(fracture_stress / 1e9, color='crimson', linestyle='--',
                linewidth=1.5, label=f'Limite de fratura ({fracture_stress/1e9:.1f} GPa)')

    if fail_idx is not None:
        ax2.scatter([strain[fail_idx] * 100], [sigma_max[fail_idx] / 1e9],
                    color='crimson', s=80, zorder=5, label=f'Falha detectada')

    ax2.set_xlabel("Deformação Nominal ε [%]",          fontsize=11)
    ax2.set_ylabel("Tensão de von Mises Máxima [GPa]",  fontsize=11)
    ax2.set_title("Critério de Falha (von Mises max)",  fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend()
    ax2.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.2f'))

    plt.tight_layout()
    plot_path = os.path.join(save_dir, "monotonic_stress_strain.png")
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Curva monotônica exportada para {plot_path}")
    if fail_idx is not None:
        print(f"  → Falha detectada no passo {fail_idx+1}: "
              f"ε = {strain[fail_idx]*100:.1f}%, σ_max = {sigma_max[fail_idx]/1e9:.3f} GPa")
    else:
        print("  → Nenhum ponto de falha detectado dentro do range simulado.")


# ============================================================
# main
# ============================================================

def main():

    os.makedirs("outputs/dxf",   exist_ok=True)
    os.makedirs("outputs/mph",   exist_ok=True)
    os.makedirs("outputs/plots", exist_ok=True)

    # ---------------------------
    # Parâmetros de geometria
    # ---------------------------
    scale = SCALE["scale"]
    h     = GEOMETRY["h"] * scale
    l     = GEOMETRY["l"] * scale
    theta = GEOMETRY["theta"]
    e     = GEOMETRY["e"] * scale
    unit  = SCALE["unit"]

    exp_type = EXPERIMENT["type"]

    # ---------------------------
    # 1. Gerar DXF
    # ---------------------------
    generate_dxf(h=h, l=l, theta=theta, e=e, filename=PATHS["dxf"])

    # ---------------------------
    # 2. Construir Geometria 3D
    # ---------------------------
    model = build_geometry(
        H        = GEOMETRY["H"],
        V        = GEOMETRY["V"],
        h        = h,
        l        = l,
        theta    = theta,
        e        = e,
        extrude  = SIMULATION["extrude"],
        fillet   = SIMULATION["fillet"],
        metric   = unit,
        geom_path= PATHS["dxf"],
        array    = True,
    )

    # ---------------------------
    # 3. Física e Simulação
    # ---------------------------
    if exp_type == "monotonic":
        print(f"[Experimento] Compressão Monotônica — strain máx.: {EXPERIMENT['max_strain']:.0%}, "
              f"{EXPERIMENT['n_steps']} passos")

        model, data_path, A0, Lx = apply_physics_monotonic(
            model           = model,
            young_mod       = MATERIAL["E"],
            poisson_ratio   = MATERIAL["nu"],
            density         = MATERIAL["rho"],
            max_strain      = EXPERIMENT["max_strain"],
            n_steps         = EXPERIMENT["n_steps"],
            fracture_stress = EXPERIMENT["fracture_stress"],
            force           = EXPERIMENT["force"],
            NonLinear       = EXPERIMENT["NonLinear"],
            file_path       = PATHS["mph"],
        )

        print(f"Simulação concluída. Modelo salvo em: {PATHS['mph']}")

        # ---------------------------
        # 4. Pós-processamento
        # ---------------------------
        if os.path.exists(data_path):
            plot_monotonic_curve(
                data_path       = data_path,
                save_dir        = "outputs/plots",
                A0              = A0,
                Lx              = Lx,
                fracture_stress = EXPERIMENT["fracture_stress"],
                geom_unit       = unit
            )

    else:
        # Modo legado: compressão estática com força fixa
        print("[Experimento] Compressão estática (força fixa)")
        model = apply_physics_compression(
            model         = model,
            young_mod     = MATERIAL["E"],
            poisson_ratio = MATERIAL["nu"],
            density       = MATERIAL["rho"],
            force         = SIMULATION["force"],
            file_path     = PATHS["mph"],
        )

        print("Modelo salvo em:", PATHS["mph"])

        data_path = PATHS["mph"].replace(".mph", "_data.txt")
        if os.path.exists(data_path):
            plot_stress_strain(data_path, "outputs/plots")

    return model


if __name__ == "__main__":
    main()