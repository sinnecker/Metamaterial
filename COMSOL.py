import mph
import os
import numpy as np


def build_geometry(client,H, V, h, l, theta, e, extrude, fillet, metric, geom_path, file_path,array=False):

    theta = np.radians(theta)
    dx = l * np.sin(theta) #distancia horizontal
    dy = l * np.cos(theta) #distancia vertical
    alpha = np.pi/2 - theta
    #calcula o espaço entre as células
    de = e * np.tan(alpha)/2 + e / np.sin(theta) #espaço vertical entre as fileiras de celulas
    dz = 2*h - 2*dy  #espaço vertical de uma célula para outra
    dV = dz + 2*de 
    dH = 2*dx + e 

    model = client.create("Deformacao_Mecanica")

    # --------------------------------------------------
    # Componente e geometria
    # --------------------------------------------------
    model.java.component().create("comp1", True)

    geom = model.java.component("comp1").geom().create("geom1", 3)
    geom.geomRep("cadps")
    geom.designBooleans(True)

    
    # --------------------------------------------------
    # Cria a geometria 2D (work plane)
    # --------------------------------------------------
    geom.create("wp1", "WorkPlane")
    geom.feature("wp1").set("unite", False)
    geom.feature("wp1").set("selresult", True)

    wp = geom.feature("wp1").geom()

    # --------------------------------------------------
    # Importa o DXF
    # --------------------------------------------------
    wp.create("imp1", "Import")
    wp.feature("imp1").set("filename", geom_path)

    # Importa apenas as layers desejadas
    wp.feature("imp1").set("alllayers", ["EXTERIOR", "HOLES"])

    # Mantém os contornos como vieram do DXF
    wp.feature("imp1").set("repairgeom", False)
    wp.feature("imp1").set("selindividual", False)

    wp.run("imp1")

    # --------------------------------------------------
    # Diferença boleana no work plane
    # Gera os buracos na célula
    # --------------------------------------------------
    wp.create("dif1", "Difference")
    wp.feature("dif1").selection("input").set("imp1(1)")
    wp.feature("dif1").selection("input2").set("imp1(2)")

    wp.run("dif1")

    geom.run()

    geom1 = model.java.component("comp1").geom("geom1")

    if fillet>0:
        # --------------------------------------------------
        # Seleciona os vértices para fillet
        # Bounding box para selecionar
        # --------------------------------------------------
        xmin, xmax, ymin, ymax, _, _ = geom1.getBoundingBox()
        epsilon = (xmax-xmin)*1e-4
    
        wp.create("bbox1", "BoxSelection")
        wp.feature("bbox1").set("entitydim", "0") 
    
        wp.feature("bbox1").set("xmin", xmin+epsilon)
        wp.feature("bbox1").set("xmax", xmax-epsilon)
        wp.feature("bbox1").set("ymin", -epsilon)
        wp.feature("bbox1").set("ymax", l*np.cos(theta)-epsilon)
    
        wp.run("bbox1")
    
        wp.create("bbox2", "BoxSelection")
        wp.feature("bbox2").set("entitydim", "0") 
    
        wp.feature("bbox2").set("xmin", xmin+epsilon)
        wp.feature("bbox2").set("xmax", xmax-epsilon)
        wp.feature("bbox2").set("ymin", h-l*np.cos(theta)+epsilon)
        wp.feature("bbox2").set("ymax", h+epsilon)
    
        wp.run("bbox2")
    
        wp.create("unisel1", "UnionSelection")
    
        wp.feature("unisel1").set("entitydim", "0")
        wp.feature("unisel1").set("input", ["bbox1", "bbox2"])
    
        wp.run("unisel1")
    
        # --------------------------------------------------
        # Fillet
        # --------------------------------------------------
        wp.create("fil1", "Fillet")
    
        wp.feature("fil1").selection("pointinsketch").named("unisel1")
    
        wp.feature("fil1").set("radius", fillet)
    
        wp.run("fil1")


    # --------------------------------------------------
    # Array 2D
    # --------------------------------------------------
    if array:
        wp.create("arr1", "Array")
        if fillet>0:
            wp.feature("arr1").selection("input").set("fil1") 
        else:
            wp.feature("arr1").selection("input").set("dif1") 
        wp.feature("arr1").set("displ", [str(dH),str(dV)])
        wp.feature("arr1").set("fullsize",[str(H),str(V)])

        wp.run("arr1")

        wp.create("uni_arr", "Union")
        wp.feature("uni_arr").selection("input").set("arr1")
        wp.feature("uni_arr").set("intbnd", False)

        wp.run("uni_arr")

        
    # --------------------------------------------------
    # Extrude do working plane
    # --------------------------------------------------
    geom.create("ext1", "Extrude")
    geom.feature("ext1").set("workplane", "wp1")

    # Seleciona apenas o espaço nao vazio
    if array:
        geom.feature("ext1").selection("input").set("wp1.uni_arr")
    else:
        geom.feature("ext1").selection("input").set("wp1.dif1")

    geom.feature("ext1").set("distance", str(extrude))

    geom.run("ext1")

    geom.run("fin");
    geom.feature().create("rmd1", "RemoveDetails");
    geom.feature("rmd1").set("detailsizetype", "absolute");
    geom.feature("rmd1").set("maxabssize", "0.01");
    geom.run("rmd1");
    
    geom.run()
    
    model.java.component("comp1").geom("geom1").lengthUnit(metric)

    if file_path!=None:
        model.build()
        model.save(file_path)
        
    return model

