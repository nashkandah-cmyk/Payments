import urllib.request, json, sys
from datetime import datetime, timedelta

# Firebase config
PROJECT_ID = "students-payments-management"
API_KEY    = "AIzaSyCngrtjF93_ol1THE31gFVe4UDEfqrNliA"
DOC_URL    = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/app/data?key={API_KEY}"

DAYS_EN  = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday']
DAYS_ICS = ['SU','MO','TU','WE','TH','FR','SA']

# ===== تحويل هيكل Firestore لـ Python dict عادي =====
def parse_value(v):
    if 'stringValue'  in v: return v['stringValue']
    if 'integerValue' in v: return int(v['integerValue'])
    if 'doubleValue'  in v: return float(v['doubleValue'])
    if 'booleanValue' in v: return v['booleanValue']
    if 'nullValue'    in v: return None
    if 'mapValue'     in v:
        return {k: parse_value(f) for k, f in v['mapValue'].get('fields', {}).items()}
    if 'arrayValue'   in v:
        return [parse_value(i) for i in v['arrayValue'].get('values', [])]
    return None

def fetch_db():
    with urllib.request.urlopen(DOC_URL) as r:
        raw = json.loads(r.read())
    fields = raw.get('fields', {})
    return {k: parse_value(v) for k, v in fields.items()}

# ===== باقي الكود بدون تغيير =====
def fmt_dt(date_str, time_str):
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return dt.strftime("%Y%m%dT%H%M%S")

def next_weekday(day_key):
    today = datetime.now()
    target = DAYS_EN.index(day_key)
    days_ahead = (target - today.weekday() - 1) % 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def ics_escape(s):
    return str(s).replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def generate_ics(db):
    lines = [
        "BEGIN:VCALENDAR","VERSION:2.0",
        "PRODID:-//English Master//Schedule//AR",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
        "X-WR-CALNAME:English Master",
        "X-WR-TIMEZONE:Asia/Amman",
    ]

    sessions = db.get('schedule', {}).get('sessions', {})
    groups   = db.get('groups', {})
    students = db.get('students', {})
    exams    = db.get('exams', {})

    print(f"📊 sessions={len(sessions)}, groups={len(groups)}, students={len(students)}, exams={len(exams)}")

    def get_name(eid, etype):
        src = groups if etype == 'group' else students
        return src.get(eid, {}).get('name', 'Unknown')

    uid_c = [0]
    def uid():
        uid_c[0] += 1
        return f"em-{uid_c[0]}@englishmaster"

    for sid, s in sessions.items():
        if s.get('status') == 'hold': continue
        day   = s.get('day', 'sunday')
        time  = s.get('time', '09:00')
        name  = get_name(s.get('entityId',''), s.get('entityType','group'))
        recur = s.get('recurrence', 'weekly')
        byday = DAYS_ICS[DAYS_EN.index(day)] if day in DAYS_EN else 'MO'
        date  = s.get('date') if recur == 'once' else next_weekday(day)
        if not date: continue
        h, m = map(int, time.split(':'))
        dt_start = datetime.strptime(date, "%Y-%m-%d").replace(hour=h, minute=m)
        dt_end   = dt_start + timedelta(hours=1)
        lines += [
            "BEGIN:VEVENT", f"UID:{uid()}",
            f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{ics_escape(name)}",
            f"DESCRIPTION:{ics_escape(s.get('entityType',''))}",
        ]
        if recur == 'weekly':
            lines.append(f"RRULE:FREQ=WEEKLY;BYDAY={byday}")
        elif recur == 'multiday':
            extra = s.get('extraDays', [])
            all_days = [byday] + [DAYS_ICS[DAYS_EN.index(d)] for d in extra if d in DAYS_EN]
            lines.append(f"RRULE:FREQ=WEEKLY;BYDAY={','.join(all_days)}")
        lines += ["BEGIN:VALARM","TRIGGER:-PT30M","ACTION:DISPLAY",
                  f"DESCRIPTION:حصة {ics_escape(name)} بعد 30 دقيقة","END:VALARM","END:VEVENT"]

    for eid, e in exams.items():
        date = e.get('date','')
        time = e.get('time','10:00')
        if not date: continue
        h, m = map(int, time.split(':'))
        dt_start = datetime.strptime(date, "%Y-%m-%d").replace(hour=h, minute=m)
        dt_end   = dt_start + timedelta(hours=1, minutes=30)
        title = e.get('title','امتحان')
        name  = get_name(e.get('entityId',''), e.get('entityType','group'))
        lines += [
            "BEGIN:VEVENT", f"UID:{uid()}",
            f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:📝 {ics_escape(title)} — {ics_escape(name)}",
            f"DESCRIPTION:{ics_escape(e.get('note',''))}",
            "BEGIN:VALARM","TRIGGER:-PT60M","ACTION:DISPLAY",
            f"DESCRIPTION:امتحان {ics_escape(name)} بعد ساعة","END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

if __name__ == "__main__":
    try:
        db  = fetch_db()
        ics = generate_ics(db)
        with open("calendar.ics", "w", encoding="utf-8") as f:
            f.write(ics)
        print(f"✓ calendar.ics generated ({ics.count('BEGIN:VEVENT')} events)")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
