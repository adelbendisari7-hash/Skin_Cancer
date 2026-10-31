"""Compte rendu PDF d'une analyse (ReportLab, sans dépendance système), en français, anglais ou arabe.

L'arabe est mis en forme ici : ligature des lettres (arabic_reshaper), ordre d'affichage droite à
gauche (python-bidi, algorithme Unicode UAX #9) et coupure des lignes faite avant la réorganisation,
pour que les lignes d'un paragraphe s'enchaînent dans le bon ordre. Une seule police (IBM Plex Sans
Arabic, licence OFL, glyphes latins et arabes) sert pour les trois langues.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import __version__, config
from .db import Analyse

POLICES = Path(__file__).parent / "polices"
POLICE, POLICE_GRAS = "DermiaPlex", "DermiaPlex-Gras"
MARGE = 1.8 * cm
LARGEUR = A4[0] - 2 * MARGE - 12          # cadre de la page : 6 pt de marge intérieure de chaque côté
PAD = 4
ENCRE, ENCRE2, TRAIT = colors.HexColor("#14213d"), colors.HexColor("#52514e"), colors.HexColor("#d9dce3")
COULEURS_NIVEAU = {"urgent": colors.HexColor("#b42318"), "eleve": colors.HexColor("#b54708"),
                   "renvoi": colors.HexColor("#344054"), "faible": colors.HexColor("#067647")}
LANGUES = ("fr", "en", "ar")
_SANS_CONTROLES = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")   # marques bidi, sans glyphe
_LATIN = re.compile("[A-Za-z\u00c0-\u024f][^\u0600-\u06ff\ufb50-\ufdff\ufe70-\ufeff\u00ab\u00bb]*")
_FIN_LATIN = " \u00a0\u2014\u2013-:;,.("        # laissés au contexte arabe en fin de passage latin


def _isoler_latin(m: re.Match) -> str:
    """Encadre un passage latin (LRE … PDF) pour qu'il garde son ordre et ses parenthèses dans un texte arabe."""
    run = m.group(0)
    fin = len(run)
    while fin and (run[fin - 1] in _FIN_LATIN
                   or (run[fin - 1] == ")" and run[:fin].count(")") > run[:fin].count("("))):
        fin -= 1
    return "\u202a" + run[:fin] + "\u202c" + run[fin:]


def _affichage_rtl(ligne: str) -> str:
    """Ligne arabe en ordre logique → glyphes liés, en ordre visuel (UAX #9 avec miroir des parenthèses)."""
    visuel = get_display(arabic_reshaper.reshape(_LATIN.sub(_isoler_latin, ligne)), base_dir="R")
    return _SANS_CONTROLES.sub("", visuel)


