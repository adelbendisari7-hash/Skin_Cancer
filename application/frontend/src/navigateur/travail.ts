// Fil de calcul de l'analyse dans le navigateur : même chaîne de décision que backend/dermia/engine/engine.py.
// L'image reste dans ce fil : aucune requête réseau ne la transporte.
import * as ort from 'onnxruntime-web/wasm'
import { mesurer, superposition } from './abcd'
import { decoder, recadrer, redimensionner, reduire, superposerCarte, versJpeg, zoneUtile, type Cadre, type ImageRGB, type RegleRecadrage } from './image'

interface Reseau { tronc: { fichier: string; sha256: string; octets: number }; tete: { fichier: string; sha256: string; octets: number } }
interface ProfilConfig { thresholds: Record<string, number>; conformal_q: number[]; reseaux: Reseau[] }
interface Config {
  nom: string; version: string; taille: number; moyenne: number[]; ecart_type: number[]; classes: string[]; mel: number
  recadrage?: RegleRecadrage
  classes_malignes: string[]; rapport_defaut: number
  encodeur: { age_mediane: number; age_moyenne: number; age_ecart_type: number; sexes: string[]; localisations: string[]
    correspondance?: Record<string, string> }
  profils: Record<string, ProfilConfig>
  hors_sujet: { seuil: number; profil: string; couches: { etage: number; dim: number }[]; n_classes: number; octets: number
    normalisation: { moyenne: number[]; ecart_type: number[] } }
  seuils_abcd: { forme: number; couleur: number; abrupt: number; part_couleur: number }
}
export interface Contexte { age: number | null; sexe: string | null; localisation: string | null }
type Sessions = { tronc: ort.InferenceSession; tete: ort.InferenceSession }[]

const BASE = '/demo/modele/'
const AGES_ET_SI = Array.from({ length: 16 }, (_, i) => 10 + 5 * i)
let config: Config | null = null
const sessions: Record<string, Sessions> = {}
let horsSujet: { mu: Float32Array; prec: Float32Array; dim: number }[] | null = null
let derniere: { cle: string; cartes: ort.Tensor[]; profil: string; ctx: Contexte } | null = null

function progres(id: number, etape: string, part: number) {
  postMessage({ id, type: 'progres', etape, part })
}

const envoyer = (id: number, donnees: unknown, transferts: Transferable[] = []) => postMessage({ id, type: 'fini', donnees }, { transfer: transferts })

async function telecharger(url: string, sha256: string | null, surOctets: (n: number) => void): Promise<Uint8Array> {
  const r = await fetch(url)
  if (!r.ok || !r.body) throw new Error(`Téléchargement impossible : ${url} (${r.status})`)
  const lecteur = r.body.getReader()
  const morceaux: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await lecteur.read()
    if (done) break
    morceaux.push(value); total += value.length; surOctets(value.length)
  }
  const out = new Uint8Array(total)
  let p = 0
  for (const m of morceaux) { out.set(m, p); p += m.length }
  if (sha256) {
    const h = await crypto.subtle.digest('SHA-256', out)
    const hex = [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('')
    if (hex !== sha256) throw new Error(`Empreinte invalide : ${url}`)
  }
  return out
}

async function chargerConfig(): Promise<Config> {
  if (!config) {
    const r = await fetch(`${BASE}config.json`)
    config = await r.json() as Config
    ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 1) : 1
    ort.env.logLevel = 'error'
  }
  return config
}

async function chargerProfil(id: number, profil: string, nb: number): Promise<void> {
  const c = await chargerConfig()
  sessions[profil] ??= []
  const manquants = c.profils[profil].reseaux.slice(sessions[profil].length, nb)
  if (!manquants.length) return
  const total = manquants.reduce((s, r) => s + r.tronc.octets + r.tete.octets, 0)
  let recu = 0
  const avancer = (n: number) => { recu += n; progres(id, 'telechargement', recu / total) }
  for (const r of manquants) {
    const opts: ort.InferenceSession.SessionOptions = { executionProviders: ['wasm'], graphOptimizationLevel: 'all' }
    const a = await telecharger(`${BASE}${r.tronc.fichier}?v=${r.tronc.sha256.slice(0, 10)}`, r.tronc.sha256, avancer)
    const b = await telecharger(`${BASE}${r.tete.fichier}?v=${r.tete.sha256.slice(0, 10)}`, r.tete.sha256, avancer)
    sessions[profil].push({ tronc: await ort.InferenceSession.create(a, opts), tete: await ort.InferenceSession.create(b, opts) })
  }
}

