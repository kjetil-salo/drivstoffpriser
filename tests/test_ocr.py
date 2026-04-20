"""Tester for OCR-hjelpere."""

from routes_api import (
    _ocr_bor_prove_gemini_fallback,
    _ocr_gemini_er_bedre,
    _ocr_korriger_med_forrige,
    _ocr_stasjon_id_fra_statistikk,
)


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


def test_ocr_prover_gemini_fallback_naar_haiku_mangler_vanlig_rad():
    resultat = {'bensin': None, 'diesel': 21.39, 'bensin98': None, 'diesel_avgiftsfri': None}
    kontekst = {'tillatte': {'bensin': True, 'diesel': True, 'bensin98': True, 'diesel_avgiftsfri': True}}

    assert _ocr_bor_prove_gemini_fallback(resultat, kontekst)


def test_ocr_velger_gemini_naar_den_dekker_flere_vanlige_rader():
    haiku = {'bensin': None, 'diesel': 21.39, 'bensin98': None, 'diesel_avgiftsfri': None}
    gemini = {'bensin': 18.19, 'diesel': 21.39, 'bensin98': None, 'diesel_avgiftsfri': None}
    kontekst = {'tillatte': {'bensin': True, 'diesel': True, 'bensin98': True, 'diesel_avgiftsfri': True}}

    assert _ocr_gemini_er_bedre(gemini, haiku, kontekst)


def test_ocr_prover_gemini_fallback_for_tre_rader_med_98_og_diesel():
    resultat = {'bensin': 18.19, 'diesel': 20.69, 'bensin98': 21.39, 'diesel_avgiftsfri': None}
    kontekst = {'tillatte': {'bensin': True, 'diesel': True, 'bensin98': True, 'diesel_avgiftsfri': True}}

    assert _ocr_bor_prove_gemini_fallback(resultat, kontekst)


def test_ocr_velger_gemini_ved_samme_dekning_paa_98_skilt():
    haiku = {'bensin': 18.19, 'diesel': 20.69, 'bensin98': 21.39, 'diesel_avgiftsfri': None}
    gemini = {'bensin': 18.19, 'diesel': 20.39, 'bensin98': 20.69, 'diesel_avgiftsfri': None}
    kontekst = {'tillatte': {'bensin': True, 'diesel': True, 'bensin98': True, 'diesel_avgiftsfri': True}}

    assert _ocr_gemini_er_bedre(gemini, haiku, kontekst)