def apply_physics(model, young_mod, poisson_ratio, density, file_path, force, force_value, NonLinear, plot_data, cuda):
    
    # --------------------------------------------------
    # Selecionando as faces para condiçoes de contorno
    # --------------------------------------------------
    geom1 = model.java.component("comp1").geom("geom1")

    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()

    epsilon = 1e-5 * (xmax-xmin)

    #Parede Esquerda

    sel_left = model.java.component("comp1").selection().create("leftWall", "Box")
    sel_left.geom("geom1", 2)

    sel_left.set("xmin", xmin - epsilon)
    sel_left.set("xmax", xmin )

    sel_left.set("ymin", ymin)
    sel_left.set("ymax", ymax)

    sel_left.set("zmin", zmin)
    sel_left.set("zmax", zmax)

    sel_left.set("condition", "allvertices")

    #Parede Direita

    sel_right = model.java.component("comp1").selection().create("rightWall", "Box")
    sel_right.geom("geom1", 2)

    sel_right.set("xmin", xmax - epsilon)
    sel_right.set("xmax", xmax + epsilon)

    sel_right.set("ymin", ymin)
    sel_right.set("ymax", ymax)

    sel_right.set("zmin", zmin)
    sel_right.set("zmax", zmax)

    sel_right.set("condition", "allvertices")

    # --------------------------------------------------
    # FISICA
    # --------------------------------------------------
    physics = model.java.component("comp1").physics().create(
        "solid",
        "SolidMechanics",
        "geom1"
    )

    fix = physics.create("fix1", "Fixed", 2)
    fix.selection().named("leftWall")

    load1 = physics.create('load1', 'BoundaryLoad', 2)
    load1.selection().named("rightWall")
    load1.set("forceType", force)
    load1.set("force", [str(k) for k in force_value])

    mat = model.java.component("comp1").material().create("mat1", "Common")

    mat.propertyGroup("def").set("youngsmodulus", str(young_mod))
    mat.propertyGroup("def").set("poissonsratio", str(poisson_ratio))
    mat.propertyGroup("def").set("density", str(density))

    study = model.java.study().create('std1')
    stat_step = study.create('stat', 'Stationary')
    stat_step.set("geometricNonlinearity", NonLinear)
    
    # 6. Solução
    model.java.sol().create('sol1')
    model.java.sol('sol1').study('std1')
    model.java.sol('sol1').create('st1', 'StudyStep')
    model.java.sol('sol1').feature('st1').set('study', 'std1')
    model.java.sol('sol1').create('v1', 'Variables')
    model.java.sol('sol1').create('s1', 'Stationary')
    if cuda:
        model.java.sol('sol1').feature('s1').feature('dDef').set('linsolver', 'cudss')
    
    # Roda a simulação de fato

        # --------------------------------------------------
    # SALVAR MODELO
    # --------------------------------------------------
    if file_path!=None:
        model.build()
        model.save(file_path)
    model.java.sol('sol1').runAll()
    model.build()

    
    # --------------------------------------------------
    # GERAR PLOTS (IMAGEM) E EXPORTAR DADOS (TEXTO)
    # --------------------------------------------------
    if plot_data:
        base_dir = os.path.dirname(os.path.abspath(file_path))
        plots_dir = os.path.join(os.path.dirname(base_dir), "plots")
        os.makedirs(plots_dir, exist_ok=True)
        
        # 1. Plot de Tensão (von Mises)
        model.java.result().create("pg1", "PlotGroup3D")
        model.java.result("pg1").create("surf1", "Surface")
        model.java.result("pg1").feature("surf1").set("expr", "solid.mises")
        
        img1_path = os.path.join(plots_dir, "comsol_stress.png")
        img1 = model.java.result().export().create("img1", "Image")
        img1.set("plotgroup", "pg1")
        img1.set("filename", img1_path)
        img1.set("size", "manualprint")
        img1.set("unit", "mm")
        img1.set("height", "150")
        img1.set("width", "200")
        img1.set("resolution", "300")
        img1.run()
        
        # 2. Plot de Deslocamento (solid.disp)
        model.java.result().create("pg2", "PlotGroup3D")
        model.java.result("pg2").create("surf2", "Surface")
        model.java.result("pg2").feature("surf2").set("expr", "solid.disp")
        
        img2_path = os.path.join(plots_dir, "comsol_displacement.png")
        img2 = model.java.result().export().create("img2", "Image")
        img2.set("plotgroup", "pg2")
        img2.set("filename", img2_path)
        img2.set("size", "manualprint")
        img2.set("unit", "mm")
        img2.set("height", "150")
        img2.set("width", "200")
        img2.set("resolution", "300")
        img2.run()
    
        # 3. Exportar dados de texto (para gráfico Stress x Strain numérico)
        export_path = os.path.abspath(file_path.replace(".mph", "_data.txt"))
        export_data = model.java.result().export().create("data1", "Data")
        
        # Extrai posições, tensão, deslocamento total e deformação elástica (strain)
        export_data.set("expr", ["x", "y", "z", "solid.mises", "solid.disp", "solid.edeve"])
        export_data.set("filename", export_path)
        export_data.run()

    return model