async function chargerHorsSujet(id: number): Promise<void> {
  const c = await chargerConfig()
  await chargerProfil(id, c.hors_sujet.profil, 1)
  if (horsSujet) return
  const b = await telecharger(`${BASE}hors_sujet.bin`, null, () => undefined)
  const f = new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4)
  const K = c.hors_sujet.n_classes
  let p = 0
  horsSujet = c.hors_sujet.couches.map(({ dim }) => {
    const mu = f.subarray(p, p + K * dim); p += K * dim
    const prec = f.subarray(p, p + dim * dim); p += dim * dim
    return { mu, prec, dim }
  })
}

/** Localisation détaillée de l'interface → zone vue par le réseau (paquet v3) ; « unknown » si non reconnue. */
function zone(c: Config, localisation: string | null): string {
  const z = localisation ? c.encodeur.correspondance?.[localisation] ?? localisation : 'unknown'
  return c.encodeur.localisations.includes(z) ? z : 'unknown'
}

function encoderContexte(c: Config, ctx: Contexte): Float32Array {
  const e = c.encodeur
  const manquant = ctx.age === null || ctx.age === undefined
  const age = ((manquant ? e.age_mediane : Number(ctx.age)) - e.age_moyenne) / e.age_ecart_type
  const sexe = ctx.sexe && e.sexes.includes(ctx.sexe) ? ctx.sexe : 'unknown'
  const loc = zone(c, ctx.localisation)
  return Float32Array.from([age, manquant ? 1 : 0, ...e.sexes.map((s) => (s === sexe ? 1 : 0)), ...e.localisations.map((l) => (l === loc ? 1 : 0))])
}

const estComplet = (ctx: Contexte) => ctx.age !== null && ctx.age !== undefined && !!ctx.sexe && ctx.sexe !== 'unknown'
  && !!ctx.localisation && ctx.localisation !== 'unknown'

const cadreAnalyse = (c: Config, im: ImageRGB): Cadre | null => (c.recadrage ? zoneUtile(im, c.recadrage) : null)

/** Lot des 4 retournements (identité, horizontal, vertical, les deux), normalisé ImageNet, après recadrage éventuel. */
function preparerLot(c: Config, im: ImageRGB, cadre: Cadre | null = cadreAnalyse(c, im)): ort.Tensor {
  const T = c.taille
  const vue = cadre ? recadrer(im, cadre) : im
  const px = redimensionner(vue.pixels, vue.largeur, vue.hauteur, T, T)
  const d = new Float32Array(4 * 3 * T * T)
  for (let v = 0; v < 4; v++) {
    const fh = v === 1 || v === 3, fv = v === 2 || v === 3
    for (let k = 0; k < 3; k++) {
      const m = c.moyenne[k], s = c.ecart_type[k]
      const o = (v * 3 + k) * T * T
      for (let y = 0; y < T; y++) {
        const yy = fv ? T - 1 - y : y
        for (let x = 0; x < T; x++) {
          const xx = fh ? T - 1 - x : x
          d[o + y * T + x] = (px[(yy * T + xx) * 3 + k] / 255 - m) / s
        }
      }
    }
  }
  return new ort.Tensor('float32', d, [4, 3, T, T])
}

function softmaxSomme(logits: Float32Array, n: number, K: number, somme: Float64Array) {
  for (let i = 0; i < n; i++) {
    let mx = -Infinity, s = 0
    for (let k = 0; k < K; k++) mx = Math.max(mx, logits[i * K + k])
    for (let k = 0; k < K; k++) s += Math.exp(logits[i * K + k] - mx)
    for (let k = 0; k < K; k++) somme[k] += Math.exp(logits[i * K + k] - mx) / s
  }
}

function scoreHorsSujet(c: Config, moyennes: Float32Array[]): number {
  const K = c.hors_sujet.n_classes
  const { moyenne, ecart_type } = c.hors_sujet.normalisation
  let z = -Infinity
  horsSujet!.forEach(({ mu, prec, dim }, e) => {
    const f = moyennes[e]
    let mn = Infinity
    const diff = new Float64Array(dim)
    for (let k = 0; k < K; k++) {
      for (let i = 0; i < dim; i++) diff[i] = f[i] - mu[k * dim + i]
      let d2 = 0
      for (let i = 0; i < dim; i++) {
        let s = 0
        for (let j = 0; j < dim; j++) s += prec[i * dim + j] * diff[j]
        d2 += s * diff[i]
      }
      if (d2 < mn) mn = d2
    }
    z = Math.max(z, (Math.log(mn) - moyenne[e]) / ecart_type[e])
  })
  return z
}

