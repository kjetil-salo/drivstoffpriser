"""Auth-ruter: innlogging, registrering, passord-tilbakestilling, invitasjoner."""

import logging
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from db import (antall_brukere, opprett_bruker, finn_bruker, finn_bruker_id,
                opprett_invitasjon, hent_invitasjon, merk_invitasjon_brukt,
                opprett_tilbakestilling, hent_tilbakestilling, merk_tilbakestilling_brukt, oppdater_passord,
                slett_bruker, hent_innstilling, sett_kallenavn,
                sjekk_rate_limit, logg_rate_limit, slett_rate_limit)

logger = logging.getLogger('drivstoff')

auth_bp = Blueprint('auth', __name__)

_EPOST_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _auth_side(tittel, innhold, feil=''):
    feil_html = f'<p class="feil">{feil}</p>' if feil else ''
    return f'''<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{tittel} – Drivstoffpriser</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e5e7eb;
       display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1rem}}
  .kort{{background:#111827;border:1px solid #1f2937;border-radius:12px;
         padding:2rem;width:100%;max-width:380px}}
  h1{{font-size:1.2rem;margin-bottom:1.5rem;color:#f1f5f9}}
  label{{display:block;font-size:0.78rem;color:#94a3b8;margin-bottom:4px}}
  input{{width:100%;background:#1f2937;border:1px solid #374151;border-radius:6px;
         color:#e5e7eb;font-size:1rem;padding:10px 12px;margin-bottom:1rem;outline:none}}
  input:focus{{border-color:#3b82f6}}
  button{{width:100%;background:#3b82f6;border:none;border-radius:6px;color:white;
          font-size:1rem;font-weight:600;padding:12px;cursor:pointer;margin-top:0.5rem}}
  button:hover{{background:#2563eb}}
  .feil{{color:#ef4444;font-size:0.85rem;margin-bottom:1rem}}
  a{{color:#94a3b8;font-size:0.82rem;display:block;text-align:center;margin-top:1rem}}
</style></head><body><div class="kort">
<h1>{tittel}</h1>{feil_html}{innhold}</div></body></html>'''


# ── Innlogging ─────────────────────────────────────

@auth_bp.route('/auth/logg-inn', methods=['GET', 'POST'])
def logg_inn():
    if session.get('bruker_id'):
        return redirect('/')

    ingen_brukere = antall_brukere() == 0

    if request.method == 'POST':
        brukernavn = request.form.get('brukernavn', '').strip()
        passord = request.form.get('passord', '').strip()
        ip = request.remote_addr

        if ingen_brukere:
            if not brukernavn or not passord:
                return _auth_side('Opprett admin', _admin_form(), 'Fyll inn brukernavn og passord.')
            opprett_bruker(brukernavn, generate_password_hash(passord), er_admin=True)
            bruker = finn_bruker(brukernavn)
            session.permanent = True
            session['bruker_id'] = bruker['id']
            return redirect('/')

        if sjekk_rate_limit('innlogging', ip, maks=10, vindu_sekunder=900):
            logger.warning(f'Innlogging blokkert (rate limit): ip={ip} brukernavn={brukernavn}')
            return _auth_side('Logg inn', _login_form(), 'For mange feil forsøk. Prøv igjen om 15 minutter.')

        bruker = finn_bruker(brukernavn)
        if not bruker or not check_password_hash(bruker['passord_hash'], passord):
            logg_rate_limit('innlogging', ip)
            logger.warning(f'Mislykket innlogging: brukernavn={brukernavn} ip={ip}')
            return _auth_side('Logg inn', _login_form(), 'Feil brukernavn eller passord.')

        slett_rate_limit('innlogging', ip)
        logger.info(f'Innlogging OK: brukernavn={brukernavn} ip={ip}')
        session.permanent = True
        session['bruker_id'] = bruker['id']
        return redirect('/')

    if ingen_brukere:
        return _auth_side('Opprett admin', _admin_form())
    return _auth_side('Logg inn', _login_form())