def apply_physics_monotonic(model, young_mod, poisson_ratio, density,
                            max_strain, min_strain, n_steps, force, NonLinear, file_path):
    """
    Simulação de compressão monotônica em X com varredura paramétrica de deslocamento.

    Usa controle de deslocamento (Displacement0) em vez de força — mais estável
    numericamente e mais próximo de experimentos reais de compressão.

    A cada passo paramétrico extrai:
      - Força de reação total em X na parede fixa (N)
      - Deslocamento prescrito (µm)
      - Tensão de von Mises máxima no domínio (Pa)

    O critério de falha é aplicado em pós-processamento (Python): marca o passo
    em que max(von Mises) ≥ fracture_stress.

    Args:
        model         : objeto COMSOL (mph)
        young_mod     : módulo de Young (Pa)
        poisson_ratio : razão de Poisson
        density       : densidade (kg/m³)
        max_strain    : strain máximo em X (fração, ex: 0.30 = 30 %)
        n_steps       : número de passos paramétricos
        fracture_stress: tensão de von Mises que define a falha (Pa)
        file_path     : caminho de saída do arquivo .mph

    Returns:
        model, caminho do arquivo de dados globais, A0 (m²), Lx (µm), Ly (µm)
    """

    # ------------------------------------------------------------------
    # Geometria: dimensões do bounding box
    # ------------------------------------------------------------------
    geom1 = model.java.component("comp1").geom("geom1")
    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()

    Lx = xmax - xmin   # comprimento em X (unidade do modelo, ex: µm)
    Ly = ymax - ymin   # altura em Y
    Lz = zmax - zmin   # profundidade em Z (extrusão)

    # Área da seção transversal (para stress nominal = F / A0)
    A0 = Ly * Lz

    # Deslocamento máximo a aplicar (mesma unidade que a geometria)
    delta_max = max_strain * Lx
    delta_start = min_strain * Lx
    step_size = (delta_max - delta_start) / n_steps

    epsilon = 1e-5 * Lx

    # ------------------------------------------------------------------
    # Parâmetro global controlado pela varredura paramétrica
    # ------------------------------------------------------------------
    model.java.param().set("para_disp", "0", "DPX")

    # ------------------------------------------------------------------
    # Seleções de contorno
    # ------------------------------------------------------------------
    sel_left = model.java.component("comp1").selection().create("leftWall", "Box")
    sel_left.geom("geom1", 2)
    sel_left.set("xmin", xmin - epsilon)
    sel_left.set("xmax", xmin + epsilon)
    sel_left.set("ymin", ymin);  sel_left.set("ymax", ymax)
    sel_left.set("zmin", zmin);  sel_left.set("zmax", zmax)
    sel_left.set("condition", "allvertices")

    sel_right = model.java.component("comp1").selection().create("rightWall", "Box")
    sel_right.geom("geom1", 2)
    sel_right.set("xmin", xmax - epsilon)
    sel_right.set("xmax", xmax + epsilon)
    sel_right.set("ymin", ymin)
    sel_right.set("ymax", ymax)
    sel_right.set("zmin", zmin)
    sel_right.set("zmax", zmax)
    sel_right.set("condition", "allvertices")

    sel_top = model.java.component("comp1").selection().create("topWall", "Box")
    sel_top.geom("geom1", 2)
    sel_top.set("xmin", xmin)
    sel_top.set("xmax", xmax)
    sel_top.set("ymin", ymax - epsilon)
    sel_top.set("ymax", ymax + epsilon)
    sel_top.set("zmin", zmin)
    sel_top.set("zmax", zmax)
    sel_top.set("condition", "allvertices")

    sel_bot = model.java.component("comp1").selection().create("botWall", "Box")
    sel_bot.geom("geom1", 2)
    sel_bot.set("xmin", xmin)
    sel_bot.set("xmax", xmax)
    sel_bot.set("ymin", ymin - epsilon)
    sel_bot.set("ymax", ymin + epsilon)
    sel_bot.set("zmin", zmin)
    sel_bot.set("zmax", zmax)
    sel_bot.set("condition", "allvertices")

    # ------------------------------------------------------------------
    # Física: Mecânica dos Sólidos
    # ------------------------------------------------------------------
    physics = model.java.component("comp1").physics().create(
        "solid", "SolidMechanics", "geom1"
    )

    # BC 1: Fixed (engastamento total) na parede esquerda
    fix1 = physics.create("fix1", "Fixed", 2)
    fix1.selection().named("leftWall")

    # BC 2: Deslocamento prescrito apenas em X na parede direita
    #   Direction = [1,0,0] → prescreve u_x, deixa u_y e u_z livres
    disp1 = physics.create("disp1", "Displacement2", 2)
    disp1.selection().named("rightWall")
    # Prescreve apenas u_x (index 0); y e z ficam livres
    disp1.setIndex("Direction", "prescribed", 0)  # x → prescrito
    if force==1:
        disp1.setIndex("U0", "para_disp", 0)         
    else:
        disp1.setIndex("U0", "-para_disp", 0)         

    # ------------------------------------------------------------------
    # Material
    # ------------------------------------------------------------------
    mat = model.java.component("comp1").material().create("mat1", "Common")
    mat.propertyGroup("def").set("youngsmodulus",  str(young_mod))
    mat.propertyGroup("def").set("poissonsratio",  str(poisson_ratio))
    mat.propertyGroup("def").set("density",        str(density))

    # ------------------------------------------------------------------
    # Operadores de acoplamento
    # intop1 : integração da força de reação na parede fixa
    # maxop1 : máximo de von Mises no volume
    # ------------------------------------------------------------------
    intop = model.java.component("comp1").cpl().create("intop1", "Integration")
    intop.selection().geom("geom1", 2)
    intop.selection().named("leftWall")

    maxop = model.java.component("comp1").cpl().create("maxop1", "Maximum")
    maxop.selection().geom("geom1", 3)
    maxop.selection().all()

    aveop_top = model.java.component("comp1").cpl().create("aveop_top", "Average")
    aveop_top.selection().geom("geom1", 2)
    aveop_top.selection().named("topWall")

    aveop_bot = model.java.component("comp1").cpl().create("aveop_bot", "Average")
    aveop_bot.selection().geom("geom1", 2)
    aveop_bot.selection().named("botWall")

    intop_vol = model.java.component("comp1").cpl().create("intop_vol", "Integration")
    intop_vol.selection().geom("geom1", 3)
    intop_vol.selection().all()

    # ------------------------------------------------------------------
    # Estudo: Estacionário + Varredura Paramétrica em para_disp
    # ------------------------------------------------------------------
    study = model.java.study().create("std1")
    stat_step = study.create("stat", "Stationary")
    stat_step.set("geometricNonlinearity", NonLinear)  # Ativa Não-Linearidade Geométrica (Grandes Deformações)

    param_step = study.create("param", "Parametric")
    param_step.set("sweeptype", "sparse")
    param_step.setIndex("pname",    "para_disp", 0)
    param_step.setIndex("plistarr", f"range({delta_start},{step_size},{delta_max})[um]", 0)
    param_step.setIndex("punit",    "um", 0)

    # ------------------------------------------------------------------
    # Configuração da solução — deixa o COMSOL gerar a sequência automática
    # (equivalente a Study > createAutoSequences no Java de referência)
    # ------------------------------------------------------------------
    study.createAutoSequences("all")

    # Roda a varredura paramétrica completa
    # sol2 é criado pelo createAutoSequences para o estudo paramétrico
    model.java.sol("sol1").runAll()
    model.build()

    # ------------------------------------------------------------------
    # Exportar tabela global: [Fx, u_x, max_mises] por passo
    # ------------------------------------------------------------------
    base_dir  = os.path.dirname(os.path.abspath(file_path))
    plots_dir = os.path.join(os.path.dirname(base_dir), "plots")
    os.makedirs(plots_dir, exist_ok=True)

    global_data_path = os.path.abspath(file_path.replace(".mph", "_monotonic.txt"))

    tbl = model.java.result().table().create("tbl1", "Table")
    tbl.comments("Compressão Monotônica — Força de Reação, Deslocamento, Tensão Máxima")

    gev = model.java.result().numerical().create("gev1", "EvalGlobal")
    gev.set("expr", [
        "intop1(solid.sx)",     # Integração do stress normal na parede fixa dá a força de reação em X
        "para_disp",            # Deslocamento prescrito
        "maxop1(solid.mises)",  # Tensão de von Mises máxima no volume
        "aveop_top(v)",         # Deslocamento Y médio no teto
        "aveop_bot(v)",         # Deslocamento Y médio no piso
        "intop_vol(1)",         # Volume sólido exato (m³)
    ])
    gev.set("unit", ["N", "m", "Pa", "m", "m", "m^3"]) # Força a extração em unidades do SI
    gev.set("descr", ["F_rx [N]", "u_x [m]", "sigma_max [Pa]", "v_top [m]", "v_bot [m]", "Vol [m^3]"])
    gev.set("table", "tbl1")
    gev.setResult()

    tbl_export = model.java.result().export().create("tblexp1", "Table")
    tbl_export.set("filename", global_data_path)
    tbl_export.set("table",    "tbl1")
    tbl_export.run()

    # ------------------------------------------------------------------
    # Plots do último passo (maior deformação / instante pré-falha)
    # ------------------------------------------------------------------
    # Plot 1: Tensão de von Mises
    pg1 = model.java.result().create("pg1", "PlotGroup3D")
    pg1.create("surf1", "Surface")
    pg1.feature("surf1").set("expr", "solid.mises")
    pg1.set("titletype", "manual")
    pg1.set("title", f"Tensão de von Mises — passo final (strain={max_strain:.0%})")

    img1_path = os.path.join(plots_dir, "monotonic_stress_final.png")
    img1 = model.java.result().export().create("img1", "Image")
    img1.set("plotgroup",  "pg1")
    img1.set("filename",   img1_path)
    img1.set("size",       "manualprint")
    img1.set("unit",       "mm")
    img1.set("height",     "150")
    img1.set("width",      "200")
    img1.set("resolution", "300")
    img1.run()

    # Plot 2: Deslocamento total
    pg2 = model.java.result().create("pg2", "PlotGroup3D")
    pg2.create("surf2", "Surface")
    pg2.feature("surf2").set("expr", "solid.disp")
    pg2.set("titletype", "manual")
    pg2.set("title", f"Deslocamento total — passo final (strain={max_strain:.0%})")

    img2_path = os.path.join(plots_dir, "monotonic_disp_final.png")
    img2 = model.java.result().export().create("img2", "Image")
    img2.set("plotgroup",  "pg2")
    img2.set("filename",   img2_path)
    img2.set("size",       "manualprint")
    img2.set("unit",       "mm")
    img2.set("height",     "150")
    img2.set("width",      "200")
    img2.set("resolution", "300")
    img2.run()

    # ------------------------------------------------------------------123
    # Salvar modelo
    # ------------------------------------------------------------------
    model.save(file_path)
    print(f"Modelo salvo em: {file_path}")
    print(f"Dados globais exportados em: {global_data_path}")

    return model, global_data_path, A0, Lx, Ly


