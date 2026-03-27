import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
import ezdxf
import mph

def auxetic_cell(h=1.0, l=1.0, theta_deg=30,plot=False):
    # Recebe o valor da altura da unitcell h, tamanho da haste lateral l
    # angulo de entrada da haste lateral theta_deg(em graus)

    #Converte o angulo para radianos
    theta = np.radians(theta_deg)
    
    #Calcula o deslocamento em x e y da haste para o angulo theta
    dx = l * np.cos(theta)
    dy = l * np.sin(theta)

    #Calcula os pontos do poligono para formar a celula unitaria
    points = [
        (dx, h - dy),     #meio central superior
        (2*dx, h),        #direita superior
        (2*dx, 0),        #direita inferior
        (dx, dy),         #meio central inferior
        (0, 0),           #esquerda inferior
        (0, h),           #esquerda superior
        (dx, h - dy)      #fecha o poligono no ponto inicial
    ]
    
    #Plot da estrutura gerada
    if plot:
        x_coords, y_coords = zip(*points)
        plt.figure(figsize=(6, 6))
        plt.plot(x_coords, y_coords, 'bo-', linewidth=2, markersize=8)
        plt.fill(x_coords, y_coords, alpha=0.3, color='skyblue')
        plt.axhline(0, color='black', linewidth=0.5, linestyle='--')
        plt.axvline(0, color='black', linewidth=0.5, linestyle='--')
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.show()

    return points

def grid_gen(e, h, l, theta):

    #converte o angulo para radianos
    theta_rad = np.radians(theta)
    alpha = np.pi/2 - theta_rad #algulo auxiliar 90-theta

    #calcula as medidas da célula 
    dx = l * np.cos(theta_rad) #distancia horizontal
    dy = l * np.sin(theta_rad) #distancia vertical

    #calcula o espaço entre as células
    de = e * np.tan(theta_rad)/2 + e / np.sin(alpha) #espaço vertical entre as fileiras de celulas
    dz = 2*h - 2*dy  #espaço vertical de uma célula para outra

    #calcula a célula unitária
    unit_cell = auxetic_cell(h, l, theta) 

    #distancias fixas entre celulas
    dx_shift = dx + e/2 #distancia vertical

    all_polygons1 = [] #salva as células principais
    all_polygons2 = [] #salva as células entre as linhas principais
    all_polygons3 = [] #salva as bordas 

    for j in range(2):
        z = j * (dz + 2*de) #deslocamento vertical

        # condição fora do loop interno
        valid_row = (j < 1)


        new_poly1 = [] if valid_row else None 
        new_poly2 = [] 
        new_poly3 = [] 

        base_y_shift = z - h + dy - de

        for (x, y) in unit_cell:
            X = x 
            Y = y 

            if valid_row:#celula normal
                new_poly1.append((X, Y))

               
            new_poly2.append((
                    x + dx_shift,
                    y + base_y_shift
                ))

                
            new_poly3.append((
                    x - dx_shift,
                    y + base_y_shift
                ))


            if new_poly1:
                all_polygons1.append(new_poly1)
            
            all_polygons2.append(new_poly2)
            
            all_polygons3.append(new_poly3)
            
    
    xmin = min(all_polygons1[0])[0]
    xmax = max(all_polygons1[-1])[0]
    ymin = min(all_polygons3[0])[1]+h/2
    ymax = max(all_polygons3[-1])[1]-h/2

    bbox = [(xmin-e,ymin),
            (xmin-e,ymax),
            (xmax+e,ymax),
            (xmax+e,ymin)]
        
    return all_polygons1, all_polygons2, all_polygons3,bbox
    


def export_void_to_dxf(polygons, cell_polygon, filename="void_mesh.dxf"):

    #criar objetos shapely
    poly_objs = [Polygon(p) for p in polygons]

    #união das células para criar os buracos
    solid = unary_union(poly_objs)

    #cria uma caixa em volta dos poligonos
    cell = Polygon(cell_polygon)

    #retira os buracos da caixa
    void = cell.difference(solid)

    # criar DXF
    doc = ezdxf.new()
    msp = doc.modelspace()

    def add_polygon(poly):

        exterior = list(poly.exterior.coords)
        msp.add_lwpolyline(exterior, close=True,dxfattribs={"layer": "EXTERIOR"})

        for hole in poly.interiors:
            msp.add_lwpolyline(list(hole.coords), close=True, dxfattribs={"layer": "HOLES"})

    if void.geom_type == "Polygon":
        add_polygon(void)

    elif void.geom_type == "MultiPolygon":
        for p in void.geoms:
            add_polygon(p)

    doc.saveas(filename)

    return void


def generate_dxf(e, h, l, theta, filename="unit_cell.dxf"):
    
    poly1, poly2, poly3, bbox = grid_gen(e, h, l, theta)

    # junta TODOS os polígonos (buracos)
    all_polygons = poly1 + poly2 + poly3

    # exporta
    void = export_void_to_dxf(all_polygons, bbox, filename)

    return {
        "void": void,
        "bbox": bbox,
        "poly1": poly1,
        "poly2":poly2,
        "poly3":poly3
    }