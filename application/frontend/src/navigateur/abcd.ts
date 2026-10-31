// Critères ABCD dans le navigateur : portage de backend/dermia/engine/abcd.py (scipy.ndimage, scikit-image).
// La fidélité au code Python est vérifiée sur de vraies images (outils/verifier_navigateur.py).
import { arrondiPython, redimensionner, reduire, type ImageRGB } from './image'

const TAILLE = 320
const COULEURS: [string, number, number, number][] = [['blanc', 88, 0, 6], ['rouge', 45, 45, 25], ['brun_clair', 55, 18, 32],
  ['brun_fonce', 30, 15, 18], ['bleu_gris', 45, -2, -10], ['noir', 12, 2, 2]]
const PEAU: [number, number, number] = [68, 20, 18]
const NB_SECTEURS = 8

export interface Seuils { forme: number; couleur: number; abrupt: number; part_couleur: number }
type Masque = Uint8Array

const arr = (x: number, n: number) => Math.round(x * 10 ** n) / 10 ** n

function disque(r: number): [number, number][] {
  const p: [number, number][] = []
  for (let y = -r; y <= r; y++) for (let x = -r; x <= r; x++) if (x * x + y * y <= r * r) p.push([y, x])
  return p
}
const CROIX: [number, number][] = [[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1]]

/** Dilatation binaire (hors image = 0). */
function dilater(m: Masque, h: number, w: number, s: [number, number][], iterations = 1): Masque {
  let cour = m
  for (let t = 0; t < iterations; t++) {
    const out = new Uint8Array(m.length)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (!cour[y * w + x]) continue
        for (const [dy, dx] of s) {
          const r = y + dy, c = x + dx
          if (r >= 0 && r < h && c >= 0 && c < w) out[r * w + c] = 1
        }
      }
    }
    cour = out
  }
  return cour
}

/** Érosion binaire (hors image = 0 : les bords sont érodés). */
function eroder(m: Masque, h: number, w: number, s: [number, number][], iterations = 1): Masque {
  let cour = m
  for (let t = 0; t < iterations; t++) {
    const out = new Uint8Array(m.length)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let ok = 1
        for (const [dy, dx] of s) {
          const r = y + dy, c = x + dx
          if (r < 0 || r >= h || c < 0 || c >= w || !cour[r * w + c]) { ok = 0; break }
        }
        out[y * w + x] = ok
      }
    }
    cour = out
  }
  return cour
}

/** Ouverture / fermeture avec bords prolongés (comme _morpho en Python). */
function morpho(type: 'ouverture' | 'fermeture', m: Masque, h: number, w: number, rayon: number): Masque {
  const p = rayon + 1, H = h + 2 * p, W = w + 2 * p
  const g = new Uint8Array(H * W)
  for (let y = 0; y < H; y++) {
    const r = Math.min(h - 1, Math.max(0, y - p))
    for (let x = 0; x < W; x++) g[y * W + x] = m[r * w + Math.min(w - 1, Math.max(0, x - p))]
  }
  const d = disque(rayon)
  const res = type === 'ouverture' ? dilater(eroder(g, H, W, d), H, W, d) : eroder(dilater(g, H, W, d), H, W, d)
  const out = new Uint8Array(h * w)
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) out[y * w + x] = res[(y + p) * W + x + p]
  return out
}

/** Composantes connexes ; retourne les étiquettes (1..n) et n. */
function etiqueter(m: Masque, h: number, w: number, voisins8: boolean): [Int32Array, number] {
  const lab = new Int32Array(m.length)
  const vois = voisins8 ? [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]] : [[-1, 0], [1, 0], [0, -1], [0, 1]]
  let n = 0
  const pile: number[] = []
  for (let i = 0; i < m.length; i++) {
    if (!m[i] || lab[i]) continue
    lab[i] = ++n
    pile.push(i)
    while (pile.length) {
      const p = pile.pop()!, y = Math.floor(p / w), x = p - y * w
      for (const [dy, dx] of vois) {
        const r = y + dy, c = x + dx
        if (r < 0 || r >= h || c < 0 || c >= w) continue
        const q = r * w + c
        if (m[q] && !lab[q]) { lab[q] = n; pile.push(q) }
      }
    }
  }
  return [lab, n]
}

