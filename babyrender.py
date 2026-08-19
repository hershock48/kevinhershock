"""
Render the Dancing Baby the way the 1996 original was made: as an actual
3D model, lit and rendered, then baked to frames.

The original was Viewpoint DataLabs' "Toddler with Diaper" model #5653 --
a scan of a plastic doll -- rigged in Character Studio and rendered at
Rhythm & Hues. Rather than draw a baby frame by frame, this builds the doll
as a signed-distance field (smooth-unioned ellipsoids and round cones,
which is how moulded vinyl actually reads: soft blended joints, no seams),
rigs it with a forward-kinematic skeleton, and ray-marches each frame.

Output is an RGBA sprite atlas the site plays back.
"""
import numpy as np
from PIL import Image
import math, sys

# ----------------------------------------------------------------- SDF prims

def sd_ellipsoid(p, r):
    """IQ's bounded ellipsoid approximation. p:(N,3) r:(3,)"""
    k0 = np.sqrt(np.sum((p / r) ** 2, axis=1))
    k1 = np.sqrt(np.sum((p / (r * r)) ** 2, axis=1))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_round_cone(p, a, b, r1, r2):
    """Exact round cone (tapered capsule) from a to b. IQ's formulation."""
    ba = b - a
    l2 = float(np.dot(ba, ba))
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - ba[None, :] * y[:, None]
    x2 = np.sum(xv * xv, axis=1)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    out = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - r1
    m1 = np.sign(z) * a2 * z2 > k
    m2 = (~m1) & (np.sign(y) * a2 * y2 < k)
    out = np.where(m1, np.sqrt(np.maximum(x2 + z2, 0)) * il2 - r2, out)
    out = np.where(m2, np.sqrt(np.maximum(x2 + y2, 0)) * il2 - r1, out)
    return out


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


# ----------------------------------------------------------------- transforms

def rotx(t):
    c, s = math.cos(t), math.sin(t)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)

def roty(t):
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)

def rotz(t):
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)


def sstep(a, b, t):
    x = min(1.0, max(0.0, (t - a) / (b - a)))
    return x * x * (3 - 2 * x)


# ----------------------------------------------------------------- the rig
# Units: head radius = 1.0. y up, +z toward the camera.

REST = dict(
    pelvis=np.array([0.00,  0.00, 0.00]),
    chest =np.array([0.00,  1.42, 0.00]),
    neck  =np.array([0.00,  2.02, 0.00]),
    headc =np.array([0.00,  2.86, 0.00]),
    shL   =np.array([-0.78, 1.72, 0.00]),
    shR   =np.array([ 0.78, 1.72, 0.00]),
    hipL  =np.array([-0.40,-0.26, 0.00]),
    hipR  =np.array([ 0.40,-0.26, 0.00]),
)
UPPER_ARM, FOREARM = 0.92, 0.80
THIGH, CALF = 1.14, 1.06


