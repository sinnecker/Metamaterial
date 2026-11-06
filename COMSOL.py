import os
import re
import sys
import csv
import math
import json
import datetime
import traceback

import numpy as np

import config as cfg
import Gridgen


# Conversões de unidade
UNIT_TO_UM = {"nm": 1e-3, "um": 1.0, "mm": 1e3, "m": 1e6}
COMSOL_UNIT = {"nm": "nm", "um": "\u00b5m", "mm": "mm", "m": "m"}

# Configuração do bloco de carga (opcional: configs antigos não têm a seção)
LOAD_BLOCK = getattr(cfg, "LOAD_BLOCK", {})


# =====================================================================
# 1) PARÂMETROS
# =====================================================================

def cell_dimensions(geometry=cfg.GEOMETRY, scale=cfg.SCALE):
    """Converte o GEOMETRY do config nas dimensões da célula (unidade do modelo)."""
    s = scale["scale"]
    sx = geometry["sx"] * s
    theta = geometry["theta"]
    return {
        "h": geometry["sy/sx"] * sx,
        "l": sx,
        "theta": theta,
        "e": geometry["widht/sx"] * sx,
        "extrude": geometry["extrude/sx"] * sx,
        "fillet": geometry["fillet/sx"] * sx,
        "H": geometry["H"] if geometry["array"] else 1,
        "V": geometry["V"] if geometry["array"] else 1,
        "array": bool(geometry["array"]),
    }


def metamaterial_info(cell):
    """
    Usa o Gridgen para obter o bounding box da célula e o passo do array
    (mesmas fórmulas de dH e dV do COMSOL.py original).
    """
    h, l, theta, e = cell["h"], cell["l"], cell["theta"], cell["e"]
    _, _, _, bbox = Gridgen.grid_gen(h, l, theta, e)
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]

    th = np.radians(theta)
    dx, dy = l * np.sin(th), l * np.cos(th)
    alpha = np.pi / 2 - th
    de = e * np.tan(alpha) / 2 + e / np.sin(th)
    dz = 2 * h - 2 * dy
    dV = dz + 2 * de
    dH = 2 * dx + e

    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W_cell = (x1 - x0) + (cell["H"] - 1) * dH   # largura no referencial da célula
    H_cell = (y1 - y0) + (cell["V"] - 1) * dV   # altura  no referencial da célula

    info = {
        "cell_x0": x0, "cell_y0": y0,          # canto do bbox antes da rotação
        "cell_w": x1 - x0, "cell_h": y1 - y0,
        "dH": dH, "dV": dV,
        "W_cell": W_cell, "H_cell": H_cell,
        "bbox": bbox,
        "load_dir": load_direction(),
    }
    # W_meta/H_meta/meta_x0/meta_y0 = footprint no referencial GLOBAL (após rotação)
    if info["load_dir"] == "x":
        # rotação de +90° em torno da origem: (x, y) -> (-y, x)
        info.update(meta_x0=-(y0 + H_cell), meta_y0=x0, W_meta=H_cell, H_meta=W_cell)
    else:
        info.update(meta_x0=x0, meta_y0=y0, W_meta=W_cell, H_meta=H_cell)
    return info
    
def load_direction(exp=cfg.EXPERIMENT):
    d = str(exp.get("load_dir", "y")).lower()
    if d not in ("x", "y"):
        raise ValueError(f"load_dir deve ser 'x' ou 'y', recebido: {d}")
    return d


def actuator_expressions(cell, meta, act=cfg.ACTUATOR, scale=cfg.SCALE):
    """
    Lista ordenada (nome, expressão, descrição) dos parâmetros globais.
    As expressões são válidas tanto no COMSOL quanto em Python (sem unidades,
    comprimentos na unidade do modelo, ângulos em graus), então a mesma lista
    alimenta o model.param() e o preview/CSV.
    """
    u2um = UNIT_TO_UM[scale["unit"]]
    ref = lambda key: act[key] / u2um  # valor de referência (µm) -> unidade do modelo

    if act["scale_mode"] == "auto":
        s_act = act["shutter_to_meta_width"] * meta["W_meta"] / (2 * ref("B_0_ref"))
    else:
        s_act = act["manual_scale"]

    tol = 1e-3 * min(cell["e"], ref("b_sink_ref") * s_act, ref("b_0_ref") * s_act)

    return [
        # --- escala e espessura ---
        ("s_act", f"{s_act:.12g}", "fator de escala do atuador"),
        ("h_0", f"{cell['extrude']:.12g}", "espessura do dispositivo (extrusão)"),
        ("tol", f"{tol:.6g}", "tolerância das seleções"),
        # --- metamaterial (valores do Gridgen) ---
        ("W_meta", f"{meta['W_meta']:.12g}", "largura do metamaterial"),
        ("H_meta", f"{meta['H_meta']:.12g}", "altura do metamaterial"),
        ("meta_x0", f"{meta['meta_x0']:.12g}", "x mínimo da célula no DXF"),
        ("meta_y0", f"{meta['meta_y0']:.12g}", "y mínimo da célula no DXF"),
        # --- vigas (chevron) ---
        ("theta_0", f"{act['theta_beam']:.12g}", "inclinação da viga (graus)"),
        ("N_beam", f"{int(act['N_beam'])}", "nº de vigas"),
        ("L_0", f"{ref('L_0_ref'):.12g}*s_act", "comprimento da viga"),
        ("b_0", f"{ref('b_0_ref'):.12g}*s_act", "largura da viga"),
        ("B_0", f"{ref('B_0_ref'):.12g}*s_act", "largura da base/pads"),
        ("delta_array", f"{act['beam_pitch/b_0']:.12g}*b_0", "passo entre vigas"),
        ("L_base", "N_beam*delta_array", "comprimento dos pads/shutter"),
        ("x_shutter", "L_0*cos(theta_0*pi/180)-b_0*sin(theta_0*pi/180)", "x do shutter"),
        ("y_shutter", "L_0*sin(theta_0*pi/180)-B_0/2", "y do shutter"),
        ("x_mirror", "x_shutter+B_0", "eixo de simetria do atuador"),
        # --- dissipador ---
        ("N_sink", f"{int(act['N_sink'])}", "nº de aletas"),
        ("L_sink", f"{ref('L_sink_ref'):.12g}*s_act", "comprimento das aletas"),
        ("b_sink", f"{ref('b_sink_ref'):.12g}*s_act", "largura das aletas"),
        ("delta_sink", f"{act['sink_pitch/b_sink']:.12g}*b_sink", "passo entre aletas"),
        ("L_sink_shutter", "N_sink*delta_sink", "comprimento do shutter do dissipador"),
        ("y_sink_shutter", "y_shutter+L_base", "y do shutter do dissipador"),
        ("x_sink", "x_shutter-L_sink", "x das aletas"),
        ("y_sink", f"y_sink_shutter+{act['sink_offset/b_sink']:.12g}*b_sink", "y da 1a aleta"),
        ("x_pad_sink", "x_sink-B_0", "x do pad do dissipador"),
        ("y_top_sink", "y_sink_shutter+L_sink_shutter", "topo do atuador"),
        # --- ligação ---
        ("g_link", f"{ref('link_gap_ref'):.12g}*s_act", "comprimento da haste"),
        ("w_link", f"{act['link_width/shutter']:.12g}*2*B_0", "largura da haste"),
        ("t_plate", f"{ref('plate_thickness_ref'):.12g}*s_act", "espessura da placa"),
        # --- posição do metamaterial ---
        ("x_meta", "x_mirror-W_meta/2", "x inicial do metamaterial"),
        ("y_meta", "y_top_sink+g_link+t_plate", "y inicial do metamaterial"),
        # --- bloco de fixação no topo ---
        ("t_block", f"{ref('block_thickness_ref'):.12g}*s_act", "espessura do bloco do topo"),
        ("w_block", f"{act['block_width/meta']:.12g}*W_meta", "largura do bloco do topo"),
        ("x_block", "x_mirror-w_block/2", "x inicial do bloco"),
        ("y_block", "y_meta+H_meta", "y inicial do bloco"),
    ]


def evaluate_expressions(expressions):
    """Avalia a lista de expressões em Python (mesma sintaxe do COMSOL)."""
    ns = {"cos": math.cos, "sin": math.sin, "tan": math.tan,
          "sqrt": math.sqrt, "pi": math.pi, "exp": math.exp}
    values = {}
    for name, expr, _ in expressions:
        values[name] = float(eval(expr.replace("^", "**"), {"__builtins__": {}}, {**ns, **values}))
    return values


def experiment_currents(p, exp=cfg.EXPERIMENT, scale=cfg.SCALE):
    """Lista de correntes (mA) da varredura."""
    if exp["current_mode"] == "absolute":
        return sorted(float(i) for i in exp["I_list"])
    act = cfg.ACTUATOR
    h_um = p["h_0"] * UNIT_TO_UM[scale["unit"]]
    b_um = p["b_0"] * UNIT_TO_UM[scale["unit"]]
    L_um = p["L_0"] * UNIT_TO_UM[scale["unit"]]
    ratio = (b_um * h_um / L_um) / (act["b_0_ref"] * exp["h_ref"] / act["L_0_ref"])
    I_nom = exp["I_ref"] * ratio
    return sorted(float(f) * I_nom for f in exp["I_factors"])


