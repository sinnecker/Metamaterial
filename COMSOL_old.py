import mph
import os
import numpy as np


def build_geometry(client,H, V, h, l, theta, e, extrude, fillet, metric, geom_path, file_path,array=False):
    '''
    Cria a geometria no COMSOL dxf -> caomsol geom -> array -> extrude
    '''

    
    # parâmetros de celula
    theta = np.radians(theta)
    dx = l * np.sin(theta) #distancia horizontal
    dy = l * np.cos(theta) #distancia vertical
    alpha = np.pi/2 - theta #angulo externo
    
    # distancias para fazer o grid
    de = e * np.tan(alpha)/2 + e / np.sin(theta) 
    dz = 2*h - 2*dy  
    dV = dz + 2*de  
    dH = 2*dx + e 


    # Cria a componente Geometrica
    model = client.create('Deformacao_Mecanica')
    model.java.component().create('comp1', True)
    geom = model.java.component('comp1').geom().create('geom1', 3)
    geom.geomRep('cadps')
    geom.designBooleans(True)


    # Cria a geometria 2D (work plane)
    geom.create('wp1', 'WorkPlane')
    geom.feature('wp1').set('unite', False)
    geom.feature('wp1').set('selresult', True)
    wp = geom.feature('wp1').geom()


    # Importa o DXF
    wp.create('imp1', 'Import')
    wp.feature('imp1').set('filename', geom_path)
    wp.feature('imp1').set('alllayers', ['EXTERIOR', 'HOLES'])
    wp.feature('imp1').set('repairgeom', False) # Mantém os contornos como vieram do DX
    wp.feature('imp1').set('selindividual', False)
    wp.run('imp1')

    # Gera os buracos na célula
    wp.create('dif1', 'Difference')
    wp.feature('dif1').selection('input').set('imp1(1)')
    wp.feature('dif1').selection('input2').set('imp1(2)')
    wp.run('dif1')
    geom.run()
    geom1 = model.java.component('comp1').geom('geom1')

    # Fillet
    if fillet>0:

        ### Bounding box dos vertices para o fillet
        xmin, xmax, ymin, ymax, _, _ = geom1.getBoundingBox()
        epsilon = (xmax-xmin)*1e-4
        wp.create('bbox1', 'BoxSelection')
        wp.feature('bbox1').set('entitydim', '0') 
        wp.feature('bbox1').set('xmin', xmin+epsilon)
        wp.feature('bbox1').set('xmax', xmax-epsilon)
        wp.feature('bbox1').set('ymin', -epsilon)
        wp.feature('bbox1').set('ymax', l*np.cos(theta)-epsilon)
        wp.run('bbox1')
    
        wp.create('bbox2', 'BoxSelection')
        wp.feature('bbox2').set('entitydim', '0') 
        wp.feature('bbox2').set('xmin', xmin+epsilon)
        wp.feature('bbox2').set('xmax', xmax-epsilon)
        wp.feature('bbox2').set('ymin', h-l*np.cos(theta)+epsilon)
        wp.feature('bbox2').set('ymax', h+epsilon)
        wp.run('bbox2')
    
        wp.create('unisel1', 'UnionSelection')
        wp.feature('unisel1').set('entitydim', '0')
        wp.feature('unisel1').set('input', ['bbox1', 'bbox2'])
        wp.run('unisel1')
    

        # Cria o fillet
        wp.create('fil1', 'Fillet')
        wp.feature('fil1').selection('pointinsketch').named('unisel1')
        wp.feature('fil1').set('radius', fillet)
        wp.run('fil1')


    # Cria o array 2D
    if array:
        wp.create('arr1', 'Array')
        if fillet>0:
            wp.feature('arr1').selection('input').set('fil1') 
        else:
            wp.feature('arr1').selection('input').set('dif1') 
        wp.feature('arr1').set('displ', [str(dH),str(dV)])
        wp.feature('arr1').set('fullsize',[str(H),str(V)])
        wp.run('arr1')
        wp.create('uni_arr', 'Union')
        wp.feature('uni_arr').selection('input').set('arr1')
        wp.feature('uni_arr').set('intbnd', False)
        wp.run('uni_arr')

        
    # Extrude
    geom.create('ext1', 'Extrude')
    geom.feature('ext1').set('workplane', 'wp1')
    if array:
        geom.feature('ext1').selection('input').set('wp1.uni_arr')
    else:
        geom.feature('ext1').selection('input').set('wp1.dif1')

    geom.feature('ext1').set('distance', str(extrude))
    geom.run('ext1')
    geom.run('fin');
    geom.feature().create('rmd1', 'RemoveDetails');
    geom.feature('rmd1').set('detailsizetype', 'absolute');
    geom.feature('rmd1').set('maxabssize', '0.01');
    geom.run('rmd1');
    geom.run()

    # Unidade de comprimento
    model.java.component('comp1').geom('geom1').lengthUnit(metric)

    # Salva o modelo
    if file_path!=None:
        model.build()
        model.save(file_path)
        
    return model

