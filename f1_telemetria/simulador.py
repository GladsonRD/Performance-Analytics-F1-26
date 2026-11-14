"""
Simulador de sessão do F1 26 (só para testes).

Gera pacotes no formato UDP 2026 de uma qualificação ou corrida fictícia e
manda para o gravador (UDP) ou grava direto num arquivo .f1rec.

    python simulador.py corrida --udp           # manda para 127.0.0.1:20777
    python simulador.py quali --arquivo teste.f1rec
"""

import argparse
import bisect
import math
import random
import socket
import struct
import time

import leitor
import pacotes

CAB = leitor.CAB
N = 22
HZ = 20
DT = 1.0 / HZ
NOMES = ["VOCÊ", "VERSTAPPEN", "NORRIS", "LECLERC", "PIASTRI", "HAMILTON", "RUSSELL", "ANTONELLI",
         "ALONSO", "STROLL", "GASLY", "COLAPINTO", "ALBON", "SAINZ", "HULKENBERG", "BORTOLETO",
         "OCON", "BEARMAN", "LAWSON", "LINDBLAD", "PEREZ", "BOTTAS"]
CORES = [(0, 161, 155), (54, 113, 198), (255, 128, 0), (232, 0, 45), (255, 128, 0), (232, 0, 45),
         (39, 244, 210), (39, 244, 210), (34, 153, 113), (34, 153, 113), (0, 147, 204), (0, 147, 204),
         (100, 196, 255), (100, 196, 255), (82, 226, 82), (82, 226, 82), (182, 186, 189), (182, 186, 189),
         (102, 146, 255), (102, 146, 255), (170, 170, 170), (170, 170, 170)]


# ------------------------------------------------------------------ pista
def gerar_pista(comp=5200, n=1300):
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        r = 1 + 0.22 * math.sin(2 * th) + 0.13 * math.sin(3 * th + 1) + 0.09 * math.cos(5 * th) + 0.05 * math.sin(7 * th + 2)
        pts.append((r * math.cos(th), r * math.sin(th) * 0.7))
    per = sum(math.dist(pts[i], pts[(i + 1) % n]) for i in range(n))
    k = comp / per
    pts = [(x * k, y * k) for x, y in pts]
    s = [0.0]
    for i in range(1, n):
        s.append(s[-1] + math.dist(pts[i - 1], pts[i]))
    raio = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
        area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        raio.append(1e5 if area2 < 1e-9 else ab * bc * ca / (2 * area2))
    # suaviza o raio
    raio = [sum(raio[(i + j) % n] for j in range(-4, 5)) / 9 for i in range(n)]
    return pts, s, raio, comp


def perfil(s, raio, comp, lat=34.0, freio=46.0, ajustes=None):
    n = len(s)
    vmax = []
    for i in range(n):
        v = min(91.0, math.sqrt(lat * raio[i]))
        if ajustes:
            for (a, b, f) in ajustes:
                if a <= s[i] <= b:
                    v *= f
        vmax.append(v)
    v = vmax[:]
    for _ in range(2):
        for i in range(1, 2 * n):
            j, p = i % n, (i - 1) % n
            ds = (s[j] - s[p]) % comp or 1
            ac = max(1.5, 11.0 * (1 - v[p] / 95.0))
            v[j] = min(v[j], math.sqrt(v[p] ** 2 + 2 * ac * ds))
        for i in range(2 * n, 0, -1):
            j, nx = i % n, (i + 1) % n
            ds = (s[nx] - s[j]) % comp or 1
            v[j] = min(v[j], math.sqrt(v[nx] ** 2 + 2 * freio * ds))
    t = [0.0]
    for i in range(1, n):
        t.append(t[-1] + (s[i] - s[i - 1]) / ((v[i] + v[i - 1]) / 2))
    t_total = t[-1] + (comp - s[-1]) / v[-1]
    return v, t, t_total


class Carro:
    def __init__(self, idx, base_t, base_v, fator):
        self.idx = idx
        self.base_t = base_t      # tempos ao longo da volta (perfil base)
        self.base_v = base_v
        self.fator = fator


