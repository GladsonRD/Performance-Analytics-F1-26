"""
Transforma uma gravação .f1rec num dicionário com tudo que o relatório precisa.

Duas passadas pelo arquivo:
  1) sessão, pilotos, voltas, posições, eventos, estado do carro do jogador;
  2) telemetria detalhada (velocidade, pedais, marcha, posição no mapa) só dos
     carros que entram nas comparações (jogador + donos das voltas de referência).
"""

import math
import os
from collections import defaultdict
from datetime import datetime

import corrida
import curvas
import dicas
import leitor
from constantes import (CLIMA, EVENTOS, GPS, INFRACOES, PENALIDADES, PISTAS, SAFETY_CAR,
                        SAFETY_CAR_EVENTO, SESSOES, SESSOES_CORRIDA, SESSOES_QUALI, pneu)

L, T, S, D, M, T2 = leitor.LAP, leitor.TEL, leitor.STATUS, leitor.DANO, leitor.MOV, leitor.TEL2
iL = L.idx
iT = T.idx
iS = S.idx
iD = D.idx
iM = M.idx
iT2 = T2.idx
VEL = __import__('struct').Struct('<H')


def _ms_setor(ms, minutos):
    return minutos * 60000 + ms


def _cor_hex(c):
    return "#%02x%02x%02x" % (c.red, c.green, c.blue)


