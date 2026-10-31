import { ChevronRight, History, ScanSearch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Analyse, type TableauDeBord } from '../api'
import { Statut } from '../components/metier'
import { Bouton, Chargement, EnTete, Message, Panneau, Vide } from '../components/ui'
import { useApp } from '../contexte'
import { t } from '../i18n'
import { dateHeure, nomClasse, nomLoc, nomNiveau, ORDRE_NIVEAU, pourcent } from '../lib/format'

export function Accueil() {
  const { utilisateur } = useApp()
  const [a_revoir, setARevoir] = useState<Analyse[] | null>(null)
  const [tb, setTb] = useState<TableauDeBord | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.analyses({ revue: 'en_attente', taille: 100 }), api.tableauDeBord()])
      .then(([p, tdb]) => {
        setARevoir([...p.elements].sort((x, y) => ORDRE_NIVEAU[x.niveau] - ORDRE_NIVEAU[y.niveau]
          || y.cree_le.localeCompare(x.cree_le)))
        setTb(tdb)
      })
      .catch((e) => setErreur(e.message))
  }, [])

  return (
    <>
      <EnTete titre={t('nav.fileTravail')} sousTitre={t('accueil.bonjour', { nom: utilisateur?.nom_complet ?? '' })}
        actions={<Link to="/analyses/nouvelle"><Bouton icone={<ScanSearch className="size-4" aria-hidden />}>{t('nav.nouvelleAnalyse')}</Bouton></Link>} />
      {erreur && <Message>{erreur}</Message>}
      {!a_revoir || !tb ? <Chargement /> : (
        <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
          <Panneau titre={t('accueil.aValider', { n: a_revoir.length })}>
            {a_revoir.length === 0 ? (
              <Vide titre={t('accueil.videTitre')} texte={t('accueil.videTexte')}
                action={<Link to="/analyses/nouvelle" className="font-semibold text-bloc hover:underline">{t('accueil.lancer')}</Link>} />
            ) : (
              <ul className="-mx-5 divide-y divide-trait-2">
                {a_revoir.map((a) => (
                  <li key={a.id}>
                    <Link to={`/analyses/${a.id}`} className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-4 px-5 py-3 hover:bg-porcelaine">
                      <img src={api.imageUrl(a.id, 'image')} alt="" className="size-11 rounded-full object-cover ring-2 ring-derme" />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Statut niveau={a.niveau} taille="petite" />
                          <span className="font-semibold">{a.patient_code}</span>
                          {a.evolution?.notable && (
                            <span className="inline-flex items-center gap-1 rounded-[4px] bg-avis-pale px-1.5 py-0.5 text-[12px] font-semibold text-avis">
                              <History className="size-3.5" aria-hidden /> {t('accueil.evolution')}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 truncate text-[13.5px] text-encre-2">
                          {a.lesion_numero ? `${t('na.lesionN', { n: a.lesion_numero })}${t('commun.liste')}` : ''}
                          {nomLoc(a.localisation)}{t('commun.liste')}{dateHeure(a.cree_le)}
                        </p>
                      </div>
                      <div className="hidden text-end sm:block">
                        <p className="text-[12.5px] text-encre-2">{t('accueil.propositionIA')}</p>
                        <p className="text-[14px] font-semibold">{nomClasse(a.decision)}</p>
                      </div>
                      <ChevronRight className="size-5 text-encre-3 rtl:rotate-180" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panneau>
          <div className="flex flex-col gap-6">
            <Panneau titre={t('accueil.activite')}>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-4">
                {([
                  [t('accueil.analyses30'), tb.analyses_30j],
                  [t('accueil.patientsSuivis'), tb.patients],
                  [t('accueil.enAttente'), tb.revues_en_attente],
                  [t('accueil.accord'), tb.taux_accord === null ? '—' : pourcent(tb.taux_accord, 0)],
                ] as const).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[13px] text-encre-2">{k}</dt>
                    <dd className="chiffres text-[22px] font-bold">{v}</dd>
                  </div>
                ))}
              </dl>
            </Panneau>
            <Panneau titre={t('accueil.orientation')}>
              {tb.total_analyses === 0 ? <p className="text-[14px] text-encre-2">{t('accueil.pasAnalyse')}</p> : (
                <ul className="flex flex-col gap-2.5">
                  {(['urgent', 'eleve', 'renvoi', 'faible'] as const).map((n) => {
                    const statut = { urgent: 'alerte_melanome', eleve: 'maligne_probable', renvoi: 'incertain', faible: 'benigne_probable' }[n]
                    const k = tb.par_statut[statut] ?? 0
                    return (
                      <li key={n} className="grid grid-cols-[1fr_auto] items-center gap-2 text-[14px]">
                        <Link to={`/analyses?statut=${statut}`} className="hover:underline">{nomNiveau(n)}</Link>
                        <span className="chiffres font-semibold">{k}</span>
                        <div className="col-span-2 h-[6px] rounded-[3px] bg-trait-2">
                          <div className="h-full rounded-[3px] bg-encre-3/60" style={{ width: `${(100 * k) / tb.total_analyses}%` }} />
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </Panneau>
          </div>
        </div>
      )}
    </>
  )
}