def check_feature_sizes(cell, p):
    """Avisa quando o atuador escalado tem detalhes muito menores que o metamaterial."""
    e = cell["e"]
    for name in ("b_0", "b_sink"):
        if p[name] < 0.5 * e:
            print(f"[aviso] {name} = {p[name]:.4g} < 0.5*e ({0.5*e:.4g}). "
                  f"A malha pode ficar pesada; considere shutter_to_meta_width maior "
                  f"ou array=True com mais células.")


# =====================================================================
# 2) PREVIEW 2D (sem COMSOL)
# =====================================================================

def actuator_polygons(p):
    """Reproduz em shapely a geometria do atuador (mesma lógica do build no COMSOL)."""
    from shapely.geometry import Polygon, box
    from shapely.affinity import scale as sh_scale

    th = math.radians(p["theta_0"])
    c, s = math.cos(th), math.sin(th)
    L, b = p["L_0"], p["b_0"]

    half = []
    for k in range(int(p["N_beam"])):
        dy = k * p["delta_array"]
        half.append(Polygon([(0, dy), (L * c, L * s + dy),
                             (L * c - b * s, L * s + b * c + dy), (-b * s, b * c + dy)]))
    half.append(box(-p["B_0"], -p["B_0"] / 2, 0, -p["B_0"] / 2 + p["L_base"]))  # pad atuador
    half.append(box(p["x_shutter"], p["y_shutter"],
                    p["x_shutter"] + p["B_0"], p["y_shutter"] + p["L_base"]))  # shutter
    half.append(box(p["x_shutter"], p["y_sink_shutter"],
                    p["x_shutter"] + p["B_0"], p["y_top_sink"]))              # shutter dissipador
    for k in range(int(p["N_sink"])):
        y = p["y_sink"] + k * p["delta_sink"]
        half.append(box(p["x_sink"], y, p["x_sink"] + p["L_sink"], y + p["b_sink"]))  # aletas
    half.append(box(p["x_pad_sink"], p["y_sink_shutter"],
                    p["x_pad_sink"] + p["B_0"], p["y_top_sink"]))             # pad dissipador

    mirrored = [sh_scale(g, xfact=-1, yfact=1, origin=(p["x_mirror"], 0)) for g in half]
    parts = half + mirrored
    if p["g_link"] > 0:
        parts.append(box(p["x_mirror"] - p["w_link"] / 2, p["y_top_sink"],
                         p["x_mirror"] + p["w_link"] / 2, p["y_top_sink"] + p["g_link"]))
    if p["t_plate"] > 0:
        y = p["y_top_sink"] + p["g_link"]
        parts.append(box(p["x_meta"], y, p["x_meta"] + p["W_meta"], y + p["t_plate"]))
    return parts


def metamaterial_polygon(cell, meta, p):
    """Metamaterial (void do Gridgen) replicado e posicionado sobre o atuador."""
    from shapely.ops import unary_union
    from shapely.affinity import translate

    res = Gridgen.generate_dxf(cell["h"], cell["l"], cell["theta"], cell["e"],
                               filename=os.path.join(_tmp_dir(), "_preview_cell.dxf"))
    void = res["void"]
    copies = [translate(void, i * meta["dH"], j * meta["dV"])
              for i in range(cell["H"]) for j in range(cell["V"])]
    meta_poly = unary_union(copies)
    return translate(meta_poly, p["x_meta"] - meta["meta_x0"], p["y_meta"] - meta["meta_y0"])


def preview_layout(cell, meta, p, save_path=None, show=False):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.ops import unary_union

    from shapely.geometry import box as sh_box
    act = unary_union(actuator_polygons(p))
    mm = metamaterial_polygon(cell, meta, p)
    blk = None
    if cfg.EXPERIMENT["top_bc"] == "block":
        blk = sh_box(p["x_block"], p["y_block"], p["x_block"] + p["w_block"],
                     p["y_block"] + p["t_block"])

    def draw(ax, geom, fc, ec):
        geoms = geom.geoms if hasattr(geom, "geoms") else [geom]
        for g in geoms:
            x, y = g.exterior.xy
            ax.fill(x, y, fc=fc, ec=ec, lw=0.6)
            for hole in g.interiors:
                hx, hy = hole.xy
                ax.fill(hx, hy, fc="white", ec=ec, lw=0.5)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax in axes:
        draw(ax, act, "#9fb7d6", "#2c4a6e")
        draw(ax, mm, "#e8a87c", "#8a4b1f")
        if blk is not None:
            draw(ax, blk, "#8fbf8f", "#2e6b2e")
        ax.set_aspect("equal")
        ax.grid(True, ls=":", alpha=0.5)
    axes[0].set_title(f"Layout completo (s_act = {p['s_act']:.4g})")
    # zoom na região do metamaterial
    m = 0.6 * max(p["W_meta"], p["H_meta"])
    axes[1].set_xlim(p["x_meta"] - m, p["x_meta"] + p["W_meta"] + m)
    top = p["y_meta"] + p["H_meta"] + (p["t_block"] if blk is not None else 0)
    axes[1].set_ylim(p["y_meta"] - p["g_link"] - p["t_plate"] - m, top + m)
    axes[1].set_title("Zoom: ligação atuador -> metamaterial")
    unit = cfg.SCALE["unit"]
    for ax in axes:
        ax.set_xlabel(f"x [{unit}]")
        ax.set_ylabel(f"y [{unit}]")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Preview salvo em: {save_path}")
    if show:
        plt.show()
    plt.close(fig)


def _tmp_dir():
    d = os.path.join(cfg.OUTPUT["folder"], "_tmp")
    os.makedirs(d, exist_ok=True)
    return d


# =====================================================================
# 3) GEOMETRIA NO COMSOL
# =====================================================================

def _wp_objects(wp, fallback):
    """
    Nomes dos objetos que existem no work plane neste ponto da sequência.
    O nome de saída nem sempre é o tag da última feature (o Fillet com
    'pointinsketch', por exemplo, mantém o nome do objeto de entrada), então
    as features seguintes selecionam pelos objetos reais. Como o metamaterial
    é construído primeiro, só há objetos dele aqui.
    """
    try:
        names = [str(n) for n in wp.objectNames()]
        if names:
            return names
    except Exception:
        pass
    return [fallback]


def build_metamaterial(wp, cell, meta, dxf_path):
    """
    Metamaterial no work plane: mesma sequência do COMSOL.py original
    (Import DXF -> Difference -> Fillet -> Array -> Union) + Move até o atuador.
    Deve vir ANTES do atuador na sequência, para que as box selections do fillet
    (em coordenadas originais da célula) não peguem pontos do atuador.
    """
    h, l, theta, e = cell["h"], cell["l"], np.radians(cell["theta"]), cell["e"]

    wp.create("imp_meta", "Import")
    wp.feature("imp_meta").set("filename", dxf_path)
    wp.feature("imp_meta").set("alllayers", ["EXTERIOR", "HOLES"])
    wp.feature("imp_meta").set("repairgeom", False)
    wp.feature("imp_meta").set("selindividual", False)
    wp.run("imp_meta")

    wp.create("dif_meta", "Difference")
    wp.feature("dif_meta").selection("input").set("imp_meta(1)")
    wp.feature("dif_meta").selection("input2").set("imp_meta(2)")
    wp.run("dif_meta")
    last = "dif_meta"


    if cell["array"] and (cell["H"] > 1 or cell["V"] > 1):
        wp.create("arr_meta", "Array")
        wp.feature("arr_meta").selection("input").set(*_wp_objects(wp, last))
        wp.feature("arr_meta").set("displ", [str(meta["dH"]), str(meta["dV"])])
        wp.feature("arr_meta").set("fullsize", [str(cell["H"]), str(cell["V"])])
        wp.run("arr_meta")
        wp.create("uni_meta", "Union")
        wp.feature("uni_meta").selection("input").set("arr_meta")
        wp.feature("uni_meta").set("intbnd", False)
        wp.run("uni_meta")
        last = "uni_meta"

    if cell["fillet"] > 0:
        xmin, ymin = meta["cell_x0"], meta["cell_y0"]
        xmax, ymax = xmin + meta["W_cell"], ymin + meta["H_cell"]

        print(xmin,xmax,ymin,ymax)
        eps = 1e-3 * cell["e"]
    
        wp.create("bbox_fil1", "BoxSelection")
        wp.feature("bbox_fil1").set("entitydim", "0")
        wp.feature("bbox_fil1").set("xmin", xmin + eps)
        wp.feature("bbox_fil1").set("xmax", xmax - eps)
        wp.feature("bbox_fil1").set("ymin", ymin + eps)
        wp.feature("bbox_fil1").set("ymax", ymax - eps)
    
        wp.create("fil_meta", "Fillet")
        wp.feature("fil_meta").selection("pointinsketch").named("bbox_fil1")
        wp.feature("fil_meta").set("radius", cell["fillet"])
        wp.run("fil_meta")
        last = "fil_meta"
        
    
    # Rotação de 90° no plano (tensionamento na direção x da célula)
    if meta["load_dir"] == "x":
        wp.create("rot_meta", "Rotate")
        wp.feature("rot_meta").selection("input").set(*_wp_objects(wp, last))
        wp.feature("rot_meta").set("rot", "90")
        wp.feature("rot_meta").set("pos", ["0", "0"])
        wp.run("rot_meta")
        last = "rot_meta"

    wp.create("mov_meta", "Move")
    wp.feature("mov_meta").selection("input").set(*_wp_objects(wp, last))
    wp.feature("mov_meta").set("displx", "x_meta-meta_x0")
    wp.feature("mov_meta").set("disply", "y_meta-meta_y0")
    wp.run("mov_meta")
    return "mov_meta"