# ---------------------------------------------------------------- passada 1
def passada1(caminho):
    sess = {}
    pilotos = {}
    n_ativos = 0
    jogador = 0
    cont_jog = {}
    historico = {}           # carro -> objeto PacketSessionHistoryData mais recente
    final = None             # PacketFinalClassificationData
    eventos = []
    flashbacks = []          # (indice_registro, tempo_sessao)

    volta_atual = {}         # carro -> nº da volta
    conclusoes = defaultdict(list)   # carro -> [(volta, t_cruzamento, posicao)]
    pit_na_volta = defaultdict(set)  # carro -> {voltas com passagem pelo pit}
    tipo_volta = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # carro->volta->driver_status->n
    grid = {}
    speed_trap = {}
    ultimo_lap = {}
    terminou = set()
    bat_inicio = {}          # volta -> J no início do trecho cronometrado (jogador)
    tv_ant = {}

    # carro do jogador
    st_ult = None
    dano_bruto = None        # último pacote de danos (todos os carros)
    desgaste_carro = defaultdict(dict)  # carro -> volta -> [4 rodas]
    comb_inicial = None      # (kg, saldo em voltas) no começo da sessão
    ers_max = 4e6
    lim_recup = 0
    snap = {}                # volta -> dict
    status_bruto = None      # último pacote de status (todos os carros)
    ers_carro = defaultdict(dict)       # carro -> volta -> {usado, recup, fim} (J)
    bat_ini_carro = defaultdict(dict)   # carro -> volta -> J no início do trecho cronometrado
    tv_ant_carro = {}
    comb_carro = defaultdict(dict)      # carro -> volta -> kg de combustível no fim da volta
    pit_aberto = {}                     # carro -> parada em andamento
    paradas = defaultdict(list)         # carro -> [{volta, pit_lane_ms, parado_ms}]
    vmax_carro = defaultdict(int)       # velocidade máxima de cada carro com cronômetro rodando
    vmax_volta_carro = defaultdict(dict)  # carro -> volta -> velocidade máxima na volta
    saldo_carro = defaultdict(dict)     # carro -> volta -> saldo de combustível (voltas) no fim da volta
    temp_carro = defaultdict(lambda: defaultdict(lambda: [0, [0, 0, 0, 0], [0, 0, 0, 0], 0]))  # carro -> volta -> [n, superfície em curva, núcleo, n em curva]
    avisos_carro = defaultdict(int)     # advertências de limite de pista
    setup_jog = None
    acum = defaultdict(lambda: {"n": 0, "temp": [0, 0, 0, 0], "nucleo": [0, 0, 0, 0], "nc": 0, "curva": [0, 0, 0, 0], "vmax": 0, "freio_t": [0, 0, 0, 0]})
    vmax_sessao = 0

    sc_ult = 0
    sc_periodos = []         # [tipo, t_ini, t_fim]
    primeiro_t = None
    ultimo_t = 0
    ultimo_lider_volta = 0
    t_por_volta_lider = {}

    def fotografar(c, ant, posicao):
        """Guarda o estado do carro no fim da volta `ant`."""
        if status_bruto:
            sc_ = S.ler(status_bruto, c)
            if sc_[iS["fuel_in_tank"]] > 0:
                comb_carro[c][ant] = round(sc_[iS["fuel_in_tank"]], 2)
                saldo_carro[c][ant] = round(sc_[iS["fuel_remaining_laps"]], 2)
                ers_carro[c][ant] = {"usado": sc_[iS["ers_deployed_this_lap"]], "fim": sc_[iS["ers_store_energy"]],
                                     "recup": sc_[iS["ers_harvested_this_lap_mguk"]] + sc_[iS["ers_harvested_this_lap_mguh"]]}
        if dano_bruto:
            dd = D.ler(dano_bruto, c)
            desgaste_carro[c][ant] = [round(dd[iD[f"tyres_wear{k}"]], 1) for k in range(4)]
        if c != jogador:
            return
        a = acum[ant]
        s = {"volta": ant, "posicao": posicao, "vmax": a["vmax"]}
        if a["n"]:
            s["temp_pneus"] = [round(x / a["n"], 1) for x in a["temp"]]
            s["temp_nucleo"] = [round(x / a["n"], 1) for x in a["nucleo"]]
            if a["nc"]:
                s["temp_curva"] = [round(x / a["nc"], 1) for x in a["curva"]]   # superfície só em curva/freada
            s["temp_freios"] = [round(x / a["n"]) for x in a["freio_t"]]
        if st_ult:
            s["combustivel"] = round(st_ult[iS["fuel_in_tank"]], 3)
            s["saldo_comb"] = round(st_ult[iS["fuel_remaining_laps"]], 2)
            s["ers_bateria_j"] = st_ult[iS["ers_store_energy"]]
            s["ers_usado_j"] = st_ult[iS["ers_deployed_this_lap"]]
            s["ers_recuperado_j"] = (st_ult[iS["ers_harvested_this_lap_mguk"]] +
                                     st_ult[iS["ers_harvested_this_lap_mguh"]])
            s["ers_modo"] = st_ult[iS["ers_deploy_mode"]]
            s["pneu_visual"] = st_ult[iS["visual_tyre_compound"]]
            s["pneu_real"] = st_ult[iS["actual_tyre_compound"]]
            s["pneu_idade"] = st_ult[iS["tyres_age_laps"]]
        if dano_bruto:
            s["desgaste"] = desgaste_carro[c][ant]
        snap[ant] = s

    for idx, cab, dados in leitor.registros(caminho):
        pid = cab[5]
        t = cab[7]
        if primeiro_t is None:
            primeiro_t = t
        ultimo_t = max(ultimo_t, t)
        jog = cab[10]
        if jog < 22:
            # o índice do jogador pode mudar no fim da sessão (tela de resultado, espectador):
            # vale o que mais apareceu durante a gravação
            cont_jog[jog] = cont_jog.get(jog, 0) + 1
            jogador = jog

        if pid == 2:  # lap data
            for c in range(22):
                r = L.ler(dados, c)
                ultimo_lap[c] = r
                nv = r[iL["current_lap_num"]]
                if nv == 0:
                    continue
                if r[iL["grid_position"]]:
                    grid[c] = r[iL["grid_position"]]
                if r[iL["speed_trap_fastest_speed"]] > 0:
                    speed_trap[c] = r[iL["speed_trap_fastest_speed"]]
                ant = volta_atual.get(c)
                if ant is not None and nv == ant + 1:
                    t_cruz = t - r[iL["current_lap_time_in_ms"]] / 1000.0
                    conclusoes[c].append((ant, t_cruz, r[iL["car_position"]]))
                    fotografar(c, ant, r[iL["car_position"]])
                    if r[iL["car_position"]] == 1:
                        ultimo_lider_volta = nv
                if r[iL["result_status"]] == 3 and c not in terminou:
                    # cruzou a linha de chegada: fotografa a última volta enquanto os dados ainda valem
                    terminou.add(c)
                    if not (ant is not None and nv == ant + 1):
                        fotografar(c, nv, r[iL["car_position"]])
                volta_atual[c] = nv
                # paradas no box: tempo no pit lane e tempo parado
                ativo = r[iL["pit_lane_timer_active"]]
                pa_ = pit_aberto.get(c)
                if ativo:
                    if pa_ is None:
                        pa_ = pit_aberto[c] = {"volta": nv, "pit_lane_ms": 0, "parado_ms": 0}
                    pa_["pit_lane_ms"] = max(pa_["pit_lane_ms"], r[iL["pit_lane_time_in_lane_in_ms"]])
                    pa_["parado_ms"] = max(pa_["parado_ms"], r[iL["pit_stop_timer_in_ms"]])
                elif pa_ is not None:
                    pa_["pit_lane_ms"] = max(pa_["pit_lane_ms"], r[iL["pit_lane_time_in_lane_in_ms"]])
                    if pa_["pit_lane_ms"] > 3000:
                        paradas[c] = [x for x in paradas[c] if x["volta"] != pa_["volta"]] + [pa_]
                    pit_aberto.pop(c)
                tvc = r[iL["current_lap_time_in_ms"]]
                pa = tv_ant_carro.get(c)
                if tvc > 0 and status_bruto and (not pa or pa[0] != nv or pa[1] == 0 or tvc < pa[1] - 500):
                    b_ = S.ler(status_bruto, c)
                    if b_[iS["fuel_in_tank"]] > 0:
                        bat_ini_carro[c][nv] = b_[iS["ers_store_energy"]]
                tv_ant_carro[c] = (nv, tvc)
                if r[iL["corner_cutting_warnings"]] > avisos_carro[c]:
                    avisos_carro[c] = r[iL["corner_cutting_warnings"]]
                if c == jogador and st_ult:
                    tv = r[iL["current_lap_time_in_ms"]]
                    if tv > 0 and (tv_ant.get("v") != nv or tv_ant.get("t", 0) == 0 or tv < tv_ant.get("t", 0)):
                        bat_inicio[nv] = st_ult[iS["ers_store_energy"]]
                    tv_ant = {"v": nv, "t": tv}
                # na quali a volta de saída usa o mesmo número da lançada, mas sem cronômetro (tempo 0)
                if r[iL["current_lap_time_in_ms"]] > 0:
                    if r[iL["pit_status"]] > 0:
                        pit_na_volta[c].add(nv)
                    tipo_volta[c][nv][r[iL["driver_status"]]] += 1
                if r[iL["car_position"]] == 1:
                    ultimo_lider_volta = nv

        elif pid == 6 and jogador is not None:
            for c, ul in ultimo_lap.items():
                if ul[iL["current_lap_time_in_ms"]] > 0 and ul[iL["pit_status"]] == 0:
                    (vc,) = VEL.unpack_from(dados, leitor.TAM_CAB + c * T.st.size)
                    if vc > vmax_carro[c] and vc < 420:
                        vmax_carro[c] = vc
                    nvc = ul[iL["current_lap_num"]]
                    if vc < 420 and vc > vmax_volta_carro[c].get(nvc, 0):
                        vmax_volta_carro[c][nvc] = vc
                    rc = T.ler(dados, c)
                    nuc = [rc[iT[f"tyres_inner_temperature{k}"]] for k in range(4)]
                    if all(nuc):                 # online, carro com telemetria fechada manda zero
                        tc = temp_carro[c][nvc]
                        tc[0] += 1
                        for k in range(4):
                            tc[2][k] += nuc[k]
                        if abs(rc[iT["steer"]]) > 0.08 or rc[iT["brake"]] > 0.2:
                            tc[3] += 1
                            for k in range(4):
                                tc[1][k] += rc[iT[f"tyres_surface_temperature{k}"]]
            r = T.ler(dados, jogador)
            nv = volta_atual.get(jogador)
            if nv:
                a = acum[nv]
                a["n"] += 1
                for k in range(4):
                    a["temp"][k] += r[iT[f"tyres_surface_temperature{k}"]]
                    a["nucleo"][k] += r[iT[f"tyres_inner_temperature{k}"]]
                if abs(r[iT["steer"]]) > 0.08 or r[iT["brake"]] > 0.2:
                    a["nc"] += 1
                    for k in range(4):
                        a["curva"][k] += r[iT[f"tyres_surface_temperature{k}"]]
                    a["freio_t"][k] += r[iT[f"brakes_temperature{k}"]]
                v = r[iT["speed"]]
                if v > a["vmax"]:
                    a["vmax"] = v
                if v > vmax_sessao:
                    vmax_sessao = v

        elif pid == 5:
            o5 = leitor.objeto(5, dados).car_setup_data[jogador]
            if o5.front_left_tyre_pressure > 0:
                setup_jog = {n_: round(getattr(o5, n_), 2) for n_, _ in o5._fields_}

        elif pid == 7:
            status_bruto = dados
            novo = S.ler(dados, jogador)
            if novo[iS["fuel_in_tank"]] > 0 or st_ult is None:
                st_ult = novo
            if comb_inicial is None and st_ult[iS["fuel_in_tank"]] > 0:
                comb_inicial = (round(st_ult[iS["fuel_in_tank"]], 2), round(st_ult[iS["fuel_remaining_laps"]], 2))
            ers_max = max(ers_max, st_ult[iS["ers_store_energy"]])
            lim_recup = max(lim_recup, st_ult[iS["ers_harvest_limit_per_lap"]])

        elif pid == 10:
            dano_bruto = dados

        elif pid == 1:
            o = leitor.objeto(1, dados)
            sess = {
                "clima": o.weather, "temp_pista": o.track_temperature, "temp_ar": o.air_temperature,
                "voltas_total": o.total_laps, "comprimento": o.track_length, "tipo": o.session_type,
                "pista": o.track_id, "formula": o.formula, "duracao": o.session_duration,
                "s2": o.sector2_lap_distance_start, "s3": o.sector3_lap_distance_start,
                "dificuldade_ia": o.ai_difficulty, "online": o.network_game,
                "n_drs": o.num_drs_zones,
                "zonas_aero": [(z.zone_start, z.zone_end) for z in list(o.active_aero_zones_full)[:o.num_active_aero_zones_full]],
            }
            sc = o.safety_car_status
            if sc != sc_ult:
                if sc_ult and sc_periodos:
                    sc_periodos[-1][2] = t
                if sc:
                    sc_periodos.append([sc, t, None])
                sc_ult = sc

        elif pid == 4:
            o = leitor.objeto(4, dados)
            n_ativos = o.num_active_cars
            for c in range(22):
                p = o.participants[c]
                nome = p.name.decode("utf-8", "replace").strip("\x00").strip()
                if not nome and c >= n_ativos:
                    continue
                cor = _cor_hex(p.livery_colours[0]) if p.num_colours else None
                pilotos[c] = {"idx": c, "nome": nome or f"Carro {c + 1}", "numero": p.race_number,
                              "equipe": p.team_id, "ia": bool(p.ai_controlled), "cor": cor,
                              "telemetria_publica": bool(p.your_telemetry)}

        elif pid == 11:
            o = leitor.objeto(11, dados)
            historico[o.car_idx] = o

        elif pid == 8:
            final = leitor.objeto(8, dados)

        elif pid == 3:
            o = leitor.objeto(3, dados)
            cod = bytes(o.event_string_code).decode("ascii", "replace")
            d = o.event_details
            ev = {"t": round(t, 2), "cod": cod, "nome": EVENTOS.get(cod, cod)}
            if cod == "FLBK":
                tf = d.flashback.flashback_session_time
                flashbacks.append((idx, tf))
                ev["para"] = round(tf, 2)
                for c in conclusoes:
                    while conclusoes[c] and conclusoes[c][-1][1] > tf:
                        conclusoes[c].pop()
                eventos = [e for e in eventos if e["t"] <= tf]
            elif cod == "PENA":
                p = d.penalty
                ev.update(carro=p.vehicle_idx, outro=p.other_vehicle_idx, volta=p.lap_num,
                          texto=PENALIDADES.get(p.penalty_type, f"tipo {p.penalty_type}"),
                          motivo=INFRACOES.get(p.infringement_type, f"infração {p.infringement_type}"),
                          tempo=p.time)
            elif cod == "OVTK":
                ev.update(carro=d.overtake.overtaking_vehicle_idx, outro=d.overtake.being_overtaken_vehicle_idx)
            elif cod == "COLL":
                ev.update(carro=d.collision.vehicle1_idx, outro=d.collision.vehicle2_idx)
            elif cod == "FTLP":
                ev.update(carro=d.fastest_lap.vehicle_idx, tempo=round(d.fastest_lap.lap_time, 3))
            elif cod == "RTMT":
                ev.update(carro=d.retirement.vehicle_idx)
            elif cod == "SCAR":
                ev.update(texto=f"{SAFETY_CAR.get(d.safety_car.safety_car_type, '')} "
                                f"{SAFETY_CAR_EVENTO.get(d.safety_car.event_type, '')}".strip())
            elif cod in ("DTSV", "SGSV", "RCWN", "TMPT"):
                ev.update(carro=d.race_winner.vehicle_idx)
            elif cod in ("BUTN", "SPTP", "STLG"):
                continue
            ev["volta_lider"] = ultimo_lider_volta
            eventos.append(ev)

    # última volta: o carro não começa outra, então fotografa no fim da gravação se ela foi completada
    for c, nv in volta_atual.items():
        h = historico.get(c)
        completou = h is not None and h.num_laps >= nv and h.lap_history_data[nv - 1].lap_time_in_ms > 0
        if completou and nv not in desgaste_carro[c] and (c != jogador or nv not in snap):
            ultimo = ultimo_lap.get(c)
            fotografar(c, nv, ultimo[iL["car_position"]] if ultimo else 0)

    if sc_periodos and sc_periodos[-1][2] is None:
        sc_periodos[-1][2] = ultimo_t

    return dict(sess=sess, pilotos=pilotos, n_ativos=n_ativos, jogador=max(cont_jog, key=cont_jog.get) if cont_jog else jogador, historico=historico,
                final=final, eventos=eventos, flashbacks=flashbacks, conclusoes=conclusoes,
                pit_na_volta=pit_na_volta, tipo_volta=tipo_volta, grid=grid, speed_trap=speed_trap,
                snap=snap, vmax=vmax_sessao, desgaste_carro=desgaste_carro, comb_inicial=comb_inicial,
                ers_max=ers_max, lim_recup=lim_recup, bat_inicio=bat_inicio, ers_carro=ers_carro,
                bat_ini_carro=bat_ini_carro, comb_carro=comb_carro, saldo_carro=saldo_carro, vmax_volta_carro=vmax_volta_carro, temp_carro=temp_carro, paradas=paradas, vmax_carro=vmax_carro, avisos_carro=avisos_carro, setup_jog=setup_jog, sc=sc_periodos, duracao_real=ultimo_t - (primeiro_t or 0))