function remplirTrous(m: Masque, h: number, w: number): Masque {
  const dehors = new Uint8Array(m.length)
  const pile: number[] = []
  const pousser = (i: number) => { if (!m[i] && !dehors[i]) { dehors[i] = 1; pile.push(i) } }
  for (let x = 0; x < w; x++) { pousser(x); pousser((h - 1) * w + x) }
  for (let y = 0; y < h; y++) { pousser(y * w); pousser(y * w + w - 1) }
  while (pile.length) {
    const p = pile.pop()!, y = Math.floor(p / w), x = p - y * w
    if (y > 0) pousser(p - w)
    if (y < h - 1) pousser(p + w)
    if (x > 0) pousser(p - 1)
    if (x < w - 1) pousser(p + 1)
  }
  const out = new Uint8Array(m.length)
  for (let i = 0; i < m.length; i++) out[i] = dehors[i] ? 0 : 1
  return out
}

const reflet = (i: number, n: number) => (i < 0 ? -i - 1 : i >= n ? 2 * n - 1 - i : i)

/** Fermeture en niveaux de gris par un disque, bords en miroir (skimage.morphology.closing). */
function fermetureGris(a: Float64Array, h: number, w: number, s: [number, number][]): Float64Array {
  const passe = (src: Float64Array, max: boolean) => {
    const out = new Float64Array(src.length)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let v = max ? -Infinity : Infinity
        for (const [dy, dx] of s) {
          const u = src[reflet(y + dy, h) * w + reflet(x + dx, w)]
          if (max ? u > v : u < v) v = u
        }
        out[y * w + x] = v
      }
    }
    return out
  }
  return passe(passe(a, true), false)
}

/** Filtre gaussien, bords prolongés (scipy.ndimage.gaussian_filter, truncate = 4). */
function gaussien(a: Float64Array, h: number, w: number, sigma: number): Float64Array {
  const r = Math.trunc(4 * sigma + 0.5)
  const k = new Float64Array(2 * r + 1)
  let somme = 0
  for (let i = -r; i <= r; i++) { k[i + r] = Math.exp((-0.5 * i * i) / (sigma * sigma)); somme += k[i + r] }
  for (let i = 0; i < k.length; i++) k[i] /= somme
  const tmp = new Float64Array(a.length), out = new Float64Array(a.length)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0
      for (let i = -r; i <= r; i++) s += k[i + r] * a[y * w + Math.min(w - 1, Math.max(0, x + i))]
      tmp[y * w + x] = s
    }
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0
      for (let i = -r; i <= r; i++) s += k[i + r] * tmp[Math.min(h - 1, Math.max(0, y + i)) * w + x]
      out[y * w + x] = s
    }
  }
  return out
}

function otsu(vals: Float64Array): number {
  let mn = Infinity, mx = -Infinity
  for (const v of vals) { if (v < mn) mn = v; if (v > mx) mx = v }
  if (mn === mx) return mn
  const nb = 256, largeur = (mx - mn) / nb
  const hist = new Float64Array(nb), centres = new Float64Array(nb)
  for (let i = 0; i < nb; i++) centres[i] = mn + (i + 0.5) * largeur
  for (const v of vals) hist[Math.min(nb - 1, Math.floor((v - mn) / largeur))]++
  const p1 = new Float64Array(nb), m1 = new Float64Array(nb), p2 = new Float64Array(nb), m2 = new Float64Array(nb)
  let a = 0, b = 0
  for (let i = 0; i < nb; i++) { a += hist[i]; b += hist[i] * centres[i]; p1[i] = a; m1[i] = b / a }
  a = 0; b = 0
  for (let i = nb - 1; i >= 0; i--) { a += hist[i]; b += hist[i] * centres[i]; p2[i] = a; m2[i] = b / a }
  let meilleur = 0, seuil = centres[0]
  for (let i = 0; i < nb - 1; i++) {
    const d = m1[i] - m2[i + 1]
    const v = p1[i] * p2[i + 1] * d * d
    if (v > meilleur) { meilleur = v; seuil = centres[i] }
  }
  return seuil
}

function lab(r: number, g: number, b: number): [number, number, number] {
  const lin = (c: number) => (c > 0.04045 ? ((c + 0.055) / 1.055) ** 2.4 : c / 12.92)
  const R = lin(r), G = lin(g), B = lin(b)
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
  const fx = f((0.412453 * R + 0.35758 * G + 0.180423 * B) / 0.95047)
  const fy = f(0.212671 * R + 0.71516 * G + 0.072169 * B)
  const fz = f((0.019334 * R + 0.119193 * G + 0.950227 * B) / 1.08883)
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)]
}