def build_actuator(wp, p):
    """Atuador chevron do thermal_auxetic.java (estado final), todo parametrizado."""
    # Viga inclinada + array
    wp.create("beam", "Rectangle")
    wp.feature("beam").label("tilted_beam")
    wp.feature("beam").set("size", ["L_0", "b_0"])
    wp.feature("beam").set("rot", "theta_0")
    wp.create("arr_beam", "Array")
    wp.feature("arr_beam").selection("input").set("beam")
    wp.feature("arr_beam").set("type", "linear")
    wp.feature("arr_beam").set("linearsize", "N_beam")
    wp.feature("arr_beam").set("displ", ["0", "delta_array"])

    # Pad do atuador
    wp.create("pad_act", "Rectangle")
    wp.feature("pad_act").label("Actuator_pads")
    wp.feature("pad_act").set("size", ["B_0", "L_base"])
    wp.feature("pad_act").set("pos", ["-B_0", "-B_0/2"])

    # Shutter central
    wp.create("shutter", "Rectangle")
    wp.feature("shutter").label("Central_shutter")
    wp.feature("shutter").set("size", ["B_0", "L_base"])
    wp.feature("shutter").set("pos", ["x_shutter", "y_shutter"])

    # Shutter do dissipador
    wp.create("sink_shutter", "Rectangle")
    wp.feature("sink_shutter").label("sink_shutter")
    wp.feature("sink_shutter").set("size", ["B_0", "L_sink_shutter"])
    wp.feature("sink_shutter").set("pos", ["x_shutter", "y_sink_shutter"])

    # Aletas + array
    wp.create("sink_fin", "Rectangle")
    wp.feature("sink_fin").label("sink_fin")
    wp.feature("sink_fin").set("size", ["L_sink", "b_sink"])
    wp.feature("sink_fin").set("pos", ["x_sink", "y_sink"])
    wp.create("arr_fin", "Array")
    wp.feature("arr_fin").selection("input").set("sink_fin")
    wp.feature("arr_fin").set("fullsize", ["1", "N_sink"])
    wp.feature("arr_fin").set("displ", ["0", "delta_sink"])

    # Pad do dissipador
    wp.create("pad_sink", "Rectangle")
    wp.feature("pad_sink").label("sink_pads")
    wp.feature("pad_sink").set("size", ["B_0", "L_sink_shutter"])
    wp.feature("pad_sink").set("pos", ["x_pad_sink", "y_sink_shutter"])

    half = ["arr_beam", "pad_act", "shutter", "sink_shutter", "arr_fin", "pad_sink"]

    # Espelha em torno de x = x_mirror
    wp.create("mir_act", "Mirror")
    wp.feature("mir_act").selection("input").set(*half)
    wp.feature("mir_act").set("pos", ["x_mirror", "0"])
    wp.feature("mir_act").set("axis", ["1", "0"])
    wp.feature("mir_act").set("keep", True)

    parts = half + ["mir_act"]

    # Haste de ligação e placa opcional
    if p["g_link"] > 0:
        wp.create("link", "Rectangle")
        wp.feature("link").label("link")
        wp.feature("link").set("size", ["w_link", "g_link"])
        wp.feature("link").set("pos", ["x_mirror-w_link/2", "y_top_sink"])
        parts.append("link")
    if p["t_plate"] > 0:
        wp.create("plate", "Rectangle")
        wp.feature("plate").label("plate")
        wp.feature("plate").set("size", ["W_meta", "t_plate"])
        wp.feature("plate").set("pos", ["x_meta", "y_top_sink+g_link"])
        parts.append("plate")

    wp.create("uni_act", "Union")
    wp.feature("uni_act").selection("input").set(*parts)
    wp.feature("uni_act").set("intbnd", False)
    wp.run("uni_act")
    return "uni_act"


def build_geometry(client, cell, meta, p, dxf_path, sim=cfg.SIMULATION, scale=cfg.SCALE):
    model = client.create("Atuador_Termico_Auxetico")
    j = model.java
    j.component().create("comp1", True)
    geom = j.component("comp1").geom().create("geom1", 3)
    geom.geomRep("cadps")
    geom.designBooleans(True)
    geom.lengthUnit(COMSOL_UNIT[scale["unit"]])

    # Parâmetros globais (mesmas expressões do Python)
    for name, expr, descr in actuator_expressions(cell, meta):
        j.param().set(name, expr, descr)
    for name, value in (("h_cell", cell["h"]), ("l_cell", cell["l"]),
                        ("theta_cell", cell["theta"]), ("e_cell", cell["e"])):
        j.param().set(name, f"{value:.12g}", "célula auxética")

    geom.create("wp1", "WorkPlane")
    geom.feature("wp1").set("unite", False)
    geom.feature("wp1").set("selresult", True)
    wp = geom.feature("wp1").geom()

    meta_tag = build_metamaterial(wp, cell, meta, dxf_path)
    act_tag = build_actuator(wp, p)
    parts = [act_tag, meta_tag]

    # Bloco de fixação no topo (domínio separado do metamaterial)
    if cfg.EXPERIMENT["top_bc"] == "block":
        wp.create("top_block", "Rectangle")
        wp.feature("top_block").label("top_block")
        wp.feature("top_block").set("size", ["w_block", "t_block"])
        wp.feature("top_block").set("pos", ["x_block", "y_block"])
        parts.append("top_block")

    # União final: mantém as fronteiras internas atuador/meta/bloco (medições)
    wp.create("uni_all", "Union")
    wp.feature("uni_all").selection("input").set(*parts)
    wp.feature("uni_all").set("intbnd", True)
    wp.run("uni_all")

    geom.create("ext1", "Extrude")
    geom.feature("ext1").set("workplane", "wp1")
    geom.feature("ext1").selection("input").set("wp1.uni_all")
    geom.feature("ext1").setIndex("distance", "h_0", 0)
    geom.run("ext1")
    geom.run("fin")

    rd = sim.get("remove_details")
    if rd:
        geom.feature().create("rmd1", "RemoveDetails")
        geom.feature("rmd1").set("detailsizetype", "absolute")
        geom.feature("rmd1").set("maxabssize", str(rd))
        geom.run("rmd1")
    geom.run()
    return model


# =====================================================================
# 4) SELEÇÕES, MATERIAL, FÍSICA
# =====================================================================

def _box(comp, tag, label, x, y, z=("-tol", "h_0+tol"), dim=2, condition="allvertices"):
    sel = comp.selection().create(tag, "Box")
    sel.label(label)
    sel.geom("geom1", dim)
    sel.set("xmin", x[0]); sel.set("xmax", x[1])
    sel.set("ymin", y[0]); sel.set("ymax", y[1])
    sel.set("zmin", z[0]); sel.set("zmax", z[1])
    sel.set("condition", condition)
    return sel


def create_meta_selections(comp):
    """
    Seleções do metamaterial usadas no Poisson efetivo.

    A união final usa intbnd=True, então as faces horizontais da placa/bloco de
    carga (em y_meta) e do bloco do topo (em y_meta+H_meta) ficam partidas em
    trechos de interface (compartilhados com o metamaterial) e trechos expostos
    entre as hastes da célula. Esses trechos expostos pertencem só aos blocos,
    mas caem dentro da box selection e entravam na média de v.

    Correção: cada parede = (box selection) ∩ (fronteiras adjacentes ao domínio
    do metamaterial). Os tags finais (sel_meta_bot, ...) não mudam.
    """
    xm = ("x_meta-tol", "x_meta+W_meta+tol")
    ym = ("y_meta-tol", "y_meta+H_meta+tol")

    # Domínio do metamaterial (placa e blocos ficam de fora: saem da faixa em y)
    _box(comp, "sel_meta_dom", "Metamaterial", xm, ym, dim=3, condition="inside")

    # Todas as fronteiras do domínio do metamaterial (inclui as interfaces com os blocos)
    adj = comp.selection().create("sel_meta_bnd", "Adjacent")
    adj.label("Fronteiras do metamaterial")
    adj.set("entitydim", "3")
    adj.set("input", ["sel_meta_dom"])
    adj.set("outputdim", "2")
    adj.set("exterior", True)
    adj.set("interior", True)

    walls = [
        ("sel_meta_bot", "Meta base", xm, ("y_meta-tol", "y_meta+tol")),
        ("sel_meta_top", "Meta topo", xm, ("y_meta+H_meta-tol", "y_meta+H_meta+tol")),
        ("sel_meta_left", "Meta esq.", ("x_meta-tol", "x_meta+tol"), ym),
        ("sel_meta_right", "Meta dir.", ("x_meta+W_meta-tol", "x_meta+W_meta+tol"), ym),
    ]
    for tag, label, x, y in walls:
        box_tag = tag.replace("sel_", "box_")
        _box(comp, box_tag, f"{label} (box)", x, y)
        sel = comp.selection().create(tag, "Intersection")
        sel.label(label)
        sel.set("entitydim", "2")
        sel.set("input", [box_tag, "sel_meta_bnd"])