# ---------------------------------------------------------------- passada 2
def passada2(caminho, voltas_quero, jogador_mx=None):
    """Amostras cronológicas só das voltas pedidas.

    voltas_quero: carro -> conjunto de voltas (None = todas).
    amostra: (t, volta, dist, t_volta_ms, vel, acel, freio, marcha, volante, asa (aerodinâmica ativa: 1 = modo reta), pit, modo_bateria, bateria_J,
             temperaturas da superfície dos 4 pneus)
    Também devolve as amostras do pacote 13 (só o carro do jogador): (t, slip ratio[4], slip angle[4]).
    """
    carros = set(voltas_quero)
    amostras = {c: [] for c in carros}
    posicoes = {c: [] for c in carros}   # (t, volta, dist, x, z)
    cur = {}
    ot = {}
    modo = {}
    bat = {}
    mx = []

    def quero(c, volta):
        q = voltas_quero[c]
        return q is None or volta in q

    t_ant = 0.0
    for idx, cab, dados in leitor.registros(caminho):
        pid = cab[5]
        t = cab[7]
        # na largada da corrida o relógio da sessão volta a zero: o que veio antes (grid, volta de
        # apresentação) tem o mesmo número de volta e bagunçaria a 1ª volta, então é descartado
        # (só os pacotes de volta e de movimento contam: no fim da sessão o jogo manda eventos com o relógio
        # zerado, e isso apagava a sessão inteira)
        if pid in (0, 2):
            if t < 1.0 and t_ant > 5.0:
                for c in carros:
                    amostras[c].clear()
                    posicoes[c].clear()
                mx.clear()
            t_ant = t
        if pid == 2:
            for c in carros:
                r = L.ler(dados, c)
                cur[c] = (r[iL["current_lap_num"]], r[iL["lap_distance"]], r[iL["current_lap_time_in_ms"]],
                          r[iL["pit_status"]])
        elif pid == 6:
            for c in carros:
                k = cur.get(c)
                if not k or k[0] == 0 or not quero(c, k[0]):
                    continue
                r = T.ler(dados, c)
                amostras[c].append((t, k[0], k[1], k[2], r[iT["speed"]], r[iT["throttle"]], r[iT["brake"]],
                                    r[iT["gear"]], r[iT["steer"]], ot.get(c, 0), k[3], modo.get(c, 0), bat.get(c, 0),
                                    (r[iT["tyres_surface_temperature0"]], r[iT["tyres_surface_temperature1"]],
                                     r[iT["tyres_surface_temperature2"]], r[iT["tyres_surface_temperature3"]]),
                                    (r[iT["tyres_inner_temperature0"]], r[iT["tyres_inner_temperature1"]],
                                     r[iT["tyres_inner_temperature2"]], r[iT["tyres_inner_temperature3"]])))
        elif pid == 0:
            for c in carros:
                k = cur.get(c)
                if not k or k[0] == 0 or not quero(c, k[0]):
                    continue
                r = M.ler(dados, c)
                posicoes[c].append((t, k[0], k[1], r[iM["world_position_x"]], r[iM["world_position_z"]], r[iM["yaw"]]))
        elif pid == 7:
            for c in carros:
                r = S.ler(dados, c)
                modo[c] = r[iS["ers_deploy_mode"]]
                bat[c] = r[iS["ers_store_energy"]]
        elif pid == 16:
            for c in carros:
                ot[c] = T2.ler(dados, c)[iT2["active_aero_mode"]]
        elif pid == 13 and jogador_mx is not None:
            o13 = leitor.objeto(13, dados)
            mx.append((t, tuple(o13.wheel_slip_ratio), tuple(o13.wheel_slip_angle)))
        elif pid == 3 and dados[leitor.TAM_CAB:leitor.TAM_CAB + 4] == b"FLBK":
            o = leitor.objeto(3, dados)
            tf = o.event_details.flashback.flashback_session_time
            for lst in list(amostras.values()) + list(posicoes.values()) + [mx]:
                while lst and lst[-1][0] > tf:
                    lst.pop()
    return amostras, posicoes, mx


