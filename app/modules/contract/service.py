from app.modules.contract.normalize import instant,sequence
from app.reasons import SENTINELS
from app.errors import RuleError

def normalize(rows,tariffs):
    valid=[];issues=[];zones={t['zone'] for t in tariffs}
    for row in rows:
        try:
            if any(row[k].strip() in SENTINELS for k in ('subscriber','session','sequence','start','end','zone')):raise RuleError('MISSING','话单必填字段缺失')
            seq=sequence(row['sequence']);a=instant(row['start']);b=instant(row['end'])
            if b<=a:raise RuleError('REVERSED','分片结束不晚于开始')
            if (b-a).total_seconds()>86400:raise RuleError('TOO_LONG','单片时长超过24小时')
            if row['zone'].strip() not in zones:raise RuleError('ZONE','资费区域未登记')
            valid.append(dict(row,subscriber=row['subscriber'].strip(),session=row['session'].strip(),sequence=seq,start=a.isoformat(),end=b.isoformat(),zone=row['zone'].strip()))
        except RuleError as e:issues.append({'line':row['line'],'code':e.code,'raw':row})
    return {'rows':valid,'issues':issues,'tariffs':tariffs,'unit':'CNY'}
