import numpy as np
import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PolyCollection  
from shapely.geometry import Polygon
from shapely.ops import unary_union
import ezdxf


def auxetic_cell(h=1.0, l=1.0, theta_deg=30, plot=False):
    '''
    Gera os vértices de uma célula unitária auxética re-entrante
    h: altura da célula unitária
    l: comprimento da haste lateral
    theta_deg: ângulo de inclinação da haste (graus)
    '''
    theta = np.radians(theta_deg)

    dx = l * np.sin(theta)  # deslocamento horizontal da haste
    dy = l * np.cos(theta)  # deslocamento vertical da haste

    # Vértices do hexágono re-entrante (anti-horário, fechado)
    points = [
        (dx,   h - dy),   # cintura superior (ponto de re-entrada)
        (2*dx, h),         # canto superior direito
        (2*dx, 0),         # canto inferior direito
        (dx,   dy),        # cintura inferior (ponto de re-entrada)
        (0,    0),         # canto inferior esquerdo
        (0,    h),         # canto superior esquerdo
        (dx,   h - dy),   # fecha o polígono no ponto inicial
    ]

    if plot:
        x_coords, y_coords = zip(*points)
        plt.figure(figsize=(6, 6))
        plt.plot(x_coords, y_coords, 'bo-', linewidth=2, markersize=8)
        plt.fill(x_coords, y_coords, alpha=0.3, color='skyblue')
        plt.axhline(0, color='black', linewidth=0.5, linestyle='--')
        plt.axvline(0, color='black', linewidth=0.5, linestyle='--')
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.title(f'Célula Auxética (h={h}, l={l}, θ={theta_deg}°)')
        plt.show()

    return points


def grid_gen(h, l, theta, e):
    '''
    Gera os polígonos da célula unitária repetível (com células de borda) para construção do padrão auxético em DXF
    e: espessura da célula
    '''
    theta_rad = np.radians(theta)
    alpha = np.pi / 2 - theta_rad  # ângulo complementar

    dx = l * np.sin(theta_rad)  # deslocamento horizontal da haste
    dy = l * np.cos(theta_rad)  # deslocamento vertical da haste

    # Espaço de parede entre fileiras (vertical) e entre colunas (horizontal)
    de = e * np.tan(alpha) / 2 + e / np.sin(theta_rad)  # gap vertical entre fileiras
    dz = 2 * h - 2 * dy                                  # altura livre dentro de uma coluna

    # Calcula a célula unitária base
    unit_cell = auxetic_cell(h, l, theta)

    # Deslocamento horizontal das células intercaladas (meio passo)
    dx_shift = dx + e / 2  # deslocamento horizontal para as meias células

    all_polygons1 = []  # célula principal
    all_polygons2 = []  # meia célula intercalada à direita
    all_polygons3 = []  # meia célula intercalada à esquerda

    # Loop sobre as duas fileiras de meias células (acima e abaixo da fileira principal)
    for j in range(2):
        z = j * (dz + 2 * de)   # deslocamento vertical acumulado

        # Somente j=0 gera a célula principal (poly1)
        valid_row = (j < 1)

        new_poly1 = [] if valid_row else None
        new_poly2 = []
        new_poly3 = []

        # Deslocamento vertical da meia célula intercalada nesta iteração
        base_y_shift = z - h + dy - de

        if theta_rad>np.pi/2:
            for k,(x, y) in enumerate(unit_cell):
                if valid_row:
                    new_poly1.append((x, y))
                
                if k==0 or k==6:
                    new_poly3.append((x - dx_shift-e*np.sin(theta_rad), y + base_y_shift -e*np.cos(theta_rad)))
                    new_poly2.append((x + dx_shift+e*np.sin(theta_rad), y + base_y_shift -e*np.cos(theta_rad)))
                elif k==3:
                    new_poly3.append((x - dx_shift-e*np.sin(theta_rad), y + base_y_shift +e*np.cos(theta_rad)))
                    new_poly2.append((x + dx_shift+e*np.sin(theta_rad), y + base_y_shift +e*np.cos(theta_rad)))
                else:
                    new_poly3.append((x - dx_shift, y+ base_y_shift))
                    new_poly2.append((x + dx_shift, y+ base_y_shift))
        
        else:
            for (x, y) in unit_cell:
                if valid_row:
                    new_poly1.append((x, y))
                new_poly3.append((x - dx_shift, y+ base_y_shift))
                new_poly2.append((x + dx_shift, y+ base_y_shift))
            
        if new_poly1:
            all_polygons1.append(new_poly1)

        all_polygons2.append(new_poly2)
        all_polygons3.append(new_poly3)

    # Bounding box da unidade de repetição (dH x dV)

    xmin = min(pt[0] for pt in all_polygons1[0])   
    xmax = max(pt[0] for pt in all_polygons1[0]) 
    ymin = all_polygons3[0][1][1] - h / 2
    ymax = all_polygons3[1][4][1] + h / 2

    # Adiciona a espessura de parede ao contorno
    ytol = e*1e-3
    bbox = [
        (xmin - e, ymin-ytol),
        (xmin - e, ymax+ytol),
        (xmax + e, ymax+ytol),
        (xmax + e, ymin-ytol),
    ]

    return all_polygons1, all_polygons2, all_polygons3, bbox