# ------------------------------------------------------------------ simulação
class Sim:
    def __init__(self, tipo, saida, seed=7):
        random.seed(seed)
        self.tipo = tipo
        self.saida = saida
        self.uid = random.getrandbits(63) ^ (1 if tipo == "corrida" else 2) << 40
        self.frame = 0
        self.pts, self.s, self.raio, self.comp = gerar_pista()
        self.v_ia, self.t_ia, self.T_ia = perfil(self.s, self.raio, self.comp)
        # jogador: mais lento em duas curvas, freia antes, um pouco melhor em outra
        self.v_j, self.t_j, self.T_j = perfil(self.s, self.raio, self.comp, freio=42.0,
                                              ajustes=[(1500, 1800, 0.93), (3300, 3500, 1.03), (4200, 4500, 0.96)])
        self.sess_tipo = 5 if tipo == "quali" else 15
        self.voltas_total = 12
        self.s2 = self.comp * 0.33
        self.s3 = self.comp * 0.68

    # ---------- empacotamento
    def cab(self, pid, t):
        return CAB.pack(2026, 25, 1, 0, 1, pid, self.uid, t, self.frame, self.frame, 0, 255)

    def enviar(self, dados):
        self.saida(dados)

    def por_carro(self, pid, pc, t, valores, extra=b""):
        partes = [self.cab(pid, t)]
        for c in range(24):
            d = valores.get(c, {})
            partes.append(pc.st.pack(*[d.get(nm, 0) for nm in pc.nomes]))
        self.enviar(b"".join(partes) + extra)

    def obj(self, cls, pid, t):
        o = cls()
        o.header = pacotes.PacketHeader.from_buffer_copy(self.cab(pid, t))
        return o

    # ---------- posição de um carro
    def estado(self, c, t):
        """Retorna (volta, dist, t_volta_ms, vel_m_s, em_pit, na_garagem, tipo_volta)."""
        sch = self.agenda[c]
        k = bisect.bisect_right(self.fins[c], t)
        if k >= len(sch):
            return None
        ini, fim, volta, f, tipo = sch[k]
        if t < ini:
            return (volta, 0.0, 0, 0.0, False, True, 0)
        tau = (t - ini) / f
        tb, vb, Tb = (self.t_j, self.v_j, self.T_j) if c == 0 else (self.t_ia, self.v_ia, self.T_ia)
        j = bisect.bisect_right(tb, tau) - 1
        j = max(0, min(j, len(tb) - 2))
        fr = (tau - tb[j]) / max(tb[j + 1] - tb[j], 1e-6)
        dist = self.s[j] + (self.s[j + 1] - self.s[j]) * min(fr, 1)
        vel = (vb[j] + (vb[j + 1] - vb[j]) * min(fr, 1)) / f
        pit = (tipo == "in" and dist > self.comp - 350) or (tipo == "out" and dist < 300)
        if pit:
            vel = min(vel, 22.2)
        return (volta, dist, int((t - ini) * 1000), vel, pit, False, tipo, j, k)

    # ---------- agendas
    def montar_agenda(self):
        self.agenda = {}
        self.voltas = {}  # c -> [(volta, ms, setores, valida)]
        self.stints = {}
        habilidade = sorted([random.uniform(0.995, 1.025) for _ in range(N)])
        hab = {c: habilidade[i] for i, c in enumerate([1, 2, 3, 4, 5, 6, 0, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21])}
        for c in range(N):
            T = self.T_j if c == 0 else self.T_ia
            sch = []
            if self.tipo == "quali":
                t0 = random.uniform(5, 120)
                plano = [("out", 1.35), ("flying", 1.0), ("in_slow", 1.28), ("flying", 1.0), ("in", 1.3)]
                volta = 1
                for tipo, mult in plano:
                    f = hab[c] * mult * random.uniform(0.997, 1.004)
                    if tipo == "flying" and volta == 4:
                        f *= 0.997  # pista melhora
                    dur = T * f
                    sch.append((t0, t0 + dur, volta, f, tipo))
                    t0 += dur
                    volta += 1
                self.stints[c] = [(16, volta - 1)]
            else:
                t0 = 3.0 + 0.25 * self.grid[c]
                pit_volta = random.choice([5, 6, 7]) if c else 6
                for volta in range(1, self.voltas_total + 1):
                    idade = volta if volta <= pit_volta else volta - pit_volta
                    deg = 0.0025 * idade if volta <= pit_volta else 0.0012 * idade
                    f = hab[c] * (1 + deg) * random.uniform(0.996, 1.006) * (1.06 if volta == 1 else 1)
                    f *= 1 - 0.002 * (volta / self.voltas_total)  # combustível
                    dur = T * f + (0.25 * self.grid[c] if volta == 1 else 0)
                    tipo = "race"
                    if volta == pit_volta:
                        dur += 11
                        tipo = "in"
                    if volta == pit_volta + 1:
                        dur += 10
                        tipo = "out"
                    f = dur / T
                    sch.append((t0, t0 + dur, volta, f, tipo))
                    t0 += dur
                self.stints[c] = [(17, pit_volta), (18, self.voltas_total)]
            self.agenda[c] = sch
        self.fins = {c: [x[1] for x in self.agenda[c]] for c in range(N)}
        for c in range(N):
            vs = []
            for ini, fim, volta, f, tipo in self.agenda[c]:
                ms = int((fim - ini) * 1000)
                Tb = self.T_j if c == 0 else self.T_ia
                tb = self.t_j if c == 0 else self.t_ia
                s1 = int(tb[bisect.bisect_left(self.s, self.s2)] / Tb * ms)
                s2 = int(tb[bisect.bisect_left(self.s, self.s3)] / Tb * ms) - s1
                valida = True
                if self.tipo == "quali" and c == 0 and volta == 2:
                    valida = False
                if tipo in ("out", "in", "in_slow") and self.tipo == "quali":
                    valida = tipo != "out" and valida
                vs.append((volta, ms, (s1, s2, ms - s1 - s2), valida))
            self.voltas[c] = vs

    # ---------- pacotes periódicos
    def pacote_sessao(self, t, sc=0):
        o = self.obj(pacotes.PacketSessionData, 1, t)
        o.weather = 1
        o.track_temperature = 34
        o.air_temperature = 24
        o.total_laps = self.voltas_total if self.tipo == "corrida" else 0
        o.track_length = int(self.comp)
        o.session_type = self.sess_tipo
        o.track_id = 16
        o.session_duration = 1080 if self.tipo == "quali" else 0
        o.safety_car_status = sc
        o.sector2_lap_distance_start = self.s2
        o.sector3_lap_distance_start = self.s3
        o.ai_difficulty = 95
        self.enviar(bytes(o))

    def pacote_participantes(self, t):
        o = self.obj(pacotes.PacketParticipantsData, 4, t)
        o.num_active_cars = N
        for c in range(N):
            p = o.participants[c]
            p.ai_controlled = 0 if c == 0 else 1
            p.team_id = c // 2
            p.race_number = c + 2
            p.name = NOMES[c].encode()
            p.your_telemetry = 1
            p.num_colours = 1
            p.livery_colours[0].red, p.livery_colours[0].green, p.livery_colours[0].blue = CORES[c]
        self.enviar(bytes(o))

    def pacote_historico(self, t, c, ate_volta):
        o = self.obj(pacotes.PacketSessionHistoryData, 11, t)
        o.car_idx = c
        vs = [v for v in self.voltas[c] if v[0] <= ate_volta]
        o.num_laps = len(vs) + (1 if ate_volta < len(self.voltas[c]) else 0)
        for i, (volta, ms, sec, valida) in enumerate(vs):
            l = o.lap_history_data[i]
            l.lap_time_in_ms = ms
            l.sector1_time_ms_part, l.sector1_time_minutes_part = sec[0] % 60000, sec[0] // 60000
            l.sector2_time_ms_part, l.sector2_time_minutes_part = sec[1] % 60000, sec[1] // 60000
            l.sector3_time_ms_part, l.sector3_time_minutes_part = sec[2] % 60000, sec[2] // 60000
            l.lap_valid_bit_flags = 0x0F if valida else 0x0E
        st = [s for s in self.stints[c]]
        o.num_tyre_stints = len(st)
        for i, (comp, fim) in enumerate(st):
            o.tyre_stints_history_data[i].end_lap = fim if fim <= ate_volta else 255
            o.tyre_stints_history_data[i].tyre_visual_compound = comp
            o.tyre_stints_history_data[i].tyre_actual_compound = comp
        self.enviar(bytes(o))

    def evento(self, t, cod, **kw):
        o = self.obj(pacotes.PacketEventData, 3, t)
        for i, ch in enumerate(cod.encode()):
            o.event_string_code[i] = ch
        d = o.event_details
        if cod == "FTLP":
            d.fastest_lap.vehicle_idx, d.fastest_lap.lap_time = kw["carro"], kw["tempo"]
        elif cod == "OVTK":
            d.overtake.overtaking_vehicle_idx, d.overtake.being_overtaken_vehicle_idx = kw["carro"], kw["outro"]
        elif cod == "PENA":
            p = d.penalty
            p.penalty_type, p.infringement_type, p.vehicle_idx, p.other_vehicle_idx = 10, 26, kw["carro"], 255
            p.lap_num = kw["volta"]
        elif cod == "FLBK":
            d.flashback.flashback_frame_identifier = 0
            d.flashback.flashback_session_time = kw["para"]
        self.enviar(bytes(o))

    # ---------- laço principal
    def rodar(self):
        if self.tipo == "corrida":
            self.grid = {c: g for g, c in enumerate([1, 2, 3, 4, 5, 6, 7, 0, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21])}
        else:
            self.grid = {c: 0 for c in range(N)}
        self.montar_agenda()
        fim_total = max(self.fins[c][-1] for c in range(N)) + (2 if self.tipo == "quali" else 1)
        if self.tipo == "corrida":
            fim_total = min(self.fins[c][-1] for c in range(N)) + 25
        t = 0.0
        self.evento(t, "SSTA")
        combust = 0
        ult_volta = {c: 0 for c in range(N)}
        hist_i = 0
        melhor = (1e9, None)
        posicoes_ant = None
        flashback_feito = False
        while t < fim_total:
            self.frame += 1
            est = {c: self.estado(c, t) for c in range(N)}
            # ordem
            if self.tipo == "corrida":
                def prog(c):
                    e = est[c]
                    if e is None:
                        return 1e6 - self.fins[c][-1]
                    return (e[0] - 1) + e[1] / self.comp - self.grid[c] * 1e-6
                ordem = sorted(range(N), key=lambda c: -prog(c))
            else:
                def melhor_c(c):
                    vs = [v[1] for v in self.voltas[c] if v[3] and v[0] < (est[c][0] if est[c] else 99)]
                    return min(vs) if vs else 1e9 + c
                ordem = sorted(range(N), key=melhor_c)
            pos = {c: i + 1 for i, c in enumerate(ordem)}
            if self.tipo == "corrida" and posicoes_ant and t > 5:
                a, b = posicoes_ant, pos
                if b[0] < a[0]:
                    outro = next(c for c in range(N) if a[c] == b[0])
                    self.evento(t, "OVTK", carro=0, outro=outro)
                elif b[0] > a[0]:
                    outro = next(c for c in range(N) if b[c] == a[0])
                    self.evento(t, "OVTK", carro=outro, outro=0)
            posicoes_ant = pos

            lap, tel, st, mov, dano, tel2 = {}, {}, {}, {}, {}, {}
            for c in range(N):
                e = est[c]
                if e is None:  # terminou
                    sch = self.agenda[c][-1]
                    lap[c] = {"current_lap_num": sch[2], "car_position": pos[c], "result_status": 3,
                              "grid_position": self.grid[c] + 1, "lap_distance": 0, "driver_status": 0}
                    continue
                if e[5]:
                    lap[c] = {"current_lap_num": e[0], "car_position": pos[c], "driver_status": 0,
                              "grid_position": self.grid[c] + 1, "result_status": 2, "pit_status": 2}
                    tel[c] = {"gear": 0, "engine_rpm": 4000}
                    continue
                volta, dist, tms, vel, pit, _g, tipo, j, k = e
                ds = {"out": 3, "in": 2, "in_slow": 2, "flying": 1, "race": 4}[tipo]
                lap[c] = {"current_lap_num": volta, "lap_distance": dist, "total_distance": (volta - 1) * self.comp + dist,
                          "current_lap_time_in_ms": tms, "car_position": pos[c], "pit_status": 1 if pit else 0,
                          "sector": 0 if dist < self.s2 else 1 if dist < self.s3 else 2, "driver_status": ds,
                          "grid_position": self.grid[c] + 1, "result_status": 2,
                          "last_lap_time_in_ms": self.voltas[c][volta - 2][1] if volta > 1 else 0,
                          "current_lap_invalid": 1 if (c == 0 and self.tipo == "quali" and volta == 2) else 0}
                vb = self.v_j if c == 0 else self.v_ia
                nx = (j + 3) % len(vb)
                dv = vb[nx] - vb[j]
                if dv < -1.2:
                    thr, brk = 0.0, min(1.0, -dv / 6)
                elif dv > 0.3:
                    thr, brk = 1.0, 0.0
                else:
                    thr, brk = 0.55 + 0.4 * random.random() * (vel > 60), 0.0
                if pit:
                    thr, brk = 0.3, 0.0
                kmh = vel * 3.6
                gear = 1 + sum(kmh > x for x in [85, 125, 160, 195, 230, 262, 292])
                pi = int(dist / self.comp * len(self.pts)) % len(self.pts)
                x, z = self.pts[pi]
                # temperaturas/desgaste do jogador
                stint_ini = 0 if self.tipo == "quali" else (self.stints[c][0][1] if volta > self.stints[c][0][1] else 0)
                idade = volta - stint_ini - 1 + dist / self.comp
                tel[c] = {"speed": int(kmh), "throttle": thr, "brake": brk, "gear": gear,
                          "steer": max(-1, min(1, 300 / self.raio[j] * (1 if (j // 200) % 2 else -1))),
                          "engine_rpm": int(8000 + (kmh % 40) * 200), "drs": 0,
                          **{f"tyres_surface_temperature{w}": int(92 + 6 * brk + random.uniform(-2, 2) + (3 if w >= 2 else 0)) for w in range(4)},
                          **{f"tyres_inner_temperature{w}": 100 for w in range(4)},
                          **{f"brakes_temperature{w}": int(450 + 500 * brk) for w in range(4)},
                          **{f"tyres_pressure{w}": 23.5 for w in range(4)}}
                comp_vis = self.stints[c][0][0] if (self.tipo == "quali" or volta <= self.stints[c][0][1]) else self.stints[c][1][0]
                st[c] = {"fuel_in_tank": max(0.5, 35 - 2.6 * ((volta - 1) + dist / self.comp)) if self.tipo == "corrida" else 8,
                         "fuel_capacity": 110, "visual_tyre_compound": comp_vis, "actual_tyre_compound": comp_vis,
                         "tyres_age_laps": int(idade), "ers_store_energy": 3.0e6 - 1.2e6 * math.sin(dist / self.comp * math.pi),
                         "ers_deployed_this_lap": (7.0e6 + 0.3e6 * (volta % 3)) * dist / self.comp, "ers_harvested_this_lap_mguk": (6.2e6 + 0.2e6 * (volta % 2)) * dist / self.comp,
                         "max_gears": 8, "max_rpm": 13000,
                         "fuel_remaining_laps": (0.6 + 0.04 * volta - 0.1 * (c % 3)) if self.tipo == "corrida" else 2.0,
                         "ers_harvest_limit_per_lap": 8.5e6,
                         "ers_deploy_mode": (2 if self.tipo == "quali" else 1) if dist < self.comp * 0.55 else (0 if c % 2 else 2)}
                mov[c] = {"world_position_x": x, "world_position_z": z}
                desg = (2.1 if comp_vis == 17 else 1.4 if comp_vis == 18 else 3.0) * idade
                dano[c] = {f"tyres_wear{w}": desg * (1.15 if w >= 2 else 1.0) for w in range(4)}
                tel2[c] = {"overtake_active": 1 if (self.tipo == "corrida" and 4400 < dist < 4900 and c % 3 == 0) else 0,
                           "2026_regulations": 1}
                # conclusão de volta
                if volta != ult_volta[c]:
                    if ult_volta[c] and self.voltas[c][ult_volta[c] - 1][3]:
                        ms = self.voltas[c][ult_volta[c] - 1][1]
                        if ms < melhor[0]:
                            melhor = (ms, c)
                            self.evento(t, "FTLP", carro=c, tempo=ms / 1000)
                    if c == 0 and self.tipo == "quali" and volta == 2:
                        pass
                    if c == 0 and self.tipo == "quali" and volta == 3:
                        self.evento(t, "PENA", carro=0, volta=2)
                    ult_volta[c] = volta
            self.por_carro(0, leitor.MOV, t, mov)
            self.por_carro(2, leitor.LAP, t, lap, b"\xff\xff")
            self.por_carro(6, leitor.TEL, t, tel, b"\xff\xff\x00")
            self.por_carro(7, leitor.STATUS, t, st)
            self.por_carro(16, leitor.TEL2, t, tel2)
            if self.frame % 2 == 0:
                self.por_carro(10, leitor.DANO, t, dano)
            if self.frame % 10 == 0:
                self.pacote_sessao(t)
            if self.frame % 100 == 1:
                self.pacote_participantes(t)
            c = hist_i % N
            hist_i += 1
            e = est[c]
            self.pacote_historico(t, c, (e[0] - 1) if e else 99)

            # um flashback no meio da corrida para testar
            if self.tipo == "corrida" and not flashback_feito and t > 300:
                flashback_feito = True
                self.evento(t, "FLBK", para=t - 8)
                t -= 8
                continue
            t += DT
            if self.ritmo:
                self.ritmo()

        # fim
        self.evento(t, "SEND")
        if self.tipo == "corrida":
            o = self.obj(pacotes.PacketFinalClassificationData, 8, t)
            o.num_cars = N
            pts = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
            for c in range(N):
                d = o.classification_data[c]
                d.position = pos[c]
                d.num_laps = self.voltas_total
                d.grid_position = self.grid[c] + 1
                d.points = pts[pos[c] - 1] if pos[c] <= 10 else 0
                d.num_pit_stops = 1
                d.result_status = 3
                d.best_lap_time_in_ms = min(v[1] for v in self.voltas[c])
                d.total_race_time = self.fins[c][-1] - 3
                d.num_tyre_stints = 2
                for i, (comp, fim) in enumerate(self.stints[c]):
                    d.tyre_stints_visual[i] = comp
                    d.tyre_stints_actual[i] = comp
                    d.tyre_stints_end_laps[i] = fim
            self.enviar(bytes(o))
        for i in range(N * 2):
            self.frame += 1
            self.pacote_historico(t, i % N, 99)
            if self.ritmo:
                self.ritmo()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tipo", choices=["quali", "corrida"])
    ap.add_argument("--udp", action="store_true")
    ap.add_argument("--porta", type=int, default=20777)
    ap.add_argument("--arquivo")
    ap.add_argument("--velocidade", type=float, default=40, help="quantas vezes mais rápido que o tempo real (UDP)")
    a = ap.parse_args()
    if a.udp:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        destino = ("127.0.0.1", a.porta)
        sim = Sim(a.tipo, lambda d: sock.sendto(d, destino))
        espera = DT / a.velocidade
        sim.ritmo = lambda: time.sleep(espera)
    else:
        f = open(a.arquivo, "wb")
        f.write(leitor.MAGIC)

        def grava(d):
            f.write(struct.pack("<H", len(d)))
            f.write(d)
        sim = Sim(a.tipo, grava)
        sim.ritmo = None
    sim.rodar()
    print("simulação concluída, frames:", sim.frame)


if __name__ == "__main__":
    main()