function fermetureBinaire(m: Masque, h: number, w: number): Masque {
  return eroder(dilater(m, h, w, CROIX), h, w, CROIX)
}

export interface MesureABCD {
  fiable: boolean; alertes: string[]; surface_relative: number
  A: { score: number; indice_forme: number[]; ecart_couleur: number[]; axes_asymetriques: boolean[] } | null
  B: { score: number; secteurs_abrupts: boolean[]; intensites: number[]; irregularite: number } | null
  C: { score: number; couleurs: string[]; fractions: Record<string, number> } | null
  D: { mm: number | null; superieur_6mm: boolean | null } | null
}
export interface Geometrie { centre: [number, number]; angle: number; majeur: number; mineur: number; masque: Masque; h: number; w: number }

function perimetre(m: Masque, h: number, w: number): number {
  const er = eroder(m, h, w, CROIX)
  const bord = new Uint8Array(m.length)
  for (let i = 0; i < m.length; i++) bord[i] = m[i] - er[i]
  const poids = new Float64Array(50)
  for (const i of [5, 7, 15, 17, 25, 27]) poids[i] = 1
  for (const i of [21, 33]) poids[i] = Math.SQRT2
  for (const i of [13, 23]) poids[i] = (1 + Math.SQRT2) / 2
  const noyau = [[10, 2, 10], [2, 1, 2], [10, 2, 10]]
  let total = 0
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let v = 0
      for (let i = -1; i <= 1; i++) {
        for (let j = -1; j <= 1; j++) {
          const r = y + i, c = x + j
          if (r >= 0 && r < h && c >= 0 && c < w) v += bord[r * w + c] * noyau[i + 1][j + 1]
        }
      }
      if (v < 50) total += poids[v]
    }
  }
  return total
}

/** Plus grand diamètre de Feret (enveloppe convexe des bords du masque, à mi-pixel). */
function feret(m: Masque, h: number, w: number): number {
  const pts: [number, number][] = []
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (!m[y * w + x]) continue
      const dehors = (r: number, c: number) => r < 0 || r >= h || c < 0 || c >= w || !m[r * w + c]
      if (dehors(y - 1, x)) pts.push([x, y - 0.5])
      if (dehors(y + 1, x)) pts.push([x, y + 0.5])
      if (dehors(y, x - 1)) pts.push([x - 0.5, y])
      if (dehors(y, x + 1)) pts.push([x + 0.5, y])
    }
  }
  pts.sort((a, b) => a[0] - b[0] || a[1] - b[1])
  const vec = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  const demi = (liste: [number, number][]) => {
    const e: [number, number][] = []
    for (const p of liste) {
      while (e.length >= 2 && vec(e[e.length - 2], e[e.length - 1], p) <= 0) e.pop()
      e.push(p)
    }
    e.pop()
    return e
  }
  const env = [...demi(pts), ...demi([...pts].reverse())]
  let d2 = 0
  for (let i = 0; i < env.length; i++) {
    for (let j = i + 1; j < env.length; j++) {
      const v = (env[i][0] - env[j][0]) ** 2 + (env[i][1] - env[j][1]) ** 2
      if (v > d2) d2 = v
    }
  }
  return Math.sqrt(d2)
}

function miroir(m: Masque, h: number, w: number, cy: number, cx: number, angle: number, axe: 'majeur' | 'mineur'): Masque {
  const out = new Uint8Array(m.length)
  const cos = Math.cos(angle), sin = Math.sin(angle)
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      if (!m[r * w + c]) continue
      const y = r - cy, x = c - cx
      let u = x * cos + y * sin, v = -x * sin + y * cos
      if (axe === 'majeur') v = -v; else u = -u
      const rr = arrondiPython(u * sin + v * cos + cy), cc = arrondiPython(u * cos - v * sin + cx)
      if (rr >= 0 && rr < h && cc >= 0 && cc < w) out[rr * w + cc] = 1
    }
  }
  return fermetureBinaire(out, h, w)
}