def add_polygon(poly, doc):
    msp = doc.modelspace()
    exterior = list(poly.exterior.coords)
    msp.add_lwpolyline(exterior, close=True, dxfattribs={'layer': 'EXTERIOR'})

    for hole in poly.interiors:
        msp.add_lwpolyline(list(hole.coords), close=True, dxfattribs={'layer': 'HOLES'})

def export_void_to_dxf(polygons, cell_polygon, filename='void_mesh.dxf'):
    '''
    Exporta o negativo (vazios = material sólido) da malha auxética para DXF
    '''
    # Cria objetos Shapely e filtra geometrias inválidas
    poly_objs = []
    for p in polygons:
        poly = Polygon(p)
        if poly.is_valid and not poly.is_empty:
            poly_objs.append(poly)
        else:
            # Tenta corrigir com buffer(0)
            fixed = poly.buffer(0)
            if not fixed.is_empty:
                poly_objs.append(fixed)

    # União de todos os furos
    solid = unary_union(poly_objs)

    # Bounding box da unidade de repetição
    cell = Polygon(cell_polygon)

    # Subtrai os furos do bounding box → obtém o material sólido
    void = cell.difference(solid)

    # Cria o arquivo DXF
    doc = ezdxf.new()

    if void.geom_type == 'Polygon':
        add_polygon(void, doc)
    elif void.geom_type == 'MultiPolygon':
        for p in void.geoms:
            add_polygon(p, doc)

    doc.saveas(filename)
    return void


def generate_dxf(h, l, theta, e, filename='unit_cell.dxf'):
    '''
    Função principal: gera a geometria DXF da célula unitária auxética
    '''
    poly1, poly2, poly3, bbox = grid_gen(h, l, theta, e)

    # Junta TODOS os polígonos (esses são os 'buracos' hexagonais)
    all_polygons = poly1 + poly2 + poly3

    # Exporta via subtração booleana
    void = export_void_to_dxf(all_polygons, bbox, filename)

    return {
        'void': void,
        'bbox': bbox,
        'poly1': poly1,
        'poly2': poly2,
        'poly3': poly3,
    }


def preview_geometry(h, l, theta, e, save_path=None):
    """
    Preview da geometria gerada (útil para depuração antes de rodar COMSOL).
    
    Args:
        e, h, l, theta: parâmetros da célula
        save_path      : se fornecido, salva o plot em PNG
    """
    result = generate_dxf(h, l, theta, e, filename="/tmp/_preview_cell.dxf")
    void = result["void"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"Preview da Geometria Auxética (h={h}, l={l}, θ={theta}°, e={e})", fontsize=13)

    # --- Painel esquerdo: polígonos crus (células + bbox) ---
    ax1 = axes[0]
    ax1.set_title("Células unitárias + Bounding Box")
    ax1.set_aspect("equal")
    ax1.grid(True, linestyle=":", alpha=0.5)

    poly1, poly2, poly3, bbox = grid_gen(h, l, theta, e)

    colors = ["#4C72B0", "#DD8452", "#55A868"]
    labels = ["Célula principal (poly1)", "Meia célula direita (poly2)", "Meia célula esquerda (poly3)"]
    for polygons, color, label in zip([poly1, poly2, poly3], colors, labels):
        for pts in polygons:
            xs, ys = zip(*pts)
            ax1.fill(xs, ys, alpha=0.35, color=color)
            ax1.plot(xs, ys, color=color, linewidth=1.2)
        ax1.plot([], [], color=color, linewidth=2, label=label)

    # Bounding box
    bx, by = zip(*bbox + [bbox[0]])
    ax1.plot(bx, by, "k--", linewidth=1.5, label="Bounding Box")
    ax1.legend(fontsize=8, loc="upper right")

    # --- Painel direito: geometria final (material sólido) ---
    ax2 = axes[1]
    ax2.set_title("Geometria Final (Material Sólido = Negativo dos Furos)")
    ax2.set_aspect("equal")
    ax2.grid(True, linestyle=":", alpha=0.5)

    def plot_shapely(ax, geom, fc="#2E86AB", ec="#1a5276", alpha=0.75):
        if geom.geom_type == "Polygon":
            xs, ys = geom.exterior.xy
            ax.fill(xs, ys, fc=fc, ec=ec, alpha=alpha, linewidth=1)
            for hole in geom.interiors:
                hx, hy = hole.xy
                ax.fill(hx, hy, fc="white", ec=ec, linewidth=0.8)
        elif geom.geom_type == "MultiPolygon":
            for p in geom.geoms:
                plot_shapely(ax, p, fc, ec, alpha)

    plot_shapely(ax2, void)
    patch = mpatches.Patch(color="#2E86AB", label="Material sólido")
    ax2.legend(handles=[patch], fontsize=9)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Preview salvo em: {save_path}")

    plt.show()