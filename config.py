# =====================================================================
# CONFIGURAÇÃO DO EXPERIMENTO: METAMATERIAL AUXÉTICO + ATUADOR TÉRMICO
# =====================================================================
# Todas as dimensões de geometria estão na unidade SCALE["unit"].
# O atuador é um chevron eletrotérmico (V-beam) igual ao thermal_auxetic.java,
# e é escalado automaticamente de acordo com o tamanho do metamaterial.

# ================================
# GEOMETRIA DA CÉLULA (igual ao COMSOL.py / Gridgen.py)
# ================================
# Convenção usada para montar a célula (Gridgen.auxetic_cell):
#   sx     -> largura da haste (l) 
#   sy     -> altura da célula (h)
#   widht  -> espessura das paredes (e)
#   extrude-> espessura fora do plano (é a espessura de TODO o dispositivo,
#             atuador incluso, pois tudo sai do mesmo work plane)
GEOMETRY = {
    "array": False,     # True -> replica a célula H x V vezes
    "H": 1,             # nº de células na horizontal
    "V": 1,             # nº de células na vertical
    "sx": 1,
    "sy/sx": 1.2,
    "theta": 60,        # graus
    "widht/sx": 0.1,
    "extrude/sx": 5,
    "fillet/sx": 0,
}

# ================================
# ESCALA FÍSICA
# ================================
SCALE = {
    "scale": 10,        # multiplica todas as dimensões da célula
    "unit": "um",       # 'nm', 'um', 'mm' ou 'm'
}

# ================================
# ATUADOR TÉRMICO (chevron do thermal_auxetic.java)
# ================================
# Os valores "ref" são o projeto original do .java (em µm, escala 1).
# Todas as dimensões do atuador = valor_ref * s_act.
#   scale_mode = 'auto'   -> s_act é escolhido para que a largura do shutter
#                            (2*B_0) seja shutter_to_meta_width * largura do metamaterial
#   scale_mode = 'manual' -> s_act = manual_scale (1.0 reproduz o .java)
# Obs.: no modo 'block' (EXPERIMENT["actuator_mode"]) o atuador não é criado,
# mas s_act continua sendo usado para escalar os blocos (block_thickness_ref).
ACTUATOR = {
    "scale_mode": "auto",
    "shutter_to_meta_width": 1.0,
    "manual_scale": 1.0,

    # --- vigas inclinadas ---
    "N_beam": 8,              # nº de vigas de cada lado
    "theta_beam": 30,         # inclinação das vigas (graus)
    "L_0_ref": 3000,          # comprimento da viga (µm)
    "b_0_ref": 50,            # largura da viga (µm)
    "B_0_ref": 100,           # largura dos pads / meio shutter (µm)
    "beam_pitch/b_0": 3,      # delta_array = 3*b_0

    # --- dissipador (aletas entre shutter e pads de dissipação) ---
    "N_sink": 14,             # nº de aletas de cada lado
    "L_sink_ref": 400,        # comprimento das aletas (µm)
    "b_sink_ref": 10,         # largura das aletas (µm)
    "sink_pitch/b_sink": 10,  # delta_sink = 10*b_sink
    "sink_offset/b_sink": 2,  # y_sink = y_sink_shutter + 2*b_sink

    # --- ligação atuador -> metamaterial ---
    "link_gap_ref": 100,      # comprimento da haste entre dissipador e metamaterial (µm)
    "link_width/shutter": 1.0,# largura da haste / largura do shutter (2*B_0)
    "plate_thickness_ref": 0, # placa de largura = metamaterial (0 = sem placa) (µm)

    # --- bloco de fixação no topo do metamaterial (r2 do wp2 no .java) ---
    # Usado quando EXPERIMENT["top_bc"] = 'block'.
    "block_thickness_ref": 20,  # espessura do bloco (µm, escala com s_act)
    "block_width/meta": 1.0,    # largura do bloco / largura do metamaterial
    "block_anchor": "outer",    # 'outer'  -> face superior do bloco (como os pads)
                                # 'bottom' -> face z=0 do bloco (ancorado no substrato)
}

# ================================
# MATERIAL (Si monocristalino, igual ao .java)
# ================================
MATERIAL = {
    "model": "anisotropic",   # 'anisotropic' (C11, C12, C44 com T) ou 'isotropic' (E, nu)
    "E": 170e9,               # Young (Pa) - usado no modo isotrópico
    "nu": 0.28,               # Poisson    - usado no modo isotrópico
    "rho": 2329,              # densidade (kg/m^3)
    "theta_rot": 0,           # rotação cristalográfica no plano do wafer (graus)
    "rel_permittivity": 11.7,
    # Funções dependentes da temperatura (T em K) - mesmas do .java
    # (no modo 'block' não há transferência de calor: C11/C12/C44 são avaliados em T0)
    "k(T)": "130*(300/T)^(1.25)",                                        # W/(m*K)
    "alpha(T)": "(3.725*(1-exp(-5.88e-3*(T-124))) + 5.548e-4*T)*1e-6",  # 1/K
    "sigma(T)": "1/(5e-5*(1 + 1.8e-3*(T-300) + 1.5e-6*(T-300)^2))",     # S/m
    "Cp(T)": "712 + 0.44*(T-300) - 1.2e-4*(T-300)^2",                    # J/(kg*K)
    "C11(T)": "165.7[GPa]*(1 - 9.4e-5[1/K]*(T - 298.15[K]))",
    "C12(T)": "63.9[GPa]*(1 - 9.4e-5[1/K]*(T - 298.15[K]))",
    "C44(T)": "79.6[GPa]*(1 - 6.5e-5[1/K]*(T - 298.15[K]))",
}