def _login_form():
    return '''<form method="post">
<label>E-post</label><input name="brukernavn" type="email" autofocus autocomplete="username">
<label>Passord</label><input name="passord" type="password" autocomplete="current-password">
<button>Logg inn</button></form>
<a href="/auth/tilbakestill">Glemt passord?</a>
<a href="/registrer">Ny bruker? Registrer deg</a>'''


def _admin_form():
    return '''<p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1rem">
Ingen brukere finnes. Opprett admin-konto.</p>
<form method="post">
<label>E-post</label><input name="brukernavn" type="email" autofocus autocomplete="username">
<label>Passord</label><input name="passord" type="password" autocomplete="new-password">
<button>Opprett admin</button></form>'''


@auth_bp.route('/auth/logg-ut')
def logg_ut():
    session.clear()
    return redirect('/')


# ── Registrering ───────────────────────────────────

@auth_bp.route('/registrer', methods=['GET', 'POST'])
def registrer():
    # Admin kan stoppe registreringer via admin-panel
    if hent_innstilling('registrering_stoppet') == '1':
        return _auth_side('Registrering', '<p style="color:#94a3b8">Registrering er midlertidig stengt.</p><a href="/">&#8592; Tilbake</a>')

    if request.method == 'POST':
        epost = request.form.get('epost', '').strip().lower()
        passord = request.form.get('passord', '').strip()
        ip = request.remote_addr

        if sjekk_rate_limit('registrering', ip, maks=5, vindu_sekunder=3600):
            logger.warning(f'Registrering blokkert (rate limit): ip={ip}')
            return _auth_side('Registrer deg', _registrer_form(), 'For mange registreringer fra din tilkobling. Prøv igjen senere.')

        if not _EPOST_RE.match(epost):
            return _auth_side('Registrer deg', _registrer_form(), 'Ugyldig e-postadresse.')
        if len(passord) < 6:
            return _auth_side('Registrer deg', _registrer_form(), 'Passordet må være minst 6 tegn.')
        if finn_bruker(epost):
            return _auth_side('Registrer deg', _registrer_form(), 'E-postadressen er allerede i bruk.')

        opprett_bruker(epost, generate_password_hash(passord))
        logg_rate_limit('registrering', ip)
        logger.info(f'Ny bruker registrert: epost={epost} ip={ip}')
        bruker = finn_bruker(epost)
        session.permanent = True
        session['bruker_id'] = bruker['id']
        return redirect('/')

    return _auth_side('Registrer deg', _registrer_form())


def _registrer_form():
    return '''<form method="post">
<label>E-post</label><input name="epost" type="email" autofocus autocomplete="email">
<label>Passord</label><input name="passord" type="password" autocomplete="new-password">
<button>Registrer deg</button></form>
<a href="/auth/logg-inn">Har du konto? Logg inn</a>'''


# ── Passord-tilbakestilling ────────────────────────

