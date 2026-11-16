from fastapi.templating import Jinja2Templates
from app.config import ROOT
from app import store
PAGES=[('intake','话单接收'),('contract','资费契约'),('model','分片拼接'),('calculate','计费重算'),('quarantine','坏单隔离'),('reconcile','账单勾稽'),('batches','批次复核')]
templates=Jinja2Templates(directory=str(ROOT/'app/templates'))
def page(request,slug):
    return templates.TemplateResponse(request=request,name=slug+'.html',context={'bundle':store.latest(),'pages':PAGES,'slug':slug,'title':dict(PAGES)[slug],'history':store.history()})