def apply_physics(model, young_mod, poisson_ratio, density, file_path, force, force_value, NonLinear, plot_data, cuda):
    
    # Selecionando as faces para condiçoes de contorno
    geom1 = model.java.component('comp1').geom('geom1')
    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()
    epsilon = 1e-5 * (xmax-xmin)

    #Parede Esquerda

    sel_left = model.java.component('comp1').selection().create('leftWall', 'Box')
    sel_left.geom('geom1', 2)
    sel_left.set('xmin', xmin - epsilon)
    sel_left.set('xmax', xmin)
    sel_left.set('ymin', ymin)
    sel_left.set('ymax', ymax)
    sel_left.set('zmin', zmin)
    sel_left.set('zmax', zmax)
    sel_left.set('condition', 'allvertices')

    #Parede Direita

    sel_right = model.java.component('comp1').selection().create('rightWall', 'Box')
    sel_right.geom('geom1', 2)
    sel_right.set('xmin', xmax - epsilon)
    sel_right.set('xmax', xmax + epsilon)
    sel_right.set('ymin', ymin)
    sel_right.set('ymax', ymax)
    sel_right.set('zmin', zmin)
    sel_right.set('zmax', zmax)
    sel_right.set('condition', 'allvertices')

    # Fisica
    physics = model.java.component('comp1').physics().create('solid','SolidMechanics','geom1')
    fix = physics.create('fix1', 'Fixed', 2)
    fix.selection().named('leftWall')
    load1 = physics.create('load1', 'BoundaryLoad', 2)
    load1.selection().named('rightWall')
    load1.set('forceType', force)
    load1.set('force', [str(k) for k in force_value])

    # Dados do material
    mat = model.java.component('comp1').material().create('mat1', 'Common')
    mat.propertyGroup('def').set('youngsmodulus', str(young_mod))
    mat.propertyGroup('def').set('poissonsratio', str(poisson_ratio))
    mat.propertyGroup('def').set('density', str(density))

    # Cria o study
    study = model.java.study().create('std1')
    stat_step = study.create('stat', 'Stationary')
    stat_step.set('geometricNonlinearity', NonLinear)
    
    # Cria a solucao
    model.java.sol().create('sol1')
    model.java.sol('sol1').study('std1')
    model.java.sol('sol1').create('st1', 'StudyStep')
    model.java.sol('sol1').feature('st1').set('study', 'std1')
    model.java.sol('sol1').create('v1', 'Variables')
    model.java.sol('sol1').create('s1', 'Stationary')
    if cuda:
        model.java.sol('sol1').feature('s1').feature('dDef').set('linsolver', 'cudss')
    
    # Salva o modelo
    if file_path!=None:
        model.build()
        model.save(file_path)
    model.java.sol('sol1').runAll()
    model.build()

    return model