@auth_bp.route('/auth/tilbakestill', methods=['GET', 'POST'])
def tilbakestill():
    import resend
    if request.method == 'POST':
        epost = request.form.get('epost', '').strip().lower()
        ip = request.remote_addr

        if sjekk_rate_limit('tilbakestilling', ip, maks=3, vindu_sekunder=3600):
            logger.warning(f'Tilbakestilling blokkert (rate limit): ip={ip} epost={epost}')
            # Samme melding som ved suksess — ikke avslør at IP er blokkert
            return _auth_side('Tilbakestill passord',
                '<p style="color:#94a3b8">Hvis e-postadressen finnes i systemet har du nå fått en lenke. Sjekk innboksen.</p>'
                '<a href="/auth/logg-inn">← Tilbake</a>')

        bruker = finn_bruker(epost)
        if bruker:
            token = secrets.token_urlsafe(32)
            utloper = (datetime.utcnow() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
            opprett_tilbakestilling(token, epost, utloper)
            logg_rate_limit('tilbakestilling', ip)
            base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
            lenke = f'{base_url}/auth/nytt-passord?token={token}'
            try:
                resend.Emails.send({
                    'from': 'Drivstoffpriser <noreply@ksalo.no>',
                    'to': epost,
                    'subject': 'Tilbakestill passord – Drivstoffpriser',
                    'html': f'<p>Klikk på lenken for å sette nytt passord (gyldig 1 time):</p>'
                            f'<p><a href="{lenke}">{lenke}</a></p>'
                            f'<p>Hvis du ikke ba om dette kan du ignorere denne e-posten.</p>',
                })
            except Exception as e:
                import logging
                logging.getLogger('drivstoff').error(f'E-postsending feilet: {e}')
        return _auth_side('Tilbakestill passord',
            '<p style="color:#94a3b8">Hvis e-postadressen finnes i systemet har du nå fått en lenke. Sjekk innboksen.</p>'
            '<a href="/auth/logg-inn">← Tilbake</a>')

    return _auth_side('Tilbakestill passord', '''<form method="post">
<label>E-post</label><input name="epost" type="email" autofocus autocomplete="email">
<button>Send tilbakestillingslenke</button></form>
<a href="/auth/logg-inn">← Tilbake</a>''')


@auth_bp.route('/auth/nytt-passord', methods=['GET', 'POST'])
def nytt_passord():
    token = request.args.get('token') or request.form.get('token', '')
    ts = hent_tilbakestilling(token)
    if not ts:
        return _auth_side('Ugyldig lenke', '<p style="color:#94a3b8">Lenken er ugyldig eller utløpt.</p><a href="/auth/logg-inn">← Logg inn</a>')

    if request.method == 'POST':
        passord = request.form.get('passord', '').strip()
        if len(passord) < 6:
            return _auth_side('Nytt passord', _nytt_passord_form(token), 'Passordet må være minst 6 tegn.')
        oppdater_passord(ts['epost'], generate_password_hash(passord))
        merk_tilbakestilling_brukt(token)
        bruker = finn_bruker(ts['epost'])
        if bruker:
            session.permanent = True
            session['bruker_id'] = bruker['id']
        return redirect('/')

    return _auth_side('Nytt passord', _nytt_passord_form(token))


def _nytt_passord_form(token):
    return f'''<form method="post">
<input type="hidden" name="token" value="{token}">
<label>Nytt passord</label><input name="passord" type="password" autofocus autocomplete="new-password">
<button>Sett nytt passord</button></form>'''


# ── Invitasjoner ───────────────────────────────────

@auth_bp.route('/invitasjon', methods=['GET', 'POST'])
def invitasjon():
    token = request.args.get('token') or request.form.get('token', '')
    inv = hent_invitasjon(token)
    if not inv:
        return _auth_side('Ugyldig lenke', '<p style="color:#94a3b8">Lenken er ugyldig eller utløpt.</p><a href="/">← Tilbake</a>')

    if request.method == 'POST':
        brukernavn = request.form.get('brukernavn', '').strip()
        passord = request.form.get('passord', '').strip()
        if not brukernavn or len(passord) < 6:
            return _auth_side('Opprett konto', _invitasjon_form(token), 'Brukernavn må fylles ut og passord må være minst 6 tegn.')
        if finn_bruker(brukernavn):
            return _auth_side('Opprett konto', _invitasjon_form(token), 'Brukernavnet er allerede i bruk.')
        opprett_bruker(brukernavn, generate_password_hash(passord))
        merk_invitasjon_brukt(token)
        bruker = finn_bruker(brukernavn)
        session.permanent = True
        session['bruker_id'] = bruker['id']
        return redirect('/')

    return _auth_side('Opprett konto', _invitasjon_form(token))


@auth_bp.route('/auth/min-konto', methods=['GET', 'POST'])
def min_konto():
    bruker_id = session.get('bruker_id')
    if not bruker_id:
        return redirect('/auth/logg-inn')
    bruker = finn_bruker_id(bruker_id)
    if not bruker:
        session.clear()
        return redirect('/auth/logg-inn')

    melding = ''
    if request.method == 'POST':
        kallenavn = request.form.get('kallenavn', '').strip()
        sett_kallenavn(bruker_id, kallenavn)
        bruker = finn_bruker_id(bruker_id)
        melding = '<p style="color:#22c55e;font-size:0.85rem;margin-bottom:1rem">Kallenavn lagret.</p>'

    kallenavn_verdi = bruker.get('kallenavn') or ''
    return _auth_side('Min konto', f'''
<p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1.5rem">
Innlogget som <strong style="color:#e5e7eb">{bruker["brukernavn"]}</strong></p>
{melding}
<form method="post" style="margin-bottom:1.5rem">
  <label style="display:block;font-size:0.85rem;color:#94a3b8;margin-bottom:4px">Kallenavn (vises i topplister)</label>
  <input name="kallenavn" value="{kallenavn_verdi}" placeholder="Velg et kallenavn …"
    style="width:100%;background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.3);
           border-radius:6px;color:#e5e7eb;font-size:0.92rem;padding:10px 14px;margin-bottom:0.75rem;outline:none">
  <button type="submit" style="width:100%;background:#3b82f6;border:none;border-radius:6px;
    color:white;font-weight:600;font-size:0.9rem;padding:12px;cursor:pointer">Lagre kallenavn</button>
</form>
<a href="/auth/logg-ut" style="display:block;text-align:center;border:1px solid #475569;border-radius:6px;
   color:#94a3b8;font-size:0.85rem;padding:10px;text-decoration:none;margin-bottom:0.75rem">Logg ut</a>
<a href="/auth/slett-meg" style="display:block;text-align:center;border:1px solid #ef4444;border-radius:6px;
   color:#ef4444;font-size:0.85rem;padding:10px;text-decoration:none">Slett min konto</a>
<a href="/" style="display:block;text-align:center;font-size:0.85rem;color:#94a3b8;margin-top:1rem">← Tilbake</a>''')


@auth_bp.route('/auth/slett-meg', methods=['GET', 'POST'])
def slett_meg():
    bruker_id = session.get('bruker_id')
    if not bruker_id:
        return redirect('/auth/logg-inn')
    bruker = finn_bruker_id(bruker_id)
    if not bruker:
        session.clear()
        return redirect('/auth/logg-inn')

    if request.method == 'POST':
        passord = request.form.get('passord', '').strip()
        if not check_password_hash(bruker['passord_hash'], passord):
            return _auth_side('Slett konto', _slett_meg_form(), 'Feil passord.')
        slett_bruker(bruker_id)
        session.clear()
        return _auth_side('Konto slettet',
            '<p style="color:#94a3b8">Kontoen din er nå slettet.</p>'
            '<a href="/">← Til forsiden</a>')

    return _auth_side('Slett konto', _slett_meg_form())


def _slett_meg_form():
    return '''<p style="color:#ef4444;font-size:0.85rem;margin-bottom:1rem">
Dette sletter kontoen din permanent. Handlingen kan ikke angres.</p>
<form method="post">
<label>Bekreft med passordet ditt</label>
<input name="passord" type="password" autofocus autocomplete="current-password">
<button style="background:#ef4444">Slett min konto</button></form>
<a href="/auth/min-konto">← Avbryt</a>'''


def _invitasjon_form(token):
    return f'''<p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1rem">
Du er invitert! Velg brukernavn og passord.</p>
<form method="post">
<input type="hidden" name="token" value="{token}">
<label>Brukernavn</label><input name="brukernavn" autofocus autocomplete="username">
<label>Passord</label><input name="passord" type="password" autocomplete="new-password">
<button>Opprett konto</button></form>'''
