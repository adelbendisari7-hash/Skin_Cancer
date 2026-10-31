"""Base de données locale (SQLite via SQLAlchemy 2).

Principe de minimisation : aucun nom de patient n'est stocké, seulement un code pseudonyme,
l'année de naissance et le sexe. Chaque analyse conserve la version exacte du modèle utilisé.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event,
                        func, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.types import TypeDecorator

from . import config


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class HorodatageUTC(TypeDecorator):
    """Date-heure stockée en UTC et relue avec son fuseau.

    SQLite ne conserve pas le fuseau : sans ce type, les dates relues seraient « naïves » et ne
    pourraient ni être comparées aux dates courantes ni affichées à la bonne heure locale.
    """
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Base(DeclarativeBase):
    pass


class Utilisateur(Base):
    __tablename__ = "utilisateurs"
    id: Mapped[int] = mapped_column(primary_key=True)
    identifiant: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nom_complet: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="medecin")         # admin | medecin
    mot_de_passe: Mapped[str] = mapped_column(String(256))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC(), default=maintenant)
    derniere_connexion: Mapped[datetime | None] = mapped_column(HorodatageUTC(), nullable=True)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)     # pseudonyme, ex. P-2026-0001
    reference_externe: Mapped[str | None] = mapped_column(String(64), nullable=True)  # n° de dossier local
    annee_naissance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sexe: Mapped[str] = mapped_column(String(8), default="unknown")            # male | female | unknown
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC(), default=maintenant)
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True)
    analyses: Mapped[list["Analyse"]] = relationship(back_populates="patient", order_by="Analyse.cree_le.desc()")
    lesions: Mapped[list["Lesion"]] = relationship(back_populates="patient", order_by="Lesion.numero")


class Lesion(Base):
    """Une lésion suivie chez un patient : ses analyses successives forment sa chronologie (critère E)."""
    __tablename__ = "lesions"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)                                # 1, 2, 3… par patient
    nom: Mapped[str | None] = mapped_column(String(64), nullable=True)         # libellé libre facultatif
    localisation: Mapped[str] = mapped_column(String(32))
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC(), default=maintenant)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient: Mapped[Patient] = relationship(back_populates="lesions")
    analyses: Mapped[list["Analyse"]] = relationship(back_populates="lesion", order_by="Analyse.cree_le")


class Analyse(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True)     # nom des fichiers image
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    auteur_id: Mapped[int] = mapped_column(ForeignKey("utilisateurs.id"))
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC(), default=maintenant, index=True)
    # entrées
    age: Mapped[float | None] = mapped_column(Float, nullable=True)
    sexe: Mapped[str] = mapped_column(String(8))
    localisation: Mapped[str] = mapped_column(String(32))
    nom_fichier_original: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # modèle et sortie
    modele: Mapped[str] = mapped_column(String(64))
    version_modele: Mapped[str] = mapped_column(String(16))
    profil: Mapped[str] = mapped_column(String(16))
    rapport_cout: Mapped[int] = mapped_column(Integer)
    seuil_melanome: Mapped[float] = mapped_column(Float)
    probabilites: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(8))
    p_melanome: Mapped[float] = mapped_column(Float)
    ensemble_conforme: Mapped[list] = mapped_column(JSON)
    traite: Mapped[bool] = mapped_column(Boolean)
    statut: Mapped[str] = mapped_column(String(32), index=True)
    niveau: Mapped[str] = mapped_column(String(16))
    titre: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    avertissements: Mapped[list] = mapped_column(JSON, default=list)
    duree_ms: Mapped[int] = mapped_column(Integer)
    # revue par le médecin
    revue: Mapped[str] = mapped_column(String(16), default="en_attente", index=True)   # en_attente | confirmee | corrigee
    diagnostic_final: Mapped[str | None] = mapped_column(String(8), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    revue_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True)
    revue_le: Mapped[datetime | None] = mapped_column(HorodatageUTC(), nullable=True)
    histologie: Mapped[bool] = mapped_column(Boolean, default=False)          # diagnostic confirmé par histologie
    # version 2
    lesion_id: Mapped[int | None] = mapped_column(ForeignKey("lesions.id"), nullable=True, index=True)
    abcd: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score_hors_sujet: Mapped[float | None] = mapped_column(Float, nullable=True)
    hors_sujet_force: Mapped[bool] = mapped_column(Boolean, default=False)    # « analyser quand même »
    evolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calibration: Mapped[str] = mapped_column(String(24), default="origine")

    patient: Mapped[Patient] = relationship(back_populates="analyses")
    lesion: Mapped[Lesion | None] = relationship(back_populates="analyses")
    auteur: Mapped[Utilisateur] = relationship(foreign_keys=[auteur_id])
    relecteur: Mapped[Utilisateur | None] = relationship(foreign_keys=[revue_par_id])


class Journal(Base):
    """Journal d'audit : qui a fait quoi, quand (connexion, analyse, export, administration)."""
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    le: Mapped[datetime] = mapped_column(HorodatageUTC(), default=maintenant, index=True)
    utilisateur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    objet: Mapped[str | None] = mapped_column(String(48), nullable=True)
    objet_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    utilisateur: Mapped[Utilisateur | None] = relationship()