# ================================
# EXPERIMENTO
# ================================
EXPERIMENT = {
    # Como a carga é aplicada no metamaterial:
    #   'thermal' -> atuador chevron eletrotérmico (simulação completa:
    #                mecânica + calor + corrente elétrica, varredura em corrente)
    #   'block'   -> o atuador é trocado por um bloco de carga sob o metamaterial,
    #                igual ao bloco do topo; só mecânica (bem mais rápido).
    #                Configuração da carga em LOAD_BLOCK.
    "actuator_mode": "block",

    # Corrente no terminal (pad direito); pad esquerdo aterrado.
    #   'scaled'   -> I_nom = I_ref * (b_0*h_0/L_0) / (b_ref*h_ref/L_ref)
    #                 (mantém o aquecimento Joule comparável ao projeto original)
    #   'absolute' -> usa I_list diretamente (mA)
    "current_mode": "scaled",
    "I_ref": 150,             # mA no projeto de referência (.java)
    "h_ref": 50,              # espessura de referência (µm)
    "I_factors": [0.25, 0.5, 0.75, 1.0],   # varredura: I = fator * I_nom
    "I_list": [50, 100, 150], # mA (modo 'absolute')

    "T0": 293.15,             # temperatura dos pads (K)

    # Direção de tensionamento NO REFERENCIAL DA CÉLULA (o atuador sempre
    # empurra ao longo do y global):
    #   'y' -> célula na orientação original (eixo y da célula // atuador)
    #   'x' -> célula rotacionada 90° no plano xy (eixo x da célula // atuador)
    "load_dir": "y",

    # Condição no topo do metamaterial:
    #   'block'  -> bloco de fixação sobre o metamaterial, ancorado (fixo + T0),
    #               como no dispositivo real do .java
    #   'fixed'  -> engaste direto na face do topo + T0
    #   'roller' -> só v = 0 (permite expansão lateral livre)
    #   'free'   -> sem restrição (atuador apenas empurra)
    "top_bc": "block",
}

# ================================
# BLOCO DE CARGA (usado só com EXPERIMENT["actuator_mode"] = 'block')
# ================================
# Um bloco igual ao do topo é colocado sob o metamaterial, no lugar do atuador.
# A carga é aplicada na face inferior desse bloco, na direção y global.
# Sinal: valores POSITIVOS = compressão (bloco sobe contra o metamaterial);
#        valores negativos = tração.
LOAD_BLOCK = {
    #   'displacement' -> deslocamento prescrito; o CSV traz a força de reação
    #   'force'        -> força total prescrita; o CSV traz o deslocamento do bloco
    "load_type": "force",

    # --- deslocamento prescrito ---
    #   'strain'   -> d = strain * H_meta (deformação nominal do metamaterial)
    #   'absolute' -> d em unidade do modelo (SCALE["unit"])
    "disp_mode": "strain",
    "strain_list": [0.005, 0.01, 0.015, 0.02],
    "disp_list": [0.05, 0.1, 0.15, 0.2],

    # --- força prescrita (força total na face inferior do bloco) ---
    "force_unit": "uN",
    "force_list": [100, 200, 300, 400],

    # True -> trava u e w na face inferior do bloco (ele só se move em y,
    #         como uma garra guiada). False -> lateral livre.
    "guided": True,

    # Dimensões do bloco de carga (None = iguais às do bloco do topo)
    "thickness_ref": None,    # µm, escala com s_act (como block_thickness_ref)
    "width/meta": None,       # largura do bloco / largura do metamaterial
}

# ================================
# COMSOL / SIMULAÇÃO
# ================================
SIMULATION = {
    "NonLinear": False,       # não linearidade geométrica
    "maxiter": 100,
    "cuda": False,            # usa cuDSS como solver linear
    "mesh_size": 4,           # autoMeshSize (1 = extremamente fina ... 9 = extremamente grossa)
    "remove_details": 0.01,   # tamanho absoluto p/ RemoveDetails (0 ou None desliga)
    "cores": None,            # nº de núcleos do servidor COMSOL (None = padrão)
}

# ================================
# SAÍDA
# ================================
OUTPUT = {
    "folder": "results",
    "csv": "experiments.csv",             # CSV das rodadas com atuador térmico
    "csv_block": "experiments_block.csv", # CSV das rodadas com bloco de carga
    "save_mph": True,         # salva o .mph de cada rodada
    "preview": True,          # salva PNG com o layout 2D antes de rodar o COMSOL
    "tag": "",                # rótulo livre para identificar a rodada no CSV
    # Colunas extras no CSV (temperaturas, potência, tensão elétrica, força de reação).
    # Com False, o CSV fica só com tensão, Poisson, deformação e deslocamento.
    "extra_outputs": False,
}
