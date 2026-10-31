"""Traduction des messages d'erreur de l'API (français → anglais, arabe).

Le code source écrit ses messages en français ; ils sont traduits au moment de la réponse selon
l'en-tête `X-Langue` envoyé par l'interface. Un message absent de la table reste en français
(le test `test_i18n` vérifie que tous les messages du code y figurent).
"""
from __future__ import annotations

import re

from fastapi import Request

LANGUES = ("fr", "en", "ar")

MESSAGES: dict[str, tuple[str, str]] = {
    # ---- analyses ------------------------------------------------------------------------------
    "40 valeurs au maximum.": ("40 values at most.", "40 قيمة على الأكثر."),
    "Analyse introuvable.": ("Analysis not found.", "التحليل غير موجود."),
    "Cette image ne ressemble pas à une image dermoscopique.":
        ("This image does not look like a dermoscopic image.", "لا تبدو هذه الصورة صورةً بالمنظار الجلدي."),
    "Fichier illisible : envoyez une image JPEG, PNG, TIFF, BMP ou WEBP.":
        ("Unreadable file: please send a JPEG, PNG, TIFF, BMP or WEBP image.",
         "ملف غير مقروء: أرسل صورة بصيغة JPEG أو PNG أو TIFF أو BMP أو WEBP."),
    "Fichier image manquant.": ("Image file missing.", "ملف الصورة مفقود."),
    "Format d'image non pris en charge.": ("Unsupported image format.", "صيغة الصورة غير مدعومة."),
    "Image trop petite (64 px minimum).": ("Image too small (64 px minimum).", "الصورة صغيرة جدًا (64 بكسل على الأقل)."),
    "Image trop volumineuse (15 Mo maximum).": ("Image too large (15 MB maximum).", "حجم الصورة كبير جدًا (15 ميغابايت كحد أقصى)."),
    "Indiquez le diagnostic retenu (une des 7 classes).":
        ("Specify the final diagnosis (one of the 7 classes).", "حدِّد التشخيص المعتمد (إحدى الفئات السبع)."),
    "Localisation inconnue.": ("Unknown body site.", "موضع غير معروف."),
    "Lésion introuvable pour ce patient.": ("Lesion not found for this patient.", "الآفة غير موجودة لدى هذا المريض."),
    "Lésion introuvable.": ("Lesion not found.", "الآفة غير موجودة."),
    "Patient introuvable.": ("Patient not found.", "المريض غير موجود."),
    "Rapport de coût non calibré pour ce modèle.":
        ("Cost ratio not calibrated for this model.", "نسبة التكلفة غير معايَرة لهذا النموذج."),
    "Âge invalide.": ("Invalid age.", "عمر غير صالح."),
    # ---- comptes -------------------------------------------------------------------------------
    "Cet identifiant existe déjà.": ("This username already exists.", "اسم المستخدم هذا موجود مسبقًا."),
    "Identifiant ou mot de passe incorrect.": ("Incorrect username or password.", "اسم المستخدم أو كلمة المرور غير صحيحة."),
    "Mot de passe actuel incorrect.": ("Current password is incorrect.", "كلمة المرور الحالية غير صحيحة."),
    "Utilisateur introuvable.": ("User not found.", "المستخدم غير موجود."),
    "Vous ne pouvez pas vous retirer vos propres droits d'administration.":
        ("You cannot remove your own administrator rights.", "لا يمكنك سحب صلاحيات الإدارة من حسابك."),
    "Un patient avec cette référence existe déjà.":
        ("A patient with this reference already exists.", "يوجد مريض بهذا المرجع مسبقًا."),
    # ---- recalibrage ---------------------------------------------------------------------------
    "Pas assez de cas validés pour proposer un recalibrage.":
        ("Not enough validated cases to propose a recalibration.", "لا توجد حالات مُصادَق عليها كافية لاقتراح إعادة معايرة."),
    "Profil inconnu.": ("Unknown profile.", "ملف تعريف غير معروف."),
    "Proposition de recalibrage introuvable.":
        ("Recalibration proposal not found.", "اقتراح إعادة المعايرة غير موجود."),
    # ---- sauvegardes ---------------------------------------------------------------------------
    "Archive trop volumineuse.": ("Archive too large.", "الأرشيف كبير جدًا."),
    "Nom de sauvegarde invalide.": ("Invalid backup name.", "اسم النسخة الاحتياطية غير صالح."),
    "Sauvegarde introuvable.": ("Backup not found.", "النسخة الاحتياطية غير موجودة."),
    "Ce fichier n'est pas une archive ZIP valide.": ("This file is not a valid ZIP archive.", "هذا الملف ليس أرشيف ZIP صالحًا."),
    "Cette sauvegarde vient d'une version plus récente de l'application.":
        ("This backup comes from a newer version of the application.", "هذه النسخة الاحتياطية صادرة عن إصدار أحدث من التطبيق."),
    "L'archive contient des fichiers inattendus.":
        ("The archive contains unexpected files.", "يحتوي الأرشيف على ملفات غير متوقعة."),
    "L'archive est endommagée.": ("The archive is damaged.", "الأرشيف تالف."),
    "L'archive est incomplète (manifeste ou base manquants).":
        ("The archive is incomplete (manifest or database missing).", "الأرشيف ناقص (البيان أو قاعدة البيانات مفقودة)."),
    "L'archive est trop volumineuse.": ("The archive is too large.", "الأرشيف كبير جدًا."),
    "La base de données de l'archive est corrompue.":
        ("The archive's database is corrupted.", "قاعدة بيانات الأرشيف تالفة."),
    "La base de données de l'archive est incomplète.":
        ("The archive's database is incomplete.", "قاعدة بيانات الأرشيف ناقصة."),
    "Restauration en cours. Réessayez dans un instant.":
        ("Restore in progress. Please try again in a moment.", "الاستعادة جارية. أعد المحاولة بعد لحظات."),
    # ---- système et sécurité -------------------------------------------------------------------
    "L'application est déjà installée.": ("The application is already installed.", "التطبيق مُثبَّت مسبقًا."),
    "Erreur interne du serveur. Consultez le journal technique.":
        ("Internal server error. Check the technical log.", "خطأ داخلي في الخادم. راجع السجل التقني."),
    "Interface non construite : lancez `npm run build` dans application/frontend.":
        ("Interface not built: run `npm run build` in application/frontend.",
         "الواجهة غير مبنية: نفّذ `npm run build` في application/frontend."),
    "Ressource introuvable.": ("Resource not found.", "المورد غير موجود."),
    "Compte désactivé.": ("Account disabled.", "الحساب مُعطَّل."),
    "Le mot de passe doit contenir au moins 10 caractères, avec des lettres et des chiffres.":
        ("The password must contain at least 10 characters, including letters and digits.",
         "يجب أن تتكون كلمة المرور من 10 أحرف على الأقل، وأن تتضمن حروفًا وأرقامًا."),
    "Origine refusée.": ("Origin refused.", "المصدر مرفوض."),
    "Réservé aux administrateurs.": ("Administrators only.", "مخصص للمسؤولين فقط."),
    "Session absente.": ("No session.", "لا توجد جلسة."),
    "Session expirée.": ("Session expired.", "انتهت صلاحية الجلسة."),
    "Trop de tentatives. Réessayez dans quelques minutes.":
        ("Too many attempts. Try again in a few minutes.", "محاولات كثيرة جدًا. أعد المحاولة بعد بضع دقائق."),
}