def create_selections(model):
    comp = model.java.component("comp1")
    ya = ("-B_0/2-tol", "-B_0/2+L_base+tol")
    ys = ("y_sink_shutter-tol", "y_top_sink+tol")

    # Faces externas dos pads (como no .java)
    _box(comp, "sel_pad_act_L", "Pad atuador esq.", ("-B_0-tol", "-B_0+tol"), ya)
    _box(comp, "sel_pad_act_R", "Pad atuador dir.", ("2*x_mirror+B_0-tol", "2*x_mirror+B_0+tol"), ya)
    _box(comp, "sel_pad_sink_L", "Pad dissipador esq.", ("x_pad_sink-tol", "x_pad_sink+tol"), ys)
    _box(comp, "sel_pad_sink_R", "Pad dissipador dir.",
         ("2*x_mirror-x_pad_sink-tol", "2*x_mirror-x_pad_sink+tol"), ys)

    pads = comp.selection().create("sel_pads", "Union")
    pads.label("Pads")
    pads.geom("geom1", 2)
    pads.set("input", ["sel_pad_act_L", "sel_pad_act_R", "sel_pad_sink_L", "sel_pad_sink_R"])

    # Paredes do metamaterial (só faces que pertencem ao domínio do metamaterial)
    create_meta_selections(comp)

    # Ancoragem do bloco do topo
    if cfg.EXPERIMENT["top_bc"] == "block":
        xb = ("x_block-tol", "x_block+w_block+tol")
        yb = ("y_block-tol", "y_block+t_block+tol")

        _box(comp, "sel_block_anchor", "Bloco top (ancoragem)", xb,
                 ("y_block+t_block-tol", "y_block+t_block+tol"))
        
        #_box(comp, "left_block_anchor", "Bloco left (ancoragem)", ("x_block-tol", "x_block+tol"),yb)

        #_box(comp, "right_block_anchor", "Bloco right (ancoragem)", ("x_block+w_block-tol", "x_block+w_block+tol"),yb)
        
        #_box(comp, "bot_block_anchor", "Bloco bottom (ancoragem)", xb,("y_block-tol", "y_block+t_block+tol"), z=("-tol", "tol"), condition="inside")
        
        b_anchor = comp.selection().create("sel_block", "Union")
        b_anchor.label("Anchor")
        b_anchor.geom("geom1", 2)
        b_anchor.set("input", ["sel_block_anchor"])#, "left_block_anchor", "right_block_anchor", "bot_block_anchor"])

def create_material(model, mat_cfg=cfg.MATERIAL):
    j = model.java
    comp = j.component("comp1")

    funcs = [("k_Si", mat_cfg["k(T)"], "W/(m*K)", "Condutividade térmica"),
             ("alpha_Si", mat_cfg["alpha(T)"], "1/K", "Expansão térmica"),
             ("sigma_Si", mat_cfg["sigma(T)"], "S/m", "Condutividade elétrica"),
             ("Cp_Si", mat_cfg["Cp(T)"], "J/(kg*K)", "Capacidade térmica")]
    for tag, expr, unit, label in funcs:
        f = j.func().create(tag, "Analytic")
        f.label(label)
        f.set("funcname", tag)
        f.set("expr", expr)
        f.set("args", "T")
        f.setIndex("argunit", "K", 0)
        f.set("fununit", unit)
        f.setIndex("plotargs", "300", 0, 1)
        f.setIndex("plotargs", "2000", 0, 2)

    j.param().set("theta_rot", f"{mat_cfg['theta_rot']}[deg]", "rotação cristalográfica")
    j.param().set("T0", f"{cfg.EXPERIMENT['T0']}[K]", "temperatura dos pads")

    mat = comp.material().create("mat1", "Common")
    mat.label("Si (T-dependente)")
    d = mat.propertyGroup("def")
    d.set("density", f"{mat_cfg['rho']}[kg/m^3]")
    d.set("thermalconductivity", ["k_Si(T)"])
    d.set("thermalexpansioncoefficient", ["alpha_Si(T)"])
    d.set("electricconductivity", ["sigma_Si(T)"])
    d.set("heatcapacity", "Cp_Si(T)")
    d.set("relpermittivity", [str(mat_cfg["rel_permittivity"])])

    if mat_cfg["model"] == "anisotropic":
        var = comp.variable().create("var_Si")
        var.label("Constantes elásticas Si")
        var.set("C11", mat_cfg["C11(T)"])
        var.set("C12", mat_cfg["C12(T)"])
        var.set("C44", mat_cfg["C44(T)"])
        an = mat.propertyGroup().create("Anisotropic", "Anisotropic", "Anisotropic")
        # Ordem triangular superior do COMSOL: D11, D12, D22, D13, D23, D33, D14 ... D66
        an.set("D", ["C11", "C12", "C11", "C12", "C12", "C11",
                     "0[Pa]", "0[Pa]", "0[Pa]", "C44",
                     "0[Pa]", "0[Pa]", "0[Pa]", "0[Pa]", "C44",
                     "0[Pa]", "0[Pa]", "0[Pa]", "0[Pa]", "0[Pa]", "C44"])
        comp.coordSystem().create("sys2", "Rotated")
        comp.coordSystem("sys2").set("angle", ["theta_rot", "0", "0"])
    else:
        d.set("youngsmodulus", str(mat_cfg["E"]))
        d.set("poissonsratio", str(mat_cfg["nu"]))
    mat.selection().all()


def create_physics(model, currents, exp=cfg.EXPERIMENT, mat_cfg=cfg.MATERIAL):
    j = model.java
    comp = j.component("comp1")
    j.param().set("I_current", f"{currents[-1]:.6g}[mA]", "corrente no terminal")

    solid = comp.physics().create("solid", "SolidMechanics", "geom1")
    solid.prop("StructuralTransientBehavior").set("StructuralTransientBehavior", "Quasistatic")
    ht = comp.physics().create("ht", "HeatTransfer", "geom1")
    ec = comp.physics().create("ec", "ConductiveMedia", "geom1")

    te = comp.multiphysics().create("te1", "ThermalExpansion", 3)
    te.set("Heat_physics", "ht")
    te.set("Solid_physics", "solid")
    te.selection().all()
    emh = comp.multiphysics().create("emh1", "ElectromagneticHeating", 3)
    emh.set("EMHeat_physics", "ec")
    emh.set("Heat_physics", "ht")
    emh.selection().all()

    if mat_cfg["model"] == "anisotropic":
        solid.feature("lemm1").set("SolidModel", "Anisotropic")
        solid.feature("lemm1").set("coordinateSystem", "sys2")

    # Temperatura inicial = T0 (ajuda a convergência)
    ht.feature("init1").set("Tinit", "T0")

    # Pads: engaste + temperatura fixa
    solid.create("fix1", "Fixed", 2).selection().named("sel_pads")
    temp = ht.create("temp1", "TemperatureBoundary", 2)
    temp.selection().named("sel_pads")
    temp.set("T0", "T0")

    # Elétrico: terra no pad esquerdo, corrente no pad direito (como no .java)
    ec.create("gnd1", "Ground", 2).selection().named("sel_pad_act_L")
    term = ec.create("term1", "Terminal", 2)
    term.selection().named("sel_pad_act_R")
    term.set("I0", "I_current")

    # Topo do metamaterial
    top = exp["top_bc"]
    if top == "block":
        solid.create("fix_block", "Fixed", 2).selection().named("sel_block")
        tb = ht.create("temp_block", "TemperatureBoundary", 2)
        tb.selection().named("sel_block_anchor")
        tb.set("T0", "T0")
    elif top == "fixed":
        solid.create("fix_top", "Fixed", 2).selection().named("sel_meta_top")
        t2 = ht.create("temp_top", "TemperatureBoundary", 2)
        t2.selection().named("sel_meta_top")
        t2.set("T0", "T0")
    elif top == "roller":
        solid.create("rol_top", "Roller", 2).selection().named("sel_meta_top")
    elif top != "free":
        raise ValueError(f"top_bc inválido: {top}")


def create_probes(model, unit=cfg.SCALE["unit"]):
    """Operadores de acoplamento e variáveis medidas no experimento."""
    comp = model.java.component("comp1")
    cpl = comp.cpl()

    def op(tag, kind, sel=None, dim=2, method=None):
        o = cpl.create(tag, kind)
        o.selection().geom("geom1", dim)
        if sel is None:
            o.selection().all()
        else:
            o.selection().named(sel)
        if method:
            o.set("method", method)
        return o

    op("aveop_mb", "Average", "sel_meta_bot")
    op("aveop_mt", "Average", "sel_meta_top")
    op("aveop_ml", "Average", "sel_meta_left")
    op("aveop_mr", "Average", "sel_meta_right")
    op("intop_mt", "Integration", "sel_meta_top", method="summation")
    if cfg.EXPERIMENT["top_bc"] == "block":
        op("intop_anchor", "Integration", "sel_block_anchor", method="summation")
    op("aveop_meta", "Average", "sel_meta_dom", dim=3)
    op("maxop_meta", "Maximum", "sel_meta_dom", dim=3)
    op("maxop_all", "Maximum", None, dim=3)
    op("intop_all", "Integration", None, dim=3)

    L = f"[{unit}]"
    var = comp.variable().create("var_exp")
    var.label("Variáveis do experimento")
    var.set("d_out", "aveop_mb(v)", "deslocamento da base do metamaterial")
    var.set("d_top", "aveop_mt(v)", "deslocamento do topo do metamaterial")
    var.set("ep_x", f"(aveop_mr(u)-aveop_ml(u))/(W_meta*1{L})", "deformação média x")
    var.set("ep_y", f"(aveop_mt(v)-aveop_mb(v))/(H_meta*1{L})", "deformação média y")
    var.set("poisson", "-ep_x/ep_y", "Poisson efetivo (carga em y global)")
    var.set("d_meta", "aveop_mt(v)-aveop_mb(v)", "variação de altura do metamaterial")
    # Deformações no referencial da célula
    if load_direction() == "x":
        var.set("ep_cell_x", "ep_y", "deformação no eixo x da célula")
        var.set("ep_cell_y", "ep_x", "deformação no eixo y da célula")
    else:
        var.set("ep_cell_x", "ep_x", "deformação no eixo x da célula")
        var.set("ep_cell_y", "ep_y", "deformação no eixo y da célula")
    var.set("P_joule", "intop_all(ec.Qrh)", "potência Joule total")