export function mesurer(image: ImageRGB, seuils: Seuils, champMm: number | null): { mesure: MesureABCD; geo: Geometrie | null } {
  const im = reduire({ ...image }, TAILLE)
  // réduction identique à _preparer : le côté long vaut toujours 320, y compris pour une petite image
  const e = TAILLE / Math.max(image.largeur, image.hauteur)
  const w = Math.max(1, arrondiPython(image.largeur * e)), h = Math.max(1, arrondiPython(image.hauteur * e))
  const px = e < 1 ? im.pixels : redimensionner(image.pixels, image.largeur, image.hauteur, w, h)
  const n = w * h
  const rgb = [new Float64Array(n), new Float64Array(n), new Float64Array(n)]
  const gris = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 3; k++) { const v = px[i * 3 + k] / 255; rgb[k][i] = v; gris[i] += v / 3 }
  }
  // champ valide : cadre noir relié au bord exclu
  const sombre = new Uint8Array(n)
  for (let i = 0; i < n; i++) sombre[i] = gris[i] < 0.12 ? 1 : 0
  const [labS] = etiqueter(sombre, h, w, false)
  const auBord = new Set<number>()
  for (let x = 0; x < w; x++) { auBord.add(labS[x]); auBord.add(labS[(h - 1) * w + x]) }
  for (let y = 0; y < h; y++) { auBord.add(labS[y * w]); auBord.add(labS[y * w + w - 1]) }
  auBord.delete(0)
  const cadre = new Uint8Array(n)
  for (let i = 0; i < n; i++) cadre[i] = auBord.has(labS[i]) ? 1 : 0
  const cadreD = dilater(cadre, h, w, CROIX, 3)
  const valide = new Uint8Array(n)
  for (let i = 0; i < n; i++) valide[i] = cadreD[i] ? 0 : 1
  // poils
  const pied = disque(4)
  const fermeGris = fermetureGris(gris, h, w, pied)
  const bh = new Uint8Array(n)
  for (let i = 0; i < n; i++) bh[i] = fermeGris[i] - gris[i] > 0.07 ? 1 : 0
  const poils = dilater(bh, h, w, CROIX)
  for (let k = 0; k < 3; k++) {
    const f = fermetureGris(rgb[k], h, w, pied)
    for (let i = 0; i < n; i++) if (poils[i]) rgb[k][i] = f[i]
  }
  // shades of gray
  let nbValide = 0
  const norme = [0, 0, 0]
  for (let i = 0; i < n; i++) {
    if (!valide[i]) continue
    nbValide++
    for (let k = 0; k < 3; k++) norme[k] += rgb[k][i] ** 6
  }
  const div = nbValide || 1
  for (let k = 0; k < 3; k++) norme[k] = (norme[k] / div) ** (1 / 6)
  const moyenne = (norme[0] + norme[1] + norme[2]) / 3
  const gain = norme.map((v) => moyenne / Math.max(v, 1e-6))
  const L0 = new Float64Array(n), A0 = new Float64Array(n), B0 = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    const [l, a, b] = lab(Math.min(1, rgb[0][i] * gain[0]), Math.min(1, rgb[1][i] * gain[1]), Math.min(1, rgb[2][i] * gain[2]))
    L0[i] = l; A0[i] = a; B0[i] = b
  }
  const vide = { mesure: { fiable: false, alertes: ['segmentation_impossible'], surface_relative: 0, A: null, B: null, C: null, D: null } as MesureABCD, geo: null }
  if (nbValide < 100) return vide
  const L2 = gaussien(L0, h, w, 2)
  const vals = new Float64Array(nbValide)
  for (let i = 0, j = 0; i < n; i++) if (valide[i]) vals[j++] = L2[i]
  const seuil = otsu(vals)
  let m = new Uint8Array(n)
  for (let i = 0; i < n; i++) m[i] = L2[i] < seuil && valide[i] ? 1 : 0
  m = morpho('ouverture', m, h, w, 3) as Uint8Array<ArrayBuffer>
  m = morpho('fermeture', m, h, w, 5) as Uint8Array<ArrayBuffer>
  m = remplirTrous(m, h, w) as Uint8Array<ArrayBuffer>
  const [etiq, nb] = etiqueter(m, h, w, true)
  const stats = Array.from({ length: nb + 1 }, () => ({ aire: 0, r: 0, c: 0 }))
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const l = etiq[y * w + x]
      if (l) { stats[l].aire++; stats[l].r += y; stats[l].c += x }
    }
  }
  let meilleure = 0, score = -1
  for (let l = 1; l <= nb; l++) {
    const s = stats[l]
    if (s.aire < 0.005 * nbValide) continue
    const d = Math.hypot(s.r / s.aire - h / 2, s.c / s.aire - w / 2)
    const v = s.aire / (1 + d / (0.15 * Math.max(h, w)))
    if (v > score) { score = v; meilleure = l }
  }
  if (!meilleure) return vide
  const masque = new Uint8Array(n)
  for (let i = 0; i < n; i++) masque[i] = etiq[i] === meilleure ? 1 : 0

  const aire = stats[meilleure].aire
  const part = aire / Math.max(nbValide, 1)
  const alertes: string[] = []
  let bordImage = false
  for (let x = 0; x < w; x++) bordImage ||= !!masque[x] || !!masque[(h - 1) * w + x]
  for (let y = 0; y < h; y++) bordImage ||= !!masque[y * w] || !!masque[y * w + w - 1]
  if (part > 0.85 || bordImage) alertes.push('lesion_coupee')
  if (part < 0.01) alertes.push('lesion_tres_petite')

  const cy = stats[meilleure].r / aire, cx = stats[meilleure].c / aire
  let mu20 = 0, mu02 = 0, mu11 = 0
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (!masque[y * w + x]) continue
      const dy = y - cy, dx = x - cx
      mu20 += dy * dy; mu02 += dx * dx; mu11 += dy * dx
    }
  }
  const a = mu02 / aire, b = -mu11 / aire, c = mu20 / aire
  const orientation = a - c === 0 ? (b < 0 ? Math.PI / 4 : -Math.PI / 4) : 0.5 * Math.atan2(-2 * b, c - a)
  const rac = Math.sqrt((a - c) ** 2 + 4 * b * b)
  const majeur = 4 * Math.sqrt(Math.max((a + c + rac) / 2, 0)), mineur = 4 * Math.sqrt(Math.max((a + c - rac) / 2, 0))
  const angle = Math.PI / 2 - orientation
  const cos = Math.cos(angle), sin = Math.sin(angle)

  // A
  const forme: number[] = [], couleur: number[] = [], asym: boolean[] = []
  for (const axe of ['majeur', 'mineur'] as const) {
    const mir = miroir(masque, h, w, cy, cx, angle, axe)
    let inter = 0
    const s1 = [0, 0, 0], s2 = [0, 0, 0]
    let n1 = 0, n2 = 0
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = y * w + x
        if (!masque[i]) continue
        if (mir[i]) inter++
        const dy = y - cy, dx = x - cx
        const u = dx * cos + dy * sin, v = -dx * sin + dy * cos
        const cote = axe === 'majeur' ? v > 0 : u > 0
        const t = cote ? s1 : s2
        t[0] += L0[i]; t[1] += A0[i]; t[2] += B0[i]
        if (cote) n1++; else n2++
      }
    }
    const indice = 1 - inter / aire
    const de = n1 && n2 ? Math.hypot(s1[0] / n1 - s2[0] / n2, s1[1] / n1 - s2[1] / n2, s1[2] / n1 - s2[2] / n2) : 0
    forme.push(arr(indice, 4)); couleur.push(arr(de, 2))
    asym.push(indice > seuils.forme || de > seuils.couleur)
  }
  // B
  const L = gaussien(L0, h, w, 1.5)
  const grad = new Float64Array(n)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x
      const gy = y === 0 ? L[i + w] - L[i] : y === h - 1 ? L[i] - L[i - w] : (L[i + w] - L[i - w]) / 2
      const gx = x === 0 ? L[i + 1] - L[i] : x === w - 1 ? L[i] - L[i - 1] : (L[i + 1] - L[i - 1]) / 2
      grad[i] = Math.hypot(gx, gy)
    }
  }
  const er = eroder(masque, h, w, CROIX)
  const di = dilater(masque, h, w, CROIX, 6)
  let sp = 0, np = 0, sm = 0
  for (let i = 0; i < n; i++) {
    if (masque[i]) sm += L[i]
    if (valide[i] && !di[i]) { sp += L[i]; np++ }
  }
  const contraste = Math.max(np ? sp / np - sm / aire : 1, 1)
  const somme = new Float64Array(NB_SECTEURS), compte = new Float64Array(NB_SECTEURS)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x
      if (!masque[i] || er[i]) continue
      const k = (Math.floor(((Math.atan2(y - cy, x - cx) + Math.PI) / (2 * Math.PI)) * NB_SECTEURS) % NB_SECTEURS + NB_SECTEURS) % NB_SECTEURS
      somme[k] += grad[i]; compte[k]++
    }
  }
  const intensites: number[] = [], abrupt: boolean[] = []
  for (let k = 0; k < NB_SECTEURS; k++) {
    const v = compte[k] ? ((somme[k] / compte[k]) * 6) / contraste : 0
    intensites.push(arr(v, 3)); abrupt.push(v > seuils.abrupt)
  }
  const per = perimetre(masque, h, w)
  // C
  const refs = [...COULEURS.map((c2) => [c2[1], c2[2], c2[3]]), PEAU]
  const comptes = new Float64Array(refs.length)
  let total = 0
  for (let i = 0; i < n; i++) {
    if (!masque[i] || poils[i]) continue
    total++
    let bk = 0, bd = Infinity
    for (let k = 0; k < refs.length; k++) {
      const d = (L0[i] - refs[k][0]) ** 2 + (A0[i] - refs[k][1]) ** 2 + (B0[i] - refs[k][2]) ** 2
      if (d < bd) { bd = d; bk = k }
    }
    comptes[bk]++
  }
  const fractions: Record<string, number> = {}
  const presentes: string[] = []
  COULEURS.forEach(([nom], k) => {
    const fr = total ? arr(comptes[k] / total, 4) : 0
    fractions[nom] = fr
    if (fr >= seuils.part_couleur) presentes.push(nom)
  })
  // D
  const dMm = champMm ? arr(feret(masque, h, w) * (champMm / w), 1) : null
  const somA = asym.filter(Boolean).length, somB = abrupt.filter(Boolean).length
  return {
    mesure: {
      fiable: !alertes.includes('lesion_coupee'), alertes, surface_relative: arr(part, 4),
      A: { score: somA, indice_forme: forme, ecart_couleur: couleur, axes_asymetriques: asym },
      B: { score: somB, secteurs_abrupts: abrupt, intensites, irregularite: arr((per * per) / (4 * Math.PI * aire), 3) },
      C: { score: Math.max(presentes.length, 1), couleurs: presentes, fractions },
      D: { mm: dMm, superieur_6mm: dMm === null ? null : dMm > 6 },
    },
    geo: { centre: [cy, cx], angle, majeur, mineur, masque, h, w },
  }
}

