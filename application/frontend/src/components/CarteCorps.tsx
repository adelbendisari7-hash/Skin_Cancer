import type { KeyboardEvent, ReactNode } from 'react'
import { t } from '../i18n'
import { nomLoc } from '../lib/format'

// Silhouette stylisée (vue de face / de dos), coordonnées dans un repère 200 × 412.
const TETE_HAUT = 'M78 40 C78 23 88 19 100 19 C112 19 122 23 122 40 Z'
const VISAGE = 'M78 40 L122 40 C122 58 112 72 100 72 C88 72 78 58 78 40 Z'
const COU = 'M91 69 L109 69 L111 87 L89 87 Z'
const POITRINE = 'M89 86 L111 86 C124 88 136 90 141 98 L139 148 L61 148 L59 98 C64 90 76 88 89 86 Z'
const ABDOMEN = 'M61 148 L139 148 L137 196 C130 204 118 208 100 208 C82 208 70 204 63 196 Z'
const DOS = 'M89 86 L111 86 C124 88 136 90 141 98 L139 148 L137 196 C130 204 118 208 100 208 C82 208 70 204 63 196 L61 148 L59 98 C64 90 76 88 89 86 Z'
const GENITAL = 'M88 205 C94 209 106 209 112 205 L106 226 L94 226 Z'
const BRAS = ['M59 98 C50 101 46 110 45 122 L40 176 L36 214 L48 216 L54 178 L62 128 Z',
  'M141 98 C150 101 154 110 155 122 L160 176 L164 214 L152 216 L146 178 L138 128 Z']
const JAMBES = ['M64 196 C72 206 86 210 98 210 L96 300 L93 390 L77 390 L72 300 C68 262 64 232 64 196 Z',
  'M136 196 C128 206 114 210 102 210 L104 300 L107 390 L123 390 L128 300 C132 262 136 232 136 196 Z']

/**
 * Carte du corps (face / dos) pour choisir la localisation de la lésion.
 * Chaque zone est un bouton accessible au clavier ; les zones de même nom s'allument ensemble.
 */
export function CarteCorps({ valeur, onChange }: { valeur: string; onChange: (loc: string) => void }) {
  const zone = (loc: string, forme: ReactNode, k: string) => {
    const choisi = valeur === loc
    const choisir = () => onChange(loc)
    return (
      <g key={k} role="button" tabIndex={0} aria-pressed={choisi} aria-label={nomLoc(loc)}
        onClick={choisir} onKeyDown={(e: KeyboardEvent) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), choisir())}
        className={`cursor-pointer outline-none transition-colors [&>*]:stroke-[1.3] [&>*]:[stroke-linejoin:round]
          ${choisi ? '[&>*]:fill-bloc [&>*]:stroke-bloc-fonce'
            : '[&>*]:fill-surface [&>*]:stroke-encre-3 hover:[&>*]:fill-bloc-pale focus-visible:[&>*]:fill-bloc-pale focus-visible:[&>*]:stroke-bloc'}`}>
        <title>{nomLoc(loc)}</title>
        {forme}
      </g>
    )
  }
  const commun = (dos: boolean) => [
    zone('lower extremity', <>{JAMBES.map((d) => <path key={d} d={d} />)}</>, `jambes${dos}`),
    zone('foot', <><ellipse cx="85" cy="398" rx="12" ry="7" /><ellipse cx="115" cy="398" rx="12" ry="7" /></>, `pieds${dos}`),
    zone('upper extremity', <>{BRAS.map((d) => <path key={d} d={d} />)}</>, `bras${dos}`),
    zone('hand', <><ellipse cx="42" cy="227" rx="7" ry="11" /><ellipse cx="158" cy="227" rx="7" ry="11" /></>, `mains${dos}`),
    zone('neck', <path d={COU} />, `cou${dos}`),
    zone('ear', <><ellipse cx="76" cy="47" rx="3.5" ry="7" /><ellipse cx="124" cy="47" rx="3.5" ry="7" /></>, `oreilles${dos}`),
  ]
  return (
    <div className="flex items-start justify-center gap-4 sm:gap-8">
      {[false, true].map((dos) => (
        <figure key={String(dos)} className="flex flex-col items-center gap-1">
          <svg viewBox="0 0 200 412" className="h-[300px] w-auto max-w-[42vw] sm:h-[340px]" aria-label={dos ? t('corps.vueDos') : t('corps.vueFace')} role="group" style={{ direction: 'ltr' }}>
            {commun(dos)}
            {dos ? <>
              {zone('back', <path d={DOS} />, 'dos')}
              {zone('scalp', <ellipse cx="100" cy="45" rx="22" ry="26" />, 'crane-dos')}
            </> : <>
              {zone('chest', <path d={POITRINE} />, 'poitrine')}
              {zone('abdomen', <path d={ABDOMEN} />, 'abdomen')}
              {zone('genital', <path d={GENITAL} />, 'genital')}
              {zone('scalp', <path d={TETE_HAUT} />, 'crane')}
              {zone('face', <path d={VISAGE} />, 'visage')}
            </>}
          </svg>
          <figcaption className="text-[13px] text-encre-2">{dos ? t('corps.dos') : t('corps.face')}</figcaption>
        </figure>
      ))}
    </div>
  )
}
