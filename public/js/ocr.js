/**
 * OCR-modul for prisgjenkjenning fra kamerabilder.
 * Strategi: Tesseract.js (klient-side) først, Claude API (backend) som fallback.
 * Kun tilgjengelig for admin/moderator.
 */

const ocrWrap = document.getElementById('sheet-ocr');
const ocrInput = document.getElementById('sheet-ocr-input');
const ocrPreview = document.getElementById('sheet-ocr-preview');
const ocrImg = document.getElementById('sheet-ocr-img');
const ocrStatus = document.getElementById('sheet-ocr-status');

let tesseractWorker = null;
let tesseractLoading = false;
const OCR_MAX_BREDDE = 2048;
const OCR_JPEG_KVALITET = 0.9;

// Statistikk for siste OCR-analyse (sendes til backend ved lagring)
let sisteOcrStat = null;

export function initOcr(onPriserGjenkjent, getKontekst = null) {
    ocrInput.addEventListener('change', async (e) => {
        const fil = e.target.files?.[0];
        if (!fil) return;

        sisteOcrStat = { tidspunkt: new Date().toISOString() };
        const kontekstInit = typeof getKontekst === 'function' ? getKontekst() : null;
        if (kontekstInit?.stasjon_id) sisteOcrStat.stasjon_id = kontekstInit.stasjon_id;

        // Vis preview
        const url = URL.createObjectURL(fil);
        ocrImg.src = url;
        ocrPreview.removeAttribute('hidden');
        visOcrStatus('Forbereder bilde ...', false);

        try {
            // Skaler ned bildet for ytelse
            const nedskalert = await skalerBilde(fil, OCR_MAX_BREDDE);

            visOcrStatus('Analyserer med AI ...', false);
            let priser = null;
            let kilde = 'ai';
            const kontekst = typeof getKontekst === 'function' ? getKontekst() : null;
            const cStart = performance.now();
            try {
                priser = await gjenkjennMedBackend(nedskalert, kontekst);
                kilde = priser._modell || 'ai';
                if (!sisteOcrStat.stasjon_id && priser._stasjon_id) {
                    sisteOcrStat.stasjon_id = priser._stasjon_id;
                }
                sisteOcrStat.claude_ms = Math.round(performance.now() - cStart);
                sisteOcrStat.claude_resultat = priser;
                sisteOcrStat.claude_ok = !!(priser && harGyldigePriser(priser));
            } catch (err) {
                sisteOcrStat.claude_ms = Math.round(performance.now() - cStart);
                sisteOcrStat.claude_feil = err.message;
                sisteOcrStat.claude_ok = false;
                loggOcrStat(sisteOcrStat);
                visOcrStatus('Kunne ikke gjenkjenne priser. Tast inn manuelt.', true);
                console.error('Backend OCR feilet:', err);
                return;
            }

            sisteOcrStat.kilde = kilde;

            if (priser && harGyldigePriser(priser)) {
                const kildeTekst = kilde === 'tesseract' ? 'lokal OCR' : `AI${modellHint(kilde)}`;
                visOcrStatus(`Priser gjenkjent (${kildeTekst})! Sjekk og lagre.`, false, true);
                loggOcrStat(sisteOcrStat).then(id => { if (id) sisteOcrStat._db_id = id; });
                onPriserGjenkjent(priser);
            } else {
                loggOcrStat(sisteOcrStat);
                visOcrStatus('Fant ingen priser i bildet. Tast inn manuelt.', true);
            }
        } catch (err) {
            visOcrStatus('Feil ved bildeanalyse. Prøv igjen.', true);
            console.error('OCR-feil:', err);
        } finally {
            ocrInput.value = '';
        }
    });
}