def create_mesh(model, sim=cfg.SIMULATION):
    comp = model.java.component("comp1")
    comp.mesh().create("mesh1")
    comp.mesh("mesh1").contribute("geom/detail", True)
    comp.mesh("mesh1").autoMeshSize(int(sim["mesh_size"]))
    comp.mesh("mesh1").run()


def create_study(model, currents, sim=cfg.SIMULATION):
    """Estacionário com varredura auxiliar em I_current (continuação entre passos)."""
    j = model.java
    study = j.study().create("std1")
    stat = study.create("stat", "Stationary")
    stat.set("geometricNonlinearity", bool(sim["NonLinear"]))
    stat.set("useparam", True)
    stat.setIndex("pname", "I_current", 0)
    stat.setIndex("plistarr", " ".join(f"{i:.6g}" for i in currents), 0)
    stat.setIndex("punit", "mA", 0)
    study.createAutoSequences("all")

    s1 = j.sol("sol1").feature("s1")
    for tag in ("fc1", "se1"):
        try:
            s1.feature(tag).set('linsolver', 'i1')
            s1.feature(tag).set("ntermauto", "itertol")
            s1.feature(tag).set("niter", str(sim["maxiter"]))
            s1.feature(tag).set("maxiter", str(sim["maxiter"]))
        except Exception:
            pass
    if sim.get("cuda"):
        s1.feature("dDef").set("linsolver", "cudss")


# =====================================================================
# 5) RESULTADOS -> CSV
# =====================================================================

# (coluna, expressão, unidade). 'reacf' só existe se o topo tiver restrição.
def result_expressions(unit=cfg.SCALE["unit"], top_bc=cfg.EXPERIMENT["top_bc"],
                       extra=cfg.OUTPUT.get("extra_outputs", False)):
    exprs = [
        ("I_current_mA", "I_current", "mA"),
        # --- tensão máxima ---
        ("mises_meta_max_MPa", "maxop_meta(solid.mises)", "MPa"),
        ("sp1_meta_max_MPa", "maxop_meta(solid.sp1)", "MPa"),   # maior tensão principal (tração)
        ("mises_max_MPa", "maxop_all(solid.mises)", "MPa"),     # dispositivo inteiro
        # --- Poisson efetivo ---
        ("poisson_eff", "poisson", "1"),
        # --- deformação ---
        ("ep_load", "ep_y", "1"),            # na direção do atuador (y global)
        ("ep_transverse", "ep_x", "1"),      # transversal (x global)
        ("ep_cell_x", "ep_cell_x", "1"),     # no referencial da célula
        ("ep_cell_y", "ep_cell_y", "1"),
        # --- deslocamento ---
        (f"d_base_{unit}", "d_out", unit),   # base (lado do atuador)
        (f"d_top_{unit}", "d_top", unit),    # topo (lado do bloco)
        (f"d_meta_{unit}", "d_meta", unit),  # variação de altura do metamaterial
        (f"disp_meta_max_{unit}", "maxop_meta(solid.disp)", unit),
    ]
    if not extra:
        return exprs
    exprs += [
        ("V_terminal_V", "ec.V0_1", "V"),
        ("P_joule_W", "P_joule", "W"),
        ("T_max_K", "maxop_all(T)", "K"),
        ("T_meta_max_K", "maxop_meta(T)", "K"),
        ("T_meta_avg_K", "aveop_meta(T)", "K"),
    ]
    if top_bc == "block":
        exprs.append(("F_top_y_uN", "intop_anchor(reacf(v))", "uN"))
    elif top_bc in ("fixed", "roller"):
        exprs.append(("F_top_y_uN", "intop_mt(reacf(v))", "uN"))
    return exprs


def extract_results(model, n_steps):
    out, errors = {}, []
    for col, expr, unit in result_expressions():
        try:
            val = model.evaluate(expr, unit)
            val = np.real(np.atleast_1d(np.asarray(val, dtype=complex))).ravel()
            if val.size != n_steps:  # garante 1 valor por passo
                val = np.resize(val, n_steps) if val.size else np.full(n_steps, np.nan)
            out[col] = val
        except Exception as err:
            errors.append(f"{col}: {err}")
            out[col] = np.full(n_steps, np.nan)
    if "I_current_mA" in out and "V_terminal_V" in out:
        with np.errstate(divide="ignore", invalid="ignore"):
            out["R_ohm"] = out["V_terminal_V"] / (out["I_current_mA"] * 1e-3)
    for e in errors:
        print(f"[aviso] não foi possível avaliar {e}")
    return out


def _flatten(prefix, d):
    flat = {}
    for k, v in d.items():
        key = f"{prefix}.{k}"
        flat[key] = json.dumps(v) if isinstance(v, (list, dict)) else v
    return flat


def save_csv(rows, csv_path):
    """Acrescenta as linhas ao CSV. Se as colunas mudaram, cria um novo arquivo."""
    header = list(rows[0].keys())
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            old = next(csv.reader(f), [])
        if old != header:
            base, ext = os.path.splitext(csv_path)
            csv_path = f"{base}_{rows[0]['run_id']}{ext}"
            print(f"[aviso] colunas diferentes do CSV existente; salvando em {csv_path}")
    new = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"Resultados salvos em: {csv_path}")
    return csv_path



# =====================================================================
# 6) EXPERIMENTO
# =====================================================================

def prepare():
    cell = cell_dimensions()
    meta = metamaterial_info(cell)
    exprs = actuator_expressions(cell, meta)
    p = evaluate_expressions(exprs)
    currents = experiment_currents(p)
    check_feature_sizes(cell, p)
    return cell, meta, exprs, p, currents


def run_experiment(preview_only=False):
    # Modo bloco: o atuador é substituído por um bloco de carga (só mecânica)
    if actuator_mode() == "block":
        return run_experiment_block(preview_only=preview_only)

    out = cfg.OUTPUT
    os.makedirs(out["folder"], exist_ok=True)
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.abspath(os.path.join(out["folder"], run_id))
    os.makedirs(run_dir, exist_ok=True)

    cell, meta, exprs, p, currents = prepare()
    print(f"Metamaterial: {meta['W_meta']:.4g} x {meta['H_meta']:.4g} {cfg.SCALE['unit']}")
    print(f"Escala do atuador s_act = {p['s_act']:.4g} | L_0 = {p['L_0']:.4g}, "
          f"b_0 = {p['b_0']:.4g}, h_0 = {p['h_0']:.4g}")
    print(f"Correntes (mA): {', '.join(f'{i:.4g}' for i in currents)}")

    if out.get("preview", True) or preview_only:
        preview_layout(cell, meta, p, save_path=os.path.join(run_dir, "layout_preview.png"))
    if preview_only:
        return None

    import mph

    dxf_path = os.path.join(run_dir, "unit_cell.dxf")
    Gridgen.generate_dxf(cell["h"], cell["l"], cell["theta"], cell["e"], filename=dxf_path)

    cores = cfg.SIMULATION.get("cores")
    client = mph.start(cores=cores) if cores else mph.start()
    mph_path = os.path.join(run_dir, f"experiment_{run_id}.mph")

    status = "ok"
    try:
        model = build_geometry(client, cell, meta, p, dxf_path)
        create_selections(model)
        create_material(model)
        create_physics(model, currents)
        create_probes(model)
        create_mesh(model)
        create_study(model, currents)
        if out["save_mph"]:
            model.save(mph_path)
        model.java.sol("sol1").runAll()
        results = extract_results(model, len(currents))
        if out["save_mph"]:
            model.save(mph_path)
    except Exception as err:
        import traceback
        status = f"erro: {err}"
        print(f"[erro] {err}")
        traceback.print_exc()
        results = {c: np.full(len(currents), np.nan) for c, _, _ in result_expressions()}
        results["I_current_mA"] = np.array(currents)

    # Config completo da rodada fica num JSON ao lado do .mph
    full_cfg = {name: sect for name, sect in (
        ("GEOMETRY", cfg.GEOMETRY), ("SCALE", cfg.SCALE), ("ACTUATOR", cfg.ACTUATOR),
        ("MATERIAL", cfg.MATERIAL), ("EXPERIMENT", cfg.EXPERIMENT),
        ("SIMULATION", cfg.SIMULATION), ("OUTPUT", cfg.OUTPUT))}
    full_cfg["derived"] = {"cell": cell, "params": p, "currents_mA": currents}
    with open(os.path.join(run_dir, "config_run.json"), "w", encoding="utf-8") as f:
        json.dump(full_cfg, f, indent=2, ensure_ascii=False, default=str)

    # No CSV, só as entradas que identificam o experimento
    unit = cfg.SCALE["unit"]
    inputs = {
        "load_dir": meta["load_dir"],
        "top_bc": cfg.EXPERIMENT["top_bc"],
        "theta_deg": cell["theta"],
        f"h_cell_{unit}": cell["h"], f"l_cell_{unit}": cell["l"],
        f"e_cell_{unit}": cell["e"], f"thickness_{unit}": cell["extrude"],
        f"fillet_{unit}": cell["fillet"],
        "H_cells": cell["H"], "V_cells": cell["V"],
        f"W_meta_{unit}": meta["W_meta"], f"H_meta_{unit}": meta["H_meta"],
        "s_act": p["s_act"],
        "material": cfg.MATERIAL["model"],
        "NonLinear": cfg.SIMULATION["NonLinear"],
    }
    derived = {}

    rows = []
    for i in range(len(currents)):
        row = {"run_id": run_id, "tag": out.get("tag", ""),
               "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
               "status": status, "step": i + 1,
               "mph_file": mph_path if out["save_mph"] else ""}
        row.update({k: float(v[i]) for k, v in results.items()})
        row.update(derived)
        row.update(inputs)
        rows.append(row)

    save_csv(rows, os.path.join(out["folder"], out["csv"]))
    return rows