def _polices() -> None:
    if POLICE not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(POLICE, str(POLICES / "IBMPlexSansArabic-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(POLICE_GRAS, str(POLICES / "IBMPlexSansArabic-Bold.ttf")))


# ---- textes (français, anglais, arabe) -----------------------------------------------------------
T: dict[str, tuple[str, str, str]] = {
    "titre": ("Compte rendu d'aide au triage — lésion cutanée", "Triage support report — skin lesion",
              "تقرير المساعدة على الفرز — آفة جلدية"),
    "meta_titre": ("Compte rendu {code}", "Report {code}", "تقرير {code}"),
    "sous_titre": ("{produit} v{version} · modèle {modele} v{vm} (profil {profil})",
                   "{produit} v{version} · model {modele} v{vm} ({profil} profile)",
                   "{produit} الإصدار {version} · النموذج {modele} الإصدار {vm} (الملف: {profil})"),
    "profil_complet": ("complet", "full", "كامل"),
    "profil_sans_contexte": ("image seule", "image only", "الصورة فقط"),
    "patient": ("Patient", "Patient", "المريض"),
    "date": ("Date de l'analyse", "Analysis date", "تاريخ التحليل"),
    "age": ("Âge", "Age", "العمر (بالسنوات)"),
    "age_val": ("{n} ans", "{n} years", "{n}"),
    "demandeur": ("Analyse demandée par", "Requested by", "طلب التحليل"),
    "sexe": ("Sexe", "Sex", "الجنس"),
    "localisation": ("Localisation", "Body site", "الموضع"),
    "lesion": ("Lésion suivie", "Tracked lesion", "الآفة المتابَعة"),
    "lesion_val": ("n° {n}", "#{n}", "رقم {n}"),
    "seuils": ("Seuils de décision", "Decision thresholds", "عتبات القرار"),
    "seuils_origine": ("d'origine", "original", "الأصلية"),
    "seuils_locaux": ("recalibrés localement (n° {id})", "locally recalibrated (#{id})", "مُعادة المعايرة محليًا (رقم {id})"),
    "non_precise": ("non précisé", "not specified", "غير محدد"),
    "date_heure": ("{d} à {h}", "{d}, {h}", "{d} {h}"),
    # niveaux et triage (par code de statut)
    "niv_urgent": ("URGENT", "URGENT", "عاجل"),
    "niv_eleve": ("AVIS SPÉCIALISÉ", "SPECIALIST OPINION", "رأي مختص"),
    "niv_renvoi": ("RENVOI AU MÉDECIN", "REFER TO A PHYSICIAN", "إحالة إلى الطبيب"),
    "niv_faible": ("BÉNIN PROBABLE", "PROBABLY BENIGN", "حميد على الأرجح"),
    "tri_alerte_melanome_t": ("Suspicion de mélanome", "Suspected melanoma", "اشتباه في ورم ميلانيني"),
    "tri_alerte_melanome_m": (
        "La probabilité de mélanome dépasse le seuil de sécurité. Avis dermatologique rapide recommandé.",
        "The probability of melanoma exceeds the safety threshold. Prompt dermatological assessment recommended.",
        "يتجاوز احتمال الورم الميلانيني عتبة الأمان. يوصى بعرض الحالة بسرعة على طبيب الأمراض الجلدية."),
    "tri_incertain_t": ("Résultat incertain : l'IA s'abstient", "Uncertain result: the AI abstains",
                        "نتيجة غير مؤكدة: الذكاء الاصطناعي يمتنع عن الحكم"),
    "tri_incertain_m": (
        "Plusieurs diagnostics restent plausibles au niveau de confiance garanti. Le cas doit être examiné par un médecin.",
        "Several diagnoses remain plausible at the guaranteed confidence level. The case must be examined by a physician.",
        "تبقى عدة تشخيصات محتملة عند مستوى الثقة المضمون. يجب أن يفحص الطبيب هذه الحالة."),
    "tri_maligne_probable_t": ("{nom} probable", "{nom} likely", "{nom} مرجَّح"),
    "tri_maligne_probable_m": (
        "Lésion maligne ou pré-maligne probable. Avis dermatologique recommandé.",
        "Probable malignant or pre-malignant lesion. Dermatological assessment recommended.",
        "آفة خبيثة أو سابقة للخباثة على الأرجح. يوصى باستشارة طبيب الأمراض الجلدية."),
    "tri_benigne_probable_t": ("{nom} probable", "{nom} likely", "{nom} مرجَّح"),
    "tri_benigne_probable_m": (
        "Lésion bénigne probable. Suivi selon le jugement clinique ; tout changement de la lésion justifie un nouvel examen.",
        "Probably benign lesion. Follow-up according to clinical judgement; any change in the lesion warrants a new examination.",
        "آفة حميدة على الأرجح. المتابعة حسب التقدير السريري، وأي تغيّر في الآفة يستدعي فحصًا جديدًا."),
    # images
    "cap_image": ("Image analysée", "Analysed image", "الصورة المحلَّلة"),
    "cap_gradcam": ("Zones ayant le plus pesé (Grad-CAM, «\u00a0{classe}\u00a0»)", "Most influential regions (Grad-CAM, “{classe}”)",
                    "المناطق الأكثر تأثيرًا (Grad-CAM، «{classe}»)"),
    "cap_abcd": ("Contour et axes utilisés pour l'ABCD", "Outline and axes used for ABCD",
                 "الحدود والمحاور المستخدمة في معايير ABCD"),
    # probabilités
    "h_probas": ("Probabilités estimées", "Estimated probabilities", "الاحتمالات المقدَّرة"),
    "col_diag": ("Diagnostic", "Diagnosis", "التشخيص"),
    "col_proba": ("Probabilité", "Probability", "الاحتمال"),
    "col_ens": ("Dans l'ensemble garanti*", "In the guaranteed set*", "ضمن المجموعة المضمونة*"),
    "oui": ("oui", "yes", "نعم"),
    "note_conforme": (
        "* Ensemble conforme (Mondrian, alpha = {alpha}) : contient le vrai diagnostic avec une probabilité d'au "
        "moins {couv} % pour chaque classe, sous l'hypothèse que les cas ressemblent aux données de calibration. "
        "Décision mélanome si p(mel) ≥ {seuil} (rapport de coût R = {R}).",
        "* Conformal set (Mondrian, alpha = {alpha}): contains the true diagnosis with a probability of at least "
        "{couv}% for each class, assuming the cases resemble the calibration data. "
        "Melanoma decision if p(mel) ≥ {seuil} (cost ratio R = {R}).",
        "* المجموعة المطابِقة (طريقة موندريان، ألفا = {alpha}): تحتوي على التشخيص الصحيح باحتمال لا يقل عن "
        "{couv}% لكل فئة، بافتراض أن الحالات تشبه بيانات المعايرة. يُتخذ قرار الورم الميلانيني إذا كان "
        "p(mel) ≥ {seuil} (نسبة التكلفة R = {R})."),
    "note_origine": ("Seuils d'origine du modèle, calibrés sur le jeu de calibration HAM10000.",
                     "Original model thresholds, calibrated on the HAM10000 calibration set.",
                     "عتبات النموذج الأصلية، معايَرة على مجموعة المعايرة من HAM10000."),
    "note_locale": ("Seuils recalibrés sur les cas validés de l'établissement (proposition n° {id}).",
                    "Thresholds recalibrated on this facility's validated cases (proposal #{id}).",
                    "عتبات أُعيدت معايرتها على الحالات المُصادَق عليها في المؤسسة (الاقتراح رقم {id})."),
    # avertissements
    "attention": ("Attention : {texte}", "Caution: {texte}", "تنبيه: {texte}"),
    "av_contexte_incomplet": (
        "contexte clinique incomplet (âge, sexe ou localisation manquant) : modèle «\u00a0image seule\u00a0» utilisé.",
        "incomplete clinical context (age, sex or body site missing): image-only model used.",
        "السياق السريري ناقص (العمر أو الجنس أو الموضع غير متوفر): استُخدم نموذج الصورة فقط."),
    "av_faible_resolution": ("image de faible résolution ({largeur} × {hauteur} px) : résultat moins fiable.",
                             "low-resolution image ({largeur} × {hauteur} px): less reliable result.",
                             "صورة منخفضة الدقة (العرض {largeur} بكسل، الارتفاع {hauteur} بكسل): النتيجة أقل موثوقية."),
    "av_image_atypique": (
        "image peu typique d'une dermoscopie, analysée à la demande de l'utilisateur : résultat à interpréter avec "
        "une grande prudence.",
        "image atypical of dermoscopy, analysed at the user's request: interpret the result with great caution.",
        "صورة غير نمطية للتنظير الجلدي، حُلِّلت بطلب من المستخدم: يجب تفسير النتيجة بحذر شديد."),
    # ABCD
    "h_abcd": ("Critères ABCD automatiques (indicatifs)", "Automatic ABCD criteria (indicative)",
               "معايير ABCD الآلية (استرشادية)"),
    "col_critere": ("Critère", "Criterion", "المعيار"),
    "col_mesure": ("Mesure", "Measure", "القياس"),
    "col_detail": ("Détail", "Detail", "التفاصيل"),
    "abcd_A": ("A — Asymétrie", "A — Asymmetry", "A — عدم التناظر"),
    "abcd_A_d": ("axes principaux asymétriques (forme ou couleurs)", "asymmetric principal axes (shape or colours)",
                 "محاور رئيسية غير متناظرة (الشكل أو الألوان)"),
    "abcd_B": ("B — Bords", "B — Border", "B — الحواف"),
    "abcd_B_d": ("secteurs à transition abrupte", "sectors with an abrupt edge", "قطاعات ذات حافة حادة"),
    "abcd_C": ("C — Couleurs", "C — Colours", "C — الألوان"),
    "abcd_D": ("D — Diamètre", "D — Diameter", "D — القطر"),
    "mm": ("{v} mm", "{v} mm", "{v} مم"),
    "abcd_D_plus": ("plus de 6 mm", "more than 6 mm", "أكثر من 6 مم"),
    "abcd_D_moins": ("6 mm ou moins", "6 mm or less", "6 مم أو أقل"),
    "abcd_D_inconnu": ("largeur du champ du dermoscope non renseignée (Paramètres)",
                       "dermatoscope field width not set (Settings)", "عرض مجال منظار الجلد غير محدد (الإعدادات)"),
    "al_lesion_coupee": ("La lésion touche le bord de l'image : A, B et D sont moins fiables.",
                         "The lesion touches the image border: A, B and D are less reliable.",
                         "تلامس الآفة حافة الصورة: المعايير A وB وD أقل موثوقية."),
    "al_lesion_tres_petite": ("Lésion très petite dans l'image : mesures peu précises.",
                              "Very small lesion in the image: measurements are imprecise.",
                              "الآفة صغيرة جدًا في الصورة: القياسات غير دقيقة."),
    "al_segmentation_impossible": ("Segmentation de la lésion impossible : critères ABCD non calculés.",
                                   "Lesion segmentation failed: ABCD criteria not computed.",
                                   "تعذّر تحديد حدود الآفة: لم تُحسب معايير ABCD."),
    "note_abcd": (
        "Mesures automatiques à valeur indicative : sur le jeu de test HAM10000, chacune ne distingue que modestement "
        "mélanome et nævus (AUC de 0,66 à 0,73). Elles ne remplacent pas l'examen dermoscopique.",
        "Indicative automatic measurements: on the HAM10000 test set, each separates melanoma from nevus only "
        "modestly (AUC 0.66 to 0.73). They do not replace dermoscopic examination.",
        "قياسات آلية استرشادية: على مجموعة الاختبار من HAM10000 لا يميّز كل منها بين الورم الميلانيني والوحمة إلا "
        "بشكل محدود (AUC من 0,66 إلى 0,73). وهي لا تُغني عن الفحص بالمنظار الجلدي."),
    # évolution
    "h_evolution": ("Évolution depuis l'analyse du {date} ({jours} j)", "Change since the analysis of {date} ({jours} days)",
                    "التطور منذ تحليل {date} (عدد الأيام: {jours})"),
    "ev_p_mel_hausse": ("Probabilité de mélanome en hausse : de {de} à {a}.",
                        "Melanoma probability increased: from {de} to {a}.",
                        "ارتفاع احتمال الورم الميلانيني: من {de} إلى {a}."),
    "ev_orientation_aggravee": ("Orientation plus sévère : de «\u00a0{de}\u00a0» à «\u00a0{a}\u00a0».",
                                "More severe triage: from “{de}” to “{a}”.", "توجيه أشد: من «{de}» إلى «{a}»."),
    "ev_asymetrie_hausse": ("Asymétrie en hausse : de {de}/2 à {a}/2.", "Asymmetry increased: from {de}/2 to {a}/2.",
                            "ازدياد عدم التناظر: من {de}/2 إلى {a}/2."),
    "ev_bords_hausse": ("Bords abrupts en hausse : de {de}/8 à {a}/8 secteurs.",
                        "Abrupt border increased: from {de}/8 to {a}/8 sectors.",
                        "ازدياد الحواف الحادة: من {de}/8 إلى {a}/8 قطاعات."),
    "ev_nouvelles_couleurs": ("Nouvelle(s) couleur(s) : {couleurs}.", "New colour(s): {couleurs}.",
                              "ألوان جديدة: {couleurs}."),
    "ev_diametre_hausse": ("Diamètre en hausse : de {de} mm à {a} mm.", "Diameter increased: from {de} mm to {a} mm.",
                           "ازدياد القطر: من {de} مم إلى {a} مم."),
    "ev_aucun": ("Aucun signal d'évolution détecté par les indicateurs automatiques.",
                 "No change detected by the automatic indicators.", "لم تكشف المؤشرات الآلية عن أي تطور."),
    "note_evolution": (
        "Comparez aussi les images visuellement : le cadrage et le grossissement peuvent différer d'un examen à l'autre.",
        "Also compare the images visually: framing and magnification may differ between examinations.",
        "قارن الصور بصريًا أيضًا: قد يختلف التأطير والتكبير من فحص لآخر."),
    # validation
    "h_validation": ("Validation médicale", "Medical review", "المراجعة الطبية"),
    "rev_en_attente": ("Non encore revue par un médecin.", "Not yet reviewed by a physician.", "لم يراجعها طبيب بعد."),
    "rev_confirmee": ("Confirmée par {qui} le {date}.", "Confirmed by {qui} on {date}.", "أكّدها {qui} بتاريخ {date}."),
    "rev_corrigee": ("Corrigée par {qui} le {date}.", "Corrected by {qui} on {date}.", "صحّحها {qui} بتاريخ {date}."),
    "diag_retenu": ("Diagnostic retenu : {d}", "Final diagnosis: {d}", "التشخيص المعتمد: {d}"),
    "histologie": ("Diagnostic confirmé par histologie.", "Diagnosis confirmed by histology.",
                   "التشخيص مؤكَّد بالفحص النسيجي."),
    "commentaire": ("Commentaire : {c}", "Comment: {c}", "تعليق: {c}"),
    "signature": ("Signature du médecin : ______________________________",
                  "Physician's signature: ______________________________", "توقيع الطبيب: ______________________________"),
    "avertissement": (
        "Avertissement. Ce document est produit par un outil d'aide à la décision. Il ne constitue pas un diagnostic "
        "et ne remplace ni l'examen clinique ni l'histologie. Statut du modèle : {statut}. Données d'entraînement : "
        "{jeu} — licence {licence}.",
        "Disclaimer. This document is produced by a decision-support tool. It is not a diagnosis and replaces neither "
        "clinical examination nor histology. Model status: {statut}. Training data: {jeu} — licence {licence}.",
        "تنبيه. أُعدَّت هذه الوثيقة بواسطة أداة للمساعدة على اتخاذ القرار، وهي لا تُعدّ تشخيصًا ولا تُغني عن الفحص "
        "السريري ولا عن الفحص النسيجي. حالة النموذج: {statut}. بيانات التدريب: {jeu} — الترخيص {licence}."),
    "non_commercial": ("", " (non-commercial)", " (غير تجاري)"),
}

NOMS_CLASSES = {  # le français vient du manifeste du modèle
    "nv": ("Melanocytic nevus", "وحمة ميلانينية"),
    "mel": ("Melanoma", "ورم ميلانيني"),
    "bkl": ("Benign keratosis", "تقرّن حميد"),
    "bcc": ("Basal cell carcinoma", "سرطانة الخلايا القاعدية"),
    "akiec": ("Actinic keratosis / Bowen's disease", "تقرّن سفعي / داء بوين"),
    "vasc": ("Vascular lesion", "آفة وعائية"),
    "df": ("Dermatofibroma", "ورم ليفي جلدي"),
}
LOCALISATIONS = {
    "abdomen": ("abdomen", "abdomen", "البطن"), "acral": ("acral (paumes, plantes)", "acral (palms, soles)",
                                                         "طرفي (راحتا اليدين، أخمصا القدمين)"),
    "back": ("dos", "back", "الظهر"), "chest": ("poitrine", "chest", "الصدر"), "ear": ("oreille", "ear", "الأذن"),
    "face": ("visage", "face", "الوجه"), "foot": ("pied", "foot", "القدم"),
    "genital": ("région génitale", "genital area", "المنطقة التناسلية"), "hand": ("main", "hand", "اليد"),
    "lower extremity": ("membre inférieur", "lower limb", "الطرف السفلي"), "neck": ("cou", "neck", "العنق"),
    "scalp": ("cuir chevelu", "scalp", "فروة الرأس"), "trunk": ("tronc", "trunk", "الجذع"),
    "upper extremity": ("membre supérieur", "upper limb", "الطرف العلوي"),
    "unknown": ("non précisée", "not specified", "غير محدد"),
}
SEXES = {"male": ("homme", "male", "ذكر"), "female": ("femme", "female", "أنثى"),
         "unknown": ("non précisé", "not specified", "غير محدد")}
COULEURS_ABCD = {"blanc": ("blanc", "white", "أبيض"), "rouge": ("rouge", "red", "أحمر"),
                 "brun_clair": ("brun clair", "light brown", "بني فاتح"),
                 "brun_fonce": ("brun foncé", "dark brown", "بني داكن"),
                 "bleu_gris": ("bleu-gris", "blue-grey", "أزرق رمادي"), "noir": ("noir", "black", "أسود")}
STATUT_V1 = ("DÉMONSTRATION — usage non commercial — pas un dispositif médical",
             "DEMONSTRATION — non-commercial use — not a medical device",
             "عرض توضيحي — استخدام غير تجاري — ليس جهازًا طبيًا")


class _Redaction:
    """Textes, nombres, dates et paragraphes dans la langue du compte rendu."""

    def __init__(self, langue: str, manifest: dict):
        self.lg, self.i, self.rtl, self.m = langue, LANGUES.index(langue), langue == "ar", manifest
        aligne = TA_RIGHT if self.rtl else TA_LEFT
        base = dict(fontName=POLICE, textColor=ENCRE, alignment=aligne)
        self.st = {
            "h": ParagraphStyle("h", **{**base, "fontName": POLICE_GRAS}, fontSize=15, leading=21, spaceAfter=2),
            "sous": ParagraphStyle("s", **{**base, "textColor": ENCRE2}, fontSize=8.8, leading=12.5),
            "n": ParagraphStyle("n", **base, fontSize=9.3, leading=13.5),
            "ng": ParagraphStyle("ng", **{**base, "fontName": POLICE_GRAS}, fontSize=9.3, leading=13.5),
            "et": ParagraphStyle("et", **{**base, "textColor": ENCRE2}, fontSize=8.8, leading=12.5),
            "petit": ParagraphStyle("p", **{**base, "textColor": ENCRE2}, fontSize=7.7, leading=10.5),
            "legende": ParagraphStyle("l", **{**base, "textColor": ENCRE2, "alignment": TA_CENTER},
                                      fontSize=7.5, leading=10),
            "centre": ParagraphStyle("c", **{**base, "alignment": TA_CENTER}, fontSize=8.8, leading=12.5),
            "entete": ParagraphStyle("e", **{**base, "fontName": POLICE_GRAS}, fontSize=8.8, leading=12.5),
            "entete_c": ParagraphStyle("ec", **{**base, "fontName": POLICE_GRAS, "alignment": TA_CENTER},
                                       fontSize=8.8, leading=12.5),
            "h2": ParagraphStyle("h2", **{**base, "fontName": POLICE_GRAS}, fontSize=11, leading=15,
                                 spaceBefore=9, spaceAfter=4),
            "bandeau": ParagraphStyle("b", **{**base, "fontName": POLICE_GRAS, "textColor": colors.white},
                                      fontSize=9, leading=12.5),
        }

    # -- textes
    def t(self, cle: str, **kw) -> str:
        return T[cle][self.i].format(**kw)

    def de(self, table: dict, cle) -> str:
        v = table.get(cle)
        return v[self.i] if v else str(cle)

    def liste(self, elements) -> str:
        return ("، " if self.rtl else ", ").join(elements) or "—"

    def classe(self, c: str) -> str:
        if self.lg == "fr" or c not in NOMS_CLASSES:
            return self.m["noms_classes"].get(c, c)
        return NOMS_CLASSES[c][self.i - 1]

    def nombre(self, x: float, decimales: int = 2) -> str:
        s = f"{x:.{decimales}f}"
        return s if self.lg == "en" else s.replace(".", ",")

    def pourcent(self, x: float) -> str:
        v = self.nombre(100 * x, 1)
        return f"{v} %" if self.lg == "fr" else f"{v}%"

    def date(self, d: datetime | str, heure: bool = False) -> str:
        if isinstance(d, str):
            d = datetime.fromisoformat(d)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        d = d.astimezone()                                  # heure locale du poste
        return self.t("date_heure", d=f"{d:%d/%m/%Y}", h=f"{d:%H:%M}") if heure else f"{d:%d/%m/%Y}"

    # -- mise en page
    def p(self, texte: str, style: str | ParagraphStyle = "n", largeur: float = LARGEUR) -> Paragraph:
        st = self.st[style] if isinstance(style, str) else style
        if not self.rtl:
            return Paragraph(escape(texte).replace("\n", "<br/>"), st)
        lignes = []                                         # coupure en ordre logique, puis affichage RTL
        for bloc in texte.split("\n"):
            cour: list[str] = []
            for mot in bloc.split():
                essai = " ".join([*cour, mot])
                if cour and pdfmetrics.stringWidth(arabic_reshaper.reshape(essai), st.fontName, st.fontSize) > largeur - 3:
                    lignes.append(" ".join(cour))
                    cour = [mot]
                else:
                    cour.append(mot)
            lignes.append(" ".join(cour))
        return Paragraph("<br/>".join(escape(_affichage_rtl(ligne)) for ligne in lignes), st)

    def _miroir(self, cmd: tuple, n: int) -> tuple:
        if not self.rtl:
            return cmd
        nom, (c0, r0), (c1, r1), *reste = cmd
        a, b = c0 % n, c1 % n
        return (nom, (n - 1 - b, r0), (n - 1 - a, r1), *reste)

    def tableau(self, lignes: list[list], largeurs: list[float], styles: list[tuple] = ()) -> Table:
        """Cellules : texte (style « n »), (texte, style) ou flowable / liste de flowables. Miroir en arabe."""
        rangs = []
        for ligne in lignes:
            rang = []
            for c, w in zip(ligne, largeurs):
                if isinstance(c, str):
                    c = self.p(c, "n", w - 2 * PAD)
                elif isinstance(c, tuple):
                    c = self.p(c[0], c[1], w - 2 * PAD)
                rang.append(c)
            rangs.append(rang[::-1] if self.rtl else rang)
        t = Table(rangs, colWidths=largeurs[::-1] if self.rtl else largeurs)
        cmds = [("LEFTPADDING", (0, 0), (-1, -1), PAD), ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        t.setStyle(TableStyle(cmds + [self._miroir(c, len(largeurs)) for c in styles]))
        return t


def _image(chemin: Path, w: float, h: float) -> RLImage:
    return RLImage(str(chemin), w, h, kind="proportional")


def compte_rendu_pdf(a: Analyse, etablissement: str, image: Path, gradcam: Path, abcd_png: Path | None,
                     manifest: dict, langue: str = "fr") -> bytes:
    _polices()
    r = _Redaction(langue if langue in LANGUES else "fr", manifest)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title=r.t("meta_titre", code=a.patient.code),
                            author=config.NOM_PRODUIT, lang={"fr": "fr-FR", "en": "en-GB", "ar": "ar"}[r.lg])
    profil = r.t(f"profil_{a.profil}") if f"profil_{a.profil}" in T else a.profil
    els = [r.p(etablissement or "", "sous"), r.p(r.t("titre"), "h"),
           r.p(r.t("sous_titre", produit=config.NOM_PRODUIT, version=__version__, modele=a.modele,
                   vm=a.version_modele, profil=profil), "sous"), Spacer(1, 8)]

    # ---- identification
    nonp = r.t("non_precise")
    if a.lesion is not None:
        lesion = r.t("lesion_val", n=a.lesion.numero) + (f" — {a.lesion.nom}" if a.lesion.nom else "")
    else:
        lesion = "—"
    cal = a.calibration or "origine"
    seuils = r.t("seuils_locaux", id=cal.split(":", 1)[1]) if cal.startswith("locale:") else r.t("seuils_origine")
    infos = [[("patient", "et"), a.patient.code, ("date", "et"), r.date(a.cree_le, heure=True)],
             [("age", "et"), r.t("age_val", n=f"{a.age:.0f}") if a.age is not None else nonp,
              ("demandeur", "et"), a.auteur.nom_complet],
             [("sexe", "et"), r.de(SEXES, a.sexe) if a.sexe else nonp,
              ("localisation", "et"), r.de(LOCALISATIONS, a.localisation)],
             [("lesion", "et"), lesion, ("seuils", "et"), seuils]]
    infos = [[(r.t(c[0]), c[1]) if isinstance(c, tuple) else c for c in ligne] for ligne in infos]
    els += [r.tableau(infos, [LARGEUR * f for f in (0.18, 0.31, 0.205, 0.305)],
                      [("LINEBELOW", (0, 0), (-1, -1), 0.4, TRAIT)]), Spacer(1, 10)]

    # ---- orientation
    couleur = COULEURS_NIVEAU.get(a.niveau, ENCRE)
    libelle = r.t(f"niv_{a.niveau}") if f"niv_{a.niveau}" in T else a.niveau
    if f"tri_{a.statut}_t" in T:
        titre = r.t(f"tri_{a.statut}_t", nom=r.classe(a.decision))
        message = r.t(f"tri_{a.statut}_m")
    else:
        titre, message = a.titre, a.message
    larg_texte = LARGEUR - 3.8 * cm
    els += [r.tableau([[(libelle, "bandeau"), [r.p(titre, "ng", larg_texte - 2 * PAD), r.p(message, "n", larg_texte - 2 * PAD)]]],
                      [3.8 * cm, larg_texte],
                      [("BACKGROUND", (0, 0), (0, 0), couleur), ("BOX", (0, 0), (-1, -1), 1, couleur),
                       ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                       ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]),
            Spacer(1, 10)]

    # ---- images
    vues = [(image, r.t("cap_image")), (gradcam, r.t("cap_gradcam", classe=r.classe(a.decision)))]
    if abcd_png is not None and Path(abcd_png).exists():
        vues.append((abcd_png, r.t("cap_abcd")))
    w = LARGEUR / len(vues)
    cote = min(w - 0.5 * cm, 6.2 * cm)
    els += [r.tableau([[_image(f, cote, cote * 0.82) for f, _ in vues], [(cap, "legende") for _, cap in vues]],
                      [w] * len(vues), [("ALIGN", (0, 0), (-1, 0), "CENTER")]), Spacer(1, 4)]

    # ---- probabilités
    corps = [r.p(r.t("h_probas"), "h2")]
    lignes = [[(r.t("col_diag"), "entete"), (r.t("col_proba"), "entete_c"), (r.t("col_ens"), "entete_c")]]
    for c, p in sorted(a.probabilites.items(), key=lambda kv: -kv[1]):
        lignes.append([r.classe(c), (r.pourcent(p), "centre"), (r.t("oui") if c in a.ensemble_conforme else "", "centre")])
    corps.append(r.tableau(lignes, [7.4 * cm, 3.4 * cm, 4.8 * cm],
                           [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f8")),
                            ("LINEBELOW", (0, 0), (-1, -1), 0.4, TRAIT),
                            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    els.append(KeepTogether(corps))
    alpha = manifest["abstention"]["alpha"]
    els.append(Spacer(1, 3))
    els.append(r.p(r.t("note_conforme", alpha=r.nombre(alpha, 2), couv=f"{100 * (1 - alpha):.0f}",
                       seuil=r.nombre(a.seuil_melanome, 2), R=a.rapport_cout), "petit"))
    els.append(r.p(r.t("note_locale", id=cal.split(":", 1)[1]) if cal.startswith("locale:") else r.t("note_origine"),
                   "petit"))
    for av in a.avertissements or []:
        code = av.get("code") if isinstance(av, dict) else "texte"
        if code == "texte":                                  # ancienne analyse (v1) : texte libre en français
            texte = av.get("texte", "") if isinstance(av, dict) else str(av)
        elif f"av_{code}" in T:
            texte = r.t(f"av_{code}", **{k: v for k, v in av.items() if k != "code"})
        else:
            continue                                         # « evolution » : détaillée plus bas
        els.append(r.p(r.t("attention", texte=texte), "petit"))

    # ---- ABCD
    m = a.abcd
    if m:
        corps = [r.p(r.t("h_abcd"), "h2")]
        if m.get("A") is None:
            corps.append(r.p(r.t("al_segmentation_impossible"), "n"))
        else:
            couleurs = r.liste(r.de(COULEURS_ABCD, c) for c in m["C"]["couleurs"])
            d = m.get("D") or {}
            if d.get("mm") is None:
                mesure_d, detail_d = "—", r.t("abcd_D_inconnu")
            else:
                mesure_d = r.t("mm", v=r.nombre(d["mm"], 1))
                detail_d = r.t("abcd_D_plus") if d.get("superieur_6mm") else r.t("abcd_D_moins")
            lignes = [[(r.t("col_critere"), "entete"), (r.t("col_mesure"), "entete_c"), (r.t("col_detail"), "entete")],
                      [r.t("abcd_A"), (f"{m['A']['score']}/2", "centre"), r.t("abcd_A_d")],
                      [r.t("abcd_B"), (f"{m['B']['score']}/8", "centre"), r.t("abcd_B_d")],
                      [r.t("abcd_C"), (f"{m['C']['score']}/6", "centre"), couleurs],
                      [r.t("abcd_D"), (mesure_d, "centre"), detail_d]]
            corps.append(r.tableau(lignes, [4.2 * cm, 2.8 * cm, LARGEUR - 7 * cm],
                                   [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f8")),
                                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, TRAIT),
                                    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            for al in m.get("alertes", []):
                if f"al_{al}" in T:
                    corps.append(r.p(r.t("attention", texte=r.t(f"al_{al}")), "petit"))
        corps.append(r.p(r.t("note_abcd"), "petit"))
        els.append(KeepTogether(corps))

    # ---- évolution de la lésion
    evo = a.evolution
    if evo:
        corps = [r.p(r.t("h_evolution", date=r.date(evo["depuis"]),
                         jours=evo["jours"] if evo.get("jours") is not None else "?"), "h2")]
        for s in evo.get("signaux", []):
            code = s["code"]
            if code == "p_mel_hausse":
                txt = r.t("ev_p_mel_hausse", de=r.pourcent(s["de"]), a=r.pourcent(s["a"]))
            elif code == "orientation_aggravee":
                txt = r.t("ev_orientation_aggravee", de=r.t(f"niv_{s['de']}"), a=r.t(f"niv_{s['a']}"))
            elif code == "nouvelles_couleurs":
                txt = r.t("ev_nouvelles_couleurs", couleurs=r.liste(r.de(COULEURS_ABCD, c) for c in s["couleurs"]))
            elif code == "diametre_hausse":
                txt = r.t("ev_diametre_hausse", de=r.nombre(s["de"], 1), a=r.nombre(s["a"], 1))
            elif f"ev_{code}" in T:
                txt = r.t(f"ev_{code}", de=s["de"], a=s["a"])
            else:
                continue
            corps.append(r.p("• " + txt, "n"))
        if not evo.get("signaux"):
            corps.append(r.p(r.t("ev_aucun"), "n"))
        corps.append(r.p(r.t("note_evolution"), "petit"))
        els.append(KeepTogether(corps))

    # ---- validation médicale
    corps = [r.p(r.t("h_validation"), "h2")]
    if a.revue == "en_attente" or a.revue_le is None:
        corps.append(r.p(r.t("rev_en_attente"), "n"))
    else:
        qui = a.relecteur.nom_complet if a.relecteur else "—"
        corps.append(r.p(r.t(f"rev_{a.revue}", qui=qui, date=r.date(a.revue_le)), "n"))
        corps.append(r.p(r.t("diag_retenu", d=r.classe(a.diagnostic_final) if a.diagnostic_final else "—"), "ng"))
        if a.histologie:
            corps.append(r.p(r.t("histologie"), "n"))
        if a.commentaire:
            corps.append(r.p(r.t("commentaire", c=a.commentaire), "n"))
    corps += [Spacer(1, 16), r.p(r.t("signature"), "n")]
    els += [KeepTogether(corps), Spacer(1, 12)]

    statut = (manifest.get("statut_i18n") or {}).get(r.lg)
    if not statut:
        statut = STATUT_V1[r.i] if manifest["statut"] == STATUT_V1[0] else manifest["statut"]
    licence = manifest["donnees_entrainement"]["licence"]
    if r.lg != "fr":
        licence = licence.split(" (")[0] + r.t("non_commercial")
    els.append(r.p(r.t("avertissement", statut=statut, jeu=manifest["donnees_entrainement"]["jeu"], licence=licence),
                   "petit"))
    doc.build(els)
    return buf.getvalue()
