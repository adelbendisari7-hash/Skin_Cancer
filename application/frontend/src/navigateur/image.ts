// Traitement d'image pour l'analyse dans le navigateur : reproduit Pillow (Image.resize LANCZOS / BILINEAR, 8 bits,
// virgule fixe, passe horizontale puis verticale) pour que le réseau reçoive les mêmes pixels que le moteur Python.

export interface ImageRGB { largeur: number; hauteur: number; pixels: Uint8Array }  // RGB entrelacé

/** Décode un fichier image (orientation EXIF appliquée, couleurs sans conversion, alpha ignoré). */
export async function decoder(fichier: Blob): Promise<ImageRGB> {
  const bmp = await createImageBitmap(fichier, { imageOrientation: 'from-image', colorSpaceConversion: 'none', premultiplyAlpha: 'none' })
    .catch(() => { throw Object.assign(new Error('illisible'), { code: 'illisible' }) })
  const toile = new OffscreenCanvas(bmp.width, bmp.height)
  const ctx = toile.getContext('2d', { willReadFrequently: true })!
  ctx.drawImage(bmp, 0, 0)
  const { data } = ctx.getImageData(0, 0, bmp.width, bmp.height)
  const pixels = new Uint8Array(bmp.width * bmp.height * 3)
  for (let i = 0, j = 0; i < data.length; i += 4, j += 3) {
    pixels[j] = data[i]; pixels[j + 1] = data[i + 1]; pixels[j + 2] = data[i + 2]
  }
  const r = { largeur: bmp.width, hauteur: bmp.height, pixels }
  bmp.close()
  return r
}

const sinc = (x: number) => (x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x))
const FILTRES = {
  lanczos: { support: 3, f: (x: number) => (x > -3 && x < 3 ? sinc(x) * sinc(x / 3) : 0) },
  bilineaire: { support: 1, f: (x: number) => { const a = Math.abs(x); return a < 1 ? 1 - a : 0 } },
  bicubique: { support: 2, f: (x: number) => {
    const a = Math.abs(x)
    return a < 1 ? (1.5 * a - 2.5) * a * a + 1 : a < 2 ? (((a - 5) * a + 8) * a - 4) * -0.5 : 0
  } },
}
const PRECISION = 22                                // bits de la virgule fixe de Pillow (32 - 8 - 2)
const UN = 2 ** PRECISION
const trunc = Math.trunc

function coefficients(entree: number, sortie: number, nom: keyof typeof FILTRES) {
  const { support: base, f } = FILTRES[nom]
  const echelle = entree / sortie
  const fe = Math.max(echelle, 1)
  const support = base * fe
  const taille = Math.ceil(support) * 2 + 1
  const debuts = new Int32Array(sortie), longueurs = new Int32Array(sortie)
  const k = new Int32Array(sortie * taille)
  const tmp = new Float64Array(taille)
  for (let xx = 0; xx < sortie; xx++) {
    const centre = (xx + 0.5) * echelle
    let xmin = trunc(centre - support + 0.5)
    if (xmin < 0) xmin = 0
    let xmax = trunc(centre + support + 0.5)
    if (xmax > entree) xmax = entree
    xmax -= xmin
    let somme = 0
    for (let x = 0; x < xmax; x++) { const w = f((x + xmin - centre + 0.5) / fe); tmp[x] = w; somme += w }
    for (let x = 0; x < xmax; x++) {
      const w = (tmp[x] / somme) * UN
      k[xx * taille + x] = w < 0 ? trunc(-0.5 + w) : trunc(0.5 + w)
    }
    debuts[xx] = xmin; longueurs[xx] = xmax
  }
  return { debuts, longueurs, k, taille }
}

const coupe = (v: number) => { const x = Math.floor(v / UN); return x < 0 ? 0 : x > 255 ? 255 : x }

/** Redimensionne `canaux` plans entrelacés de 8 bits, à l'identique de Pillow. */
export function redimensionner(src: Uint8Array, l: number, h: number, L: number, H: number, canaux = 3, filtre: keyof typeof FILTRES = 'lanczos'): Uint8Array {
  let lignes = src
  if (L !== l) {
    const c = coefficients(l, L, filtre)
    const out = new Uint8Array(L * h * canaux)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < L; x++) {
        const d = c.debuts[x], n = c.longueurs[x], o = x * c.taille
        for (let k = 0; k < canaux; k++) {
          let s = UN / 2
          for (let i = 0; i < n; i++) s += src[(y * l + d + i) * canaux + k] * c.k[o + i]
          out[(y * L + x) * canaux + k] = coupe(s)
        }
      }
    }
    lignes = out
  }
  if (H === h) return lignes === src ? src.slice() : lignes
  const c = coefficients(h, H, filtre)
  const out = new Uint8Array(L * H * canaux)
  for (let y = 0; y < H; y++) {
    const d = c.debuts[y], n = c.longueurs[y], o = y * c.taille
    for (let x = 0; x < L * canaux; x++) {
      let s = UN / 2
      for (let i = 0; i < n; i++) s += lignes[(d + i) * L * canaux + x] * c.k[o + i]
      out[y * L * canaux + x] = coupe(s)
    }
  }
  return out
}

export interface RegleRecadrage { cote_analyse: number; coin: number; seuil_coins: number; seuil_clair: number; part_claire_min: number; marge: number }
export type Cadre = [number, number, number, number]                  // x0, y0, x1, y1 (comme Pillow)

/** Champ du dermoscope : carré inscrit dans la zone claire quand les coins sont noirs, sinon null.
 *  Reproduit zone_utile() du moteur Python (gris de Pillow, réduction bicubique). */
