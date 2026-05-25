#!/usr/bin/env python3
"""
Wrapper for cron-jobber. Kjør med:
  cron-alarm.py "Beskrivelse" kommando arg1 arg2 ...

Sender epost til k@vikebo.com via Resend (gjennom Docker-containeren) hvis kommandoen feiler.
"""
import os, sys, subprocess, json, socket
from datetime import datetime

VARSLE_TIL = "k@vikebo.com"
CONTAINER  = "drivstoffpriser-drivstoffpriser-1"

def send_epost(emne, kropp):
    py_script = f"""
import os, sys
try:
    import resend
    resend.api_key = os.environ.get('RESEND_API_KEY', '')
    if not resend.api_key:
        print('RESEND_API_KEY ikke satt', file=sys.stderr)
        sys.exit(1)
    resend.Emails.send({{
        'from': 'Drivstoffprisene <noreply@ksalo.no>',
        'to': ['{VARSLE_TIL}'],
        'subject': {json.dumps(emne)},
        'text': {json.dumps(kropp)},
    }})
    print('Epost sendt OK')
except Exception as e:
    print(f'Feil: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
    result = subprocess.run(
        ['docker', 'exec', CONTAINER, 'python3', '-c', py_script],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode != 0:
        print(f"Epost-sending feilet: {result.stderr}", file=sys.stderr)
    else:
        print(result.stdout.strip())

if len(sys.argv) < 3:
    print(f"Bruk: {sys.argv[0]} 'Beskrivelse' kommando [arg ...]")
    sys.exit(1)

beskrivelse = sys.argv[1]
kommando    = sys.argv[2:]
tidspunkt   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
host        = socket.gethostname()

result = subprocess.run(kommando, capture_output=True, text=True)

if result.returncode != 0:
    stdout_tail = result.stdout[-2000:].strip() if result.stdout.strip() else '(ingen output)'
    stderr_tail = result.stderr[-2000:].strip() if result.stderr.strip() else '(ingen output)'
    kropp = f"""Cron-jobb feilet på {host}
Tidspunkt:  {tidspunkt}
Jobb:       {beskrivelse}
Kommando:   {' '.join(kommando)}
Exit-kode:  {result.returncode}

--- STDOUT ---
{stdout_tail}

--- STDERR ---
{stderr_tail}
"""
    send_epost(f"[drivstoffpriser] ALARM: {beskrivelse} feilet", kropp)
    print(kropp, file=sys.stderr)
    sys.exit(result.returncode)
else:
    if result.stdout:
        print(result.stdout, end='')