def apply_physics_stiffness(model, young_mod, poisson_ratio, density, load_val, file_path, maxiter=100,save_data=False,NonLinear=False,pre_solve=None,cuda=False):
    """
    Simulação para extração de dados de rigidez (Kxx, Kxy, Kxz).
    Usa deslocamentos prescritos e varredura paramétrica (axial: 1, 2, 3), 
    similar ao modelo Java exportado.
    """
    geom1 = model.java.component("comp1").geom("geom1")
    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()
    Lx = xmax - xmin
    Ly = ymax - ymin
    epsilonx = 1e-5 * Lx
    epsilony = 1e-5 * Ly

    model.java.param().set("axial", "1")
    model.java.param().set("F0", f"{load_val}[N]")

    # Selecoes
    sel_left = model.java.component("comp1").selection().create("leftWall", "Box")
    sel_left.geom("geom1", 2)
    sel_left.set("xmin", xmin - epsilonx)
    sel_left.set("xmax", xmin + epsilonx)
    sel_left.set("ymin", ymin)
    sel_left.set("ymax", ymax)
    sel_left.set("zmin", zmin)
    sel_left.set("zmax", zmax)
    sel_left.set("condition", "allvertices")

    sel_right = model.java.component("comp1").selection().create("rightWall", "Box")
    sel_right.geom("geom1", 2)
    sel_right.set("xmin", xmax - epsilonx)
    sel_right.set("xmax", xmax + epsilonx)
    sel_right.set("ymin", ymin)
    sel_right.set("ymax", ymax)
    sel_right.set("zmin", zmin)
    sel_right.set("zmax", zmax)
    sel_right.set("condition", "allvertices")


    sel_left = model.java.component("comp1").selection().create("downWall", "Box")
    sel_left.geom("geom1", 2)
    sel_left.set("xmin", xmin)
    sel_left.set("xmax", xmax)
    sel_left.set("ymin", ymin - epsilony)
    sel_left.set("ymax", ymin + epsilony)
    sel_left.set("zmin", zmin)
    sel_left.set("zmax", zmax)
    sel_left.set("condition", "allvertices")

    sel_left = model.java.component("comp1").selection().create("upWall", "Box")
    sel_left.geom("geom1", 2)
    sel_left.set("xmin", xmin)
    sel_left.set("xmax", xmax)
    sel_left.set("ymin", ymax - epsilony)
    sel_left.set("ymax", ymax + epsilony)
    sel_left.set("zmin", zmin)
    sel_left.set("zmax", zmax)
    sel_left.set("condition", "allvertices")
    

    # Fisica
    physics = model.java.component("comp1").physics().create("solid", "SolidMechanics", "geom1")
    
    fix1 = physics.create("fix1", "Fixed", 2)
    fix1.selection().named("leftWall")

    bndl1 = physics.create("bndl1", "BoundaryLoad", 2)
    bndl1.selection().named("rightWall")
    bndl1.set("forceType", "ForceArea")
    bndl1.set("forceReferenceArea", ["(axial==1)*F0", "(axial==2)*F0", "(axial==3)*F0"])

    # Material
    mat = model.java.component("comp1").material().create("mat1", "Common")
    mat.propertyGroup("def").set("youngsmodulus", str(young_mod))
    mat.propertyGroup("def").set("poissonsratio", str(poisson_ratio))
    mat.propertyGroup("def").set("density", str(density))

    # Operador de integracao na parede fixa
    intop1 = model.java.component("comp1").cpl().create("intop1", "Integration")
    intop1.set("method", "summation")
    intop1.selection().geom("geom1", 2)
    intop1.selection().named("leftWall")

    # Operador de media na parede movel
    aveop1 = model.java.component("comp1").cpl().create("aveop1", "Average")
    aveop1.selection().geom("geom1", 2)
    aveop1.selection().named("rightWall")

    aveop1 = model.java.component("comp1").cpl().create("aveop2", "Average")
    aveop1.selection().geom("geom1", 2)
    aveop1.selection().named("leftWall")

    aveop1 = model.java.component("comp1").cpl().create("aveop3", "Average")
    aveop1.selection().geom("geom1", 2)
    aveop1.selection().named("upWall")

    aveop1 = model.java.component("comp1").cpl().create("aveop4", "Average")
    aveop1.selection().geom("geom1", 2)
    aveop1.selection().named("downWall")

    # Variaveis Kxx, Kxy, Kxz, P1
    var = model.java.component("comp1").variable().create("var1")
    var.set("Kxx", "abs(intop1(solid.RFx)/aveop1(u))")
    var.set("Kxy", "abs(intop1(solid.RFy)/aveop1(v))")
    var.set("Kxz", "abs(intop1(solid.RFz)/aveop1(w))")
    var.set("ep_x", "aveop1(u)-aveop2(u)")
    var.set("ep_y", "aveop3(v)-aveop4(v)")
    var.set("poisson", "-ep_y/ep_x")

    # Estudo
    study = model.java.study().create("std1")
    stat = study.create("stat", "Stationary")
    stat.set("geometricNonlinearity", NonLinear)
    
    param = study.create("param", "Parametric")
    param.set("sweeptype", "sparse")
    param.setIndex("pname", "axial", 0)
    param.setIndex("plistarr", "range(1,1,3)", 0)
    
    study.createAutoSequences("all")
    model.java.sol("sol1").feature("s1").feature("fc1").set("ntermauto", "itertol")
    model.java.sol("sol1").feature("s1").feature("fc1").set("niter", str(maxiter))

    model.java.component("comp1").mesh().create("mesh1")
    model.java.component("comp1").mesh("mesh1").contribute("geom/detail", True)
    model.java.component("comp1").mesh("mesh1").run()
    if cuda:
        try:
            model.java.sol("sol1").feature("s1").feature("fc1").set("linsolver", "dDef")
            model.java.sol("sol1").feature("s1").feature("dDef").set("linsolver", "cudss")
        except:
            print("NO CUDA")
            pass
    if pre_solve!=None:
        model.build()
        model.save(file_path)
    model.java.sol("sol1").runAll()
    model.build()

    # Resultados
    if file_path!=None:
        import os
        base_dir  = os.path.dirname(os.path.abspath(file_path))
        os.makedirs(base_dir, exist_ok=True)

        if save_data:
            tbl = model.java.result().table().create("tbl1", "Table")
            tbl.comments("Stiffness Evaluation")
    
            gev = model.java.result().numerical().create("gev1", "EvalGlobal")
            gev.set("expr", ["Kxx", "Kxy", "Kxz", "poisson"])
            gev.set("table", "tbl1")
            gev.setResult()
    
            global_data_path = os.path.abspath(file_path.replace(".mph", "_stiffness.txt"))
            tbl_export = model.java.result().export().create("tblexp1", "Table")
            tbl_export.set("filename", global_data_path)
            tbl_export.set("table", "tbl1")
            tbl_export.run()
            print(f"Dados de rigidez exportados em: {global_data_path}")
        
        model.save(file_path)
        print(f"Modelo salvo em: {file_path}")

    return model



