export async function hentStasjoner(lat, lon) {
    const resp = await fetch(`/api/stasjoner?lat=${lat}&lon=${lon}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (data.utenfor) throw Object.assign(new Error('utenfor'), { utenfor: true });
        throw new Error('Feil ved henting av stasjoner');
    }
    const data = await resp.json();
    return data.stasjoner || [];
}

export async function oppdaterPris(stasjonId, bensin, diesel) {
    const resp = await fetch('/api/pris', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stasjon_id: stasjonId, bensin, diesel }),
    });
    if (resp.status === 401) return { status: 401 };
    if (!resp.ok) throw new Error('Feil ved lagring av pris');
    return resp.json();
}
