import logging
import threading
import time

logger = logging.getLogger('drivstoff')

_oppdatering_aktiv = False
_lock = threading.Lock()
_OPPDATER_INTERVALL = 86400  # 24 timer


def start_bakgrunnsoppdatering():
    """Starter en bakgrunnstråd som oppdaterer stasjoner fra OSM daglig."""
    t = threading.Thread(target=_bakgrunnsloop, daemon=True)
    t.start()
    logger.info('Bakgrunnsoppdatering av stasjoner startet (hver 24. time)')


def _bakgrunnsloop():
    """Kjører seed daglig. Venter 60s ved oppstart for å la serveren komme i gang."""
    time.sleep(60)
    while True:
        try:
            from seed_stasjoner import hent_alle_stasjoner_norge
            antall = hent_alle_stasjoner_norge()
            logger.info(f'Bakgrunnsoppdatering ferdig: {antall} stasjoner')
        except Exception as e:
            logger.warning(f'Bakgrunnsoppdatering feilet: {e}')
        time.sleep(_OPPDATER_INTERVALL)