export function zoneUtile(im: ImageRGB, r: RegleRecadrage): Cadre | null {
  const { largeur: W, hauteur: H, pixels } = im
  const gris = new Uint8Array(W * H)
  for (let i = 0; i < W * H; i++) {
    gris[i] = (pixels[3 * i] * 19595 + pixels[3 * i + 1] * 38470 + pixels[3 * i + 2] * 7471 + 0x8000) >>> 16
  }
  const n = r.cote_analyse, s = r.coin
  const g = redimensionner(gris, W, H, n, n, 1, 'bicubique')
  const moyenne = (y0: number, x0: number) => {
    let t = 0
    for (let y = y0; y < y0 + s; y++) for (let x = x0; x < x0 + s; x++) t += g[y * n + x]
    return t / (s * s)
  }
  const coins = (moyenne(0, 0) + moyenne(0, n - s) + moyenne(n - s, 0) + moyenne(n - s, n - s)) / 4
  if (coins >= r.seuil_coins) return null
  let nb = 0, sy = 0, sx = 0
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (g[y * n + x] > r.seuil_clair) { nb++; sy += y; sx += x }
  const part = nb / (n * n)
  if (part < r.part_claire_min) return null
  const cy = sy / nb / n, cx = sx / nb / n
  const c = Math.sqrt(part / Math.PI) * Math.SQRT2 * r.marge
  return [Math.trunc(Math.max(0, cx - c / 2) * W), Math.trunc(Math.max(0, cy - c / 2) * H),
    Math.trunc(Math.min(1, cx + c / 2) * W), Math.trunc(Math.min(1, cy + c / 2) * H)]
}

export function recadrer(im: ImageRGB, [x0, y0, x1, y1]: Cadre): ImageRGB {
  const largeur = x1 - x0, hauteur = y1 - y0
  const pixels = new Uint8Array(largeur * hauteur * 3)
  for (let y = 0; y < hauteur; y++) {
    pixels.set(im.pixels.subarray(((y0 + y) * im.largeur + x0) * 3, ((y0 + y) * im.largeur + x1) * 3), y * largeur * 3)
  }
  return { largeur, hauteur, pixels }
}

export function reduire(im: ImageRGB, coteMax: number): ImageRGB {
  const e = Math.min(1, coteMax / Math.max(im.largeur, im.hauteur))
  const largeur = Math.max(1, arrondiPython(im.largeur * e)), hauteur = Math.max(1, arrondiPython(im.hauteur * e))
  return { largeur, hauteur, pixels: redimensionner(im.pixels, im.largeur, im.hauteur, largeur, hauteur) }
}

/** round() de Python : arrondi au pair pour les demis. */
export function arrondiPython(x: number): number {
  const b = Math.floor(x), d = x - b
  if (d > 0.5) return b + 1
  if (d < 0.5) return b
  return b % 2 === 0 ? b : b + 1
}

export async function versJpeg(im: ImageRGB, qualite = 0.88): Promise<Blob> {
  const toile = new OffscreenCanvas(im.largeur, im.hauteur)
  const ctx = toile.getContext('2d')!
  const d = ctx.createImageData(im.largeur, im.hauteur)
  for (let i = 0, j = 0; j < im.pixels.length; i += 4, j += 3) {
    d.data[i] = im.pixels[j]; d.data[i + 1] = im.pixels[j + 1]; d.data[i + 2] = im.pixels[j + 2]; d.data[i + 3] = 255
  }
  ctx.putImageData(d, 0, 0)
  return toile.convertToBlob({ type: 'image/jpeg', quality: qualite })
}

// Palette séquentielle de la carte Grad-CAM (identique au moteur Python)
const PALETTE = [[0, 0, 4], [87, 16, 110], [188, 55, 84], [249, 142, 9], [252, 255, 164]]

/** Superpose la carte (288×288, valeurs dans [0, 1]) à l'image, aux proportions de celle-ci.
 *  `cadre` (coordonnées de `base`) : partie analysée quand l'image a été recadrée ; la carte est nulle ailleurs. */
export function superposerCarte(base: ImageRGB, carte: Float32Array, cote: number, opacite = 0.45, cadre: Cadre | null = null): ImageRGB {
  const octets = new Uint8Array(carte.length)
  for (let i = 0; i < carte.length; i++) octets[i] = Math.trunc(carte[i] * 255)
  const [x0, y0, x1, y1] = cadre ?? [0, 0, base.largeur, base.hauteur]
  const l = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0)
  const partielle = redimensionner(octets, cote, cote, l, h, 1, 'bilineaire')
  const c = new Uint8Array(base.largeur * base.hauteur)
  for (let y = 0; y < Math.min(h, base.hauteur - y0); y++) {
    c.set(partielle.subarray(y * l, y * l + Math.min(l, base.largeur - x0)), (y0 + y) * base.largeur + x0)
  }
  const pixels = new Uint8Array(base.pixels.length)
  for (let i = 0; i < c.length; i++) {
    const x = (c[i] / 255) * (PALETTE.length - 1)
    const b = Math.min(Math.trunc(x), PALETTE.length - 2), t = x - b
    for (let k = 0; k < 3; k++) {
      const v = Math.trunc(PALETTE[b][k] * (1 - t) + PALETTE[b + 1][k] * t)
      pixels[i * 3 + k] = Math.trunc((1 - opacite) * base.pixels[i * 3 + k] + opacite * v)
    }
  }
  return { largeur: base.largeur, hauteur: base.hauteur, pixels }
}