def create_physics_disp(model, e, h, metric, young_mod, poisson_ratio, density, direction, file_path):
    '''
    Cria a física do modelo
    '''

    # Dimensões do problema
    geom1 = model.java.component('comp1').geom('geom1')
    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()
    Lx = xmax - xmin
    Ly = ymax - ymin
    epsilonx = 1e-5 * Lx
    epsilony = 1e-5 * Ly

    model.java.param().set('disp', '1')

    # Selecoes das faces para aplicar a física
    sel_left = model.java.component('comp1').selection().create('leftWall', 'Box')
    sel_left.geom('geom1', 2)
    sel_left.set('xmin', xmin - epsilonx)
    sel_left.set('xmax', xmin + epsilonx)
    sel_left.set('ymin', ymin)
    sel_left.set('ymax', ymax)
    sel_left.set('zmin', zmin - epsilonx)
    sel_left.set('zmax', zmax + epsilonx)
    sel_left.set('condition', 'allvertices')

    sel_right = model.java.component('comp1').selection().create('rightWall', 'Box')
    sel_right.geom('geom1', 2)
    sel_right.set('xmin', xmax - epsilonx)
    sel_right.set('xmax', xmax + epsilonx)
    sel_right.set('ymin', ymin)
    sel_right.set('ymax', ymax)
    sel_right.set('zmin', zmin - epsilonx)
    sel_right.set('zmax', zmax + epsilonx)
    sel_right.set('condition', 'allvertices')

    sel_down = model.java.component('comp1').selection().create('downWall', 'Box')
    sel_down.geom('geom1', 2)
    sel_down.set('xmin', xmin)
    sel_down.set('xmax', xmax)
    sel_down.set('ymin', ymin - epsilony)
    sel_down.set('ymax', ymin + epsilony)
    sel_down.set('zmin', zmin)
    sel_down.set('zmax', zmax)
    sel_down.set('condition', 'allvertices')

    sel_up = model.java.component('comp1').selection().create('upWall', 'Box')
    sel_up.geom('geom1', 2)
    sel_up.set('xmin', xmin)
    sel_up.set('xmax', xmax)
    sel_up.set('ymin', ymax - epsilony)
    sel_up.set('ymax', ymax + epsilony)
    sel_up.set('zmin', zmin)
    sel_up.set('zmax', zmax)
    sel_up.set('condition', 'allvertices')

    union1 = model.java.component('comp1').selection().create('union1', 'Union')
    union1.geom('geom1', 2)
    union1.set('input', ['downWall', 'upWall'])

    
    # Fisica (deslocamento)
    physics = model.java.component('comp1').physics().create('solid', 'SolidMechanics', 'geom1')


    dis1 = physics.create('disp1', 'Displacement2', 2)
    dis1.setIndex('Direction', 'prescribed', 0)
    dis1.setIndex('Direction', 'prescribed', 1)
    dis1.setIndex('Direction', 'prescribed', 2)
    if direction == 'x':
        dis1.selection().named('rightWall')
        dis1.setIndex('U0', '0.5*disp*'+str(Lx)+'['+metric+']', 0)
    else:
        dis1.selection().named('upWall')
        dis1.setIndex('U0', '0.5*disp*'+str(Ly)+'['+metric+']', 1)

    dis2 = physics.create('disp2', 'Displacement2', 2)
    dis2.setIndex('Direction', 'prescribed', 0)
    dis2.setIndex('Direction', 'prescribed', 1)
    dis2.setIndex('Direction', 'prescribed', 2)
    if direction == 'x':
        dis2.selection().named('leftWall')
        dis2.setIndex('U0', '-0.5*disp*'+str(Lx)+'['+metric+']', 0)
    else:
        dis2.selection().named('downWall')
        dis2.setIndex('U0', '-0.5*disp*'+str(Ly)+'['+metric+']', 1)

    
    # Propriedades do material
    mat = model.java.component('comp1').material().create('mat1', 'Common')
    mat.propertyGroup('def').set('youngsmodulus', str(young_mod))
    mat.propertyGroup('def').set('poissonsratio', str(poisson_ratio))
    mat.propertyGroup('def').set('density', str(density))

    # Operador de integracao na parede fixa
    intop1 = model.java.component('comp1').cpl().create('intop1', 'Integration')
    intop1.set('method', 'summation')
    intop1.selection().geom('geom1', 2)
    intop1.selection().named('leftWall')
    
    # Operadores de media nas paredes
    aveop1 = model.java.component('comp1').cpl().create('aveop1', 'Average')
    aveop1.selection().geom('geom1', 2)
    aveop1.selection().named('rightWall')

    aveop2 = model.java.component('comp1').cpl().create('aveop2', 'Average')
    aveop2.selection().geom('geom1', 2)
    aveop2.selection().named('leftWall')

    aveop3 = model.java.component('comp1').cpl().create('aveop3', 'Average')
    aveop3.selection().geom('geom1', 2)
    aveop3.selection().named('upWall')

    aveop4 = model.java.component('comp1').cpl().create('aveop4', 'Average')
    aveop4.selection().geom('geom1', 2)
    aveop4.selection().named('downWall')

    # Variaveis
    var = model.java.component('comp1').variable().create('var1')
    var.set('ep_x', 'aveop1(u)-aveop2(u)')
    var.set('ep_y', 'aveop3(v)-aveop4(v)')
    if direction == 'x':
        var.set('poisson', '-ep_y/ep_x')
    else:
        var.set('poisson', '-ep_x/ep_y')


    model.java.component('comp1').mesh().create('mesh1')
    model.java.component('comp1').mesh('mesh1').contribute('geom/detail', True)
    model.java.component('comp1').mesh('mesh1').run()
    if file_path!=None:
        model.save(file_path)
    return model
    
