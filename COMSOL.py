import mph
import os
import numpy as np



def build_geometry(H, V, h, l, theta, e, extrude, fillet, metric, geom_path, array=False):

    theta = np.radians(theta)
    dx = l * np.cos(theta) #distancia horizontal
    dy = l * np.sin(theta) #distancia vertical
    alpha = np.pi/2 - theta
    #calcula o espaço entre as células
    de = e * np.tan(theta)/2 + e / np.sin(alpha) #espaço vertical entre as fileiras de celulas
    dz = 2*h - 2*dy  #espaço vertical de uma célula para outra
    dV = dz + 2*de 
    dH = 2*dx + e 
    
    # Inicia o cliente (usa o binário em /usr/local/bin/comsol automaticamente)
    client = mph.start()

    model = client.create("Deformacao_Mecanica")

    # --------------------------------------------------
    # Componente e geometria
    # --------------------------------------------------
    model.java.component().create("comp1", True)

    geom = model.java.component("comp1").geom().create("geom1", 3)
    geom.geomRep("cadps")
    geom.designBooleans(True)

    model.java.component("comp1").mesh().create("mesh1")
    model.java.component("comp1").mesh("mesh1").contribute("geom/detail", True)

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
    wp.feature("bbox1").set("ymin", -e)
    wp.feature("bbox1").set("ymax", l*np.sin(theta)-epsilon)

    wp.run("bbox1")

    wp.create("bbox2", "BoxSelection")
    wp.feature("bbox2").set("entitydim", "0") 

    wp.feature("bbox2").set("xmin", xmin+epsilon)
    wp.feature("bbox2").set("xmax", xmax-epsilon)
    wp.feature("bbox2").set("ymin", h-l*np.sin(theta)+epsilon)
    wp.feature("bbox2").set("ymax", h+e)

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
        wp.feature("arr1").selection("input").set("fil1") 
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


    geom.run()

    model.java.component("comp1").geom("geom1").lengthUnit(metric)
    return model

def apply_physics_compression(model, young_mod, poisson_ratio, density, file_path):
    
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
    load1.set("forceType", "ForceArea")
    load1.set("forceReferenceArea", ["300", "0", "0"])

    mat = model.java.component("comp1").material().create("mat1", "Common")

    mat.propertyGroup("def").set("youngsmodulus", str(young_mod))
    mat.propertyGroup("def").set("poissonsratio", str(poisson_ratio))
    mat.propertyGroup("def").set("density", str(density))

    study = model.java.study().create('std1')
    study.create('stat', 'Stationary')

    # 6. Solução
    model.java.sol().create('sol1')
    model.java.sol('sol1').study('std1')
    model.java.sol('sol1').create('st1', 'StudyStep')
    model.java.sol('sol1').feature('st1').set('study', 'std1')
    model.java.sol('sol1').create('v1', 'Variables')
    model.java.sol('sol1').create('s1', 'Stationary')
    
    # Roda a simulação de fato
    model.java.sol('sol1').runAll()
    model.build()

    # --------------------------------------------------
    # SALVAR MODELO
    # --------------------------------------------------
    model.save(file_path)
    
    # --------------------------------------------------
    # GERAR PLOTS (IMAGEM) E EXPORTAR DADOS (TEXTO)
    # --------------------------------------------------
    
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