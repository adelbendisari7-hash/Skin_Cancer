import { useMemo, useState } from 'react'
import type { EtSiReponse } from '../api'
import { t } from '../i18n'
import { nomLoc, pourcent } from '../lib/format'

/** Contrefactuel « et si » : p(mélanome) pour la même image, en changeant l'âge ou la localisation. */
export function EtSi({ donnees }: { donnees: EtSiReponse }) {
  return donnees.variable === 'age' ? <CourbeAge d={donnees} /> : <BarresLocalisation d={donnees} />
}

function CourbeAge({ d }: { d: EtSiReponse }) {
  const W = 560, H = 230, M = { g: 44, d: 16, h: 14, b: 34 }
  const pts = d.serie.map((s) => ({ x: Number(s.valeur), y: s.p_melanome }))
  const xmin = Math.min(...pts.map((p) => p.x)), xmax = Math.max(...pts.map((p) => p.x))
  const sx = (x: number) => M.g + ((x - xmin) / (xmax - xmin)) * (W - M.g - M.d)
  const sy = (y: number) => M.h + (1 - y) * (H - M.h - M.b)
  const [survol, setSurvol] = useState<number | null>(null)
  const chemin = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ')
  const actuel = typeof d.actuel === 'number' ? d.actuel : null
  const yActuel = useMemo(() => {
    if (actuel === null) return null
    const i = pts.findIndex((p) => p.x >= actuel)
    if (i <= 0) return pts[Math.max(i, 0)]?.y ?? null
    const a = pts[i - 1], b = pts[i]
    return a.y + ((actuel - a.x) / (b.x - a.x)) * (b.y - a.y)
  }, [actuel, pts])
  const p = survol !== null ? pts[survol] : null

  function bouger(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - r.left) / r.width) * W
    let best = 0
    pts.forEach((q, i) => { if (Math.abs(sx(q.x) - x) < Math.abs(sx(pts[best].x) - x)) best = i })
    setSurvol(best)
  }

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full touch-none" role="img" style={{ direction: 'ltr' }}
        aria-label={t('etsi.ariaAge')}
        onPointerMove={bouger} onPointerLeave={() => setSurvol(null)}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={M.g} x2={W - M.d} y1={sy(t)} y2={sy(t)} stroke="var(--color-trait-2)" />
            <text x={M.g - 8} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--color-encre-3)">{pourcent(t, 0)}</text>
          </g>
        ))}
        {pts.filter((q) => q.x % 10 === 0).map((q) => (
          <text key={q.x} x={sx(q.x)} y={H - 12} textAnchor="middle" fontSize="11" fill="var(--color-encre-3)">{q.x}</text>
        ))}
        <line x1={M.g} x2={W - M.d} y1={sy(d.seuil_melanome)} y2={sy(d.seuil_melanome)} stroke="var(--color-urgent)" strokeWidth="1.5" />
        <text x={W - M.d} y={sy(d.seuil_melanome) - 6} textAnchor="end" fontSize="11.5" fill="var(--color-urgent)">{t('etsi.seuil')}</text>
        <path d={chemin} fill="none" stroke="var(--color-bloc)" strokeWidth="2.25" strokeLinejoin="round" />
        {actuel !== null && yActuel !== null && (
          <g>
            <line x1={sx(actuel)} x2={sx(actuel)} y1={M.h} y2={H - M.b} stroke="var(--color-encre-3)" strokeWidth="1" />
            <circle cx={sx(actuel)} cy={sy(yActuel)} r="5.5" fill="var(--color-bloc)" stroke="var(--color-surface)" strokeWidth="2" />
            <text x={sx(actuel) + 8} y={M.h + 10} fontSize="11.5" fill="var(--color-encre-2)">{t('etsi.agePatient')}</text>
          </g>
        )}
        {p && (
          <g pointerEvents="none">
            <line x1={sx(p.x)} x2={sx(p.x)} y1={M.h} y2={H - M.b} stroke="var(--color-encre)" strokeOpacity="0.35" />
            <circle cx={sx(p.x)} cy={sy(p.y)} r="5" fill="var(--color-surface)" stroke="var(--color-bloc)" strokeWidth="2" />
            <g transform={`translate(${Math.min(sx(p.x) + 10, W - 150)},${Math.max(sy(p.y) - 34, M.h)})`}>
              <rect width="138" height="28" rx="4" fill="var(--color-encre)" />
              <text x="9" y="18" fontSize="12" fill="#fff">{t('commun.ans', { n: p.x })} : {pourcent(p.y)}</text>
            </g>
          </g>
        )}
      </svg>
      <table className="sr-only">
        <caption>{t('etsi.legende')}</caption>
        <tbody>{pts.map((q) => <tr key={q.x}><td>{t('commun.ans', { n: q.x })}</td><td>{pourcent(q.y)}</td></tr>)}</tbody>
      </table>
    </div>
  )
}

function BarresLocalisation({ d }: { d: EtSiReponse }) {
  const lignes = [...d.serie].sort((a, b) => b.p_melanome - a.p_melanome)
  return (
    <div className="flex flex-col gap-1.5">
      {lignes.map((s) => {
        const actuelle = s.valeur === d.actuel
        return (
          <div key={String(s.valeur)} className="grid grid-cols-[10.5rem_1fr_3.8rem] items-center gap-3 text-[13.5px]">
            <span className={actuelle ? 'font-bold' : 'text-encre-2'}>
              {nomLoc(String(s.valeur))}{actuelle && t('etsi.actuelle')}
            </span>
            <div className="relative h-[8px] rounded-[3px] bg-trait-2">
              <div className={`h-full rounded-[3px] ${actuelle ? 'bg-bloc' : 'bg-encre-3/50'}`} style={{ width: `${s.p_melanome * 100}%` }} />
              <div className="absolute -top-1 h-4 w-[2px] bg-urgent" style={{ insetInlineStart: `calc(${d.seuil_melanome * 100}% - 1px)` }} />
            </div>
            <span className="chiffres text-end font-semibold">{pourcent(s.p_melanome)}</span>
          </div>
        )
      })}
    </div>
  )
}
