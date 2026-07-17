"""
Relatório diário do lançamento WICI3 no Discord.

Roda de manhã (GitHub Actions), lê as mesmas planilhas da dash pública e posta o
fechamento do dia anterior: vendas (tráfego/orgânico/total), investimento, CPA e
o pace necessário até o evento (15/08).

Fonte de verdade das VENDAS = aba MÉTRICAS (o Meta sub-reporta). Investimento vem
das abas Malu/Hire Meta (Cost em US$ → R$ pela cotação). Metas vêm da aba Metas.

Rodar local sem enviar:  python report.py --dry-run
"""
import requests, csv, io, os, sys, json, math
from datetime import datetime
import pytz

FONTE_ID = '1DnIF0UDbdpZ7wV09dEjIkYP8G4H47Tzi7PXOKES5gkI'   # Malu Meta / Hire Meta / Metas
METR_ID  = '1V4WEVo5A0TYZ5_1Ez4rb_RHXwd6ExneizW38hzS8YZE'   # aba MÉTRICAS (vendas)
METR_GID = '1075509571'
WEBHOOK  = os.environ.get('DISCORD_WEBHOOK', '')
BR_TZ    = pytz.timezone('America/Sao_Paulo')

EVENT      = datetime(2026, 8, 15)   # data do evento — base do pace
COTACAO    = 5.16                    # US$ → R$ (mesma da dash)
# Metas (default; sobrescritas pela aba Metas quando presentes)
META_TOTAL = 1800
META_TRAF  = 1170
META_ORG   = 630
META_INV   = 87750.0
CPA_META   = 71.0
DASH_URL   = 'https://cardo-jpg.github.io/wici3-dash/'

OK, WARN, FAIL = '✅', '⚠️', '❌'
TICK, CASH, CHART, CAL = '\U0001F39F', '\U0001F4B0', '\U0001F4CA', '\U0001F4C5'
PURPLE, GREEN, PIN, LINK, DART = '\U0001F7E3', '\U0001F7E2', '\U0001F4CC', '\U0001F517', '\U0001F3AF'
UP, MAG = '\U0001F4C8', '\U0001F50D'
SEP = '`' + '─' * 34 + '`'


def fetch(sid, gid=None, sheet=None):
    q = f'gid={gid}' if gid else 'sheet=' + requests.utils.quote(sheet)
    url = f'https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&{q}'
    r = requests.get(url, timeout=20); r.encoding = 'utf-8'
    return list(csv.reader(io.StringIO(r.text)))


def n(s):
    """Número no formato BR: 'R$ 1.055,59' / '0,68' / '82,00%' → float."""
    s = str(s or '').strip().replace('R$', '').replace('%', '').replace(' ', '')
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def i(s):
    return int(round(n(s)))


def dm(d):
    """DD/MM/AAAA → DD/MM."""
    p = str(d or '').strip().split('/')
    return f"{p[0].zfill(2)}/{p[1].zfill(2)}" if len(p) >= 2 else str(d or '').strip()


def fmt_r(v):
    return ('R$ ' + f"{v:,.2f}").replace(',', '§').replace('.', ',').replace('§', '.')


def fmt_r0(v):
    return ('R$ ' + f"{round(v):,}").replace(',', '.')


def load_metas():
    """Lê a aba Metas (rótulo na col 0, valor na col 1) e sobrescreve os defaults."""
    global META_TRAF, META_INV, CPA_META, META_ORG
    try:
        for row in fetch(FONTE_ID, sheet='Metas'):
            if len(row) < 2:
                continue
            lbl = row[0].strip().lower()
            if 'trafego' in lbl or 'tráfego' in lbl:
                META_TRAF = i(row[1])
            elif lbl == 'investimento':
                META_INV = n(row[1])
            elif lbl == 'cpa':
                CPA_META = n(row[1])
        META_ORG = max(0, META_TOTAL - META_TRAF)
    except Exception as e:
        print('Metas: usando defaults —', e)


def load_vendas():
    """Série (data, org, ads, total) das linhas com dado. Colunas acumuladas."""
    serie = []
    for row in fetch(METR_ID, gid=METR_GID)[1:]:
        if len(row) < 13 or not row[0].strip():
            continue
        org, total = i(row[3]), i(row[12])
        if org > 0 or total > 0:
            serie.append(dict(date=row[0].strip(), dm=dm(row[0]),
                              org=org, ads=i(row[10]) + i(row[11]), total=total))
    return serie


def load_investimento(dm_dia):
    """Investido total (acumulado) e do dia, somando Malu + Hire (US$ → R$)."""
    total = dia = 0.0
    for sheet in ('Malu Meta', 'Hire Meta'):
        for row in fetch(FONTE_ID, sheet=sheet)[1:]:
            if len(row) < 4 or not row[0].strip():
                continue
            cost = n(row[3]) * COTACAO
            total += cost
            if dm(row[0]) == dm_dia:
                dia += cost
    return total, dia


