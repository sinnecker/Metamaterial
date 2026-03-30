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


def plot_monotonic_curve(data_path, save_dir, A0, Lx, Ly, geom_unit="um"):
    """
    Gera a curva de compressão monotônica nominal (stress vs strain).

    Lê a tabela exportada pelo COMSOL com colunas:
        para_disp | F_rx | u_x | sigma_max | v_top | v_bot | Vol

    Calcula:
        strain_nominal = u_x / Lx_m
        stress_nominal = F_rx / A0_m2

    Marca o ponto de falha onde sigma_max ≥ fracture_stress.
    """
    print(f"Gerando curva de compressão monotônica de {data_path}...")

    # Lê os dados — o COMSOL exporta com cabeçalho comentado com '%'
    data = np.loadtxt(data_path, comments='%')

    if data.ndim == 1:
        data = data.reshape(1, -1)

    # O COMSOL exportou:
    # Col 0: Parâmetro da varredura (para_disp)
    # Col 1: F_rx
    # Col 2: u_x
    # Col 3: sigma_max
    # Col 4: v_top
    # Col 5: v_bot
    # Col 6: Vol
    para_disp = data[:, 0]
    F_rx      = data[:, 1]          # força de reação em X (N)
    u_x       = data[:, 2]          # deslocamento prescrito X (m)
    sigma_max = data[:, 3]          # von Mises máxima por passo (Pa)
    v_top     = data[:, 4]          # descolamento no Y_max (m)
    v_bot     = data[:, 5]          # deslocamento no Y_min (m)
    V_sol     = data[:, 6]          # Volume do sólido exato (m³)

    # ------------------------------------------------------------------
    # Conversão de dimensões para o SI (metros) para o cálculo
    # ------------------------------------------------------------------
    if geom_unit == "um":
        Lx_m = Lx * 1e-6
        Ly_m = Ly * 1e-6
        A0_m2 = A0 * 1e-12
    elif geom_unit == "mm":
        Lx_m = Lx * 1e-3
        Ly_m = Ly * 1e-3
        A0_m2 = A0 * 1e-6
    else:
        Lx_m = Lx
        Ly_m = Ly
        A0_m2 = A0

    V_box_m3 = Lx_m * A0_m2  # Lz = A0/Ly -> Volume Bounding Box = Lx * Ly * Lz = Lx * A0

    # Stress e strain nominais calculados coerentemente
    strain = np.abs(u_x) / Lx_m         # adimensional (fração > 0)
    stress = np.abs(F_rx) / A0_m2       # Pa (stress nominal de compressão)

    # ------------------------------------------------------------------
    # CÁLCULOS MACROSCÓPICOS (PROPRIEDADES EFETIVAS)
    # ------------------------------------------------------------------
    # 1. Porosidade
    porosity = 1.0 - (V_sol[0] / V_box_m3)

    # 2. Coeficiente de Poisson Erfetivo
    # Axial strain real (negativo em compressão):
    e_x = - strain 
    # Transversal strain real (positiva se estica em Y, expansão lateral):
    delta_Ly = v_top - v_bot
    e_y = delta_Ly / Ly_m
    
    with np.errstate(divide='ignore', invalid='ignore'):
        nu_array = -e_y / e_x
    
    # Pegamos o valor correspondente ao final ou inicio da zona elástica dependendo da estabilidade.
    # O COMSOL exporta o passo 0 como 0/0=nan. Vamos pegar o índice 2 (primeiro passo confiável estabilizado)
    idx_nu = 2 if len(nu_array) > 2 else 1 if len(nu_array) > 1 else 0
    nu_eq = nu_array[idx_nu]

    # 3. Módulo de Young Efetivo
    # Feito pela regressão na zona puramente elástica inicial (se for muito pequeno strain < 0.05)
    # ou pegando simplesmente os primeiros passos se o max_strain for muito pequeno
    mask_linear = (strain > 0) & (strain < 0.05) if np.max(strain) >= 0.05 else (strain > 0)
    
    if np.sum(mask_linear) >= 2:
        E_eq, _ = np.polyfit(strain[mask_linear], stress[mask_linear], 1)
    else:
        E_eq = stress[1] / strain[1] if len(stress) > 1 else 0.0

    # 4. Stress Levels
    yield_stress = np.max(stress)

    # ------------------------------------------------------------------
    # OUTPUT NO TERMINAL
    # ------------------------------------------------------------------
    print("\n" + "="*50)
    print("      PROPRIEDADES MACROSCÓPICAS DA CÉLULA")
    print("="*50)
    print(f" Porosidade Física (Vazio) : {porosity*100:.2f} %")
    print(f" Módulo de Young Efetivo   : {E_eq / 1e6:.2f} MPa")
    print(f" Coef. de Poisson Efetivo  : {nu_eq:.3f} (em {strain[idx_nu]*100:.2f}% deformação)")
    print(f" Máx Tensão Atingida       : {yield_stress / 1e6:.2f} MPa")
    print("="*50 + "\n")

    # Ponto de falha: maior valor de estresse
    fail_idx  = np.argmax(sigma_max) 
    fracture_stress = sigma_max[fail_idx]

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

    print(f"Curva monotônica (Stress x Strain) exportada para {plot_path}")

    # ------------------------------------------------------------------
    # FIGURA 2: Força vs Deslocamento
    # ------------------------------------------------------------------
    plt.figure(figsize=(7, 5))
    
    # Converter deslocamento (m) para micrômetros (um) para o plot ficar legível
    disp_um = np.abs(u_x) * 1e6
    force_N = np.abs(F_rx)

    plt.plot(disp_um, force_N, 'D-', color='#2A9D8F', linewidth=2, markersize=5, label='Força de Reação')
    
    # Marcação de falha nesse gráfico
    if fail_idx is not None:
        plt.axvline(disp_um[fail_idx], color='crimson', linestyle='--', linewidth=1.5,
                    label=f'Falha ($\delta$ = {disp_um[fail_idx]:.2f} $\mu$m)')
        plt.scatter([disp_um[fail_idx]], [force_N[fail_idx]], color='crimson', s=80, zorder=5)

    plt.xlabel(r"Deslocamento Prescrito $\delta$ [$\mu$m]", fontsize=11)
    plt.ylabel("Força de Reação Global F_rx [N]", fontsize=11)
    plt.title("Força vs Deslocamento", fontsize=12, fontweight='bold')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend()
    
    plot_fd_path = os.path.join(save_dir, "monotonic_force_displacement.png")
    plt.savefig(plot_fd_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Curva Força vs Deslocamento exportada para {plot_fd_path}")

    # ------------------------------------------------------------------
    # RELATÓRIO FINAL
    # ------------------------------------------------------------------
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

        model, data_path, A0, Lx, Ly = apply_physics_monotonic(
            model           = model,
            young_mod       = MATERIAL["E"],
            poisson_ratio   = MATERIAL["nu"],
            density         = MATERIAL["rho"],
            max_strain      = EXPERIMENT["max_strain"],
            min_strain      = EXPERIMENT["min_strain"],
            n_steps         = EXPERIMENT["n_steps"],
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
                Ly              = Ly,
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