import mph
import os
import numpy as np



def comsol_model_unitcell(h, l, theta, e, young_mod, poisson_ratio, density,
                           extrude, fillet, metric,geom_path,file_path):

    theta = np.radians(theta)
    
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
    # Extrude do working plane
    # --------------------------------------------------
    geom.create("ext1", "Extrude")
    geom.feature("ext1").set("workplane", "wp1")

    # Seleciona apenas o espaço nao vazio
    geom.feature("ext1").selection("input").set(["wp1.dif1"])

    geom.feature("ext1").set("distance", str(extrude))

    geom.run("ext1")


    geom.run()

    
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

    model.java.component("comp1").geom("geom1").lengthUnit(metric)

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
    #model.java.sol('sol1').runAll()
    model.build()

    # --------------------------------------------------
    # SALVAR MODELO
    # --------------------------------------------------
    model.save(file_path)

    return model