def create_physics_stiffness(model, e, h, metric, young_mod, poisson_ratio, density, load_val, direction, file_path):
    """
    Cria a física para extração de dados de rigidez (Kxx, Kxy, Kxz).
    Define seleções, condições de contorno, material, operadores de
    acoplamento e variáveis. Usa deslocamentos prescritos com varredura
    paramétrica (axial: 1, 2, 3).
    """
    geom1 = model.java.component("comp1").geom("geom1")
    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()
    Lx = xmax - xmin
    Ly = ymax - ymin
    epsilonx = 1e-5 * Lx
    epsilony = 1e-5 * Ly

    model.java.param().set("disp", "1")

    # Selecoes
    sel_left = model.java.component("comp1").selection().create("leftWall", "Box")
    sel_left.geom("geom1", 2)
    sel_left.set("xmin", xmin - epsilonx)
    sel_left.set("xmax", xmin + epsilonx)
    sel_left.set("ymin", ymin)
    sel_left.set("ymax", ymax)
    sel_left.set("zmin", zmin - epsilonx)
    sel_left.set("zmax", zmax + epsilonx)
    sel_left.set("condition", "allvertices")

    sel_right = model.java.component("comp1").selection().create("rightWall", "Box")
    sel_right.geom("geom1", 2)
    sel_right.set("xmin", xmax - epsilonx)
    sel_right.set("xmax", xmax + epsilonx)
    sel_right.set("ymin", ymin)
    sel_right.set("ymax", ymax)
    sel_right.set("zmin", zmin - epsilonx)
    sel_right.set("zmax", zmax + epsilonx)
    sel_right.set("condition", "allvertices")

    sel_down = model.java.component("comp1").selection().create("downWall", "Box")
    sel_down.geom("geom1", 2)
    sel_down.set("xmin", xmin)
    sel_down.set("xmax", xmax)
    sel_down.set("ymin", ymin - epsilony)
    sel_down.set("ymax", ymin + epsilony)
    sel_down.set("zmin", zmin)
    sel_down.set("zmax", zmax)
    sel_down.set("condition", "allvertices")

    sel_up = model.java.component("comp1").selection().create("upWall", "Box")
    sel_up.geom("geom1", 2)
    sel_up.set("xmin", xmin)
    sel_up.set("xmax", xmax)
    sel_up.set("ymin", ymax - epsilony)
    sel_up.set("ymax", ymax + epsilony)
    sel_up.set("zmin", zmin)
    sel_up.set("zmax", zmax)
    sel_up.set("condition", "allvertices")

    union1 = model.java.component("comp1").selection().create("union1", "Union")
    union1.geom("geom1", 2)
    union1.set("input", ["downWall", "upWall"])

    
    # Fisica
    physics = model.java.component("comp1").physics().create("solid", "SolidMechanics", "geom1")


    dis1 = physics.create("disp1", "Displacement2", 2)
    dis1.setIndex("Direction", "prescribed", 0)
    dis1.setIndex("Direction", "prescribed", 1)
    dis1.setIndex("Direction", "prescribed", 2)
    if direction == "x":
        dis1.selection().named("rightWall")
        dis1.setIndex("U0", "0.5*disp*"+str(Lx)+"["+metric+"]", 0)
    else:
        dis1.selection().named("upWall")
        dis1.setIndex("U0", "0.5*disp*"+str(Ly)+"["+metric+"]", 1)

    dis2 = physics.create("disp2", "Displacement2", 2)
    dis2.setIndex("Direction", "prescribed", 0)
    dis2.setIndex("Direction", "prescribed", 1)
    dis2.setIndex("Direction", "prescribed", 2)
    if direction == "x":
        dis2.selection().named("leftWall")
        dis2.setIndex("U0", "-0.5*disp*"+str(Lx)+"["+metric+"]", 0)
    else:
        dis2.selection().named("downWall")
        dis2.setIndex("U0", "-0.5*disp*"+str(Ly)+"["+metric+"]", 1)

    
    # Material
    mat = model.java.component("comp1").material().create("mat1", "Common")
    mat.propertyGroup("def").set("youngsmodulus", str(young_mod))
    mat.propertyGroup("def").set("poissonsratio", str(poisson_ratio))
    mat.propertyGroup("def").set("density", str(density))

    # Operador de integracao na parede fixa
    intop1 = model.java.component("comp1").cpl().create("intop1", "Integration")
    intop1.set("method", "summation")
    intop1.selection().geom("geom1", 2)
    intop1.selection().named("leftWall")
    
    # Operadores de media nas paredes
    aveop1 = model.java.component("comp1").cpl().create("aveop1", "Average")
    aveop1.selection().geom("geom1", 2)
    aveop1.selection().named("rightWall")

    aveop2 = model.java.component("comp1").cpl().create("aveop2", "Average")
    aveop2.selection().geom("geom1", 2)
    aveop2.selection().named("leftWall")

    aveop3 = model.java.component("comp1").cpl().create("aveop3", "Average")
    aveop3.selection().geom("geom1", 2)
    aveop3.selection().named("upWall")

    aveop4 = model.java.component("comp1").cpl().create("aveop4", "Average")
    aveop4.selection().geom("geom1", 2)
    aveop4.selection().named("downWall")

    # Variaveis
    var = model.java.component("comp1").variable().create("var1")
    var.set("ep_x", "aveop1(u)-aveop2(u)")
    var.set("ep_y", "aveop3(v)-aveop4(v)")
    if direction == "x":
        var.set("poisson", "-ep_y/ep_x")
    else:
        var.set("poisson", "-ep_x/ep_y")


    model.java.component("comp1").mesh().create("mesh1")
    model.java.component("comp1").mesh("mesh1").contribute("geom/detail", True)
    model.java.component("comp1").mesh("mesh1").run()
    if file_path!=None:
        model.save(file_path)
    return model
    
