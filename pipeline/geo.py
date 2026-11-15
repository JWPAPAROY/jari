"""순수 파이썬 좌표 변환 + shapefile 폴리곤 읽기 (외부 라이브러리 없음).

- 인허가(LOCALDATA) 좌표: Bessel 기반 중부원점 TM (EPSG:2097 또는 5174 계열)
- 상권 영역 shapefile: Korea 2000 중부원점 (EPSG:5181, GRS80)
"""
import math, struct

BESSEL = (6377397.155, 1 / 299.1528128)
GRS80 = (6378137.0, 1 / 298.257222101)


def _tm_consts(a, f):
    e2 = f * (2 - f)
    return a, e2


def tm_inverse(x, y, ell, lon0, lat0=38.0, fe=200000.0, fn=500000.0, k0=1.0):
    a, e2 = _tm_consts(*ell)
    ep2 = e2 / (1 - e2)
    def M(phi):
        return a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
                    - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * phi)
                    + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
                    - (35 * e2**3 / 3072) * math.sin(6 * phi))
    m = M(math.radians(lat0)) + (y - fn) / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
            + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
            + (151 * e1**3 / 96) * math.sin(6 * mu) + (1097 * e1**4 / 512) * math.sin(8 * mu))
    c1 = ep2 * math.cos(phi1)**2
    t1 = math.tan(phi1)**2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
    d = (x - fe) / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
                                              + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720)
    lon = math.radians(lon0) + (d - (1 + 2 * t1 + c1) * d**3 / 6
                                + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def tm_forward(lat, lon, ell, lon0, lat0=38.0, fe=200000.0, fn=500000.0, k0=1.0):
    a, e2 = _tm_consts(*ell)
    ep2 = e2 / (1 - e2)
    phi, lam = math.radians(lat), math.radians(lon)
    def M(p):
        return a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * p
                    - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * p)
                    + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * p)
                    - (35 * e2**3 / 3072) * math.sin(6 * p))
    n = a / math.sqrt(1 - e2 * math.sin(phi)**2)
    t = math.tan(phi)**2
    c = ep2 * math.cos(phi)**2
    A = (lam - math.radians(lon0)) * math.cos(phi)
    x = fe + k0 * n * (A + (1 - t + c) * A**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * A**5 / 120)
    y = fn + k0 * (M(phi) - M(math.radians(lat0)) + n * math.tan(phi) * (
        A**2 / 2 + (5 - t + 9 * c + 4 * c**2) * A**4 / 24 + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * A**6 / 720))
    return x, y


def _to_ecef(lat, lon, ell):
    a, f = ell
    e2 = f * (2 - f)
    p, l = math.radians(lat), math.radians(lon)
    n = a / math.sqrt(1 - e2 * math.sin(p)**2)
    return n * math.cos(p) * math.cos(l), n * math.cos(p) * math.sin(l), n * (1 - e2) * math.sin(p)


def _from_ecef(X, Y, Z, ell):
    a, f = ell
    e2 = f * (2 - f)
    lon = math.atan2(Y, X)
    p = math.hypot(X, Y)
    lat = math.atan2(Z, p * (1 - e2))
    for _ in range(6):
        n = a / math.sqrt(1 - e2 * math.sin(lat)**2)
        lat = math.atan2(Z + e2 * n * math.sin(lat), p)
    return math.degrees(lat), math.degrees(lon)


def bessel_to_grs80(lat, lon, shift, rot=(0, 0, 0), ppm=0):
    """Bessel → GRS80. 7변수(Position Vector, proj towgs84와 같은 방식): 이동(m), 회전(초), 축척(ppm)."""
    X, Y, Z = _to_ecef(lat, lon, BESSEL)
    rx, ry, rz = (math.radians(v / 3600) for v in rot); k = 1 + ppm * 1e-6
    X2 = shift[0] + k * (X - rz * Y + ry * Z)
    Y2 = shift[1] + k * (rz * X + Y - rx * Z)
    Z2 = shift[2] + k * (-ry * X + rx * Y + Z)
    return _from_ecef(X2, Y2, Z2, GRS80)


# EPSG 정의. 5174는 회전·축척까지 넣어야 함: 이동량 3개만 쓰면 서울에서 북쪽 약 15m·서쪽 약 8m 어긋남(2026-11-15 확인)
VARIANTS = {
    '2097': dict(lon0=127.0, shift=(-146.43, 507.89, 681.46)),
    '5174': dict(lon0=127.0028902777778, shift=(-115.80, 474.99, 674.11), rot=(1.16, -2.31, -1.63), ppm=6.43),
}


def localdata_to_latlon(x, y, variant):
    v = VARIANTS[variant]
    lat, lon = tm_inverse(x, y, BESSEL, v['lon0'])
    return bessel_to_grs80(lat, lon, v['shift'], v.get('rot', (0, 0, 0)), v.get('ppm', 0))


def latlon_to_5181(lat, lon):
    return tm_forward(lat, lon, GRS80, 127.0)


def read_shp_polygons(shp_bytes):
    """shapefile(.shp) 폴리곤 → [(bbox, [ring,...]), ...] 레코드 순서대로."""
    out = []
    pos = 100
    n = len(shp_bytes)
    while pos < n:
        _, clen = struct.unpack('>ii', shp_bytes[pos:pos + 8])
        rec = shp_bytes[pos + 8: pos + 8 + clen * 2]
        pos += 8 + clen * 2
        stype = struct.unpack('<i', rec[:4])[0]
        if stype == 0:
            out.append(None)
            continue
        bbox = struct.unpack('<4d', rec[4:36])
        nparts, npts = struct.unpack('<ii', rec[36:44])
        parts = list(struct.unpack(f'<{nparts}i', rec[44:44 + 4 * nparts]))
        off = 44 + 4 * nparts
        pts = [struct.unpack('<2d', rec[off + 16 * i: off + 16 * i + 16]) for i in range(npts)]
        rings = [pts[parts[i]: parts[i + 1] if i + 1 < nparts else npts] for i in range(nparts)]
        out.append((bbox, rings))
    return out


def read_dbf(dbf_bytes, encoding='utf-8'):
    nrec, hlen, rlen = struct.unpack('<IHH', dbf_bytes[4:12])
    fields = []
    i = 32
    while dbf_bytes[i] != 0x0D:
        name = dbf_bytes[i:i + 11].split(b'\x00')[0].decode('ascii', 'replace')
        flen = dbf_bytes[i + 16]
        fields.append((name, flen))
        i += 32
    rows = []
    for r in range(nrec):
        base = hlen + r * rlen + 1
        row, o = {}, base
        for name, flen in fields:
            row[name] = dbf_bytes[o:o + flen].decode(encoding, 'replace').strip()
            o += flen
        rows.append(row)
    return rows


def point_in_rings(x, y, rings):
    inside = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
                inside = not inside
            j = i
    return inside
