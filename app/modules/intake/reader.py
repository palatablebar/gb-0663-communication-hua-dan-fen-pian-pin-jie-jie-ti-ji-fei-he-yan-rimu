import csv,io
from app.config import MAX_BYTES,MAX_ROWS
from app.errors import RuleError
COLUMNS=['subscriber','session','sequence','start','end','zone']
def read(raw):
    if len(raw)>MAX_BYTES:raise RuleError('LIMIT','话单超过2MB')
    for encoding in ('utf-8-sig','gb18030'):
        try:text=raw.decode(encoding);break
        except UnicodeDecodeError:continue
    else:raise RuleError('ENCODING','编码无法识别')
    if not text:return {'rows':[],'issues':[],'blank':0,'input':0,'state':'EMPTY_FILE','encoding':encoding,'headers':0}
    reader=csv.reader(io.StringIO(text,newline=''),strict=True)
    try:header=next(reader)
    except (StopIteration,csv.Error):raise RuleError('HEADER','缺少话单表头')
    if header!=COLUMNS:raise RuleError('HEADER','话单字段应为六列')
    rows=[];issues=[];blank=0;total=0;headers=0
    try:
        for fields in reader:
            total+=1
            if total>MAX_ROWS:raise RuleError('LIMIT','最多接收10000条话单')
            if not fields or all(not x.strip() for x in fields):blank+=1;continue
            if fields==header:headers+=1;total-=1;continue
            if len(fields)!=6:issues.append({'line':reader.line_num,'code':'COLUMN_COUNT','raw':fields});continue
            rows.append(dict(zip(COLUMNS,fields),line=reader.line_num))
    except csv.Error:raise RuleError('TRUNCATED','话单末尾不完整')
    return {'rows':rows,'issues':issues,'blank':blank,'input':total,'state':'READY' if rows or issues else ('BLANK_ROWS' if blank else 'HEADER_ONLY'),'encoding':encoding,'headers':headers}