def pace_icon(feito, precisa):
    if precisa <= 0:
        return OK
    return OK if feito >= precisa else (WARN if feito >= precisa * 0.6 else FAIL)


def send(content):
    if '--dry-run' in sys.argv or not WEBHOOK:
        print(content + '\n')
        return
    payload = json.dumps({'content': content}, ensure_ascii=False).encode('utf-8')
    r = requests.post(WEBHOOK, data=payload,
                      headers={'Content-Type': 'application/json; charset=utf-8'}, timeout=10)
    print(f"Discord {r.status_code}")


def main():
    now = datetime.now(BR_TZ)
    load_metas()
    serie = load_vendas()
    if not serie:
        send(f"{WARN} **WICI3** — sem dados de vendas na planilha ainda.")
        return

    cur = serie[-1]
    prev = serie[-2] if len(serie) >= 2 else dict(org=0, ads=0, total=0)
    d_org = max(0, cur['org'] - prev['org'])
    d_ads = max(0, cur['ads'] - prev['ads'])
    d_tot = max(0, cur['total'] - prev['total'])

    inv_tot, inv_dia = load_investimento(cur['dm'])
    cpa_dia = inv_dia / d_ads if d_ads else 0
    ic_cpa = OK if (cpa_dia and cpa_dia <= CPA_META) else (WARN if cpa_dia else OK)

    dias = max(1, (EVENT - now.replace(tzinfo=None)).days)
    need_traf = math.ceil(max(0, META_TRAF - cur['ads']) / dias)
    need_org  = math.ceil(max(0, META_ORG  - cur['org']) / dias)
    need_tot  = math.ceil(max(0, META_TOTAL - cur['total']) / dias)
    disp = max(0, META_INV - inv_tot)
    need_inv = disp / dias
    pct = f"{cur['total'] / META_TOTAL * 100:.1f}".replace('.', ',')

    # ── MSG 1 — Fechamento do dia ──────────────────────────────────────────────
    msg1 = '\n'.join([
        f"{TICK} **DIÁRIO DE BORDO — WICI3**",
        "**Workshop Intensivo de Carreira Internacional**",
        f"{CAL} **{cur['date']}**  ·  fechamento do dia",
        "",
        SEP,
        f"{CHART} **VENDAS DO DIA — {cur['dm']}**",
        SEP,
        f"{TICK} **Total no dia: {d_tot}**",
        f"  {PURPLE} Tráfego (Ads): **{d_ads}**",
        f"  {GREEN} Orgânico: **{d_org}**",
        f"{CASH} **Investido no dia:** {fmt_r(inv_dia)}",
        f"{CHART} **CPA Tráfego (dia):** {fmt_r(cpa_dia)}  (meta {fmt_r(CPA_META)}) {ic_cpa}",
        "",
        f"{TICK} **Acumulado: {cur['total']}/{META_TOTAL}  ({pct}%)**",
        f"  {PURPLE} Tráfego: **{cur['ads']}**/{META_TRAF}   {GREEN} Orgânico: **{cur['org']}**/{META_ORG}",
    ])

    # ── MSG 2 — Pace até o evento ──────────────────────────────────────────────
    msg2 = '\n'.join([
        SEP,
        f"{UP} **PACE ATÉ O EVENTO (15/08) — faltam {dias} dias**",
        SEP,
        f"{PURPLE} **Tráfego:** {cur['ads']}/{META_TRAF} · precisa **{need_traf}/dia** (dia: {d_ads}) {pace_icon(d_ads, need_traf)}",
        f"{GREEN} **Orgânico:** {cur['org']}/{META_ORG} · precisa **{need_org}/dia** (dia: {d_org}) {pace_icon(d_org, need_org)}",
        f"{TICK} **Total:** {cur['total']}/{META_TOTAL} · precisa **{need_tot}/dia** (dia: {d_tot}) {pace_icon(d_tot, need_tot)}",
        "",
        f"{CASH} **Investimento:** {fmt_r0(inv_tot)} / {fmt_r0(META_INV)}",
        f"  Disponível: **{fmt_r0(disp)}**  ·  usar **{fmt_r0(need_inv)}/dia** pra gastar tudo",
        "",
        f"{LINK} [Dashboard ao vivo]({DASH_URL})",
    ])

    # ── MSG 3 — Anotações do dia (template pra equipe preencher no canal) ───────
    msg3 = '\n'.join([
        SEP,
        f"{PIN} **OBSERVAÇÃO DO DIA**",
        SEP,
        "> ",
        "",
        SEP,
        f"{DART} **DECISÕES TOMADAS**",
        SEP,
        "> ",
        "",
        SEP,
        f"{MAG} **AÇÕES PARA AMANHÃ**",
        SEP,
        "> ",
    ])

    send(msg1)
    send(msg2)
    send(msg3)


if __name__ == '__main__':
    main()