def _create_study_force(model, NonLinear=False):
    """
    Cria o estudo Stationary + varredura paramétrica (axial 1..3).
    NÃO cria o sol1 (cada função de solver é responsável por isso).
    """
    study = model.java.study().create("std1")
    stat = study.create("stat", "Stationary")
    stat.set("geometricNonlinearity", NonLinear)
    study.createAutoSequences("all")
    
    return study

def _create_study_disp_param(model, p_list, NonLinear=False):
    """
    Cria o estudo Stationary + varredura paramétrica (axial 1..3).
    NÃO cria o sol1 (cada função de solver é responsável por isso).
    """
    study = model.java.study().create("std1")
    stat = study.create("stat", "Stationary")
    stat.set("geometricNonlinearity", NonLinear)

    param = study.create("param", "Parametric")
    param.set("sweeptype", "sparse")
    param.setIndex("pname", "disp", 0)
    param.setIndex("plistarr", str(p_list), 0)
    study.createAutoSequences("all")

    return study

def _create_study_disp(model, disp,NonLinear=False):
    """
    Cria o estudo Stationary + varredura paramétrica (axial 1..3).
    NÃO cria o sol1 (cada função de solver é responsável por isso).
    """
    study = model.java.study().create("std1")
    stat = study.create("stat", "Stationary")
    stat.set("geometricNonlinearity", NonLinear)

    model.java.param().set("disp", str(disp))
    study.createAutoSequences("all")

    return study


