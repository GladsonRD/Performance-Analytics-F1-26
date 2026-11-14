"""Leitura rápida das gravações .f1rec (struct em vez de ctypes campo a campo)."""

import ctypes
import gzip
import struct

import pacotes

MAGIC = b"F1REC1\n"
CAB = struct.Struct("<HBBBBBQfIIBB")
TAM_CAB = CAB.size

_CODIGOS = {
    ctypes.c_uint8: "B", ctypes.c_int8: "b", ctypes.c_uint16: "H", ctypes.c_int16: "h",
    ctypes.c_uint32: "I", ctypes.c_int32: "i", ctypes.c_uint64: "Q", ctypes.c_float: "f",
    ctypes.c_double: "d", ctypes.c_uint: "I",
}


def _achatar(cls, prefixo=""):
    fmt, nomes = "", []
    for nome, tipo in cls._fields_:
        if hasattr(tipo, "_length_") and hasattr(tipo, "_type_") and tipo._type_ is ctypes.c_char:
            fmt += f"{tipo._length_}s"
            nomes.append(prefixo + nome)
        elif hasattr(tipo, "_length_"):
            base = tipo._type_
            for i in range(tipo._length_):
                if base in _CODIGOS:
                    fmt += _CODIGOS[base]
                    nomes.append(f"{prefixo}{nome}{i}")
                else:
                    f, n = _achatar(base, f"{prefixo}{nome}{i}_")
                    fmt += f
                    nomes += n
        elif tipo in _CODIGOS:
            fmt += _CODIGOS[tipo]
            nomes.append(prefixo + nome)
        else:
            f, n = _achatar(tipo, prefixo + nome + "_")
            fmt += f
            nomes += n
    return fmt, nomes


class PorCarro:
    """Desempacota o bloco de um carro (ex.: LapData) de um pacote de 24 carros."""

    def __init__(self, cls_carro):
        fmt, self.nomes = _achatar(cls_carro)
        self.st = struct.Struct("<" + fmt)
        assert self.st.size == ctypes.sizeof(cls_carro), cls_carro
        self.idx = {n: i for i, n in enumerate(self.nomes)}

    def ler(self, dados, carro):
        return self.st.unpack_from(dados, TAM_CAB + carro * self.st.size)

    def ler_dict(self, dados, carro):
        return dict(zip(self.nomes, self.ler(dados, carro)))


LAP = PorCarro(pacotes.LapData)
TEL = PorCarro(pacotes.CarTelemetryData)
STATUS = PorCarro(pacotes.CarStatusData)
DANO = PorCarro(pacotes.CarDamageData)
MOV = PorCarro(pacotes.CarMotionData)
TEL2 = PorCarro(pacotes.CarTelemetry2Data)

TAMANHOS = {k[2]: v.size() for k, v in pacotes.HEADER_FIELD_TO_PACKET_TYPE.items()}
TIPOS = {k[2]: v for k, v in pacotes.HEADER_FIELD_TO_PACKET_TYPE.items()}


def completo(pid, dados):
    """Garante o tamanho esperado (preenche com zeros se vier menor)."""
    t = TAMANHOS.get(pid)
    if t and len(dados) < t:
        return dados + bytes(t - len(dados))
    return dados


def objeto(pid, dados):
    return TIPOS[pid].from_buffer_copy(completo(pid, dados)[:TAMANHOS[pid]])


def registros(caminho):
    """Gera (índice, cabeçalho, dados) para cada pacote gravado."""
    with open(caminho, "rb") as f:
        inicio = f.read(2)
    abrir = gzip.open if inicio == b"\x1f\x8b" else open
    with abrir(caminho, "rb") as f:
        try:
            bruto = f.read()
        except EOFError:  # gzip sem final (gravação interrompida)
            bruto = _ler_gzip_truncado(caminho)
    if not bruto.startswith(MAGIC):
        raise ValueError("Arquivo não é uma gravação .f1rec")
    pos = len(MAGIC)
    n = len(bruto)
    i = 0
    while pos + 2 <= n:
        (tam,) = struct.unpack_from("<H", bruto, pos)
        pos += 2
        if pos + tam > n:
            break  # gravação cortada no meio de um pacote
        dados = bruto[pos:pos + tam]
        pos += tam
        if tam >= TAM_CAB:
            cab = CAB.unpack_from(dados)
            yield i, cab, dados
            i += 1


def _ler_gzip_truncado(caminho):
    import zlib
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    partes = []
    with open(caminho, "rb") as f:
        while True:
            bloco = f.read(1 << 20)
            if not bloco:
                break
            try:
                partes.append(d.decompress(bloco))
            except zlib.error:
                break
    return b"".join(partes)