def pose(t):
    """Joint angles for beat t. The routine is the documented one:
       cha-cha with arm thrusts and hip sways (0-4), a burst of air guitar
       (4-6), then bend over and shake the shoulders (6-8)."""
    cyc = t % 8.0
    ph = cyc * math.pi
    P = {}

    if cyc < 4.0:                                   # ---- cha-cha
        sw = math.sin(ph)
        P['rootY'] = 0.20 * sw
        P['bob'] = -0.13 * abs(math.sin(2 * ph))
        P['rootX'] = 0.08 * sw
        P['pelvisZ'] = 0.17 * sw
        P['chestY'] = -0.24 * sw
        P['chestZ'] = -0.11 * sw
        P['chestX'] = 0.06
        P['headY'] = 0.10 * sw
        P['headZ'] = 0.09 * sw
        P['headX'] = -0.04
        arms, legs = {}, {}
        for s, key in ((-1, 'L'), (1, 'R')):
            a = math.sin(ph + (math.pi if s > 0 else 0.0))
            # shoulders out and up, elbows cocked -- the thrust
            arms[key] = dict(
                abd=s * (0.95 + 0.42 * a),          # away from the body (z rot)
                fwd=-0.30 - 0.22 * a,               # toward camera (x rot)
                twist=s * 0.25,
                elbow=1.25 + 0.55 * a,
            )
            lift = max(0.0, s * sw)
            legs[key] = dict(
                hipX=-0.34 * lift, hipZ=s * (0.10 + 0.16 * lift),
                knee=0.30 + 0.62 * lift, ankle=0.18 - 0.24 * lift,
            )
        P['arms'], P['legs'] = arms, legs

    elif cyc < 6.0:                                 # ---- air guitar
        u = cyc - 4.0
        turn = sstep(0, 0.5, u) * 0.62
        strum = math.sin(u * math.pi * 4)
        P['rootY'] = turn
        P['bob'] = -0.10 * abs(math.sin(u * math.pi * 2))
        P['rootX'] = 0.0
        P['pelvisZ'] = 0.06 * math.sin(u * math.pi * 2)
        P['chestY'] = -0.18
        P['chestZ'] = -0.06
        P['chestX'] = 0.10
        P['headY'] = -0.20
        P['headZ'] = 0.14
        P['headX'] = -0.10
        # left hand up on the neck of the guitar, right hand strumming
        P['arms'] = {
            'L': dict(abd=-1.15, fwd=-1.05, twist=-0.5, elbow=1.55),
            'R': dict(abd=0.55, fwd=-0.55 - strum * 0.30, twist=0.6,
                      elbow=1.85 + strum * 0.45),
        }
        P['legs'] = {
            'L': dict(hipX=-0.10, hipZ=-0.14, knee=0.34, ankle=0.16),
            'R': dict(hipX=0.05, hipZ=0.16, knee=0.30, ankle=0.16),
        }

    else:                                           # ---- bend over and shake
        u = cyc - 6.0
        bend = sstep(0, 0.7, u) * (1.0 - sstep(1.5, 2.0, u))
        shake = math.sin(u * math.pi * 8) * bend
        P['rootY'] = 0.0
        P['bob'] = -0.16 * bend
        P['rootX'] = 0.0
        P['pelvisZ'] = 0.05 * shake
        P['chestX'] = 0.95 * bend                   # fold forward at the waist
        P['chestY'] = 0.30 * shake                  # shoulders shaking
        P['chestZ'] = 0.10 * shake
        P['headX'] = -0.45 * bend
        P['headY'] = -0.18 * shake
        P['headZ'] = 0.0
        arms, legs = {}, {}
        for s, key in ((-1, 'L'), (1, 'R')):
            arms[key] = dict(abd=s * (0.42 + 0.10 * bend),
                             fwd=-0.30 - 0.55 * bend + shake * s * 0.25,
                             twist=s * 0.2,
                             elbow=0.55 + 0.40 * bend)
            legs[key] = dict(hipX=0.22 * bend, hipZ=s * 0.13,
                             knee=0.30 + 0.45 * bend, ankle=0.14)
        P['arms'], P['legs'] = arms, legs
    return P