/** Kalles fra station-sheet når pris faktisk lagres, for å logge endelig resultat. */
export function loggOcrVedLagring(lagretPriser) {
    if (!sisteOcrStat) return;
    const dbId = sisteOcrStat._db_id;
    if (dbId) {
        fetch(`/api/ocr-statistikk/${dbId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lagret: lagretPriser }),
        }).catch(() => {});
    } else {
        sisteOcrStat.lagret = lagretPriser;
        loggOcrStat(sisteOcrStat);
    }
    sisteOcrStat = null;
}

/** Kalles når brukeren bekrefter ett OCR-felt med OK-knappen. */
export function loggOcrVedBekreftelse(stasjonId, type, verdi) {
    if (!sisteOcrStat || !type || verdi == null) return;
    const stat = { ...sisteOcrStat };
    if (!stat.stasjon_id && stasjonId) stat.stasjon_id = stasjonId;
    stat.lagret = {
        stasjon_id: stasjonId,
        _bekreftet_felt: [type],
        [type]: verdi,
    };
    loggOcrStat(stat);
}

/**
 * Gjenkjenn priser fra en bildefil. Gjenbrukbar pipeline (Tesseract → Claude fallback).
 * Returnerer { priser, kilde, stat } eller kaster feil.
 */
export async function gjenkjennPriserFraBilde(bildeFile, onStatus, kontekst = null) {
    const stat = { tidspunkt: new Date().toISOString() };

    if (onStatus) onStatus('Forbereder bilde …');
    const nedskalert = await skalerBilde(bildeFile, OCR_MAX_BREDDE);

    if (onStatus) onStatus('Analyserer med AI …');
    let priser = null;
    let kilde = 'ai';
    const cStart = performance.now();
    try {
        priser = await gjenkjennMedBackend(nedskalert, kontekst);
        kilde = priser._modell || 'ai';
        if (priser._stasjon_id) {
            stat.stasjon_id = priser._stasjon_id;
        }
        stat.claude_ms = Math.round(performance.now() - cStart);
        stat.claude_resultat = priser;
        stat.claude_ok = !!(priser && harGyldigePriser(priser));
    } catch (err) {
        stat.claude_ms = Math.round(performance.now() - cStart);
        stat.claude_feil = err.message;
        stat.claude_ok = false;
        loggOcrStat(stat);
        throw new Error('Kunne ikke gjenkjenne priser');
    }

    stat.kilde = kilde;
    loggOcrStat(stat);

    return {
        priser: priser && harGyldigePriser(priser) ? priser : null,
        kilde,
        stat,
    };
}

export function visOcrForRolle() {
    const r = window.__roller || [];
    const harKameraTilgang = window.__erAdmin || r.includes('moderator') || r.includes('kamera');
    if (harKameraTilgang) {
        ocrWrap.removeAttribute('hidden');
    }
}

export function skjulOcrPreview() {
    ocrPreview.setAttribute('hidden', '');
    ocrStatus.setAttribute('hidden', '');
}

function visOcrStatus(tekst, erFeil, erOk = false) {
    ocrStatus.textContent = tekst;
    ocrStatus.removeAttribute('hidden');
    if (erFeil) {
        ocrStatus.className = 'ocr-status ocr-status-feil';
    } else if (erOk) {
        ocrStatus.className = 'ocr-status ocr-status-ok';
    } else {
        ocrStatus.className = 'ocr-status ocr-status-loading';
    }
}

function harGyldigePriser(priser) {
    return priser.bensin != null || priser.diesel != null ||
           priser.bensin98 != null || priser.diesel_avgiftsfri != null;
}

/** Logg OCR-statistikk til backend. Returnerer Promise med rad-ID. */
function loggOcrStat(stat) {
    return fetch('/api/ocr-statistikk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(stat),
    }).then(r => r.ok ? r.json() : null).then(d => d?.id ?? null).catch(() => null);
}

/** Skaler bilde ned via canvas for å spare båndbredde og OCR-tid. */
function skalerBilde(fil, maxBredde) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            let { width, height } = img;
            if (width > maxBredde) {
                height = Math.round(height * (maxBredde / width));
                width = maxBredde;
            }
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, width, height);
            canvas.toBlob((blob) => {
                if (blob) resolve(blob);
                else reject(new Error('Canvas toBlob feilet'));
            }, 'image/jpeg', OCR_JPEG_KVALITET);
        };
        img.onerror = () => reject(new Error('Kunne ikke laste bilde'));
        img.src = URL.createObjectURL(fil);
    });
}

/** Prøv Tesseract.js (lazy-loaded fra CDN). Returnerer priser + råtekst. */
async function gjenkjennMedTesseract(bildeBlob) {
    if (!tesseractWorker) {
        await lastTesseract();
    }

    const { data } = await tesseractWorker.recognize(bildeBlob);
    return { priser: parserOcrTekst(data.text), raatekst: data.text };
}

async function lastTesseract() {
    if (tesseractLoading) {
        while (tesseractLoading) await new Promise(r => setTimeout(r, 100));
        return;
    }
    tesseractLoading = true;
    try {
        const { createWorker } = await import('https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.esm.min.js');
        tesseractWorker = await createWorker('nor', 1, {
            workerPath: 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/worker.min.js',
            corePath: 'https://cdn.jsdelivr.net/npm/tesseract.js-core@5/tesseract-core.wasm.js',
        });
    } finally {
        tesseractLoading = false;
    }
}

/** Parser OCR-tekst og finn drivstoffpriser. */
function parserOcrTekst(tekst) {
    const linjer = tekst.split('\n').map(l => l.trim()).filter(Boolean);
    const resultat = { bensin: null, diesel: null, bensin98: null, diesel_avgiftsfri: null };

    for (let i = 0; i < linjer.length; i++) {
        const linje = linjer[i].toLowerCase();
        const pris = finnPrisILinje(linjer[i]);

        if (pris == null) continue;
        if (pris < 15 || pris > 30) continue;

        // Sjekk spesifikke termer før generelle
        if (linje.includes('98')) {
            resultat.bensin98 = resultat.bensin98 || pris;
        } else if (/\bfd\b/.test(linje) || linje.includes('farget') || linje.includes('fargen') || linje.includes('avgiftsfri') || linje.includes('avg.fri') || linje.includes('avgfri') || linje.includes('anlegg')) {
            // "FD", "Farget diesel", "Avgiftsfri", "Anleggsdiesel"
            resultat.diesel_avgiftsfri = resultat.diesel_avgiftsfri || pris;
        } else if (/\bhvo\b/.test(linje) || linje.includes('blank') || linje.includes('biodiesel') || linje.includes('bio diesel')) {
            // "HVO", "Blank diesel", "Biodiesel" → vanlig diesel
            resultat.diesel = resultat.diesel || pris;
        } else if (/\bd\b/.test(linje) || linje.includes('diesel')) {
            // "D", "Diesel"
            resultat.diesel = resultat.diesel || pris;
        } else if (linje.includes('95') || linje.includes('bensin') || linje.includes('blyfri')) {
            resultat.bensin = resultat.bensin || pris;
        }
    }

    if (!harGyldigePriser(resultat)) {
        const allePriser = [];
        for (const linje of linjer) {
            const p = finnPrisILinje(linje);
            if (p != null && p >= 15 && p <= 30) allePriser.push(p);
        }
        const unike = dedup(allePriser);
        if (unike.length >= 1) resultat.bensin = unike[0];
        if (unike.length >= 2) resultat.diesel = unike[1];
        if (unike.length >= 3) resultat.bensin98 = unike[2];
    }

    return resultat;
}

function finnPrisILinje(linje) {
    const match = linje.match(/(\d{1,2})[.,](\d{2})/);
    if (match) {
        return parseFloat(match[1] + '.' + match[2]);
    }
    const match4 = linje.match(/\b(\d{4})\b/);
    if (match4) {
        const v = parseInt(match4[1]);
        if (v >= 1500 && v <= 3000) {
            return v / 100;
        }
    }
    return null;
}

function dedup(priser) {
    const resultat = [];
    for (const p of priser) {
        if (!resultat.some(r => Math.abs(r - p) < 0.05)) {
            resultat.push(p);
        }
    }
    return resultat;
}

/** Send bilde til backend for AI-analyse. Returnerer priser + _modell. */
async function gjenkjennMedBackend(bildeBlob, kontekst = null) {
    const formData = new FormData();
    formData.append('bilde', bildeBlob, 'pristavle.jpg');
    if (kontekst?.stasjon_id) {
        formData.append('stasjon_id', String(kontekst.stasjon_id));
    }
    if (kontekst?.forventet_kjede) {
        formData.append('forventet_kjede', kontekst.forventet_kjede);
    }

    const resp = await fetch('/api/gjenkjenn-priser', {
        method: 'POST',
        body: formData,
    });

    if (resp.status === 403) {
        throw new Error('Ikke tilgang');
    }
    if (resp.status === 429) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || 'For mange forsøk');
    }
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || 'Feil fra server');
    }

    return resp.json();
}

function modellHint(modell) {
    if (modell === 'gemini') return ' [G]';
    if (modell === 'haiku') return ' [H]';
    return ' [AI]';
}
