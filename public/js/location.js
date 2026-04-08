/**
 * To-stegs geolokasjon (forenklet fra enkel-ao).
 * Steg 1: Rask nettverksposisjon for å vekke GPS-hardware.
 * Steg 2: Høy-nøyaktighets watchPosition, stopper ved ≤50m eller etter 10s.
 */
export function hentPosisjon(onSuccess, onError, onStatus) {
    if (!navigator.geolocation) {
        onError('Nettleseren støtter ikke geolokasjon.');
        return;
    }

    let bestPosition = null;
    let finished = false;
    let watchId = null;

    const timeoutId = setTimeout(() => {
        if (!finished) finish();
    }, 10000);

    function finish(nektet = false) {
        if (finished) return;
        finished = true;
        if (watchId !== null) navigator.geolocation.clearWatch(watchId);
        clearTimeout(timeoutId);

        if (!bestPosition) {
            onError({ nektet });
            return;
        }
        onSuccess(bestPosition);
    }

    function startWatch() {
        watchId = navigator.geolocation.watchPosition(
            (pos) => {
                const { latitude: lat, longitude: lon, accuracy } = pos.coords;
                if (!bestPosition || accuracy < bestPosition.accuracy) {
                    bestPosition = { lat, lon, accuracy };
                }
                onStatus(`Henter posisjon … ±${Math.round(accuracy)} m`);
                if (accuracy <= 50) finish();
            },
            (err) => {
                if (!bestPosition) {
                    finished = true;
                    clearTimeout(timeoutId);
                    onError({ nektet: err.code === 1 });
                } else {
                    finish();
                }
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 }
        );
    }

    navigator.geolocation.getCurrentPosition(
        (pos) => {
            if (finished) return;
            const { latitude: lat, longitude: lon, accuracy } = pos.coords;
            bestPosition = { lat, lon, accuracy };
            onStatus(`Henter posisjon … ±${Math.round(accuracy)} m`);
            startWatch();
        },
        (err) => {
            if (!finished) {
                if (err.code === 1) {
                    finished = true;
                    clearTimeout(timeoutId);
                    onError({ nektet: true });
                } else {
                    startWatch();
                }
            }
        },
        { enableHighAccuracy: false, maximumAge: 0, timeout: 5000 }
    );
}

export function startFollowWatch(onPosisjon, onError) {
    if (!navigator.geolocation) {
        onError('Nettleseren støtter ikke geolokasjon.');
        return () => {};
    }
    const id = navigator.geolocation.watchPosition(
        (pos) => {
            const { latitude: lat, longitude: lon, accuracy } = pos.coords;
            onPosisjon({ lat, lon, accuracy });
        },
        (err) => onError({ nektet: err.code === 1 }),
        { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 }
    );
    return () => navigator.geolocation.clearWatch(id);
}