# Messages construits avec une valeur variable : (motif, gabarit anglais, gabarit arabe).
MODELES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"^Rapport de coût non calibré pour ce modèle \(disponibles : (.+)\)\.$"),
     "Cost ratio not calibrated for this model (available: {0}).", "نسبة التكلفة غير معايَرة لهذا النموذج (المتاح: {0})."),
    (re.compile(r"^Moteur d'IA indisponible : chargement en cours$"),
     "AI engine unavailable: loading in progress", "محرك الذكاء الاصطناعي غير متاح: التحميل جارٍ"),
    (re.compile(r"^Moteur d'IA indisponible : (.+)$"),
     "AI engine unavailable: {0}", "محرك الذكاء الاصطناعي غير متاح: {0}"),
]


def langue(request: Request) -> str:
    lg = (request.headers.get("x-langue") or "fr").lower()[:2]
    return lg if lg in LANGUES else "fr"


def traduire(texte: str, lg: str) -> str:
    if lg == "fr" or not isinstance(texte, str):
        return texte
    i = LANGUES.index(lg) - 1
    if texte in MESSAGES:
        return MESSAGES[texte][i]
    for motif, *gabarits in MODELES:
        m = motif.match(texte)
        if m:
            return gabarits[i].format(*m.groups())
    return texte


def traduire_detail(detail, lg: str):
    """Traduit le champ `detail` d'une erreur : texte simple ou objet {code, message, ...}."""
    if isinstance(detail, str):
        return traduire(detail, lg)
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return {**detail, "message": traduire(detail["message"], lg)}
    return detail