# =====================================================================
# 7) MODO BLOCO: atuador substituído por um bloco de carga
# =====================================================================
# Layout (y global):
#   y_load .. y_load+t_load         -> bloco de carga (no lugar do atuador)
#   y_meta .. y_meta+H_meta         -> metamaterial
#   y_block .. y_block+t_block      -> bloco do topo (igual ao modo térmico)
# Só Solid Mechanics: sem calor, sem corrente, sem expansão térmica.
# A carga (deslocamento ou força) é aplicada na face inferior do bloco de carga.
# Valores positivos = compressão (bloco sobe contra o metamaterial).

def actuator_mode(exp=cfg.EXPERIMENT):
    m = str(exp.get("actuator_mode", "thermal")).lower()
    if m not in ("thermal", "block"):
        raise ValueError(f"actuator_mode deve ser 'thermal' ou 'block', recebido: {m}")
    return m


def load_type(lb=LOAD_BLOCK):
    t = str(lb.get("load_type", "displacement")).lower()
    if t not in ("displacement", "force"):
        raise ValueError(f"LOAD_BLOCK['load_type'] deve ser 'displacement' ou 'force', recebido: {t}")
    return t


def load_param(lb=LOAD_BLOCK, unit=cfg.SCALE["unit"]):
    """(nome do parâmetro, unidade COMSOL do parâmetro, unidade da força)."""
    f_unit = lb.get("force_unit", "uN")
    if load_type(lb) == "force":
        return "F_load", f_unit, f_unit
    return "d_load", COMSOL_UNIT[unit], f_unit


def load_block_expressions(cell, meta, act=cfg.ACTUATOR, lb=LOAD_BLOCK, scale=cfg.SCALE):
    """
    Parâmetros globais do modo bloco (mesmo formato de actuator_expressions).
    s_act segue a mesma regra do atuador, para que os blocos tenham o mesmo
    tamanho que teriam no modo térmico.
    """
    u2um = UNIT_TO_UM[scale["unit"]]
    ref = lambda v: v / u2um  # valor de referência (µm) -> unidade do modelo

    if act["scale_mode"] == "auto":
        s_act = act["shutter_to_meta_width"] * meta["W_meta"] / (2 * ref(act["B_0_ref"]))
    else:
        s_act = act["manual_scale"]

    t_top_ref = act["block_thickness_ref"]
    t_load_ref = lb.get("thickness_ref") or t_top_ref
    w_load_rel = lb.get("width/meta") or act["block_width/meta"]
    tol = 1e-3 * min(cell["e"], ref(t_top_ref) * s_act, ref(t_load_ref) * s_act)

    return [
        # --- escala e espessura ---
        ("s_act", f"{s_act:.12g}", "fator de escala (blocos)"),
        ("h_0", f"{cell['extrude']:.12g}", "espessura do dispositivo (extrusão)"),
        ("tol", f"{tol:.6g}", "tolerância das seleções"),
        # --- metamaterial (valores do Gridgen) ---
        ("W_meta", f"{meta['W_meta']:.12g}", "largura do metamaterial"),
        ("H_meta", f"{meta['H_meta']:.12g}", "altura do metamaterial"),
        ("meta_x0", f"{meta['meta_x0']:.12g}", "x mínimo da célula no DXF"),
        ("meta_y0", f"{meta['meta_y0']:.12g}", "y mínimo da célula no DXF"),
        ("rot_meta", "90", "rotação do metamaterial quando load_dir = 'x' (graus)"),
        # --- bloco de carga (substitui o atuador) ---
        ("x_mirror", "W_meta/2", "eixo de simetria (centro do metamaterial)"),
        ("t_load", f"{ref(t_load_ref):.12g}*s_act", "espessura do bloco de carga"),
        ("w_load", f"{w_load_rel:.12g}*W_meta", "largura do bloco de carga"),
        ("x_load", "x_mirror-w_load/2", "x inicial do bloco de carga"),
        ("y_load", "0", "y inicial do bloco de carga"),
        # --- posição do metamaterial ---
        ("x_meta", "0", "x inicial do metamaterial"),
        ("y_meta", "y_load+t_load", "y inicial do metamaterial"),
        # --- bloco de fixação no topo ---
        ("t_block", f"{ref(t_top_ref):.12g}*s_act", "espessura do bloco do topo"),
        ("w_block", f"{act['block_width/meta']:.12g}*W_meta", "largura do bloco do topo"),
        ("x_block", "x_mirror-w_block/2", "x inicial do bloco"),
        ("y_block", "y_meta+H_meta", "y inicial do bloco"),
    ]


def load_values(p, lb=LOAD_BLOCK):
    """Valores da varredura: deslocamento (unidade do modelo) ou força (force_unit)."""
    if load_type(lb) == "force":
        vals = [float(f) for f in lb.get("force_list", [])]
    elif str(lb.get("disp_mode", "strain")).lower() == "strain":
        vals = [float(s) * p["H_meta"] for s in lb.get("strain_list", [])]
    else:
        vals = [float(d) for d in lb.get("disp_list", [])]
    if not vals:
        raise ValueError("LOAD_BLOCK: lista de carga vazia")
    return sorted(vals, key=abs)  # continuação: do menor para o maior módulo


def check_block_bcs(exp=cfg.EXPERIMENT, lb=LOAD_BLOCK):
    """Garante que o modelo não fica com movimento de corpo rígido."""
    top, guided = exp["top_bc"], bool(lb.get("guided", True))
    if top == "free" and not (load_type(lb) == "displacement" and guided):
        raise ValueError("top_bc = 'free' só funciona no modo bloco com "
                         "load_type='displacement' e guided=True (senão o modelo fica solto).")
    if top == "roller" and not guided:
        print("[aviso] top_bc='roller' com guided=False: x e z podem ficar sem restrição.")


def prepare_block():
    cell = cell_dimensions()
    meta = metamaterial_info(cell)
    exprs = load_block_expressions(cell, meta)
    p = evaluate_expressions(exprs)
    values = load_values(p)
    check_block_bcs()
    return cell, meta, exprs, p, values


def preview_layout_block(cell, meta, p, save_path=None, show=False):
    """Preview 2D do modo bloco: bloco de carga + metamaterial + bloco do topo."""
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import box as sh_box

    mm = metamaterial_polygon(cell, meta, p)
    load = sh_box(p["x_load"], p["y_load"], p["x_load"] + p["w_load"], p["y_load"] + p["t_load"])
    blk = None
    if cfg.EXPERIMENT["top_bc"] == "block":
        blk = sh_box(p["x_block"], p["y_block"], p["x_block"] + p["w_block"],
                     p["y_block"] + p["t_block"])

    def draw(ax, geom, fc, ec):
        geoms = geom.geoms if hasattr(geom, "geoms") else [geom]
        for g in geoms:
            x, y = g.exterior.xy
            ax.fill(x, y, fc=fc, ec=ec, lw=0.6)
            for hole in g.interiors:
                hx, hy = hole.xy
                ax.fill(hx, hy, fc="white", ec=ec, lw=0.5)

    fig, ax = plt.subplots(figsize=(7, 7))
    draw(ax, load, "#9fb7d6", "#2c4a6e")
    draw(ax, mm, "#e8a87c", "#8a4b1f")
    if blk is not None:
        draw(ax, blk, "#8fbf8f", "#2e6b2e")
    # seta indicando a carga na face inferior do bloco
    xc = p["x_load"] + p["w_load"] / 2
    arrow = 0.25 * p["H_meta"]
    ax.annotate("", xy=(xc, p["y_load"]), xytext=(xc, p["y_load"] - arrow),
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=2))
    ax.set_aspect("equal")
    ax.grid(True, ls=":", alpha=0.5)
    unit = cfg.SCALE["unit"]
    ax.set_title(f"Modo bloco ({load_type()}) | s_act = {p['s_act']:.4g}")
    ax.set_xlabel(f"x [{unit}]")
    ax.set_ylabel(f"y [{unit}]")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Preview salvo em: {save_path}")
    if show:
        plt.show()
    plt.close(fig)