def skeleton(t):
    """Forward kinematics -> world joint positions and part frames."""
    P = pose(t)
    root = roty(P['rootY']) @ rotx(P['rootX'])
    rootT = np.array([0.0, P['bob'], 0.0])

    def W(v):                       # rest-space point -> world
        return root @ v + rootT

    pelvisR = root @ rotz(P['pelvisZ'])
    pelvis = rootT.copy()
    chestR = pelvisR @ roty(P['chestY']) @ rotx(P['chestX']) @ rotz(P['chestZ'])
    chest = pelvis + pelvisR @ REST['chest']
    headR = chestR @ roty(P['headY']) @ rotx(P['headX']) @ rotz(P['headZ'])
    neck = chest + chestR @ (REST['neck'] - REST['chest'])
    headc = neck + headR @ (REST['headc'] - REST['neck'])

    J = dict(pelvis=pelvis, chest=chest, neck=neck, headc=headc,
             pelvisR=pelvisR, chestR=chestR, headR=headR, rootR=root)

    for s, key in ((-1, 'L'), (1, 'R')):
        A = P['arms'][key]
        sh = chest + chestR @ (REST['sh' + key] - REST['chest'])
        aR = chestR @ rotz(A['abd']) @ rotx(A['fwd']) @ roty(A['twist'])
        elbow = sh + aR @ np.array([s * UPPER_ARM * 0.55, -UPPER_ARM * 0.83, 0.0])
        fR = aR @ rotx(-A['elbow'])
        wrist = elbow + fR @ np.array([s * FOREARM * 0.42, -FOREARM * 0.90, 0.0])
        J['sh' + key], J['el' + key], J['wr' + key] = sh, elbow, wrist
        J['fR' + key] = fR

        L = P['legs'][key]
        hip = pelvis + pelvisR @ REST['hip' + key]
        lR = pelvisR @ rotz(L['hipZ']) @ rotx(L['hipX'])
        knee = hip + lR @ np.array([0.0, -THIGH, 0.0])
        cR = lR @ rotx(L['knee'])
        ankle = knee + cR @ np.array([0.0, -CALF, 0.0])
        J['hip' + key], J['kn' + key], J['an' + key] = hip, knee, ankle
        J['cR' + key] = cR
    return J


# ----------------------------------------------------------------- the doll

def make_sdf(J):
    """Returns f(p)->distance. Skin is one smooth blend; the nappy is a
       separate solid so it can carry its own colour."""
    hR, hRi = J['headR'], J['headR'].T
    cR, cRi = J['chestR'], J['chestR'].T
    pR, pRi = J['pelvisR'], J['pelvisR'].T

    def skin(p):
        # head: cranium + jaw, blended -- a big braincase with a small face
        ph = (p - J['headc']) @ hR
        d = sd_ellipsoid(ph, np.array([1.00, 1.06, 1.00]))
        d = smin(d, sd_ellipsoid(ph - np.array([0, -0.52, 0.16]),
                                 np.array([0.74, 0.60, 0.80])), 0.34)
        # ears
        for s in (-1, 1):
            d = smin(d, sd_ellipsoid(ph - np.array([s * 0.96, -0.06, -0.10]),
                                     np.array([0.15, 0.28, 0.13])), 0.10)
        # a moulded nose, barely there
        d = smin(d, sd_ellipsoid(ph - np.array([0, -0.30, 0.92]),
                                 np.array([0.14, 0.11, 0.14])), 0.13)
        # neck
        d = smin(d, sd_round_cone(p, J['chest'] + (J['neck'] - J['chest']) * 0.3,
                                  J['headc'] + (J['neck'] - J['headc']) * 0.30,
                                  0.40, 0.36), 0.30)
        # torso: chest over a toddler belly, then the hips
        pc = (p - J['chest']) @ cR
        d = smin(d, sd_ellipsoid(pc - np.array([0, -0.10, 0]),
                                 np.array([0.80, 0.68, 0.60])), 0.26)
        d = smin(d, sd_ellipsoid(pc - np.array([0, -0.86, 0.04]),
                                 np.array([0.80, 0.66, 0.64])), 0.30)
        pp = (p - J['pelvis']) @ pR
        d = smin(d, sd_ellipsoid(pp - np.array([0, -0.10, 0]),
                                 np.array([0.74, 0.52, 0.58])), 0.30)
        # limbs
        for key in ('L', 'R'):
            d = smin(d, sd_round_cone(p, J['sh' + key], J['el' + key], 0.31, 0.25), 0.16)
            d = smin(d, sd_round_cone(p, J['el' + key], J['wr' + key], 0.25, 0.20), 0.12)
            fR = J['fR' + key]
            hand = J['wr' + key] + fR @ np.array([0, -0.20, 0.03])
            d = smin(d, sd_ellipsoid((p - hand) @ fR,
                                     np.array([0.24, 0.26, 0.15])), 0.10)
            d = smin(d, sd_round_cone(p, J['hip' + key], J['kn' + key], 0.46, 0.34), 0.22)
            d = smin(d, sd_round_cone(p, J['kn' + key], J['an' + key], 0.34, 0.25), 0.16)
            cRk = J['cR' + key]
            foot = J['an' + key] + cRk @ np.array([0, -0.14, 0.20])
            d = smin(d, sd_ellipsoid((p - foot) @ cRk,
                                     np.array([0.25, 0.19, 0.42])), 0.12)
        return d

    def nappy(p):
        pp = (p - J['pelvis']) @ pR
        d = sd_ellipsoid(pp - np.array([0, -0.12, 0]),
                         np.array([0.86, 0.66, 0.70]))
        # trim it to a low band so it sits on the hips, not up the belly
        d = np.maximum(d, pp[:, 1] - 0.40)
        d = np.maximum(d, -(pp[:, 1] + 0.86))
        return d

    return skin, nappy