/** Grad-CAM : carte de classe positive, moyenne des réseaux, agrandie (bilinéaire) puis ramenée à [0, 1]. */
function carteFinale(cartes: Float64Array, H: number, T: number): Float32Array {
  const out = new Float32Array(T * T)
  const e = H / T
  for (let y = 0; y < T; y++) {
    const fy = Math.min(H - 1, Math.max(0, (y + 0.5) * e - 0.5)), y0 = Math.floor(fy), y1 = Math.min(H - 1, y0 + 1), ty = fy - y0
    for (let x = 0; x < T; x++) {
      const fx = Math.min(H - 1, Math.max(0, (x + 0.5) * e - 0.5)), x0 = Math.floor(fx), x1 = Math.min(H - 1, x0 + 1), tx = fx - x0
      out[y * T + x] = (cartes[y0 * H + x0] * (1 - tx) + cartes[y0 * H + x1] * tx) * (1 - ty)
        + (cartes[y1 * H + x0] * (1 - tx) + cartes[y1 * H + x1] * tx) * ty
    }
  }
  let mn = Infinity, mx = -Infinity
  for (const v of out) { if (v < mn) mn = v; if (v > mx) mx = v }
  const d = Math.max(mx - mn, 1e-8)
  for (let i = 0; i < out.length; i++) out[i] = (out[i] - mn) / d
  return out
}

async function analyser(id: number, fichier: Blob, ctx: Contexte, rapport: number | null, forcer: boolean, cle: string) {
  const c = await chargerConfig()
  const profil = estComplet(ctx) ? 'complet' : 'sans_contexte'
  const nb = c.profils[profil].reseaux.length
  await chargerProfil(id, profil, nb)
  await chargerHorsSujet(id)
  progres(id, 'calcul', 0)
  const t0 = performance.now()
  const im = await decoder(fichier)
  if (Math.min(im.largeur, im.hauteur) < 64) throw Object.assign(new Error('trop_petite'), { code: 'trop_petite' })
  const cadre = cadreAnalyse(c, im)
  const lot = preparerLot(c, im, cadre)
  const K = c.classes.length
  const z = encoderContexte(c, ctx)
  const contexte = new ort.Tensor('float32', new Float32Array(z.length * 4).map((_, i) => z[i % z.length]), [4, z.length])
  const somme = new Float64Array(K)
  const memo: ort.Tensor[] = []
  const brutes: Float32Array[] = []
  let H = 0, moyennes: Float32Array[] = []
  for (let r = 0; r < nb; r++) {
    const s = sessions[profil][r]
    const estDetecteur = profil === c.hors_sujet.profil && r === 0
    const noms = estDetecteur ? ['carte', ...c.hors_sujet.couches.map((_, e) => `e${e}`)] : ['carte']
    const sortie = await s.tronc.run({ image: lot }, noms)
    if (estDetecteur) moyennes = c.hors_sujet.couches.map(({ dim }, e) => (sortie[`e${e}`].data as Float32Array).slice(0, dim))
    memo.push(sortie.carte)
    const t = await s.tete.run({ carte: sortie.carte, contexte })
    softmaxSomme(t.logits.data as Float32Array, 4, K, somme)
    H = t.cartes.dims[3]
    brutes.push((t.cartes.data as Float32Array).slice(0, K * H * H))    // vue d'origine seulement
    progres(id, 'calcul', (r + 1) / (nb + 1))
  }
  if (!moyennes.length) {
    const T = c.taille
    const seule = new ort.Tensor('float32', (lot.data as Float32Array).slice(0, 3 * T * T), [1, 3, T, T])
    const sortie = await sessions[c.hors_sujet.profil][0].tronc.run({ image: seule }, c.hors_sujet.couches.map((_, e) => `e${e}`))
    moyennes = c.hors_sujet.couches.map((_, e) => sortie[`e${e}`].data as Float32Array)
  }
  const score = scoreHorsSujet(c, moyennes)
  const hors = score > c.hors_sujet.seuil
  if (hors && !forcer) {
    return { refus: true, score: Math.round(score * 100) / 100, seuil: Math.round(c.hors_sujet.seuil * 100) / 100 }
  }

  // Décision au coût, ensemble conforme Mondrian, abstention, orientation
  const n = 4 * nb
  const p = Array.from(somme, (v) => v / n)
  const R = rapport ?? c.rapport_defaut
  const pc = c.profils[profil]
  const seuil = pc.thresholds[String(R)]
  let k = c.mel
  if (p[c.mel] < seuil) {
    k = 0
    let mx = -1
    p.forEach((v, i) => { if (i !== c.mel && v > mx) { mx = v; k = i } })
  }
  const ens = c.classes.filter((_, i) => 1 - p[i] <= pc.conformal_q[i])
  const decision = c.classes[k]
  const traite = ens.length === 1 && ens[0] === decision
  const [statut, niveau] = decision === 'mel' ? ['alerte_melanome', 'urgent'] : !traite ? ['incertain', 'renvoi']
    : c.classes_malignes.includes(decision) ? ['maligne_probable', 'eleve'] : ['benigne_probable', 'faible']
  const avertissements: Record<string, unknown>[] = []
  if (profil === 'sans_contexte') avertissements.push({ code: 'contexte_incomplet' })
  if (Math.min(im.largeur, im.hauteur) < 150) avertissements.push({ code: 'faible_resolution', largeur: im.largeur, hauteur: im.hauteur })
  if (hors) avertissements.push({ code: 'image_atypique' })

  // Images : version réduite, Grad-CAM de la classe retenue, ABCD
  const carte = new Float64Array(H * H)
  for (const b of brutes) for (let i = 0; i < H * H; i++) carte[i] += Math.max(b[k * H * H + i], 0) / brutes.length
  const T = c.taille
  const cam = carteFinale(carte, H, T)
  const base = reduire(im, 640)
  const ex = base.largeur / im.largeur, ey = base.hauteur / im.hauteur
  const cadreBase: Cadre | null = cadre && [Math.round(cadre[0] * ex), Math.round(cadre[1] * ey), Math.round(cadre[2] * ex), Math.round(cadre[3] * ey)]
  const { mesure, geo } = mesurer(im, c.seuils_abcd, null)
  const [image, gradcam, abcd] = await Promise.all([versJpeg(base), versJpeg(superposerCarte(base, cam, T, 0.45, cadreBase)),
    geo ? superposition(base, geo) : versJpeg(base)])
  derniere = { cle, cartes: memo, profil, ctx }
  return {
    refus: false, profil, probabilites: Object.fromEntries(c.classes.map((x, i) => [x, p[i]])), decision, p_melanome: p[c.mel],
    seuil_melanome: seuil, rapport_cout: R, ensemble_conforme: ens, traite, statut, niveau, avertissements,
    modele: c.nom, version: c.version, duree_ms: Math.round(performance.now() - t0), abcd: mesure,
    score_hors_sujet: Math.round(score * 100) / 100, hors_sujet: hors, images: { image, gradcam, abcd },
  }
}