def create_physics_force(model, e, h, metric, young_mod, poisson_ratio, density, direction, file_path):
    '''
    Cria a física do modelo
    '''

    # Dimensões do problema
    geom1 = model.java.component('comp1').geom('geom1')
    xmin, xmax, ymin, ymax, zmin, zmax = geom1.getBoundingBox()
    Lx = xmax - xmin
    Ly = ymax - ymin
    epsilonx = 1e-5 * Lx
    epsilony = 1e-5 * Ly

    model.java.param().set('F0', '1')

    # Selecoes das faces para aplicar a física
    sel_left = model.java.component('comp1').selection().create('leftWall', 'Box')
    sel_left.geom('geom1', 2)
    sel_left.set('xmin', xmin - epsilonx)
    sel_left.set('xmax', xmin + epsilonx)
    sel_left.set('ymin', ymin)
    sel_left.set('ymax', ymax)
    sel_left.set('zmin', zmin - epsilonx)
    sel_left.set('zmax', zmax + epsilonx)
    sel_left.set('condition', 'allvertices')

    sel_right = model.java.component('comp1').selection().create('rightWall', 'Box')
    sel_right.geom('geom1', 2)
    sel_right.set('xmin', xmax - epsilonx)
    sel_right.set('xmax', xmax + epsilonx)
    sel_right.set('ymin', ymin)
    sel_right.set('ymax', ymax)
    sel_right.set('zmin', zmin - epsilonx)
    sel_right.set('zmax', zmax + epsilonx)
    sel_right.set('condition', 'allvertices')

    sel_down = model.java.component('comp1').selection().create('downWall', 'Box')
    sel_down.geom('geom1', 2)
    sel_down.set('xmin', xmin)
    sel_down.set('xmax', xmax)
    sel_down.set('ymin', ymin - epsilony)
    sel_down.set('ymax', ymin + epsilony)
    sel_down.set('zmin', zmin)
    sel_down.set('zmax', zmax)
    sel_down.set('condition', 'allvertices')

    sel_up = model.java.component('comp1').selection().create('upWall', 'Box')
    sel_up.geom('geom1', 2)
    sel_up.set('xmin', xmin)
    sel_up.set('xmax', xmax)
    sel_up.set('ymin', ymax - epsilony)
    sel_up.set('ymax', ymax + epsilony)
    sel_up.set('zmin', zmin)
    sel_up.set('zmax', zmax)
    sel_up.set('condition', 'allvertices')

    union1 = model.java.component('comp1').selection().create('union1', 'Union')
    union1.geom('geom1', 2)
    union1.set('input', ['downWall', 'upWall'])

    
    # Fisica força 
    physics = model.java.component('comp1').physics().create('solid', 'SolidMechanics', 'geom1')


    fix1 = physics.create("fix1", "Fixed", 2)
    if direction == 'x':
        fix1.selection().named("leftWall")

        bndl1 = physics.create("bndl1", "BoundaryLoad", 2)
        bndl1.selection().named("rightWall")
        bndl1.set("forceType", "ForceArea")
        bndl1.set("forceReferenceArea", ["F0", "0", "0"])
    if direction =='y':
        fix1.selection().named("downWall")
        
        bndl1 = physics.create("bndl1", "BoundaryLoad", 2)
        bndl1.selection().named("upWall")
        bndl1.set("forceType", "ForceArea")
        bndl1.set("forceReferenceArea", ["0", "F0", "0"])

    
    # Propriedades do material
    mat = model.java.component('comp1').material().create('mat1', 'Common')
    mat.propertyGroup('def').set('youngsmodulus', str(young_mod))
    mat.propertyGroup('def').set('poissonsratio', str(poisson_ratio))
    mat.propertyGroup('def').set('density', str(density))

    # Operador de integracao na parede fixa
    intop1 = model.java.component('comp1').cpl().create('intop1', 'Integration')
    intop1.set('method', 'summation')
    intop1.selection().geom('geom1', 2)
    intop1.selection().named('leftWall')
    
    # Operadores de media nas paredes
    aveop1 = model.java.component('comp1').cpl().create('aveop1', 'Average')
    aveop1.selection().geom('geom1', 2)
    aveop1.selection().named('rightWall')

    aveop2 = model.java.component('comp1').cpl().create('aveop2', 'Average')
    aveop2.selection().geom('geom1', 2)
    aveop2.selection().named('leftWall')

    aveop3 = model.java.component('comp1').cpl().create('aveop3', 'Average')
    aveop3.selection().geom('geom1', 2)
    aveop3.selection().named('upWall')

    aveop4 = model.java.component('comp1').cpl().create('aveop4', 'Average')
    aveop4.selection().geom('geom1', 2)
    aveop4.selection().named('downWall')

    # Variaveis
    var = model.java.component('comp1').variable().create('var1')
    var.set('ep_x', 'aveop1(u)-aveop2(u)')
    var.set('ep_y', 'aveop3(v)-aveop4(v)')
    if direction == 'x':
        var.set('poisson', '-ep_y/ep_x')
    else:
        var.set('poisson', '-ep_x/ep_y')


    model.java.component('comp1').mesh().create('mesh1')
    model.java.component('comp1').mesh('mesh1').contribute('geom/detail', True)
    model.java.component('comp1').mesh('mesh1').run()
    if file_path!=None:
        model.save(file_path)
    return model




