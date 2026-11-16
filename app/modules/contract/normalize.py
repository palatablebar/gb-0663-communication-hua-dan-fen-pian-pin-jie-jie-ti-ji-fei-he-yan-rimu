from datetime import datetime,timezone
import unicodedata
from app.errors import RuleError
from app.reasons import SENTINELS

def instant(value):
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.tzinfo is None:raise ValueError()
        return d.astimezone(timezone.utc)
    except (ValueError,TypeError):raise RuleError('TIME','时间必须带偏移')

def sequence(value):
    s=unicodedata.normalize('NFKC',value).strip()
    if s in SENTINELS:raise RuleError('MISSING','分片序号缺失')
    if not s.isascii() or not s.isdecimal() or int(s)<1 or int(s)>100000:raise RuleError('NUMBER','分片序号应为正整数')
    return int(s)
