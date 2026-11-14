"""Tabelas de apoio (nomes de pistas, sessões, pneus, eventos)."""

PISTAS = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Xangai", 3: "Sakhir (Bahrein)",
    4: "Barcelona-Catalunha", 5: "Mônaco", 6: "Montreal", 7: "Silverstone",
    8: "Hockenheim", 9: "Hungaroring", 10: "Spa-Francorchamps", 11: "Monza",
    12: "Singapura", 13: "Suzuka", 14: "Abu Dhabi", 15: "Austin (COTA)",
    16: "Interlagos", 17: "Red Bull Ring", 18: "Sochi", 19: "Cidade do México",
    20: "Baku", 21: "Sakhir (curto)", 22: "Silverstone (curto)",
    23: "Austin (curto)", 24: "Suzuka (curto)", 25: "Hanói", 26: "Zandvoort",
    27: "Ímola", 28: "Portimão", 29: "Jeddah", 30: "Miami", 31: "Las Vegas",
    32: "Lusail (Catar)", 39: "Silverstone (invertido)",
    40: "Red Bull Ring (invertido)", 41: "Zandvoort (invertido)",
}

SESSOES = {
    0: "Desconhecida", 1: "Treino Livre 1", 2: "Treino Livre 2",
    3: "Treino Livre 3", 4: "Treino Curto", 5: "Q1", 6: "Q2", 7: "Q3",
    8: "Classificação Curta", 9: "Classificação Volta Única",
    10: "Sprint Shootout 1", 11: "Sprint Shootout 2", 12: "Sprint Shootout 3",
    13: "Sprint Shootout Curto", 14: "Sprint Shootout Volta Única",
    15: "Corrida", 16: "Corrida 2", 17: "Corrida 3", 18: "Time Trial",
}
SESSOES_QUALI = set(range(5, 15))
SESSOES_CORRIDA = {15, 16, 17}

CLIMA = {0: "Céu limpo", 1: "Poucas nuvens", 2: "Nublado",
         3: "Chuva fraca", 4: "Chuva forte", 5: "Tempestade"}

# Composto visual -> (letra, nome, cor convencional da F1)
PNEUS = {
    16: ("M", "Macio", "#e8382f"),
    17: ("MD", "Médio", "#f2c200"),
    18: ("D", "Duro", "#d9d9d6"),
    7: ("I", "Intermediário", "#2ba84a"),
    8: ("C", "Chuva", "#2f74d0"),
    15: ("C", "Chuva", "#2f74d0"),
}


def pneu(visual):
    return PNEUS.get(visual, ("?", f"Composto {visual}", "#999999"))


STATUS_RESULTADO = {0: "inválido", 1: "inativo", 2: "ativo", 3: "terminou",
                    4: "não terminou", 5: "desclassificado",
                    6: "não classificado", 7: "aposentado"}

EVENTOS = {
    "SSTA": "Início da sessão", "SEND": "Fim da sessão",
    "FTLP": "Volta mais rápida", "RTMT": "Abandono", "DRSE": "DRS liberado",
    "DRSD": "DRS desativado", "TMPT": "Companheiro nos boxes",
    "CHQF": "Bandeira quadriculada", "RCWN": "Vencedor", "PENA": "Penalidade",
    "SPTP": "Speed trap", "STLG": "Luzes de largada", "LGOT": "Largada",
    "DTSV": "Drive-through cumprido", "SGSV": "Stop & go cumprido",
    "FLBK": "Flashback", "BUTN": "Botão", "RDFL": "Bandeira vermelha",
    "OVTK": "Ultrapassagem", "SCAR": "Safety car", "COLL": "Colisão",
}

PENALIDADES = {
    0: "Drive-through", 1: "Stop & go", 2: "Punição no grid",
    3: "Lembrete de punição", 4: "Punição de tempo", 5: "Advertência",
    6: "Desclassificado", 7: "Removido da volta de apresentação",
    8: "Parado tempo demais", 9: "Regulamento de pneus",
    10: "Volta invalidada", 11: "Volta atual e próxima invalidadas",
    12: "Volta invalidada", 13: "Volta atual e próxima invalidadas",
    14: "Volta atual e anterior invalidadas", 15: "Volta atual e anterior invalidadas",
    16: "Abandono", 17: "Bandeira preta",
}

INFRACOES = {
    0: "bloqueio por andar devagar", 1: "bloqueio na contramão", 2: "ré na largada",
    3: "colisão grave", 4: "colisão leve", 5: "não devolveu posição após colisão",
    6: "não devolveu posições após colisão", 7: "corte de pista com ganho de tempo",
    8: "ultrapassagem cortando pista", 9: "ultrapassagens cortando pista",
    10: "cruzou a linha de saída dos boxes", 11: "ignorou bandeira azul",
    12: "ignorou bandeira amarela", 13: "ignorou drive-through",
    14: "drive-throughs demais", 15: "cumprir drive-through em N voltas",
    16: "cumprir drive-through nesta volta", 17: "excesso de velocidade no pit",
    18: "parado tempo demais", 19: "regulamento de pneus", 20: "punições demais",
    21: "várias advertências", 22: "perto da desclassificação",
    23: "regulamento de pneus", 24: "regulamento de pneus",
    25: "corte de pista (volta invalidada)", 26: "passou dos limites da pista (volta invalidada)",
    27: "corte de pista (ganho leve)", 28: "corte de pista (ganho significativo)",
    29: "corte de pista (ganho extremo)", 30: "andou no muro (volta invalidada)",
    31: "flashback usado (volta invalidada)", 32: "reset para a pista (volta invalidada)",
    33: "bloqueio no pit lane", 34: "queima de largada", 35: "colisão com safety car",
    36: "ultrapassagem ilegal sob safety car", 37: "ritmo acima do permitido sob SC",
    38: "ritmo acima do permitido sob VSC", 39: "volta de apresentação lenta demais",
    40: "estacionou na volta de apresentação", 41: "falha mecânica",
    42: "dano terminal", 43: "ficou longe demais do safety car",
    44: "bandeira preta", 45: "stop & go não cumprido", 46: "drive-through não cumprido",
    47: "troca de componente do motor", 48: "troca de câmbio", 49: "mudança em parc fermé",
    50: "punição de grid da liga", 51: "punição por retry", 52: "ganho de tempo ilegal",
    53: "pit stop obrigatório", 54: "atributo atribuído",
}

SAFETY_CAR = {0: "Sem SC", 1: "Safety Car", 2: "Virtual Safety Car", 3: "SC volta de apresentação"}
SAFETY_CAR_EVENTO = {0: "acionado", 1: "recolhendo", 2: "recolhido", 3: "volta retomada"}

# Nome do GP (usado no nome da pasta de cada fim de semana)
GPS = {
    0: "Australia", 2: "China", 3: "Bahrein", 4: "Espanha", 5: "Monaco", 6: "Canada",
    7: "Gra-Bretanha", 9: "Hungria", 10: "Belgica", 11: "Italia", 12: "Singapura",
    13: "Japao", 14: "Abu Dhabi", 15: "Estados Unidos", 16: "Brasil", 17: "Austria",
    19: "Mexico", 20: "Azerbaijao", 26: "Holanda", 27: "Emilia-Romanha",
    29: "Arabia Saudita", 30: "Miami", 31: "Las Vegas", 32: "Catar",
    39: "Gra-Bretanha (invertido)", 40: "Austria (invertido)", 41: "Holanda (invertido)",
}
