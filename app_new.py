"""
app.py — 量化交易儀表板
"""
import json, os, time, logging, threading
from datetime import datetime
from pathlib import Path
import pytz
import streamlit as st

logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="量化交易儀表板", page_icon="📊", layout="wide")
st.markdown("""<style>
html,body,[class*="css"]{font-family:"PingFang TC","Microsoft JhengHei",sans-serif;}
.rec-badge{display:inline-block;padding:5px 14px;border-radius:20px;font-size:1.1rem;font-weight:700;margin:8px 0;}
.rec-buy{background:#0d3d2e;color:#4ade80;border:1px solid #16a34a;}
.rec-sell{background:#3d0d0d;color:#f87171;border:1px solid #dc2626;}
.rec-hold{background:#3d3400;color:#fbbf24;border:1px solid #d97706;}
.rec-none{background:#2a2a2a;color:#9ca3af;border:1px solid #4b5563;}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_db():
    try:
        from sqlalchemy import Column,DateTime,Integer,String,Text,create_engine
        from sqlalchemy.orm import DeclarativeBase,sessionmaker
        url = os.environ.get("DATABASE_URL","sqlite:///quant_dashboard.db")
        if url.startswith("postgres://"): url=url.replace("postgres://","postgresql://",1)
        class Base(DeclarativeBase): pass
        class SR(Base):
            __tablename__="strategy_results"
            id=Column(Integer,primary_key=True,autoincrement=True)
            strategy_id=Column(String(100),nullable=False,index=True)
            strategy_name=Column(String(200),nullable=False)
            recommendation=Column(Text,nullable=True)
            signal=Column(String(20),nullable=True)
            details=Column(Text,nullable=True)
            chart_path=Column(String(500),nullable=True)
            status=Column(String(20),nullable=False,default="pending")
            error_message=Column(Text,nullable=True)
            updated_at=Column(DateTime,nullable=True)
            created_at=Column(DateTime,default=datetime.utcnow)
        e=create_engine(url)
        Base.metadata.create_all(e)
        return {"S":sessionmaker(bind=e),"M":SR}
    except Exception as ex:
        st.warning(f"DB init failed: {ex}"); return None

def get_latest(d,sid):
    if not d: return None
    try:
        with d["S"]() as s: return s.query(d["M"]).filter(d["M"].strategy_id==sid).order_by(d["M"].updated_at.desc()).first()
    except: return None

def save_running(d,sid,name):
    if not d: return None
    try:
        with d["S"]() as s:
            r=d["M"](strategy_id=sid,strategy_name=name,status="running",updated_at=datetime.utcnow())
            s.add(r); s.commit(); s.refresh(r); return r.id
    except: return None

def save_ok(d,rid,rec,sig,chart,details=None):
    if not d or not rid: return
    try:
        with d["S"]() as s:
            r=s.get(d["M"],rid)
            if r: r.recommendation=rec;r.signal=sig;r.chart_path=chart;r.details=details;r.status="success";r.updated_at=datetime.utcnow();s.commit()
    except: pass

def save_err(d,rid,msg):
    if not d or not rid: return
    try:
        with d["S"]() as s:
            r=s.get(d["M"],rid)
            if r: r.status="error";r.error_message=msg;r.updated_at=datetime.utcnow();s.commit()
    except: pass

@st.cache_data(ttl=60)
def load_strategies():
    try:
        p=Path(__file__).parent/"strategies_config.json"
        return json.loads(p.read_text(encoding="utf-8")).get("strategies",[]) if p.exists() else []
    except: return []

def fmt_time(dt):
    if not dt: return "尚未執行"
    try: return dt.replace(tzinfo=pytz.utc).astimezone(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
    except: return str(dt)

def sig_css(s):
    s=(s or "").upper()
    if s in("BUY","LONG"): return "rec-buy"
    if s in("SELL","SHORT"): return "rec-sell"
    if s=="HOLD": return "rec-hold"
    return "rec-none"

def parse_sig(rec):
    r=rec.upper()
    if any(k in r for k in("做多","買入","BUY","LONG","多")): return "BUY"
    if any(k in r for k in("做空","賣出","SELL","SHORT","空")): return "SELL"
    return "HOLD"

def trigger(strategy,db):
    sid=strategy["id"]; sname=strategy["name"]
    script=str(Path(__file__).parent/strategy["script"])
    st.session_state[f"running_{sid}"]=True
    rid=save_running(db,sid,sname)
    def _run():
        import subprocess,sys,json as j
        odir=Path(__file__).parent/"outputs"/sid; odir.mkdir(parents=True,exist_ok=True)
        env=os.environ.copy(); env["STRATEGY_OUTPUT_DIR"]=str(odir)
        try:
            r=subprocess.run([sys.executable,script],env=env,capture_output=True,text=True,timeout=300)
            if r.returncode!=0: raise RuntimeError(r.stderr or "failed")
            rec=(odir/"recommendation.txt").read_text(encoding="utf-8").strip() if (odir/"recommendation.txt").exists() else "（無推薦）"
            chart=next((str(odir/x) for x in("chart.png","chart.jpg") if (odir/x).exists()),None)
            sig=""
            try: sig=j.loads((odir/"result.json").read_text()).get("signal","")
            except: pass
            if not sig: sig=parse_sig(rec)
            save_ok(db,rid,rec,sig,chart)
        except Exception as ex: save_err(db,rid,str(ex))
        finally: st.session_state[f"running_{sid}"]=False
    threading.Thread(target=_run,daemon=True).start()

# ── UI ──────────────────────────────────────────────────────────────────────
now=datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f'<div style="background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);border-radius:12px;padding:20px 28px;margin-bottom:24px;color:white;"><h1 style="margin:0;font-size:1.8rem;letter-spacing:2px;">📊 量化交易儀表板</h1><p style="margin:4px 0 0;opacity:.65;font-size:.9rem;">Quantitative Trading Monitor · {now}</p></div>',unsafe_allow_html=True)

db=get_db(); strategies=load_strategies()
cl,cr=st.columns([6,2])
with cr:
    if st.button("🔄 更新全部策略",use_container_width=True,type="primary"):
        for s in strategies:
            if s.get("enabled",True): trigger(s,db)
        st.toast("已觸發所有策略更新"); time.sleep(0.5); st.rerun()

if not strategies:
    st.info("尚未設定策略，請編輯 strategies_config.json 後重新部署。"); st.stop()

for row in [strategies[i:i+3] for i in range(0,len(strategies),3)]:
    for col,s in zip(st.columns(len(row)),row):
        sid=s["id"]; is_run=st.session_state.get(f"running_{sid}",False); lat=get_latest(db,sid)
        with col:
            with st.container(border=True):
                st.markdown(f"### {s['name']}")
                if is_run: st.markdown("🔵 **執行中…**")
                elif lat:
                    dot={"success":"🟢","error":"🔴","running":"🔵"}.get(lat.status,"⚪")
                    st.markdown(f"{dot} &nbsp;<small style='color:#6b7280'>更新：{fmt_time(lat.updated_at)}</small>",unsafe_allow_html=True)
                if lat and lat.status=="success":
                    rec=lat.recommendation or "—"; sig=lat.signal or parse_sig(rec)
                    st.markdown(f'<div class="rec-badge {sig_css(sig)}">{rec}</div>',unsafe_allow_html=True)
                    if lat.details:
                        with st.expander("詳細"): st.write(lat.details)
                elif lat and lat.status=="error": st.error(lat.error_message)
                else: st.markdown('<div class="rec-badge rec-none">尚無資料</div>',unsafe_allow_html=True)
                chart=lat.chart_path if lat else None
                if chart and Path(chart).exists():
                    try:
                        from PIL import Image; st.image(Image.open(chart),use_container_width=True)
                    except: st.caption("圖片載入失敗")
                else:
                    st.markdown("<div style='height:110px;display:flex;align-items:center;justify-content:center;color:#6b7280;font-size:.85rem;border:1px dashed #374151;border-radius:8px;margin:6px 0'>📈 執行後顯示損益圖</div>",unsafe_allow_html=True)
                if st.button("⏳ 執行中..." if is_run else "🔄 更新此策略",key=f"btn_{sid}",disabled=is_run,use_container_width=True):
                    trigger(s,db); st.toast(f"已觸發「{s['name']}」更新"); time.sleep(0.3); st.rerun()

if any(st.session_state.get(f"running_{s['id']}",False) for s in strategies):
    time.sleep(5); st.rerun()