def build_geometry_block(client, cell, meta, dxf_path, sim=cfg.SIMULATION, scale=cfg.SCALE):
    """Mesma geometria do build_geometry, com o bloco de carga no lugar do atuador."""
    model = client.create("Metamaterial_Bloco")
    j = model.java
    j.component().create("comp1", True)
    geom = j.component("comp1").geom().create("geom1", 3)
    geom.geomRep("cadps")
    geom.designBooleans(True)
    geom.lengthUnit(COMSOL_UNIT[scale["unit"]])

    for name, expr, descr in load_block_expressions(cell, meta):
        j.param().set(name, expr, descr)
    for name, value in (("h_cell", cell["h"]), ("l_cell", cell["l"]),
                        ("theta_cell", cell["theta"]), ("e_cell", cell["e"])):
        j.param().set(name, f"{value:.12g}", "célula auxética")

    geom.create("wp1", "WorkPlane")
    geom.feature("wp1").set("unite", False)
    geom.feature("wp1").set("selresult", True)
    wp = geom.feature("wp1").geom()

    # Metamaterial primeiro (box selections do fillet em coordenadas da célula)
    meta_tag = build_metamaterial(wp, cell, meta, dxf_path)

    wp.create("load_block", "Rectangle")
    wp.feature("load_block").label("load_block")
    wp.feature("load_block").set("size", ["w_load", "t_load"])
    wp.feature("load_block").set("pos", ["x_load", "y_load"])
    parts = ["load_block", meta_tag]

    if cfg.EXPERIMENT["top_bc"] == "block":
        wp.create("top_block", "Rectangle")
        wp.feature("top_block").label("top_block")
        wp.feature("top_block").set("size", ["w_block", "t_block"])
        wp.feature("top_block").set("pos", ["x_block", "y_block"])
        parts.append("top_block")

    wp.create("uni_all", "Union")
    wp.feature("uni_all").selection("input").set(*parts)
    wp.feature("uni_all").set("intbnd", True)
    wp.run("uni_all")

    geom.create("ext1", "Extrude")
    geom.feature("ext1").set("workplane", "wp1")
    geom.feature("ext1").selection("input").set("wp1.uni_all")
    geom.feature("ext1").setIndex("distance", "h_0", 0)
    geom.run("ext1")
    geom.run("fin")

    rd = sim.get("remove_details")
    if rd:
        geom.feature().create("rmd1", "RemoveDetails")
        geom.feature("rmd1").set("detailsizetype", "absolute")
        geom.feature("rmd1").set("maxabssize", str(rd))
        geom.run("rmd1")
    geom.run()
    return model


def create_selections_block(model):
    """Seleções do metamaterial e do bloco do topo (iguais ao modo térmico) + bloco de carga."""
    comp = model.java.component("comp1")

    # Paredes do metamaterial (só faces que pertencem ao domínio do metamaterial)
    create_meta_selections(comp)

    # Bloco de carga: face inferior (onde a carga é aplicada) e domínio
    xl = ("x_load-tol", "x_load+w_load+tol")
    _box(comp, "sel_load_bot", "Bloco de carga (face inferior)", xl,
         ("y_load-tol", "y_load+tol"))
    _box(comp, "sel_load_dom", "Bloco de carga", xl,
         ("y_load-tol", "y_load+t_load+tol"), dim=3, condition="inside")

    # Ancoragem do bloco do topo (mesma do modo térmico)
    if cfg.EXPERIMENT["top_bc"] == "block":
        xb = ("x_block-tol", "x_block+w_block+tol")
        yb = ("y_block-tol", "y_block+t_block+tol")
        _box(comp, "sel_block_anchor", "Bloco top (ancoragem)", xb,
             ("y_block+t_block-tol", "y_block+t_block+tol"))
        _box(comp, "left_block_anchor", "Bloco left (ancoragem)",
             ("x_block-tol", "x_block+tol"), yb)
        _box(comp, "right_block_anchor", "Bloco right (ancoragem)",
             ("x_block+w_block-tol", "x_block+w_block+tol"), yb)
        _box(comp, "bot_block_anchor", "Bloco bottom (ancoragem)", xb,
             ("y_block-tol", "y_block+t_block+tol"), z=("-tol", "tol"), condition="inside")
        b_anchor = comp.selection().create("sel_block", "Union")
        b_anchor.label("Anchor")
        b_anchor.geom("geom1", 2)
        b_anchor.set("input", ["sel_block_anchor", "left_block_anchor",
                               "right_block_anchor", "bot_block_anchor"])


_T_TOKEN = re.compile(r"(?<![A-Za-z0-9_])T(?![A-Za-z0-9_])")


def create_material_block(model, mat_cfg=cfg.MATERIAL):
    """
    Mesmo material do modo térmico. Como não há transferência de calor, a
    temperatura T não existe como variável: as constantes elásticas C11/C12/C44
    são avaliadas em T0.
    """
    create_material(model, mat_cfg)
    if mat_cfg["model"] == "anisotropic":
        var = model.java.component("comp1").variable("var_Si")
        for name in ("C11", "C12", "C44"):
            var.set(name, _T_TOKEN.sub("T0", mat_cfg[f"{name}(T)"]))


def _prescribe(feat, idx, expr):
    """Prescreve a componente idx (0=x, 1=y, 2=z) de um Prescribed Displacement."""
    try:
        feat.setIndex("Direction", "prescribed", idx)
    except Exception:
        feat.setIndex("Direction", True, idx)  # versões antigas do COMSOL
    feat.setIndex("U0", expr, idx)


def create_physics_block(model, values, exp=cfg.EXPERIMENT, mat_cfg=cfg.MATERIAL, lb=LOAD_BLOCK):
    """Só Solid Mechanics. Carga na face inferior do bloco de carga, em y global."""
    j = model.java
    comp = j.component("comp1")
    pname, punit, _ = load_param(lb)
    j.param().set(pname, f"{values[-1]:.6g}[{punit}]", "carga aplicada pelo bloco de carga")

    solid = comp.physics().create("solid", "SolidMechanics", "geom1")
    if mat_cfg["model"] == "anisotropic":
        solid.feature("lemm1").set("SolidModel", "Anisotropic")
        solid.feature("lemm1").set("coordinateSystem", "sys2")

    # Topo do metamaterial (mesmas opções do modo térmico, sem a parte térmica)
    top = exp["top_bc"]
    if top == "block":
        solid.create("fix_block", "Fixed", 2).selection().named("sel_block")
    elif top == "fixed":
        solid.create("fix_top", "Fixed", 2).selection().named("sel_meta_top")
    elif top == "roller":
        solid.create("rol_top", "Roller", 2).selection().named("sel_meta_top")
    elif top != "free":
        raise ValueError(f"top_bc inválido: {top}")

    guided = bool(lb.get("guided", True))
    if load_type(lb) == "displacement":
        pd = solid.create("disp_load", "Displacement2", 2)
        pd.label("Deslocamento do bloco de carga")
        pd.selection().named("sel_load_bot")
        _prescribe(pd, 1, pname)
        if guided:
            _prescribe(pd, 0, "0")
            _prescribe(pd, 2, "0")
    else:
        bl = solid.create("bl_load", "BoundaryLoad", 2)
        bl.label("Força do bloco de carga")
        bl.selection().named("sel_load_bot")
        bl.set("LoadType", "TotalForce")
        bl.set("Ftot", ["0", pname, "0"])
        if guided:
            gd = solid.create("guide_load", "Displacement2", 2)
            gd.label("Guia do bloco de carga (u = w = 0)")
            gd.selection().named("sel_load_bot")
            _prescribe(gd, 0, "0")
            _prescribe(gd, 2, "0")


def create_probes_block(model, unit=cfg.SCALE["unit"]):
    """Mesmas variáveis do create_probes (sem potência Joule) + medições do bloco de carga."""
    comp = model.java.component("comp1")
    cpl = comp.cpl()

    def op(tag, kind, sel=None, dim=2, method=None):
        o = cpl.create(tag, kind)
        o.selection().geom("geom1", dim)
        if sel is None:
            o.selection().all()
        else:
            o.selection().named(sel)
        if method:
            o.set("method", method)
        return o

    op("aveop_mb", "Average", "sel_meta_bot")
    op("aveop_mt", "Average", "sel_meta_top")
    op("aveop_ml", "Average", "sel_meta_left")
    op("aveop_mr", "Average", "sel_meta_right")
    op("intop_mt", "Integration", "sel_meta_top", method="summation")
    op("aveop_lb", "Average", "sel_load_bot")
    op("intop_lb", "Integration", "sel_load_bot", method="summation")
    if cfg.EXPERIMENT["top_bc"] == "block":
        op("intop_anchor", "Integration", "sel_block_anchor", method="summation")
    op("aveop_meta", "Average", "sel_meta_dom", dim=3)
    op("maxop_meta", "Maximum", "sel_meta_dom", dim=3)
    op("maxop_all", "Maximum", None, dim=3)

    L = f"[{unit}]"
    var = comp.variable().create("var_exp")
    var.label("Variáveis do experimento")
    var.set("d_out", "aveop_mb(v)", "deslocamento da base do metamaterial")
    var.set("d_top", "aveop_mt(v)", "deslocamento do topo do metamaterial")
    var.set("d_block", "aveop_lb(v)", "deslocamento da face inferior do bloco de carga")
    var.set("ep_x", f"(aveop_mr(u)-aveop_ml(u))/(W_meta*1{L})", "deformação média x")
    var.set("ep_y", f"(aveop_mt(v)-aveop_mb(v))/(H_meta*1{L})", "deformação média y")
    var.set("poisson", "-ep_x/ep_y", "Poisson efetivo (carga em y global)")
    var.set("d_meta", "aveop_mt(v)-aveop_mb(v)", "variação de altura do metamaterial")
    if load_direction() == "x":
        var.set("ep_cell_x", "ep_y", "deformação no eixo x da célula")
        var.set("ep_cell_y", "ep_x", "deformação no eixo y da célula")
    else:
        var.set("ep_cell_x", "ep_x", "deformação no eixo x da célula")
        var.set("ep_cell_y", "ep_y", "deformação no eixo y da célula")


