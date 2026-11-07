import { CircleCheck, CircleQuestionMark, Stethoscope, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Avertissement, Evolution, MesureABCD, Niveau } from '../api'
import { estCle, t } from '../i18n'
import { date, NIVEAUX, nomClasse, nomCouleur, nomNiveau, nombre, pourcent, texteSignal } from '../lib/format'

const ICONES = { urgent: TriangleAlert, eleve: Stethoscope, renvoi: CircleQuestionMark, faible: CircleCheck }

/** Statut de triage : icône + libellé + couleur réservée (jamais la couleur seule). */
export function Statut({ niveau, taille = 'normale' }: { niveau: Niveau; taille?: 'normale' | 'petite' }) {
  const n = NIVEAUX[niveau]
  const Icone = ICONES[niveau]
  const petite = taille === 'petite'
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-[4px] font-semibold ${n.fond} ${n.texte}
      ${petite ? 'px-1.5 py-0.5 text-[12px]' : 'px-2 py-1 text-[13px]'}`}>
      <Icone className={petite ? 'size-3.5' : 'size-4'} aria-hidden /> {nomNiveau(niveau)}
    </span>
  )
}

type Vue = 'image' | 'carte' | 'abcd'

/**
 * L'oculaire : la lésion vue comme dans le dermoscope (champ circulaire, anneau gradué).
 * Bascule entre l'image, les zones qui ont le plus pesé (Grad-CAM) et le contour utilisé pour l'ABCD.
 */
export function Oculaire({ image, carte, abcd, taille = 360, legendeCarte, legendeAbcd, animer = false }:
  { image: string; carte?: string; abcd?: string; taille?: number; legendeCarte?: string; legendeAbcd?: string; animer?: boolean }) {
  const [vue, setVue] = useState<Vue>('image')
  const graduations = Array.from({ length: 72 }, (_, i) => i * 5)
  const r = 50
  const vues: Vue[] = ['image', ...(carte ? ['carte' as const] : []), ...(abcd ? ['abcd' as const] : [])]
  const src = vue === 'carte' && carte ? carte : vue === 'abcd' && abcd ? abcd : image
  const alt = { image: t('oculaire.altImage'), carte: t('oculaire.altCarte'), abcd: t('oculaire.altAbcd') }[vue]
  const legende = vue === 'carte' ? legendeCarte : vue === 'abcd' ? legendeAbcd : undefined
  return (
    <figure className="flex w-full min-w-0 flex-col items-center gap-3">
      <div className="relative" style={{ width: `min(${taille}px, 100%)`, aspectRatio: '1' }}>
        <svg viewBox="-56 -56 112 112" className="absolute inset-0 size-full" aria-hidden>
          <circle r={r + 4.5} fill="var(--color-derme)" />
          {graduations.map((a) => {
            const long = a % 30 === 0
            const rad = (a * Math.PI) / 180
            const r1 = r + 0.8, r2 = r + (long ? 4 : 2.2)
            return <line key={a} x1={r1 * Math.cos(rad)} y1={r1 * Math.sin(rad)} x2={r2 * Math.cos(rad)} y2={r2 * Math.sin(rad)}
              stroke="var(--color-encre)" strokeOpacity={long ? 0.55 : 0.28} strokeWidth={long ? 0.55 : 0.35} />
          })}
        </svg>
        <div className="absolute overflow-hidden rounded-full bg-encre" style={{ inset: `${(6 / 112) * 100}%` }}>
          <img src={src} alt={alt} className={`size-full object-cover ${animer ? 'mise-au-point' : ''}`} draggable={false} />
        </div>
      </div>
      {vues.length > 1 && (
        <div role="group" aria-label={t('oculaire.affichage')} className="inline-flex flex-wrap justify-center rounded-[5px] border border-trait bg-surface p-0.5 text-[13px]">
          {vues.map((v) => (
            <button key={v} onClick={() => setVue(v)} aria-pressed={vue === v}
              className={`rounded-[4px] px-3 py-1.5 font-semibold ${vue === v ? 'bg-bloc text-white' : 'text-encre-2 hover:text-encre'}`}>
              {{ image: t('oculaire.image'), carte: t('oculaire.carte'), abcd: t('oculaire.abcd') }[v]}
            </button>
          ))}
        </div>
      )}
      {legende && <figcaption className="max-w-[340px] text-center text-[13px] text-encre-2">{legende}</figcaption>}
    </figure>
  )
}

/**
 * Probabilités par diagnostic, triées. Une seule série : barres neutres, la décision en accent.
 * L'appartenance à l'ensemble garanti est écrite (pas seulement colorée) ; le seuil mélanome est marqué.
 */
export function Probabilites({ probabilites, decision, ensemble, seuilMel }:
  { probabilites: Record<string, number>; decision: string; ensemble: string[]; seuilMel: number }) {
  const lignes = Object.entries(probabilites).sort((a, b) => b[1] - a[1])
  return (
    <div className="flex flex-col gap-2.5" role="list">
      {lignes.map(([c, p]) => {
        const estDecision = c === decision
        const dansEnsemble = ensemble.includes(c)
        return (
          <div key={c} role="listitem" className="grid grid-cols-[1fr_4.2rem] items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,11.5rem)_1fr_4.2rem]">
            <div className="col-span-2 min-w-0 text-[14px] leading-tight sm:col-span-1">
              <span className={estDecision ? 'font-semibold' : ''}>{nomClasse(c)}</span>
              {dansEnsemble && <span className="block text-[12px] text-bloc">{t('probas.dansEnsemble')}</span>}
            </div>
            <div className="relative h-[10px] rounded-[3px] bg-trait-2">
              <div className={`h-full rounded-[3px] ${estDecision ? 'bg-bloc' : 'bg-encre-3/55'}`}
                style={{ width: `${Math.max(p * 100, p > 0 ? 0.6 : 0)}%` }} />
              {c === 'mel' && (
                <div className="absolute -top-1.5 h-[22px] w-[2px] bg-urgent" style={{ insetInlineStart: `calc(${seuilMel * 100}% - 1px)` }}
                  title={t('probas.seuilTitre', { seuil: nombre(seuilMel) })} />
              )}
            </div>
            <div className="chiffres text-end text-[14px] font-semibold">{pourcent(p)}</div>
          </div>
        )
      })}
      <p className="mt-1 flex items-center gap-2 text-[12px] text-encre-2">
        <span className="inline-block h-3 w-[2px] shrink-0 bg-urgent" aria-hidden />
        {t('probas.seuilLegende', { seuil: pourcent(seuilMel, 0) })}
      </p>
    </div>
  )
}

/** Avertissements codés de l'analyse, dans la langue active (« evolution » est détaillé ailleurs). */
export function Avertissements({ liste: avs }: { liste: Avertissement[] }) {
  const textes = avs.flatMap((av) => {
    if (av.code === 'texte') return av.texte ? [av.texte] : []
    if (av.code === 'evolution') return [t('av.evolution', { date: date(av.depuis) })]
    const k = `av.${av.code}`
    return estCle(k) ? [t(k, { largeur: av.largeur ?? '', hauteur: av.hauteur ?? '' })] : []
  })
  return <>{textes.map((x) => <p key={x} className="mt-2 text-[13px] text-avis">{x}</p>)}</>
}

function Pastilles({ couleurs }: { couleurs: string[] }) {
  const teinte: Record<string, string> = { blanc: '#f4f1ec', rouge: '#b9473f', brun_clair: '#a8714f', brun_fonce: '#5a3423',
    bleu_gris: '#6d7c8c', noir: '#1d1715' }
  if (couleurs.length === 0) return <span className="text-encre-2">{t('abcd.aucuneCouleur')}</span>
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
      {couleurs.map((c) => (
        <span key={c} className="inline-flex items-center gap-1.5">
          <span className="inline-block size-3 rounded-full ring-1 ring-encre/25" style={{ background: teinte[c] ?? '#999' }} aria-hidden />
          {nomCouleur(c)}
        </span>
      ))}
    </span>
  )
}

/** Critères ABCD automatiques, présentés comme indicateurs (pouvoir discriminant modeste, mesuré). */
export function CriteresABCD({ m }: { m: MesureABCD }) {
  if (!m.A || !m.B || !m.C) {
    return <p className="text-[14px] text-encre-2">{t('abcd.segmentation_impossible')}</p>
  }
  const d = m.D
  const lignes: [string, string, React.ReactNode, number | null][] = [
    ['A', t('abcd.A'), t('abcd.Ad'), m.A.score / 2],
    ['B', t('abcd.B'), t('abcd.Bd'), m.B.score / 8],
    ['C', t('abcd.C'), <Pastilles key="C" couleurs={m.C.couleurs} />, m.C.score / 6],
    ['D', t('abcd.D'), d?.mm == null ? t('abcd.Dinconnu') : d.superieur_6mm ? t('abcd.Dplus') : t('abcd.Dmoins'), null],
  ]
  const valeur = (k: string) => k === 'A' ? `${m.A!.score}/2` : k === 'B' ? `${m.B!.score}/8` : k === 'C' ? `${m.C!.score}/6`
    : d?.mm == null ? '—' : t('commun.mm', { n: nombre(d.mm, 1) })
  return (
    <div>
      <dl className="flex flex-col gap-3">
        {lignes.map(([k, nom, detail, part]) => (
          <div key={k} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-start gap-x-3">
            <dt className="grid size-8 place-items-center rounded-full bg-bloc-pale text-[15px] font-semibold text-bloc-fonce" aria-hidden>{k}</dt>
            <div className="min-w-0">
              <p className="text-[14px] font-semibold">{nom}</p>
              <dd className="text-[13px] text-encre-2">{detail}</dd>
              {part !== null && (
                <div className="mt-1.5 h-[6px] max-w-[220px] rounded-[3px] bg-trait-2" aria-hidden>
                  <div className="h-full rounded-[3px] bg-encre-3/70" style={{ width: `${Math.max(part * 100, 2)}%` }} />
                </div>
              )}
            </div>
            <span className="chiffres pt-0.5 text-[15px] font-semibold" dir="ltr">{valeur(k)}</span>
          </div>
        ))}
      </dl>
      {m.alertes.map((a) => {
        const k = `abcd.${a}`
        return estCle(k) ? <p key={a} className="mt-3 text-[13px] text-avis">{t(k)}</p> : null
      })}
      <p className="mt-3 text-[12px] text-encre-2">{t('abcd.note')}</p>
    </div>
  )
}

export function SignauxEvolution({ evo }: { evo: Evolution }) {
  return evo.signaux.length === 0 ? <p className="text-[14px]">{t('evo.aucun')}</p> : (
    <ul className="flex flex-col gap-1.5 text-[14px]">
      {evo.signaux.map((s) => (
        <li key={s.code} className="flex gap-2"><TriangleAlert className="mt-0.5 size-4 shrink-0 text-avis" aria-hidden />{texteSignal(s)}</li>
      ))}
    </ul>
  )
}

/** Évolution d'une lésion depuis l'analyse précédente (critère E de l'ABCDE). */
export function PanneauEvolution({ evo, lesionId, analyseId }: { evo: Evolution; lesionId: number; analyseId: number }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[14px] text-encre-2">
        {t('evo.depuis', { date: date(evo.depuis), jours: t('commun.jours', { n: evo.jours ?? '?' }) })}
      </p>
      <SignauxEvolution evo={evo} />
      <p className="text-[12px] text-encre-2">{t('evo.note')}</p>
      <Link to={`/lesions/${lesionId}?a=${evo.analyse_precedente}&b=${analyseId}`} className="self-start font-semibold text-bloc hover:underline">
        {t('evo.comparer')}
      </Link>
    </div>
  )
}