def create_solver_direct(model, BC, Value, NonLinear=False, maxiter=100, file_path=None):
    '''
    Cria um solver Stationary com solver linear DIRETO (default do Comsol)
    '''
    study = model.java.study().create('std1')
    stat = study.create('stat', 'Stationary')
    stat.set('geometricNonlinearity', NonLinear)
    
    if BC == 'force':
        model.java.param().set('F0', str(Value))
    if BC == 'disp':
        model.java.param().set('disp', str(Value))

    study.createAutoSequences('all')

    s1 = model.java.sol('sol1').feature('s1')
    s1.feature('fc1').set('linsolver', 'd1')
    s1.feature('fc1').set('ntermauto', 'itertol')
    s1.feature('fc1').set('niter', str(maxiter))

    if file_path!=None:
        model.save(file_path)
    
    return model

def create_solver_iterative(model, BC, Value, NonLinear=False, maxiter=100, file_path=None):
    '''
    Cria um solver Stationary com solver linear ITERATIVO.
    '''

    study = model.java.study().create('std1')
    stat = study.create('stat', 'Stationary')
    stat.set('geometricNonlinearity', NonLinear)
    
    if BC == 'force':
        model.java.param().set('F0', str(Value))
    if BC == 'disp':
        model.java.param().set('disp', str(Value))

    study.createAutoSequences('all')
    
    s1 = model.java.sol('sol1').feature('s1')
    s1.feature('fc1').set('linsolver', 'i1')
    s1.feature('fc1').set('ntermauto', 'itertol')
    s1.feature('fc1').set('niter', str(maxiter))

    if file_path!=None:
        model.save(file_path)
    
    return model