def create_study_block(model, values, sim=cfg.SIMULATION, lb=LOAD_BLOCK):
    """Estacionário com varredura auxiliar na carga do bloco (continuação entre passos)."""
    j = model.java
    pname, punit, _ = load_param(lb)
    study = j.study().create("std1")
    stat = study.create("stat", "Stationary")
    stat.set("geometricNonlinearity", bool(sim["NonLinear"]))
    stat.set("useparam", True)
    stat.setIndex("pname", pname, 0)
    stat.setIndex("plistarr", " ".join(f"{v:.6g}" for v in values), 0)
    stat.setIndex("punit", punit, 0)
    study.createAutoSequences("all")

    s1 = j.sol("sol1").feature("s1")
    for tag in ("fc1", "se1"):
        try:
            s1.feature(tag).set('linsolver', 'i1')
            s1.feature(tag).set("ntermauto", "itertol")
            s1.feature(tag).set("niter", str(sim["maxiter"]))
            s1.feature(tag).set("maxiter", str(sim["maxiter"]))
        except Exception:
            pass
    if sim.get("cuda"):
        s1.feature("dDef").set("linsolver", "cudss")


def result_expressions_block(unit=cfg.SCALE["unit"], top_bc=cfg.EXPERIMENT["top_bc"],
                             extra=cfg.OUTPUT.get("extra_outputs", False), lb=LOAD_BLOCK):
    """
    Colunas do modo bloco. Sempre traz deslocamento e força do bloco de carga:
      displacement -> d_load = parâmetro, F_load = força de reação na face inferior
      force        -> F_load = parâmetro, d_load = deslocamento medido do bloco
    """
    _, _, f_unit = load_param(lb)
    if load_type(lb) == "displacement":
        load_cols = [(f"d_load_{unit}", "d_load", unit),
                     (f"F_load_{f_unit}", "intop_lb(reacf(v))", f_unit)]
    else:
        load_cols = [(f"d_load_{unit}", "d_block", unit),
                     (f"F_load_{f_unit}", "F_load", f_unit)]

    exprs = load_cols + [
        # --- tensão máxima ---
        ("mises_meta_max_MPa", "maxop_meta(solid.mises)", "MPa"),
        ("sp1_meta_max_MPa", "maxop_meta(solid.sp1)", "MPa"),
        ("mises_max_MPa", "maxop_all(solid.mises)", "MPa"),
        # --- Poisson efetivo ---
        ("poisson_eff", "poisson", "1"),
        # --- deformação ---
        ("ep_load", "ep_y", "1"),
        ("ep_transverse", "ep_x", "1"),
        ("ep_cell_x", "ep_cell_x", "1"),
        ("ep_cell_y", "ep_cell_y", "1"),
        # --- deslocamento ---
        (f"d_base_{unit}", "d_out", unit),
        (f"d_top_{unit}", "d_top", unit),
        (f"d_meta_{unit}", "d_meta", unit),
        (f"disp_meta_max_{unit}", "maxop_meta(solid.disp)", unit),
    ]
    if extra:
        if top_bc == "block":
            exprs.append((f"F_top_y_{f_unit}", "intop_anchor(reacf(v))", f_unit))
        elif top_bc in ("fixed", "roller"):
            exprs.append((f"F_top_y_{f_unit}", "intop_mt(reacf(v))", f_unit))
    return exprs


def extract_results_block(model, n_steps):
    out, errors = {}, []
    for col, expr, unit in result_expressions_block():
        try:
            val = model.evaluate(expr, unit)
            val = np.real(np.atleast_1d(np.asarray(val, dtype=complex))).ravel()
            if val.size != n_steps:
                val = np.resize(val, n_steps) if val.size else np.full(n_steps, np.nan)
            out[col] = val
        except Exception as err:
            errors.append(f"{col}: {err}")
            out[col] = np.full(n_steps, np.nan)
    for e in errors:
        print(f"[aviso] não foi possível avaliar {e}")
    return out


def run_experiment_block(preview_only=False):
    """Mesmo fluxo do run_experiment, com o bloco de carga no lugar do atuador."""
    out = cfg.OUTPUT
    os.makedirs(out["folder"], exist_ok=True)
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.abspath(os.path.join(out["folder"], run_id))
    os.makedirs(run_dir, exist_ok=True)

    unit = cfg.SCALE["unit"]
    cell, meta, exprs, p, values = prepare_block()
    ltype = load_type()
    _, _, f_unit = load_param()
    v_unit = f_unit if ltype == "force" else unit
    print(f"[modo bloco] Metamaterial: {meta['W_meta']:.4g} x {meta['H_meta']:.4g} {unit}")
    print(f"Bloco de carga: {p['w_load']:.4g} x {p['t_load']:.4g} {unit} | "
          f"bloco do topo: {p['w_block']:.4g} x {p['t_block']:.4g} {unit}")
    print(f"Carga ({ltype}, {v_unit}): {', '.join(f'{v:.4g}' for v in values)}")

    if out.get("preview", True) or preview_only:
        preview_layout_block(cell, meta, p, save_path=os.path.join(run_dir, "layout_preview.png"))
    if preview_only:
        return None

    import mph

    dxf_path = os.path.join(run_dir, "unit_cell.dxf")
    Gridgen.generate_dxf(cell["h"], cell["l"], cell["theta"], cell["e"], filename=dxf_path)

    cores = cfg.SIMULATION.get("cores")
    client = mph.start(cores=cores) if cores else mph.start()
    mph_path = os.path.join(run_dir, f"experiment_block_{run_id}.mph")

    status = "ok"
    try:
        model = build_geometry_block(client, cell, meta, dxf_path)
        create_selections_block(model)
        create_material_block(model)
        create_physics_block(model, values)
        create_probes_block(model)
        create_mesh(model)
        create_study_block(model, values)
        if out["save_mph"]:
            model.save(mph_path)
        model.java.sol("sol1").runAll()
        results = extract_results_block(model, len(values))
        if out["save_mph"]:
            model.save(mph_path)
    except Exception as err:
        status = f"erro: {err}"
        print(f"[erro] {err}")
        traceback.print_exc()
        results = {c: np.full(len(values), np.nan) for c, _, _ in result_expressions_block()}
        results[result_expressions_block()[0 if ltype == "displacement" else 1][0]] = np.array(values)

    full_cfg = {name: sect for name, sect in (
        ("GEOMETRY", cfg.GEOMETRY), ("SCALE", cfg.SCALE), ("ACTUATOR", cfg.ACTUATOR),
        ("MATERIAL", cfg.MATERIAL), ("EXPERIMENT", cfg.EXPERIMENT),
        ("LOAD_BLOCK", LOAD_BLOCK), ("SIMULATION", cfg.SIMULATION), ("OUTPUT", cfg.OUTPUT))}
    full_cfg["derived"] = {"cell": cell, "params": p, "load_values": values}
    with open(os.path.join(run_dir, "config_run.json"), "w", encoding="utf-8") as f:
        json.dump(full_cfg, f, indent=2, ensure_ascii=False, default=str)

    inputs = {
        "actuator_mode": "block",
        "load_type": ltype,
        "guided": bool(LOAD_BLOCK.get("guided", True)),
        "load_dir": meta["load_dir"],
        "top_bc": cfg.EXPERIMENT["top_bc"],
        "theta_deg": cell["theta"],
        f"h_cell_{unit}": cell["h"], f"l_cell_{unit}": cell["l"],
        f"e_cell_{unit}": cell["e"], f"thickness_{unit}": cell["extrude"],
        f"fillet_{unit}": cell["fillet"],
        "H_cells": cell["H"], "V_cells": cell["V"],
        f"W_meta_{unit}": meta["W_meta"], f"H_meta_{unit}": meta["H_meta"],
        f"t_load_{unit}": p["t_load"], f"t_block_{unit}": p["t_block"],
        "material": cfg.MATERIAL["model"],
        "NonLinear": cfg.SIMULATION["NonLinear"],
    }

    rows = []
    for i in range(len(values)):
        row = {"run_id": run_id, "tag": out.get("tag", ""),
               "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
               "status": status, "step": i + 1,
               "mph_file": mph_path if out["save_mph"] else ""}
        row.update({k: float(v[i]) for k, v in results.items()})
        row.update(inputs)
        rows.append(row)

    save_csv(rows, os.path.join(out["folder"], out.get("csv_block", "experiments_block.csv")))
    return rows


if __name__ == "__main__":
    run_experiment(preview_only="--preview" in sys.argv)
