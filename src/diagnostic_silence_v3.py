"""Mélanomes classés bénins sans renvoi : v2 contre v3 sur la validation et la calibration HAM (réglage croisé, test jamais utilisé).

Usage : python -m src.diagnostic_silence_v3
"""
import numpy as np
from src import config as C
from src.evaluer_v3 import ensemble, P, PROFILS
from src.donnees_v3 import get_split_v3
from src.data import get_split
from src.decision import tune_mel_threshold, decide
from src.conformal import Conformal, abstain_rule
ham, v3df = get_split(), get_split_v3()
def silencieux(tune_v, tune_c, ev):
    seuil = tune_mel_threshold(P(tune_v), tune_v.y.to_numpy(), 10)[0]
    cf = Conformal("mondrian", C.ALPHA).fit(P(tune_c), tune_c.y.to_numpy())
    p, y = P(ev), ev.y.to_numpy(); pred = decide(p, seuil); tr = abstain_rule(cf.sets(p), pred)
    mel = y == C.MEL
    return seuil, int(mel.sum()), int((mel & tr & (pred != C.MEL)).sum()), round(float((pred[mel] == C.MEL).mean()), 3), round(float(1 - tr.mean()), 3)
for pr in PROFILS:
    v2 = ensemble(*PROFILS[pr]["v2"], ham); v3 = ensemble(*PROFILS[pr]["v3"], v3df)
    h3 = v3[v3.source == "HAM10000"]
    # évaluation sur calib HAM, seuil réglé sur val, conforme réglé sur val (pas sur l'évalué)
    print(pr, "v2 eval=calibHAM", silencieux(v2[v2.split=="val"], v2[v2.split=="val"], v2[v2.split=="calib"]))
    print(pr, "v3(comb) eval=calibHAM", silencieux(v3[v3.split=="val"], v3[(v3.split=="val")], h3[h3.split=="calib"]))
    print(pr, "v3(HAM) eval=calibHAM", silencieux(h3[h3.split=="val"], h3[h3.split=="val"], h3[h3.split=="calib"]))
    print(pr, "v2 eval=valHAM", silencieux(v2[v2.split=="calib"], v2[v2.split=="calib"], v2[v2.split=="val"]))
    print(pr, "v3(comb) eval=valHAM", silencieux(v3[v3.split=="calib"], v3[v3.split=="calib"], h3[h3.split=="val"]))
    ev = h3[h3.split.isin(["val","calib"])]; pm = P(ev)[:, C.MEL]; mel = ev.y.to_numpy()==C.MEL
    pv2 = P(v2[v2.split.isin(["val","calib"])])[:, C.MEL]
    print("  p_mel des mélanomes HAM val+calib : v3 quantiles", np.round(np.quantile(pm[mel],[.02,.05,.1]),4), " v2", np.round(np.quantile(pv2[mel],[.02,.05,.1]),4))
