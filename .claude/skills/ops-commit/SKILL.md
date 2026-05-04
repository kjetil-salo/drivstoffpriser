---
name: commit
description: Lag git-commit for drivstoffpriser — auto-bump SW cache ved frontend-endringer, norsk commit-melding
allowed-tools: Bash, Read, Edit
user-invocable: true
---

Lag en git-commit for drivstoffpriser.no.

## Kontekst

- Nåværende git-status: !`git status`
- Endringer (staged + unstaged): !`git diff HEAD`
- Siste commits: !`git log --oneline -5`
- Gjeldende SW cache-versjon: !`grep CACHE_VERSION public/sw.js | head -1`

## Fremgangsmåte

### Steg 1: Sjekk om SW cache må bumpes

Se på endrede filer fra git-status og diff.

**SW cache MÅ bumpes hvis noen av disse er endret:**
- `public/js/*.js`
- `public/css/*.css`
- `templates/*.html`
- `public/manifest.json`
- `public/sw.js` (men bare hvis endringen *ikke* er en ren cache-bump)

**SW cache skal IKKE bumpes hvis:**
- Kun backend-filer er endret (`.py`, `db.py`, `routes_*.py`)
- Kun tester er endret (`tests/`)
- Kun konfig-filer er endret
- `public/sw.js` allerede er endret (unngå dobbel-bump)

Hvis SW cache må bumpes:
1. Les gjeldende versjon fra `public/sw.js` (f.eks. `v90`)
2. Inkrementer (→ `v91`)
3. Oppdater med Edit
4. Stage filen: `git add public/sw.js`

### Steg 2: Stage og commit

Stage relevante filer (unngå `.env`, credentials, store binærfiler).

Lag commit-melding på **norsk** etter dette mønsteret:
- Kort, imperativ setning som beskriver *hva* som er gjort
- Ingen "Co-Authored-By", ingen emoji med mindre brukeren ba om det
- Eksempler: `Fiks: SW cache bumpes automatisk ved commit`, `Legg til: søkefunksjon i stasjonsliste`

Bruk HEREDOC for commit-meldingen for å unngå quoting-problemer:
```bash
git commit -m "$(cat <<'EOF'
Commit-melding her
EOF
)"
```

### Steg 3: Påminn om push

Etter vellykket commit, si:
> "Husk å pushe: `git push`"

## Regler

- Aldri bruk `--no-verify`
- Aldri legg til `Co-Authored-By: Claude`
- Commit-melding alltid på norsk
- Ikke commit `.env`, nøkler eller credentials
- SW cache-bump er kritisk — uten det sitter brukere på gammel JS/CSS