def _reamostrar(xs, ys, grade):
    """Interpolação linear de ys(xs) nos pontos da grade (xs crescente)."""
    out = []
    j = 0
    n = len(xs)
    for g in grade:
        while j < n - 2 and xs[j + 1] < g:
            j += 1
        x0, x1 = xs[j], xs[j + 1]
        if x1 == x0:
            out.append(ys[j])
        else:
            f = min(max((g - x0) / (x1 - x0), 0.0), 1.0)
            out.append(ys[j] + (ys[j + 1] - ys[j]) * f)
    return out


def _degrau(xs, ys, grade):
    out, j, n = [], 0, len(xs)
    for g in grade:
        while j < n - 1 and xs[j + 1] <= g:
            j += 1
        out.append(ys[j])
    return out


def _trecho_cronometrado(am, comprimento):
    """Separa as amostras da volta em trechos contínuos com cronômetro rodando e devolve o
    último que cobre a volta inteira. Na quali, a volta de saída dos boxes tem o mesmo número
    da volta lançada, mas o tempo de volta fica em 0; depois de um flashback o tempo volta atrás."""
    trechos, atual = [], []
    for a in am:
        tv, dist = a[3], a[2]
        # online o tempo às vezes "volta" uns milissegundos (correção da rede): só quebra se voltar mais de 0,5 s
        quebra = tv <= 0 or dist < 0 or (atual and (tv < atual[-1][3] - 500 or dist < atual[-1][2] - 50))
        if quebra:
            if atual:
                trechos.append(atual)
            atual = [] if (tv <= 0 or dist < 0) else [a]
        else:
            atual.append(a)
    if atual:
        trechos.append(atual)
    bons = [t for t in trechos if len(t) > 20 and t[0][2] < 250 and t[-1][2] > comprimento - 250]
    return bons[-1] if bons else None


PRE_M = 700   # metros antes da linha mostrados no relatório


def _mapa(ps, tempos, dists, grade):
    """x, z, rumo e yaw rate na grade de distância, a partir das posições (t, volta, dist, x, z, yaw)."""
    out = {}
    if len(ps) <= 20 or len(tempos) < 2:
        return out
    dp = _reamostrar(tempos, dists, [p[0] for p in ps])
    # yaw rate (°/s) pela variação do ângulo de rumo do carro (pacote 0, todos os carros)
    yr = [0.0] * len(ps)
    for i in range(1, len(ps) - 1):
        dt = ps[i + 1][0] - ps[i - 1][0]
        dy = ps[i + 1][5] - ps[i - 1][5]
        dy = (dy + math.pi) % (2 * math.pi) - math.pi
        yr[i] = math.degrees(dy / dt) if dt > 1e-3 else yr[i - 1]
    yr[0], yr[-1] = yr[1], yr[-2]
    lp, ult = [], -1e9
    for d_, p, y_ in zip(dp, ps, yr):
        if d_ > ult:
            lp.append((d_, p[3], p[4], y_, p[5]))
            ult = d_
    if len(lp) <= 20:
        return out
    d = [p[0] for p in lp]
    out["x"] = [round(v, 1) for v in _reamostrar(d, [p[1] for p in lp], grade)]
    out["z"] = [round(v, 1) for v in _reamostrar(d, [p[2] for p in lp], grade)]
    # rumo do carro (rad), sem saltos de ±π, para desenhar o carrinho virado certo no traçado
    ru = []
    for p in lp:
        a_ = p[4]
        if ru:
            while a_ - ru[-1] > math.pi:
                a_ -= 2 * math.pi
            while a_ - ru[-1] < -math.pi:
                a_ += 2 * math.pi
        ru.append(a_)
    out["rumo"] = [round(v, 3) for v in _reamostrar(d, ru, grade)]
    y_ = [-v for v in _reamostrar(d, [p[3] for p in lp], grade)]   # sinal igual ao do volante: + = direita
    j = 2   # suaviza o ruído da derivada (média móvel de ±2 pontos da grade)
    out["yaw"] = [round(sum(y_[max(0, i - j):i + j + 1]) / len(y_[max(0, i - j):i + j + 1]), 1) for i in range(len(y_))]
    return out


def _dist_por_posicao(antes, posicoes, t0, ref_x, ref_z, comprimento, passo):
    """Distância antes da linha calculada pela posição no mapa (o jogo manda distância 0 para
    os rivais online durante a volta de saída). Projeta cada posição no traçado do fim da volta."""
    if not ref_x or not ref_z:
        return []
    n = min(len(ref_x), len(ref_z))
    i0 = max(0, int((comprimento - PRE_M - 300) / passo))
    cand = range(i0, n)
    pp = [p for p in posicoes if t0 - 60 <= p[0] <= t0 + 0.2]
    marcas = []
    for p in pp:
        x, z = p[3], p[4]
        i = min(cand, key=lambda k: (ref_x[k] - x) ** 2 + (ref_z[k] - z) ** 2)
        if (ref_x[i] - x) ** 2 + (ref_z[i] - z) ** 2 > 35 ** 2:
            continue                                   # fora da pista (box, garagem)
        # ajuste fino projetando no segmento até o ponto seguinte
        j = min(n - 1, i + 1)
        sx, sz = ref_x[j] - ref_x[i], ref_z[j] - ref_z[i]
        L2 = sx * sx + sz * sz
        f = max(0.0, min(1.0, ((x - ref_x[i]) * sx + (z - ref_z[i]) * sz) / L2)) if L2 > 0 else 0.0
        d = (i + f) * passo - comprimento
        if d > 5:
            continue
        marcas.append((p[0], min(0.0, d)))
    if len(marcas) < 5:
        return []
    ts, ds = [m[0] for m in marcas], [m[1] for m in marcas]
    out = []
    for a in antes:
        if ts[0] <= a[0] <= ts[-1]:
            out.append((_reamostrar(ts, ds, [a[0]])[0], a))
    return out


