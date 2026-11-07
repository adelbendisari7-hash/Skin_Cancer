import { History, Pencil } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type Analyse, type LesionDetail as Detail } from '../api'
import { Oculaire, SignauxEvolution, Statut } from '../components/metier'
import { Bouton, Champ, Chargement, Dialogue, EnTete, Message, Panneau, Saisie } from '../components/ui'
import { DEMO } from '../demoStatique'
import { t } from '../i18n'
import { date, dateHeure, liste, nombre, nomCouleur, nomLoc, pourcent } from '../lib/format'

/** p(mélanome) au fil des examens, avec le seuil d'alerte (axe du temps de gauche à droite dans toutes les langues). */
function Courbe({ analyses }: { analyses: Analyse[] }) {
  const W = 560, H = 190, M = { g: 44, d: 20, h: 14, b: 30 }
  const temps = analyses.map((a) => new Date(a.cree_le).getTime())
  const t0 = Math.min(...temps), t1 = Math.max(...temps)
  const sx = (x: number) => M.g + (t1 === t0 ? 0.5 : (x - t0) / (t1 - t0)) * (W - M.g - M.d)
  const sy = (y: number) => M.h + (1 - y) * (H - M.h - M.b)
  const seuil = analyses.at(-1)!.seuil_melanome
  const chemin = analyses.map((a, i) => `${i ? 'L' : 'M'}${sx(temps[i]).toFixed(1)},${sy(a.p_melanome).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[680px]" role="img" aria-label={t('les.courbe')} style={{ direction: 'ltr' }}>
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line x1={M.g} x2={W - M.d} y1={sy(v)} y2={sy(v)} stroke="var(--color-trait-2)" />
          <text x={M.g - 8} y={sy(v) + 4} textAnchor="end" fontSize="11" fill="var(--color-encre-3)">{pourcent(v, 0)}</text>
        </g>
      ))}
      <line x1={M.g} x2={W - M.d} y1={sy(seuil)} y2={sy(seuil)} stroke="var(--color-urgent)" strokeWidth="1.5" strokeDasharray="5 4" />
      <text x={W - M.d} y={sy(seuil) - 6} textAnchor="end" fontSize="11.5" fill="var(--color-urgent)">{t('etsi.seuil')}</text>
      <path d={chemin} fill="none" stroke="var(--color-bloc)" strokeWidth="2.25" strokeLinejoin="round" />
      {analyses.map((a, i) => (
        <g key={a.id}>
          <circle cx={sx(temps[i])} cy={sy(a.p_melanome)} r="5" fill="var(--color-bloc)" stroke="var(--color-surface)" strokeWidth="2" />
          <text x={sx(temps[i])} y={H - 10} fontSize="11" fill="var(--color-encre-3)"
            textAnchor={analyses.length > 1 && i === 0 ? 'start' : analyses.length > 1 && i === analyses.length - 1 ? 'end' : 'middle'}>
            {date(a.cree_le)}</text>
        </g>
      ))}
    </svg>
  )
}

function Colonne({ titre, a }: { titre: string; a: Analyse }) {
  return (
    <div className="flex min-w-0 flex-col items-center gap-2">
      <p className="text-[14px] font-semibold text-encre-2">{titre}</p>
      <Oculaire image={api.imageUrl(a.id, 'image')} abcd={a.abcd?.A ? api.imageUrl(a.id, 'abcd') : undefined} taille={300} />
      <p className="text-[14px] font-semibold">{dateHeure(a.cree_le)}</p>
      <Statut niveau={a.niveau} taille="petite" />
      <p className="text-[14px]">{t('les.pmel')} : <b className="chiffres">{pourcent(a.p_melanome)}</b></p>
      <Link to={`/analyses/${a.id}`} className="text-[13px] font-semibold text-bloc hover:underline">{t('les.ouvrir')}</Link>
    </div>
  )
}

export function LesionDetail() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const a = Number(params.get('a')) || undefined
  const b = Number(params.get('b')) || undefined
  const [d, setD] = useState<Detail | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [edition, setEdition] = useState(false)
  const [nom, setNom] = useState('')

  useEffect(() => { api.lesion(Number(id), a, b).then(setD).catch((e) => setErreur(e.message)) }, [id, a, b])

  if (erreur) return <Message>{erreur}</Message>
  if (!d) return <Chargement />
  const l = d.lesion
  const comp = d.comparaison
  const avant = comp ? d.analyses.find((x) => x.id === comp.avant) : undefined
  const apres = comp ? d.analyses.find((x) => x.id === comp.apres) : undefined
  const choisir = (cle: 'a' | 'b', aid: number) => {
    const n = new URLSearchParams(params)
    n.set(cle, String(aid))
    if (!n.get(cle === 'a' ? 'b' : 'a')) n.set(cle === 'a' ? 'b' : 'a', String(cle === 'a' ? apres?.id ?? aid : avant?.id ?? aid))
    setParams(n, { replace: true })
  }

  async function renommer(e: FormEvent) {
    e.preventDefault()
    try {
      const maj = await api.modifierLesion(l.id, { nom: nom.trim() || null })
      setD({ ...d!, lesion: { ...l, nom: maj.nom } })
      setEdition(false)
    } catch (err) { setErreur((err as Error).message) }
  }

  return (
    <>
      <p className="mb-1 text-[14px]"><Link to={`/patients/${l.patient_id}`} className="font-semibold text-bloc hover:underline">{d.patient_code}</Link></p>
      <EnTete titre={<>{t('les.titre', { n: l.numero })}{l.nom ? <span className="font-normal text-encre-2"> — {l.nom}</span> : null}</>}
        sousTitre={`${nomLoc(l.localisation)}${t('commun.liste')}${t('pat.nbImages', { n: d.analyses.length })}`}
        actions={<>
          {!DEMO && <Bouton variante="secondaire" onClick={() => { setNom(l.nom ?? ''); setEdition(true) }} icone={<Pencil className="size-4" aria-hidden />}>{t('les.renommer')}</Bouton>}
          <Link to={`/analyses/nouvelle?patient=${l.patient_id}&lesion=${l.id}`}>
            <Bouton icone={<History className="size-4" aria-hidden />}>{t('les.nouvelleImage')}</Bouton>
          </Link>
        </>} />

      <Panneau titre={t('les.chronologie')}>
        <ol className="flex gap-3 overflow-x-auto pb-2">
          {d.analyses.map((x) => {
            const estA = x.id === avant?.id, estB = x.id === apres?.id
            return (
              <li key={x.id} className={`flex w-[190px] shrink-0 flex-col gap-1.5 rounded-[5px] border p-3 ${estA || estB ? 'border-bloc bg-bloc-pale/60' : 'border-trait'}`}>
                <Link to={`/analyses/${x.id}`} className="flex items-center gap-2.5">
                  <img src={api.imageUrl(x.id, 'image')} alt="" className="size-12 rounded-full object-cover ring-2 ring-derme" />
                  <span className="text-[13px] font-semibold">{date(x.cree_le)}</span>
                </Link>
                <Statut niveau={x.niveau} taille="petite" />
                <span className="chiffres text-[13px] text-encre-2">p(mel) {pourcent(x.p_melanome)}</span>
                {d.analyses.length > 1 && (
                  <div className="mt-1 flex gap-1 text-[12px]">
                    <button onClick={() => choisir('a', x.id)} aria-pressed={estA} title={t('les.commeAvant')}
                      className={`rounded-[4px] border px-2 py-0.5 font-semibold ${estA ? 'border-bloc bg-bloc text-white' : 'border-trait text-encre-2 hover:border-encre-3'}`}>{t('les.avant')}</button>
                    <button onClick={() => choisir('b', x.id)} aria-pressed={estB} title={t('les.commeApres')}
                      className={`rounded-[4px] border px-2 py-0.5 font-semibold ${estB ? 'border-bloc bg-bloc text-white' : 'border-trait text-encre-2 hover:border-encre-3'}`}>{t('les.apres')}</button>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
        {d.analyses.length > 1
          ? <div className="mt-4"><h3 className="mb-1 text-[14px] font-semibold text-encre-2">{t('les.courbe')}</h3><Courbe analyses={d.analyses} /></div>
          : <p className="mt-3 text-[14px] text-encre-2">{t('les.uneSeule')}</p>}
      </Panneau>

      {comp && avant && apres && (
        <Panneau titre={t('les.comparaison')} className="mt-6">
          <div className="grid gap-8 md:grid-cols-2">
            <Colonne titre={t('les.avant')} a={avant} />
            <Colonne titre={t('les.apres')} a={apres} />
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <h3 className="mb-2 text-[15px] font-semibold">{t('les.signaux')}</h3>
              <p className="mb-2 text-[13px] text-encre-2">{t('evo.depuis', { date: date(avant.cree_le), jours: t('commun.jours', { n: comp.jours ?? '?' }) })}</p>
              <SignauxEvolution evo={comp} />
              <p className="mt-3 text-[12px] text-encre-2">{t('evo.note')}</p>
            </div>
            <TableauComparaison avant={avant} apres={apres} />
          </div>
        </Panneau>
      )}

      <Dialogue ouvert={edition} titre={t('les.renommer')} onFermer={() => setEdition(false)}>
        <form onSubmit={renommer} className="flex flex-col gap-4">
          <Champ label={t('les.nom')} aide={t('les.nomAide')}>{(fid) => <Saisie id={fid} value={nom} onChange={(e) => setNom(e.target.value)} maxLength={64} autoFocus />}</Champ>
          <Bouton type="submit" className="self-start">{t('pat.enregistrer')}</Bouton>
        </form>
      </Dialogue>
    </>
  )
}

/** Indicateurs des deux analyses comparées, ligne par ligne. */
function TableauComparaison({ avant, apres }: { avant: Analyse; apres: Analyse }) {
  const abcd = (a: Analyse) => a.abcd?.A ? a.abcd : null
  const lignes: [string, (a: Analyse) => string][] = [
    [t('les.pmel'), (a) => pourcent(a.p_melanome)],
    [`A — ${t('abcd.A')}`, (a) => (abcd(a) ? `${abcd(a)!.A!.score}/2` : '—')],
    [`B — ${t('abcd.B')}`, (a) => (abcd(a) ? `${abcd(a)!.B!.score}/8` : '—')],
    [`C — ${t('abcd.C')}`, (a) => (abcd(a) ? liste(abcd(a)!.C!.couleurs.map(nomCouleur)) || '—' : '—')],
    [`D — ${t('abcd.D')}`, (a) => (abcd(a)?.D?.mm != null ? t('commun.mm', { n: nombre(abcd(a)!.D!.mm!, 1) }) : '—')],
  ]
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-start text-[14px]">
        <thead className="border-b border-trait text-[13px] text-encre-2">
          <tr><th className="py-2 pe-3 text-start font-semibold">{t('les.indicateur')}</th>
            <th className="px-3 text-start font-semibold">{t('les.avant')}</th><th className="ps-3 text-start font-semibold">{t('les.apres')}</th></tr>
        </thead>
        <tbody className="divide-y divide-trait-2">
          <tr><td className="py-2 pe-3">{t('les.orientation')}</td>
            <td className="px-3"><Statut niveau={avant.niveau} taille="petite" /></td><td className="ps-3"><Statut niveau={apres.niveau} taille="petite" /></td></tr>
          {lignes.map(([nom, f]) => (
            <tr key={nom}><td className="py-2 pe-3">{nom}</td>
              <td className="chiffres px-3">{f(avant)}</td>
              <td className={`chiffres ps-3 ${f(avant) !== f(apres) ? 'font-semibold' : ''}`}>{f(apres)}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[12px] text-encre-2">{t('abcd.note')}</p>
    </div>
  )
}