# ----------------------------------------------------------------- rendering

W, H = 176, 250
SS = 2                                     # supersample factor
KEY = np.array([-0.30, 0.46, 0.84]); KEY /= np.linalg.norm(KEY)
FILL = np.array([0.72, 0.10, 0.68]); FILL /= np.linalg.norm(FILL)
RIM = np.array([0.10, 0.30, -0.95]); RIM /= np.linalg.norm(RIM)
SKIN = np.array([0.930, 0.876, 0.858])     # pale unpainted vinyl, faintly pink
NAPPY = np.array([0.706, 0.784, 0.778])    # the blue-grey cloth


def render(t):
    w, h = W * SS, H * SS
    J = skeleton(t)
    skin, nappy = make_sdf(J)

    def f(p):
        return np.minimum(skin(p), nappy(p))

    # camera: long lens, slight perspective, framed on the whole doll
    view_h = 7.9
    cam = np.array([0.0, 0.55, 17.0])
    xs = (np.arange(w) + 0.5) / w * (view_h * w / h) - (view_h * w / h) / 2
    ys = (view_h / 2) - (np.arange(h) + 0.5) / h * view_h
    gx, gy = np.meshgrid(xs, ys)
    tgt = np.stack([gx.ravel(), gy.ravel() + 0.30, np.zeros(gx.size)], 1)
    ro = np.broadcast_to(cam, tgt.shape).copy()
    rd = tgt - ro
    rd /= np.linalg.norm(rd, axis=1, keepdims=True)

    n = tgt.shape[0]
    tt = np.full(n, 11.0)
    alive = np.arange(n)
    hit = np.zeros(n, bool)
    for _ in range(90):
        if alive.size == 0:
            break
        p = ro[alive] + rd[alive] * tt[alive][:, None]
        d = f(p)
        tt[alive] += d * 0.92
        done = d < 0.0016
        hit[alive[done]] = True
        keep = (~done) & (tt[alive] < 24.0)
        alive = alive[keep]

    img = np.zeros((n, 4), np.float32)
    idx = np.nonzero(hit)[0]
    if idx.size:
        p = ro[idx] + rd[idx] * tt[idx][:, None]
        # normals by central difference
        e = 0.0035
        nrm = np.empty_like(p)
        for k in range(3):
            off = np.zeros(3); off[k] = e
            nrm[:, k] = f(p + off) - f(p - off)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)

        # material: nappy where its own field is the nearer one
        ds, dn = skin(p), nappy(p)
        is_nap = dn < ds
        base = np.where(is_nap[:, None], NAPPY, SKIN).astype(np.float32)

        # painted features, tested in head-local space so they ride the head
        ph = (p - J['headc']) @ J['headR']
        front = ph[:, 2] > 0.25
        for s in (-1, 1):
            e_ = (((ph[:, 0] - s * 0.335) / 0.175) ** 2 +
                  ((ph[:, 1] - 0.02) / 0.085) ** 2 +
                  ((ph[:, 2] - 0.92) / 0.75) ** 2)
            m = front & (e_ < 1.0)
            base[m] *= 0.30                                    # half-lidded eye
            e_ = (((ph[:, 0] - s * 0.335) / 0.20) ** 2 +
                  ((ph[:, 1] + 0.115) / 0.055) ** 2 +
                  ((ph[:, 2] - 0.92) / 0.75) ** 2)
            base[front & (e_ < 1.0)] *= 0.86                   # lower lid
        e_ = ((ph[:, 0] / 0.20) ** 2 + ((ph[:, 1] + 0.60) / 0.055) ** 2 +
              ((ph[:, 2] - 0.85) / 0.75) ** 2)
        base[front & (e_ < 1.0)] *= 0.74                       # mouth line

        # ambient occlusion: how much of the field crowds the normal
        ao = np.ones(p.shape[0], np.float32)
        for i in range(1, 6):
            hstep = 0.05 * i
            ao -= (hstep - np.maximum(f(p + nrm * hstep), 0)) * (0.55 ** i) * 1.5
        ao = np.clip(ao, 0.25, 1.0)

        # wrap-around key: vinyl this pale scatters, so the terminator is soft
        raw = nrm @ KEY
        ndl = np.clip((raw + 0.45) / 1.45, 0.0, 1.0) ** 1.25
        ndf = np.maximum(nrm @ FILL, 0.0)
        ndr = np.maximum(nrm @ RIM, 0.0) ** 2
        vdir = -rd[idx]
        hvec = KEY + vdir
        hvec /= np.maximum(np.linalg.norm(hvec, axis=1, keepdims=True), 1e-9)
        spec = np.maximum(np.sum(nrm * hvec, axis=1), 0.0) ** 13 * 0.20
        # hemispheric ambient plus a floor bounce -- in the reference nothing
        # ever falls to black, not even the undersides of the arms
        sky = 0.72 + 0.28 * nrm[:, 1]
        bounce = np.maximum(-nrm[:, 1], 0.0) ** 1.5

        lit = (base * (0.42 * (ao * sky)[:, None]
                       + 0.58 * ndl[:, None]
                       + 0.18 * ndf[:, None] * np.array([0.84, 0.89, 1.0])
                       + 0.15 * bounce[:, None] * np.array([1.0, 0.95, 0.90])
                       + 0.11 * ndr[:, None] * np.array([1.0, 0.96, 0.93]))
               + spec[:, None] * np.array([1.0, 0.99, 0.96]) * ao[:, None])
        lit = np.clip(lit, 0, 1) ** (1 / 1.08)
        img[idx, :3] = np.clip(lit, 0, 1)
        img[idx, 3] = 1.0

    img = img.reshape(h, w, 4)
    # box-downsample with premultiplied alpha so edges don't fringe
    img[..., :3] *= img[..., 3:]
    img = img.reshape(H, SS, W, SS, 4).mean(axis=(1, 3))
    a = img[..., 3:]
    img[..., :3] = np.divide(img[..., :3], np.maximum(a, 1e-6))
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


if __name__ == '__main__':
    NF = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    COLS = 8
    rows = (NF + COLS - 1) // COLS
    atlas = Image.new('RGBA', (COLS * W, rows * H), (0, 0, 0, 0))
    for i in range(NF):
        t = i / NF * 8.0
        fr = Image.fromarray(render(t), 'RGBA')
        atlas.paste(fr, ((i % COLS) * W, (i // COLS) * H))
        print(f'frame {i+1}/{NF}', flush=True)
    atlas.save('/home/claude/baby_atlas.png')
    atlas.save('/home/claude/baby_atlas.webp', quality=86, method=6)
    print('atlas', atlas.size)