def create_solver_direct(model, NonLinear=False, maxiter=100, file_path=None):
    """
    Cria um solver Stationary com solver linear DIRETO (default do Comsol).
    Equivalente ao Java:

        model.sol().create("sol1");
        model.sol("sol1").study("std1");
        model.sol("sol1").create("s1", "Stationary");
        model.sol("sol1").feature("s1").create("d1", "Direct");
        model.sol("sol1").feature("s1").feature("fcDef").set("linsolver", "d1");
    """
    _create_study(model, NonLinear=NonLinear)

    s1 = model.java.sol("sol1").feature("s1")
    s1.feature("fc1").set("linsolver", "d1")
    s1.feature("fc1").set("ntermauto", "itertol")
    s1.feature("fc1").set("niter", str(maxiter))

    if file_path!=None:
        model.save(file_path)
    
    return model

def create_solver_iterative(model, BC, disp, NonLinear=False, maxiter=100, file_path=None):
    """
    Cria um solver Stationary com solver linear ITERATIVO.
    Equivalente ao Java fornecido:

        model.sol().create("sol1");
        model.sol("sol1").study("std1");
        model.sol("sol1").create("s1", "Stationary");
        model.sol("sol1").feature("s1").create("d1", "Direct");
        model.sol("sol1").feature("s1").create("i1", "Iterative");
        model.sol("sol1").feature("s1").feature("fcDef").set("linsolver", "i1");
    """
    if BC == "force":
        _create_study_force(model, NonLinear=NonLinear)
    if BC == "disp":
        _create_study_disp(model, disp, NonLinear=NonLinear)

    s1 = model.java.sol("sol1").feature("s1")
    s1.feature("fc1").set("linsolver", "i1")
    s1.feature("fc1").set("ntermauto", "itertol")
    s1.feature("fc1").set("niter", str(maxiter))

    if file_path!=None:
        model.save(file_path)
    
    return model

def create_solver_cuda(model, NonLinear=False, maxiter=100, file_path=None):
    """
    Cria um solver Stationary usando o solver linear CUDA (cudss),
    com fallback para Direct caso CUDA não esteja disponível.
    """
    _create_study(model, NonLinear=NonLinear)

    sol = model.java.sol().create("sol1")
    sol.study("std1")
    sol.create("st1", "StudyStep")
    s1 = sol.create("s1", "Stationary")
    s1.create("d1", "Direct")
    s1.create("dDef", "Direct")
    s1.feature("fcDef").set("ntermauto", "itertol")
    s1.feature("fcDef").set("niter", str(maxiter))

    try:
        s1.feature("dDef").set("linsolver", "cudss")
        s1.feature("fcDef").set("linsolver", "dDef")
    except Exception:
        print("NO CUDA - fallback para Direct (d1)")
        s1.feature("fcDef").set("linsolver", "d1")

    if file_path!=None:
        model.save(file_path)
    
    return model