def _pre_volta(amostras, posicoes, trecho, comprimento, passo, cap_bateria, ref_x=None, ref_z=None):
    """Os últimos PRE_M metros antes de cruzar a linha, em distância negativa (−700 … 0)."""
    t0 = trecho[0][0] - trecho[0][3] / 1000          # instante em que cruzou a linha
    antes = [a for a in amostras if t0 - 60 <= a[0] < trecho[0][0]]
    pts = []
    for a in antes:
        d = a[2]
        if a[3] > 0 and d < comprimento / 2:       # já é a volta cronometrada
            continue
        if d > comprimento / 2:
            d -= comprimento                          # fim da volta anterior / de saída
        if -PRE_M - 3 * passo <= d <= 0 and not (d == 0 and a[3] == 0):
            pts.append((d, a))
    if len(pts) < 5 or min(d for d, _ in pts) > -150:
        geo = _dist_por_posicao(antes, posicoes, t0, ref_x, ref_z, comprimento, passo)
        if geo:
            pts = [(d, a) for d, a in geo if -PRE_M - 3 * passo <= d <= 0]
    # só a última passagem contínua até a linha (descarta voltas para trás e saltos)
    cont = []
    for d, a in reversed(pts):
        if cont and (d > cont[-1][0] + 2 or cont[-1][0] - d > 120):
            break
        if cont and d >= cont[-1][0]:
            continue
        cont.append((d, a))
    cont.reverse()
    if len(cont) < 5 or cont[0][0] > -150:
        return None
    dist = [d for d, _ in cont] + [0.0]
    lim = [a for _, a in cont]
    lim = lim + [trecho[0]]
    n = int(min(PRE_M, -cont[0][0]) // passo)
    grade = [-(m * passo) for m in range(n, 0, -1)]
    tempos = [a[0] for a in lim[:-1]] + [t0]
    pre = {
        "d": grade,
        "t": [round(v) for v in _reamostrar(dist, [(t - t0) * 1000 for t in tempos], grade)],
        "v": [round(v) for v in _reamostrar(dist, [a[4] for a in lim], grade)],
        "acel": [round(v * 100) for v in _reamostrar(dist, [a[5] for a in lim], grade)],
        "freio": [round(v * 100) for v in _reamostrar(dist, [a[6] for a in lim], grade)],
        "marcha": [round(v) for v in _reamostrar(dist, [a[7] for a in lim], grade)],
        "volante": [round(v * 100) for v in _reamostrar(dist, [a[8] for a in lim], grade)],
        "modo": _degrau(dist, [a[11] for a in lim], grade),
        "bat": [round(v / cap_bateria * 100) for v in _reamostrar(dist, [a[12] for a in lim], grade)],
        "asa": _degrau(dist, [1 if a[9] else 0 for a in lim], grade),
    }
    pre.update(_mapa([p for p in posicoes if tempos[0] - 0.5 <= p[0] <= t0 + 0.2], tempos, dist, grade))
    return pre


def _alinhar_setores(xs, t_, setores):
    """Ajusta o relógio da volta para bater com os tempos oficiais dos setores (vindos do servidor).
    Os carros dos outros pilotos chegam pela internet com posição estimada; sem isso, cada computador
    mostraria minissetores e diferenças um pouco diferentes para a mesma volta."""
    if not setores:
        return t_
    d2, d3, s1, s2 = setores
    if not (s1 and s2 and 0 < d2 < d3 < xs[-1]):
        return t_
    o1, o2 = _reamostrar(xs, t_, [d2, d3])
    L = t_[-1]
    a1, a2 = s1, s1 + s2
    if not (0 < o1 < o2 < L and 0 < a1 < a2 < L):
        return t_
    k = (a1 / o1, (a2 - a1) / (o2 - o1), (L - a2) / (L - o2))
    if any(not 0.93 < x < 1.07 for x in k):
        return t_                                   # diferença grande demais: dado estranho, não mexe
    return [t * k[0] if t <= o1 else a1 + (t - o1) * k[1] if t <= o2 else a2 + (t - o2) * k[2] for t in t_]


def montar_traco(amostras, posicoes, volta, comprimento, passo, tempo_volta_ms, cap_bateria=4e6, mx=None, setores=None):
    trecho = _trecho_cronometrado([a for a in amostras if a[1] == volta], comprimento)
    if not trecho:
        return None
    t_ini, t_fim = trecho[0][0], trecho[-1][0]
    lim = []
    ult = -1
    for a in trecho:
        if a[2] > ult:
            lim.append(a)
            ult = a[2]
    dist = [a[2] for a in lim]
    if max(b - a for a, b in zip(dist, dist[1:])) > 250:
        return None
    pit = any(a[10] for a in lim)
    grade = [i * passo for i in range(int(comprimento // passo) + 1)]
    tempos = [a[3] for a in lim]
    xs = [0.0] + dist + [float(comprimento)]
    t_ = [0.0] + tempos + [float(tempo_volta_ms or tempos[-1])]
    t_ = _alinhar_setores(xs, t_, setores)
    tr = {
        "t": [round(v) for v in _reamostrar(xs, t_, grade)],
        "v": [round(v) for v in _reamostrar(dist, [a[4] for a in lim], grade)],
        "acel": [round(v * 100) for v in _reamostrar(dist, [a[5] for a in lim], grade)],
        "freio": [round(v * 100) for v in _reamostrar(dist, [a[6] for a in lim], grade)],
        "marcha": [round(v) for v in _reamostrar(dist, [a[7] for a in lim], grade)],
        "volante": [round(v * 100) for v in _reamostrar(dist, [a[8] for a in lim], grade)],
        # modo de bateria do pacote de status: 0 nenhum, 1 médio, 2 volta rápida, 3 boost.
        # (o "overtake_active" do pacote 16 fica ligado o tempo todo no F1 26, então não é usado)
        "modo": _degrau(dist, [a[11] for a in lim], grade),
        "bat": [round(v / cap_bateria * 100) for v in _reamostrar(dist, [a[12] for a in lim], grade)],
        "pit": pit,
        # aerodinâmica ativa (pacote 16): 1 = modo reta (asa aberta), 0 = modo curva
        "asa": _degrau(dist, [1 if a[9] else 0 for a in lim], grade),
    }
    if mx is not None:
        # temperatura da superfície dos 4 pneus (ordem do jogo: TE, TD, DE, DD)
        tr["temp"] = [[round(v) for v in _reamostrar(dist, [a[13][k] for a in lim], grade)] for k in range(4)]
        # temperatura do núcleo (carcaça): é ela que o jogo usa para a janela de aderência
        tr["temp_n"] = [[round(v) for v in _reamostrar(dist, [a[14][k] for a in lim], grade)] for k in range(4)]
        # pacote 13 (rodas): pontos esparsos, convertidos para distância pelo tempo
        pm = [m for m in mx if t_ini <= m[0] <= lim[-1][0]]
        if pm:
            dm = _reamostrar([a[0] for a in lim], dist, [m[0] for m in pm])
            tr["mx"] = {
                "d": [round(x) for x in dm],
                "trava": [round(min(m[1][2], m[1][3]), 3) for m in pm],       # deslizamento das dianteiras (negativo = travando)
                "trava_t": [round(min(m[1][0], m[1][1]), 3) for m in pm],     # traseiras
                "patina": [round(max(m[1][0], m[1][1]), 3) for m in pm],      # traseiras patinando
                "af": [round((abs(m[2][2]) + abs(m[2][3])) / 2, 3) for m in pm],  # ângulo de deriva médio, dianteiras
                "ar": [round((abs(m[2][0]) + abs(m[2][1])) / 2, 3) for m in pm],  # traseiras
            }
    # posição no mapa: pega pelo tempo e converte para distância usando a própria telemetria
    # (o pacote de movimento às vezes chega antes da distância da volta ser atualizada)
    tr.update(_mapa([p for p in posicoes if t_ini <= p[0] <= lim[-1][0]], [a[0] for a in lim], dist, grade))
    # trecho antes da linha (até PRE_M metros): fim da volta de saída ou da volta anterior.
    # Serve para ver onde o piloto liga a bateria e com que velocidade cruza a linha.
    pre = _pre_volta(amostras, posicoes, trecho, comprimento, passo, cap_bateria, tr.get("x"), tr.get("z"))
    if pre:
        if tr.get("rumo") and pre.get("rumo"):
            k = round((tr["rumo"][0] - pre["rumo"][-1]) / (2 * math.pi))
            pre["rumo"] = [round(v + k * 2 * math.pi, 3) for v in pre["rumo"]]
        tr["pre"] = pre
    return tr


# ---------------------------------------------------------------- montagem
def _voltas_historico(h):
    voltas = []
    if h is None:
        return voltas
    for i in range(min(h.num_laps, 100)):
        l = h.lap_history_data[i]
        if l.lap_time_in_ms == 0:
            continue
        s1 = _ms_setor(l.sector1_time_ms_part, l.sector1_time_minutes_part)
        s2 = _ms_setor(l.sector2_time_ms_part, l.sector2_time_minutes_part)
        s3 = _ms_setor(l.sector3_time_ms_part, l.sector3_time_minutes_part)
        f = l.lap_valid_bit_flags
        voltas.append({"n": i + 1, "ms": l.lap_time_in_ms, "s": [s1, s2, s3],
                       "valida": bool(f & 1), "s_validos": [bool(f & 2), bool(f & 4), bool(f & 8)]})
    return voltas


def _aplicar_punicoes(classif):
    """A classificação final do jogo vem com a posição de quem cruzou a linha, sem descontar as punições de tempo
    (o tempo total também vem sem elas). Reordena quem terminou a corrida pelo tempo com a punição somada, como na
    classificação oficial: mais voltas primeiro e, com o mesmo número de voltas, o menor tempo + punição.
    Quem abandonou ou foi desclassificado fica onde o jogo colocou. Os pontos acompanham a posição."""
    grupo = [x for x in classif if x["status"] in (2, 3)]
    if len(grupo) < 2 or not all(x["tempo_total"] > 0 for x in grupo) or not any(x["penal_s"] for x in grupo):
        return
    vagas = sorted(x["pos"] for x in grupo)
    pontos = {x["pos"]: x["pontos"] for x in grupo}
    nova = sorted(grupo, key=lambda x: (-x["voltas"], x["tempo_total"] + x["penal_s"], x["pos"]))
    for x, pos in zip(nova, vagas):
        if x["pos"] != pos:
            x["pos_jogo"] = x["pos"]
        x["pos"] = pos
        x["pontos"] = pontos[pos]
    classif.sort(key=lambda x: x["pos"])


def _juntar_stints(st):
    """O jogo às vezes abre um stint de 1 volta com o mesmo pneu no meio da parada (ex.: duas
    paradas seguidas na mesma equipe): médio até a 5, médio até a 6, duro. Junta esse pedaço ao
    stint anterior (que mantém o próprio fim) para não aparecer um "stint 2" fantasma."""
    out = []
    for x in st:
        if out and x["pneu"] == out[-1]["pneu"] and x["fim"] != 255 and x["fim"] - out[-1]["fim"] <= 1:
            continue   # fica o fim do primeiro: a volta seguinte já é do pneu novo
        else:
            out.append(dict(x))
    return out


def _stints_historico(h):
    if h is None:
        return []
    return _juntar_stints([{"fim": s.end_lap, "pneu": s.tyre_visual_compound}
                           for s in list(h.tyre_stints_history_data)[:h.num_tyre_stints]])


def _inicio_sessao(caminho, duracao_s):
    """Horário de início da sessão: vem do nome do arquivo gravado (2026-11-11_19-07-52_...);
    se não der, usa a data do arquivo menos a duração gravada."""
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})", os.path.basename(caminho))
    if m:
        return datetime(*map(int, m.groups()))
    return datetime.fromtimestamp(os.path.getmtime(caminho) - (duracao_s or 0))


TRECHO_DESG = 25   # metros por trecho no mapa de desgaste


def desgaste_por_trecho(caminho, comprimento, carros):
    """Onde cada carro gasta pneu: soma o aumento do desgaste (pacote 10) entre duas leituras
    e reparte pelo trecho de pista percorrido entre elas. Só na corrida, fora do box.
    A 1ª volta fica de fora (a largada parada gasta muito pneu num ponto só).
    Resultado por carro e por composto: desgaste (%) e metros percorridos em cada trecho."""
    nb = int(comprimento // TRECHO_DESG) + 1
    L, DN, S = leitor.LAP, leitor.DANO, leitor.STATUS
    iL, iD, iS = L.idx, DN.idx, S.idx
    lap = {}          # carro -> (volta, dist, no_box)
    comp = {}         # carro -> composto real
    vis = {}          # carro -> composto visual (macio/médio/duro)
    ult = {}          # carro -> (volta, dist, desgaste[4])
    out = {}
    carros = set(carros)
    for idx, cab, dados in leitor.registros(caminho):
        pid = cab[5]
        if pid == 2:
            for c in carros:
                r = L.ler(dados, c)
                # online, depois do box o jogo deixa os rivais marcados como "volta de entrada" (2) até o fim:
                # vale qualquer status na pista, o que tira o box é o pit_status
                lap[c] = (r[iL["current_lap_num"]], r[iL["lap_distance"]], r[iL["pit_status"]] == 0 and r[iL["driver_status"]] in (1, 2, 3, 4))
        elif pid == 7:
            for c in carros:
                r = S.ler(dados, c)
                comp[c] = r[iS["actual_tyre_compound"]]
                vis[c] = r[iS["visual_tyre_compound"]]
        elif pid == 10:
            for c in carros:
                if c not in lap or not comp.get(c):
                    continue
                r = DN.ler(dados, c)
                w = [r[iD[f"tyres_wear{k}"]] for k in range(4)]
                volta, dist, ok = lap[c]
                ant = ult.get(c)
                # o desgaste dos rivais chega pela rede e oscila um pouco para cima e para baixo:
                # guarda o maior valor já visto de cada pneu e só conta o que passar dele
                topo = ant[2] if ant else w
                if any(x < t_ - 5 for x, t_ in zip(w, topo)):
                    topo = w          # caiu muito: troca de pneu (ou flashback), recomeça
                    ult[c] = (volta, dist, w)
                    continue
                novo = [max(x, t_) for x, t_ in zip(w, topo)]
                ult[c] = (volta, dist, novo)
                if volta <= 1 or not ok or not ant or ant[0] != volta or dist <= ant[1] or dist - ant[1] > 150 or ant[1] < 0:
                    continue
                dw = [n_ - t_ for n_, t_ in zip(novo, topo)]
                if any(x > 3 for x in dw):
                    continue          # salto estranho
                g = out.setdefault(c, {}).setdefault(comp[c], {"w": [[0.0] * nb for _ in range(4)], "m": [0.0] * nb, "vis": vis.get(c)})
                a, b = ant[1], dist
                k0, k1 = int(a // TRECHO_DESG), min(nb - 1, int(b // TRECHO_DESG))
                for k in range(k0, k1 + 1):
                    ini, fim = max(a, k * TRECHO_DESG), min(b, (k + 1) * TRECHO_DESG)
                    f = (fim - ini) / (b - a)
                    if f <= 0:
                        continue
                    g["m"][k] += fim - ini
                    for r_ in range(4):
                        g["w"][r_][k] += dw[r_] * f
    # arredonda e descarta carros sem dado (telemetria privada manda desgaste zerado)
    res = {}
    for c, por in out.items():
        for cp, g in por.items():
            if sum(map(sum, g["w"])) <= 0.01:
                continue
            res.setdefault(c, {})[cp] = {"w": [[round(x, 4) for x in w] for w in g["w"]], "m": [round(x) for x in g["m"]], "vis": g["vis"]}
    return {"passo": TRECHO_DESG, "carros": res}


def analisar(caminho):
    p1 = passada1(caminho)
    sess = p1["sess"]
    if not sess:
        raise ValueError("A gravação não tem dados de sessão (o jogo mandou telemetria?).")
    tipo_n = sess["tipo"]
    tipo = "quali" if tipo_n in SESSOES_QUALI else "corrida" if tipo_n in SESSOES_CORRIDA else "outro"
    comp = sess["comprimento"] or 5000
    jogador = p1["jogador"]
    pilotos = p1["pilotos"]
    carros = sorted(c for c in pilotos if c < max(p1["n_ativos"], 1) or p1["historico"].get(c))
    if jogador not in carros:
        carros.append(jogador)

    voltas = {c: _voltas_historico(p1["historico"].get(c)) for c in carros}
    stints = {c: _stints_historico(p1["historico"].get(c)) for c in carros}

    # melhores voltas válidas
    melhores = []
    for c in carros:
        vv = [v for v in voltas[c] if v["valida"]]
        if vv:
            b = min(vv, key=lambda v: v["ms"])
            melhores.append((b["ms"], c, b["n"]))
    melhores.sort()

    # classificação
    classif = []
    fin = p1["final"]
    if fin is not None and fin.num_cars:
        for c in range(min(fin.num_cars, 22)):
            d = fin.classification_data[c]
            if d.position == 0:
                continue
            classif.append({
                "idx": c, "pos": d.position, "grid": d.grid_position, "voltas": d.num_laps,
                "melhor_ms": d.best_lap_time_in_ms, "tempo_total": round(d.total_race_time, 3),
                "pits": d.num_pit_stops, "status": d.result_status, "pontos": d.points,
                "penal_s": d.penalties_time, "n_penal": d.num_penalties,
                "stints": _juntar_stints([{"pneu": d.tyre_stints_visual[k], "fim": d.tyre_stints_end_laps[k]}
                                          for k in range(d.num_tyre_stints)]),
            })
        classif.sort(key=lambda x: x["pos"])
        if tipo == "corrida":
            _aplicar_punicoes(classif)
    else:
        # sem classificação final: monta pela ordem atual / melhor volta
        if tipo == "corrida":
            ult = {c: (p1["conclusoes"][c][-1] if p1["conclusoes"][c] else (0, 0, 99)) for c in carros}
            ordem = sorted(carros, key=lambda c: (-ult[c][0], ult[c][1]))
        else:
            ordem = [c for _, c, _ in melhores] + [c for c in carros if c not in {m[1] for m in melhores}]
        for i, c in enumerate(ordem):
            mv = [v["ms"] for v in voltas[c] if v["valida"]]
            classif.append({"idx": c, "pos": i + 1, "grid": p1["grid"].get(c, 0), "voltas": len(voltas[c]),
                            "melhor_ms": min(mv) if mv else 0, "tempo_total": 0,
                            "pits": len(stints[c]) - 1 if stints[c] else 0, "status": 0, "pontos": 0,
                            "penal_s": 0, "n_penal": 0, "stints": stints[c]})

    # posições e diferença para o líder ao fim de cada volta (corrida)
    posicoes, gaps = {}, {}
    cruz_lider = {}
    for c in carros:
        for volta, tc, pos in p1["conclusoes"][c]:
            if volta not in cruz_lider or tc < cruz_lider[volta]:
                cruz_lider[volta] = tc
    for c in carros:
        posicoes[c] = {}
        gaps[c] = {}
        for volta, tc, pos in p1["conclusoes"][c]:
            posicoes[c][volta] = pos
            gaps[c][volta] = round((tc - cruz_lider[volta]) * 1000)

    # última volta da corrida: o carro não "começa" outra volta, então usa a classificação final
    if tipo == "corrida" and fin is not None:
        max_voltas = max((y["voltas"] for y in classif), default=0)
        tempo_lider = min((x["tempo_total"] for x in classif if x["tempo_total"] > 0 and x["voltas"] == max_voltas),
                          default=0)
        for x in classif:
            c = x["idx"]
            if c in posicoes and x["voltas"] and x["voltas"] not in posicoes[c]:
                posicoes[c][x["voltas"]] = x["pos"]
                if x["tempo_total"] and tempo_lider and x["status"] == 3 and x["voltas"] == max_voltas:
                    gaps[c][x["voltas"]] = round((x["tempo_total"] + x["penal_s"] - tempo_lider) * 1000)

    # safety car -> voltas do líder
    def volta_no_tempo(tq):
        melhor = 0
        for volta, tc in sorted(cruz_lider.items()):
            if tc <= tq:
                melhor = volta
        return melhor + 1

    sc = [{"tipo": SAFETY_CAR.get(s[0], ""), "de": volta_no_tempo(s[1]), "ate": volta_no_tempo(s[2])}
          for s in p1["sc"]]

    # escolha das voltas com telemetria detalhada
    # rivais: na quali, todas as voltas válidas; na corrida, as 5 melhores de cada um (arquivo menor)
    ref = []
    for c in carros:
        if c == jogador:
            continue
        vv = sorted((v for v in voltas[c] if v["valida"]), key=lambda v: v["ms"])
        if tipo == "corrida":
            vv = vv[:5]
        ref += [(v["ms"], c, v["n"]) for v in vv]
    quero = {}
    for _, c, nv in ref:
        quero.setdefault(c, set()).add(nv)
        quero[c].add(nv - 1)   # fim da volta anterior: trecho antes da linha
    quero[jogador] = None
    amostras, posicoes_xy, mx = passada2(caminho, quero, jogador)
    passo = max(5, round(comp / 900))

    tracos = []
    tempos_hist = {(c, v["n"]): v for c in carros for v in voltas[c]}

    def setores_de(h):
        if not h or not h.get("s") or not sess.get("s2") or not sess.get("s3"):
            return None
        return (sess["s2"], sess["s3"], h["s"][0], h["s"][1])
    voltas_jog = sorted({a[1] for a in amostras.get(jogador, [])})
    for nv in voltas_jog:
        h = tempos_hist.get((jogador, nv))
        tr = montar_traco(amostras[jogador], posicoes_xy[jogador], nv, comp, passo, h["ms"] if h else None, p1["ers_max"], mx,
                          setores=setores_de(h))
        if tr and h:
            tr.update(carro=jogador, volta=nv, ms=h["ms"], valida=h["valida"], s=h["s"])
            tracos.append(tr)
    for ms, c, nv in ref:
        h = tempos_hist.get((c, nv))
        tr = montar_traco(amostras[c], posicoes_xy[c], nv, comp, passo, ms, p1["ers_max"], setores=setores_de(h))
        if tr:
            tr.update(carro=c, volta=nv, ms=ms, valida=True, s=h["s"] if h else None)
            tracos.append(tr)

    # voltas do jogador com dados de carro
    jv = []
    for v in voltas.get(jogador, []):
        s = p1["snap"].get(v["n"], {})
        e = dict(v)
        e.update(s)
        e["pit"] = v["n"] in p1["pit_na_volta"].get(jogador, set())
        tv = p1["tipo_volta"][jogador].get(v["n"], {})
        e["tipo"] = max(tv, key=tv.get) if tv else None
        jv.append(e)

    # ERS em % da capacidade da bateria (assim: fim = início − usada + recuperada)
    cap = p1["ers_max"]
    ci = p1["comb_inicial"]
    ant_comb, ant_saldo, ant_desg = (ci[0], ci[1], None) if ci else (None, None, None)
    for e in jv:
        if "ers_bateria_j" in e:
            e["ers_bateria"] = round(e.pop("ers_bateria_j") / cap * 100, 1)
            e["ers_usado"] = round(e.pop("ers_usado_j") / cap * 100, 1)
            e["ers_recuperado"] = round(e.pop("ers_recuperado_j") / cap * 100, 1)
        if e["n"] in p1["bat_inicio"]:
            e["ers_inicio"] = round(p1["bat_inicio"][e["n"]] / cap * 100, 1)
        # a bateria no início da volta é a do fim da volta anterior (a leitura no meio da volta pode
        # pegar um flashback ou um pacote atrasado)
        prev = next((x for x in jv if x["n"] == e["n"] - 1), None)
        if prev and prev.get("ers_bateria") is not None:
            e["ers_inicio"] = prev["ers_bateria"]
        if e.get("combustivel") is not None:
            if ant_comb is not None:
                e["comb_gasto"] = round(ant_comb - e["combustivel"], 2)
            if ant_saldo is not None and e.get("saldo_comb") is not None:
                e["saldo_delta"] = round(e["saldo_comb"] - ant_saldo, 2)
            ant_comb, ant_saldo = e["combustivel"], e.get("saldo_comb")
        if e.get("desgaste"):
            pior = max(e["desgaste"])
            if ant_desg is None or pior < ant_desg:   # primeira volta ou pneu trocado
                ant_desg = 0.0
            e["desgaste_volta"] = round(pior - ant_desg, 1)
            ant_desg = pior

    # pista no mapa a partir da melhor volta com posição
    data_gravacao = _inicio_sessao(caminho, p1["duracao_real"])
    eventos = [e for e in p1["eventos"] if e["cod"] not in ("DRSE", "DRSD", "BUTN")]

    # energia (% da bateria) de todos os carros por volta
    energia = {}
    for c in carros:
        lin = {}
        for nv, e in p1["ers_carro"].get(c, {}).items():
            x = {"usado": round(e["usado"] / cap * 100, 1), "fim": round(e["fim"] / cap * 100, 1)}
            if "recup" in e:
                x["recup"] = round(e["recup"] / cap * 100, 1)
            # online o jogo às vezes não manda a energia do rival: volta com 0 usado e 0 recuperado = sem dado
            if x["usado"] < 1 and x.get("recup", 0) < 1:
                continue
            if nv in p1["bat_ini_carro"].get(c, {}):
                x["ini"] = round(p1["bat_ini_carro"][c][nv] / cap * 100, 1)
            lin[nv] = x
        for nv, x in lin.items():
            if nv - 1 in lin:
                x["ini"] = lin[nv - 1]["fim"]
        if lin:
            energia[c] = lin

    # o trecho antes da linha só interessa na classificação (preparação da volta lançada)
    if tipo == "corrida":
        for t_ in tracos:
            t_.pop("pre", None)
        try:
            desg_trechos = desgaste_por_trecho(caminho, comp, carros)
        except Exception:
            desg_trechos = None
    else:
        desg_trechos = None

    D = {
        "meta": {
            "pista": PISTAS.get(sess["pista"], f"Pista #{sess['pista']}"),
            "pista_id": sess["pista"],
            "gp": GPS.get(sess["pista"], PISTAS.get(sess["pista"], f"Pista {sess['pista']}")),
            "dia": data_gravacao.strftime("%d-%m-%Y"),
            "hora": data_gravacao.strftime("%Hh%M"),
            "inicio_ts": data_gravacao.timestamp(),
            "sessao": SESSOES.get(tipo_n, str(tipo_n)), "tipo": tipo, "tipo_n": tipo_n,
            "data": data_gravacao.strftime("%d/%m/%Y %H:%M"),
            "clima": CLIMA.get(sess["clima"], ""), "temp_pista": sess["temp_pista"], "temp_ar": sess["temp_ar"],
            "voltas_total": sess["voltas_total"], "comprimento": comp, "s2": sess["s2"], "s3": sess["s3"],
            "jogador": jogador, "online": bool(sess["online"]), "dificuldade_ia": sess["dificuldade_ia"],
            "vmax": p1["vmax"], "passo": passo, "arquivo": os.path.basename(caminho),
            "duracao_min": round(p1["duracao_real"] / 60, 1),
            "classificacao_provisoria": fin is None,
            "comb_inicial": p1["comb_inicial"],
            "bateria_mj": round(p1["ers_max"] / 1e6, 2),
        },
        "pilotos": {c: pilotos.get(c, {"idx": c, "nome": f"Carro {c + 1}", "numero": 0, "cor": None})
                    for c in carros},
        "classificacao": classif,
        "voltas": voltas,
        "stints": stints,
        "posicoes": posicoes,
        "gaps": gaps,
        "grid": p1["grid"],
        "speed_trap": {c: round(v, 1) for c, v in p1["speed_trap"].items()},
        "jogador_voltas": jv,
        "desgaste_carro": {c: v for c, v in p1["desgaste_carro"].items() if c in carros},
        "tracos": tracos,
        "eventos": eventos,
        "flashbacks": len(p1["flashbacks"]),
        "sc": sc,
        "vmax_carro": {c: v for c, v in p1["vmax_carro"].items() if c in carros and v},
        "avisos_carro": {c: v for c, v in p1["avisos_carro"].items() if c in carros},
        "energia_carros": energia,
        "setup": p1["setup_jog"],
        "desgaste_trechos": desg_trechos,
        "paradas": {c: v for c, v in p1["paradas"].items() if c in carros and v},
        "comb_carro": {c: v for c, v in p1["comb_carro"].items() if c in carros and v},
        "saldo_carro": {c: v for c, v in p1["saldo_carro"].items() if c in carros and v},
        "vmax_volta_carro": {c: v for c, v in p1["vmax_volta_carro"].items() if c in carros and v},
        "temp_curva_carro": {c: {n: [round(x / t[3], 1) for x in t[1]] for n, t in v.items() if t[3] >= 10}
                             for c, v in p1["temp_carro"].items() if c in carros},
        "temp_nucleo_carro": {c: {n: [round(x / t[0], 1) for x in t[2]] for n, t in v.items() if t[0] >= 20}
                              for c, v in p1["temp_carro"].items() if c in carros},
        "pit_voltas": {c: sorted(p1["pit_na_volta"].get(c, ())) for c in carros if p1["pit_na_volta"].get(c)},
    }
    try:
        import setups_ref
        D["setup_ref"] = setups_ref.carregar(sess["pista"]) if D.get("setup") else None
    except Exception:  # noqa: BLE001
        D["setup_ref"] = None
    if tipo == "corrida":
        try:
            D["ritmo"] = corrida.analisar_corrida(D)
        except Exception as ex:  # noqa: BLE001
            D["ritmo"] = {"aviso": f"Não foi possível analisar o ritmo: {ex}"}
    try:
        idx, oficial = curvas.apices(sess["pista"], comp, passo, tracos)
        D["curvas"] = {"apices": idx, "oficial": oficial}
        # bordas da pista (mapeadas ou acumuladas sessão a sessão) para o traçado e replay
        try:
            import pistas
            n_ = min((min(len(t["x"]), len(t["z"])) for t in tracos if t.get("x") and t.get("z")), default=0)
            if n_:
                geo = pistas.acumular(sess["pista"], comp, tracos, passo)
                D["pista_geo"] = pistas.para_relatorio(geo, passo, n_)
        except Exception:
            D["pista_geo"] = None
        D["seu_resumo"] = dicas.seu_resumo(D, idx)
        try:
            import perfil
            D["estilo"] = perfil.montar(D, idx)
        except Exception as ex:  # noqa: BLE001
            D["estilo"] = {"aviso": f"Não foi possível montar o perfil: {ex}"}
    except Exception as ex:  # o resumo nunca pode impedir o relatório
        D["seu_resumo"] = {"aviso": f"Não foi possível montar as dicas: {ex}"}
    D["resumo_sessao"] = dicas.resumo_sessao(D)
    # temperaturas ponto a ponto só servem para as contas acima; o relatório não usa (deixa o arquivo menor)
    for tr in D.get("tracos") or []:
        tr.pop("temp", None)
        tr.pop("temp_n", None)
    return D