/** « Et si » : même image, contexte modifié. Seule la tête est recalculée quand l'analyse est encore en mémoire. */
async function etSi(id: number, fichier: Blob, ctx: Contexte, variable: 'age' | 'localisation', cle: string) {
  const c = await chargerConfig()
  const profil = estComplet(ctx) ? 'complet' : 'sans_contexte'
  await chargerProfil(id, profil, c.profils[profil].reseaux.length)
  if (derniere?.cle !== cle || derniere.profil !== profil) {
    const lot = preparerLot(c, await decoder(fichier))
    const cartes: ort.Tensor[] = []
    for (const s of sessions[profil]) cartes.push((await s.tronc.run({ image: lot }, ['carte'])).carte)
    derniere = { cle, cartes, profil, ctx }
  }
  const valeurs: (number | string)[] = variable === 'age' ? AGES_ET_SI : c.encodeur.localisations.filter((l) => l !== 'unknown')
  const K = c.classes.length
  const serie = []
  for (const v of valeurs) {
    const z = encoderContexte(c, { ...ctx, [variable]: v })
    const contexte = new ort.Tensor('float32', new Float32Array(z.length * 4).map((_, i) => z[i % z.length]), [4, z.length])
    const somme = new Float64Array(K)
    for (let r = 0; r < sessions[profil].length; r++) {
      const t = await sessions[profil][r].tete.run({ carte: derniere.cartes[r], contexte }, ['logits'])
      softmaxSomme(t.logits.data as Float32Array, 4, K, somme)
    }
    serie.push({ valeur: v, p_melanome: somme[c.mel] / (4 * sessions[profil].length) })
  }
  return { variable, actuel: variable === 'age' ? ctx.age : zone(c, ctx.localisation), serie, seuil_melanome: c.profils[profil].thresholds[String(c.rapport_defaut)] }
}

// Les fils internes d'ONNX Runtime rechargent ce même fichier : ils gardent leur propre gestionnaire de messages.
if (!self.name.startsWith('em-pthread')) self.onmessage = async (e: MessageEvent) => {
  const { id, type } = e.data
  try {
    if (type === 'analyser') {
      const r = await analyser(id, e.data.fichier, e.data.contexte, e.data.rapport, e.data.forcer, e.data.cle)
      envoyer(id, r)
    } else if (type === 'etsi') {
      envoyer(id, await etSi(id, e.data.fichier, e.data.contexte, e.data.variable, e.data.cle))
    } else if (type === 'abcd') {
      const c = await chargerConfig()
      envoyer(id, mesurer(await decoder(e.data.fichier), c.seuils_abcd, e.data.champ).mesure)
    }
  } catch (err) {
    postMessage({ id, type: 'erreur', message: err instanceof Error ? err.message : String(err), code: (err as { code?: string }).code })
  }
}
