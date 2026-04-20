"""Tester for OCR-hjelpere."""

from routes_api import _ocr_korriger_med_forrige, _ocr_stasjon_id_fra_statistikk


def test_ocr_korrigerer_1_til_7_mot_forrige_pris():
    resultat = {'bensin': 16.19, 'diesel': 20.29}
    kontekst = {'forrige_priser': {'bensin': 16.79, 'diesel': 20.29}}

    korrigert = _ocr_korriger_med_forrige(resultat, kontekst)

    assert korrigert['bensin'] == 16.79
    assert korrigert['diesel'] == 20.29


def test_ocr_korrigerer_ikke_naar_swap_fortsatt_er_langt_unna():
    resultat = {'bensin': 16.19}
    kontekst = {'forrige_priser': {'bensin': 18.49}}

    korrigert = _ocr_korriger_med_forrige(resultat, kontekst)

    assert korrigert['bensin'] == 16.19


def test_ocr_statistikk_henter_stasjon_id_fra_lagret_fasit():
    data = {}
    lagret = {'stasjon_id': 1765, 'bensin': 16.79}

    assert _ocr_stasjon_id_fra_statistikk(data, lagret) == 1765


def test_ocr_statistikk_henter_stasjon_id_fra_ocr_resultat():
    data = {'claude_resultat': {'_stasjon_id': 1765, 'bensin': 16.79}}

    assert _ocr_stasjon_id_fra_statistikk(data, None) == 1765


def test_ocr_statistikk_prioriterer_eksplisitt_stasjon_id():
    data = {'stasjon_id': '42'}
    lagret = {'stasjon_id': 1765}

    assert _ocr_stasjon_id_fra_statistikk(data, lagret) == 42