class Calibration(Base):
    """Recalibrage local des seuils (proposition puis activation par un administrateur)."""
    __tablename__ = "calibrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC(), default=maintenant)
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"), nullable=True)
    modele: Mapped[str] = mapped_column(String(64))
    version_modele: Mapped[str] = mapped_column(String(16))
    profil: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    applique_le: Mapped[datetime | None] = mapped_column(HorodatageUTC(), nullable=True)
    parametres: Mapped[dict] = mapped_column(JSON)         # thresholds, conformal_q, sources par classe
    resume: Mapped[dict] = mapped_column(JSON)             # effectifs, couvertures estimées avant / après
    auteur: Mapped[Utilisateur | None] = relationship()


class Parametre(Base):
    __tablename__ = "parametres"
    cle: Mapped[str] = mapped_column(String(48), primary_key=True)
    valeur: Mapped[str] = mapped_column(Text)


PARAMETRES_DEFAUT = {"nom_etablissement": "Cabinet de dermatologie", "rapport_cout_defaut": "10",
                     "champ_dermoscope_mm": "", "schema_version": "2"}
SCHEMA_VERSION = 2

config.DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(conn, _):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _migrer() -> list[str]:
    """Ajoute les colonnes manquantes (base créée par une version antérieure). Renvoie les ajouts."""
    ajouts = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existantes = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info('{table.name}')")}
            for col in table.columns:
                if col.name in existantes:
                    continue
                typ = col.type.compile(dialect=engine.dialect)
                defaut = ""
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    v = col.default.arg
                    defaut = f" DEFAULT {int(v)}" if isinstance(v, bool) else f" DEFAULT '{v}'"
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {typ}{defaut}')
                ajouts.append(f"{table.name}.{col.name}")
    with SessionLocal() as s:
        # analyses antérieures sans lésion : une lésion par analyse (on ne devine pas les regroupements)
        for a in s.scalars(select(Analyse).where(Analyse.lesion_id.is_(None)).order_by(Analyse.cree_le)).all():
            n = (s.scalar(select(func.max(Lesion.numero)).where(Lesion.patient_id == a.patient_id)) or 0) + 1
            les = Lesion(patient_id=a.patient_id, numero=n, localisation=a.localisation, cree_le=a.cree_le)
            s.add(les)
            s.flush()
            a.lesion_id = les.id
        # avertissements de la version 1 (phrases) → codes
        for a in s.scalars(select(Analyse)).all():
            if a.avertissements and any(isinstance(w, str) for w in a.avertissements):
                a.avertissements = [{"code": "texte", "texte": w} if isinstance(w, str) else w for w in a.avertissements]
        s.commit()
    return ajouts


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrer()
    with SessionLocal() as s:
        for k, v in PARAMETRES_DEFAUT.items():
            if s.get(Parametre, k) is None:
                s.add(Parametre(cle=k, valeur=v))
        s.merge(Parametre(cle="schema_version", valeur=str(SCHEMA_VERSION)))
        s.commit()


def get_db():
    with SessionLocal() as s:
        yield s


def parametre(s, cle: str) -> str:
    p = s.get(Parametre, cle)
    return p.valeur if p else PARAMETRES_DEFAUT[cle]


def journaliser(s, utilisateur_id: int | None, action: str, objet: str | None = None,
                objet_id: str | int | None = None, details: dict | None = None) -> None:
    s.add(Journal(utilisateur_id=utilisateur_id, action=action, objet=objet,
                  objet_id=None if objet_id is None else str(objet_id), details=details))
