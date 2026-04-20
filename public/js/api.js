import { getInnstillinger } from './settings.js';

export async function hentStasjoner(lat, lon) {
    const { radius } = getInnstillinger();
    const resp = await fetch(`/api/stasjoner?lat=${lat}&lon=${lon}&radius=${radius}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (data.utenfor) throw Object.assign(new Error('utenfor'), { utenfor: true });
        throw new Error('Feil ved henting av stasjoner');
    }
    const data = await resp.json();
    return data.stasjoner || [];
}

export async function hentTotaltMedPris() {
    const resp = await fetch('/api/totalt-med-pris');
    if (!resp.ok) return null;
    return (await resp.json()).totalt;
}

export async function finnBilligstLangsRute({ fra, til, via, drivstoff, maksAvvikKm }) {
    const resp = await fetch('/api/rutepris', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            fra,
            til,
            via,
            drivstoff,
            maks_avvik_km: maksAvvikKm,
        }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || 'Kunne ikke beregne rute');
    return data;
}

export async function opprettStasjon(navn, kjede, lat, lon) {
    const resp = await fetch('/api/stasjon', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ navn, kjede, lat, lon }),
    });
    const data = await resp.json();
    if (!resp.ok) throw Object.assign(new Error(data.error || 'Feil ved opprettelse'), { status: resp.status, data });
    return data;
}

export async function meldNedlagt(stasjonId) {
    const resp = await fetch('/api/rapporter-nedlagt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId }),
    });
    if (resp.status === 401) return { status: 401 };
    if (!resp.ok) throw new Error('Feil ved rapportering');
    return resp.json();
}

export async function foreslåEndring(stasjonId, foreslattNavn, foreslattKjede, erNedlagt = false, kommentar = null) {
    const resp = await fetch('/api/foreslaa-endring', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, foreslatt_navn: foreslattNavn, foreslatt_kjede: foreslattKjede, er_nedlagt: erNedlagt, kommentar }),
    });
    if (resp.status === 401) return { status: 401 };
    if (!resp.ok) throw new Error('Feil ved innsending');
    return resp.json();
}

export async function settKjede(stasjonId, kjede) {
    const resp = await fetch('/admin/sett-kjede', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, kjede }),
    });
    if (resp.status === 403) return { status: 403 };
    if (!resp.ok) throw new Error('Feil ved oppdatering av kjede');
    return resp.json();
}

export async function endreNavn(stasjonId, navn) {
    const resp = await fetch('/admin/endre-navn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, navn }),
    });
    if (resp.status === 403) return { status: 403 };
    if (!resp.ok) throw new Error('Feil ved oppdatering av navn');
    return resp.json();
}

export async function settDrivstofftyper(stasjonId, typer) {
    const resp = await fetch('/admin/sett-drivstofftyper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, ...typer }),
    });
    if (resp.status === 403) return { status: 403 };
    if (!resp.ok) throw new Error('Feil ved oppdatering av drivstofftyper');
    return resp.json();
}

export async function oppdaterPris(stasjonId, bensin, diesel, bensin98, diesel_avgiftsfri) {
    const resp = await fetch('/api/pris', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, bensin, diesel, bensin98, diesel_avgiftsfri }),
    });
    if (resp.status === 401) return { status: 401 };
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || 'Feil ved lagring av pris');
    }
    return resp.json();
}

export async function bekreftEnPris(stasjonId, type) {
    const resp = await fetch('/api/bekreft-pris', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, type }),
    });
    if (resp.status === 401) return { status: 401 };
    if (!resp.ok) throw new Error('Feil ved bekreftelse');
    return resp.json();
}
