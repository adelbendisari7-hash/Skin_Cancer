"""Schémas d'entrée / sortie de l'API (validation automatique par Pydantic)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "medecin"]
Sexe = Literal["male", "female", "unknown"]


class Installation(BaseModel):
    identifiant: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    nom_complet: str = Field(min_length=2, max_length=128)
    mot_de_passe: str
    nom_etablissement: str = Field(min_length=2, max_length=128)


class Connexion(BaseModel):
    identifiant: str
    mot_de_passe: str


class ChangementMotDePasse(BaseModel):
    ancien: str
    nouveau: str


class UtilisateurSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    identifiant: str
    nom_complet: str
    role: Role
    actif: bool
    cree_le: datetime
    derniere_connexion: datetime | None


class UtilisateurCreation(BaseModel):
    identifiant: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    nom_complet: str = Field(min_length=2, max_length=128)
    role: Role = "medecin"
    mot_de_passe: str


class UtilisateurMaj(BaseModel):
    nom_complet: str | None = Field(default=None, min_length=2, max_length=128)
    role: Role | None = None
    actif: bool | None = None
    mot_de_passe: str | None = None


class PatientEntree(BaseModel):
    reference_externe: str | None = Field(default=None, max_length=64)
    annee_naissance: int | None = Field(default=None, ge=1900, le=2100)
    sexe: Sexe = "unknown"
    notes: str | None = Field(default=None, max_length=2000)


class PatientSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    reference_externe: str | None
    annee_naissance: int | None
    sexe: Sexe
    notes: str | None
    cree_le: datetime
    nb_analyses: int = 0
    derniere_analyse: datetime | None = None
    dernier_statut: str | None = None


class AnalyseSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    uid: str
    patient_id: int
    patient_code: str
    auteur: str
    cree_le: datetime
    age: float | None
    sexe: str
    localisation: str
    modele: str
    version_modele: str
    profil: str
    rapport_cout: int
    seuil_melanome: float
    probabilites: dict[str, float]
    decision: str
    p_melanome: float
    ensemble_conforme: list[str]
    traite: bool
    statut: str
    niveau: str
    titre: str
    message: str
    avertissements: list[dict | str]
    duree_ms: int
    revue: str
    diagnostic_final: str | None
    commentaire: str | None
    relecteur: str | None
    revue_le: datetime | None
    histologie: bool = False
    lesion_id: int | None = None
    lesion_numero: int | None = None
    lesion_nom: str | None = None
    abcd: dict | None = None
    score_hors_sujet: float | None = None
    hors_sujet_force: bool = False
    evolution: dict | None = None
    calibration: str = "origine"


class Revue(BaseModel):
    revue: Literal["confirmee", "corrigee"]
    diagnostic_final: str | None = None
    commentaire: str | None = Field(default=None, max_length=2000)
    histologie: bool = False


class EtSi(BaseModel):
    variable: Literal["age", "localisation"]
    valeurs: list | None = None


class Parametres(BaseModel):
    nom_etablissement: str | None = Field(default=None, min_length=2, max_length=128)
    rapport_cout_defaut: int | None = None
    champ_dermoscope_mm: float | None = Field(default=None, ge=0, le=60)   # 0 = inconnu


class LesionSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    numero: int
    nom: str | None
    localisation: str
    cree_le: datetime
    notes: str | None
    nb_analyses: int = 0
    derniere_analyse: datetime | None = None
    dernier_niveau: str | None = None
    derniere_image: int | None = None          # id de la dernière analyse (vignette)
    evolution_notable: bool = False


class LesionMaj(BaseModel):
    nom: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)


class PropositionRecalibrage(BaseModel):
    profil: Literal["complet", "sans_contexte"] = "complet"
    histologie_seulement: bool = False