/** Image avec le contour de la lésion et ses deux axes principaux (superposition_png en Python). */
export async function superposition(im: ImageRGB, geo: Geometrie): Promise<Blob> {
  const toile = new OffscreenCanvas(im.largeur, im.hauteur)
  const ctx = toile.getContext('2d')!
  const d = ctx.createImageData(im.largeur, im.hauteur)
  const { masque, h, w } = geo
  const er2 = eroder(masque, h, w, CROIX, 2)
  const trace = new Uint8Array(im.largeur * im.hauteur)
  for (let y = 0; y < im.hauteur; y++) {
    const r = Math.min(h - 1, Math.floor(((y + 0.5) * h) / im.hauteur))
    for (let x = 0; x < im.largeur; x++) {
      const c = Math.min(w - 1, Math.floor(((x + 0.5) * w) / im.largeur))
      trace[y * im.largeur + x] = masque[r * w + c] && !er2[r * w + c] ? 1 : 0
    }
  }
  const epais = dilater(trace, im.hauteur, im.largeur, CROIX)
  for (let i = 0; i < trace.length; i++) {
    const b = epais[i]
    d.data[i * 4] = b ? 255 : im.pixels[i * 3]
    d.data[i * 4 + 1] = b ? 255 : im.pixels[i * 3 + 1]
    d.data[i * 4 + 2] = b ? 255 : im.pixels[i * 3 + 2]
    d.data[i * 4 + 3] = 255
  }
  ctx.putImageData(d, 0, 0)
  const fy = im.hauteur / h, fx = im.largeur / w
  const cy = geo.centre[0] * fy, cx = geo.centre[1] * fx
  ctx.strokeStyle = 'rgb(14,106,100)'
  ctx.lineWidth = 3
  for (const [longueur, ang] of [[geo.majeur, geo.angle], [geo.mineur, geo.angle + Math.PI / 2]]) {
    const dx = (Math.cos(ang) * longueur * fx) / 2, dy = (Math.sin(ang) * longueur * fy) / 2
    ctx.beginPath(); ctx.moveTo(cx - dx, cy - dy); ctx.lineTo(cx + dx, cy + dy); ctx.stroke()
  }
  return toile.convertToBlob({ type: 'image/jpeg', quality: 0.88 })
}
