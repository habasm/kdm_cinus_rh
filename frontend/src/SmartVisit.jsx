import {useEffect,useMemo,useState} from 'react'
import WHOHelp from './WHOHelp'

const authHeaders=()=>{try{return {'X-User':JSON.parse(localStorage.getItem('clinical-user')||'{}').username||'admin'}}catch{return {'X-User':'admin'}}}
const api=async(p,o={})=>{
  const r=await fetch('/api'+p,{...o,headers:{...(o.headers||{}),...authHeaders()}}),t=await r.text()
  let d
  try{d=JSON.parse(t)}catch{}
  if(!r.ok)throw new Error(d?.detail||t)
  return d
}
const F=({label,...p})=><label className="field"><span>{label}</span><input {...p}/></label>
const S=({label,options,...p})=><label className="field"><span>{label}</span><select {...p}>{options.map(x=><option key={x[0]} value={x[0]} disabled={x[2]}>{x[1]}</option>)}</select></label>
const blank=()=>({visit_date:new Date().toISOString().slice(0,10),weight:'',height:'',muac:'',edema:false,health_worker:'Clinical Officer',nutrition_result:'normal',referral:'',vitamin_a_dose:'0',deworming_dose:'0',developmental_result:'ndd',development_notes:''})
const ageOf=(a,b)=>{a=new Date(a);b=new Date(b);return(b.getFullYear()-a.getFullYear())*12+b.getMonth()-a.getMonth()-(b.getDate()<a.getDate()?1:0)}
const next=(day,n)=>{const d=new Date(day);d.setDate(d.getDate()+n);return d.toISOString().slice(0,10)}
const daysBetween=(a,b)=>(new Date(a)-new Date(b))/86400000
const zValue=v=>v==null?'--':Number(v).toFixed(2)
const zClass=v=>v==null?'pending':v<-3?'danger':v<-2?'warn':'good'
const zLabel=v=>v==null?'Enter weight and height':v<-3?'Severe':v<-2?'Moderate':'Normal'
const primaryZName=age=>age!=null&&age<24?'WLZ':'WHZ'
const muacStatus=(raw,edema)=>{
  const v=parseFloat(raw)
  if(edema)return {level:'danger',label:'SAM',text:'Oedema present'}
  if(!Number.isFinite(v))return {level:'pending',label:'MUAC',text:'Enter MUAC'}
  if(v<11.5)return {level:'danger',label:'SAM',text:v.toFixed(1)+' cm'}
  if(v<12.5)return {level:'warn',label:'MAM',text:v.toFixed(1)+' cm'}
  return {level:'good',label:'Normal',text:v.toFixed(1)+' cm'}
}
const yearCount=(history,visitDate,field,editing)=>history.filter(x=>x.id!==editing&&x[field]&&new Date(x.visit_date).getFullYear()===new Date(visitDate).getFullYear()).length
const latestDose=(history,field,editing)=>history.filter(x=>x.id!==editing&&x[field]).sort((a,b)=>b.visit_date.localeCompare(a.visit_date))[0]

export default function SmartVisit({children,done}){
  const linked=sessionStorage.getItem('cinus_follow_child')||new URLSearchParams(location.hash.split('?')[1]||'').get('child')
  const initial=children.find(c=>String(c.id)===String(linked))||null
  const [child,setChild]=useState(initial),[q,setQ]=useState(initial?initial.first_name+' '+initial.last_name:''),[f,setF]=useState(blank()),[history,setHistory]=useState([]),[scores,setScores]=useState(null),[editing,setEditing]=useState(null),[msg,setMsg]=useState('Select a child to unlock the form.'),[historyDate,setHistoryDate]=useState(''),[historyPage,setHistoryPage]=useState(1)
  const calculating=msg.startsWith('Calculating WHO z-score')
  const size=4
  const matches=useMemo(()=>q&&!child?children.filter(c=>(c.first_name+' '+c.last_name+' '+c.child_code+' '+(c.phone||'')).toLowerCase().includes(q.toLowerCase())).slice(0,6):[],[q,child,children])
  const age=child?ageOf(child.date_of_birth,f.visit_date):null,va=age>=6&&age<=59,dw=age>=24&&age<=59
  const lastVa=latestDose(history,'vitamin_a_dose',editing),lastDw=latestDose(history,'deworming_dose',editing)
  const vaCount=yearCount(history,f.visit_date,'vitamin_a_dose',editing),dwCount=yearCount(history,f.visit_date,'deworming_dose',editing)
  const vaTooSoon=lastVa&&daysBetween(f.visit_date,lastVa.visit_date)<120,vaLocked=!va||vaTooSoon||vaCount>=2
  const dwTooSoon=lastDw&&daysBetween(f.visit_date,lastDw.visit_date)<365,dwLocked=!dw||dwTooSoon||dwCount>=2
  const nutritionFromMuac=muacStatus(f.muac,f.edema)
  const filtered=historyDate?history.filter(x=>x.visit_date===historyDate):history,pages=Math.max(1,Math.ceil(filtered.length/size)),shown=filtered.slice((historyPage-1)*size,historyPage*size)
  const reload=async c=>setHistory(await api('/children/'+c.id+'/history?_='+Date.now()))

  useEffect(()=>{if(!child&&linked){const c=children.find(x=>String(x.id)===String(linked));if(c){sessionStorage.setItem('cinus_follow_child',String(c.id));setChild(c);setQ(c.first_name+' '+c.last_name);setMsg('Child selected. Enter visit measurements.')}}},[children])
  useEffect(()=>{if(child)reload(child)},[child])
  useEffect(()=>{
    if(!child)return
    const old=history.find(x=>x.visit_date===f.visit_date)
    if(old){
      setEditing(old.id)
      setF(x=>({...x,visit_date:old.visit_date,weight:old.weight,height:old.height,muac:old.muac,edema:!!old.edema,health_worker:old.health_worker||'',nutrition_result:old.nutrition_result||'normal',referral:old.referral||'',vitamin_a_dose:String(old.vitamin_a_dose||0),deworming_dose:String(old.deworming_dose||0),developmental_result:old.developmental_result||'ndd',development_notes:old.development_notes||''}))
      setMsg('Existing visit found on this date. The form is now in update mode.')
    }else setEditing(null)
  },[child,f.visit_date,history])
  useEffect(()=>{
    if(!child||!f.weight||!f.height){setScores(null);return}
    const controller=new AbortController()
    setMsg('Calculating WHO z-score from the latest measurements...')
    const params=new URLSearchParams({child_id:String(child.id),visit_date:f.visit_date,weight:String(f.weight),height:String(f.height)})
    const t=setTimeout(()=>api('/growth-assessment?'+params.toString(),{signal:controller.signal}).then(x=>{setScores(x);setMsg('WHO z-score updated from the latest measurements.')}).catch(e=>{if(e.name==='AbortError')return;setScores(null);setMsg(e.message)}),250)
    return()=>{controller.abort();clearTimeout(t)}
  },[child,f.visit_date,f.weight,f.height])
  useEffect(()=>{
    if(f.vitamin_a_dose!=='0'&&vaLocked)setF(x=>({...x,vitamin_a_dose:'0'}))
    if(f.deworming_dose!=='0'&&dwLocked)setF(x=>({...x,deworming_dose:'0'}))
  },[vaLocked,dwLocked])
  useEffect(()=>{
    if(!msg||msg==='Select a child to unlock the form.'||msg.startsWith('Calculating WHO z-score'))return
    const t=setTimeout(()=>setMsg(''),3600)
    return()=>clearTimeout(t)
  },[msg])

  const u=e=>{
    const value=e.target.type==='checkbox'?e.target.checked:e.target.value
    const nextForm={...f,[e.target.name]:value}
    const muac=muacStatus(nextForm.muac,nextForm.edema)
    if(muac.label==='SAM')nextForm.nutrition_result='sam'
    else if(muac.label==='MAM')nextForm.nutrition_result='mam'
    else if(muac.label==='Normal')nextForm.nutrition_result='normal'
    setF(nextForm)
  }
  const chooseChild=c=>{sessionStorage.setItem('cinus_follow_child',String(c.id));setChild(c);setQ(c.first_name+' '+c.last_name+' · '+c.child_code);setMsg('Child selected. Enter visit measurements.')}
  const save=async e=>{
    e.preventDefault()
    try{
      const body={...f,child_id:child.id,weight:+f.weight,height:+f.height,muac:+f.muac,vitamin_a_dose:+f.vitamin_a_dose,deworming_dose:+f.deworming_dose}
      await api(editing?'/visits/'+editing:'/visits',{method:editing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      const wasEditing=!!editing;setHistoryDate('');setHistoryPage(1);setEditing(null);setF(blank());await reload(child);setMsg(wasEditing?'Visit updated successfully.':'New visit saved successfully.');done(wasEditing?'Visit updated.':'Follow-up saved.')
    }catch(x){setMsg('Cannot save: '+x.message)}
  }
  const vaHint=!va?'Not age eligible':vaCount>=2?'Two Vitamin A doses already recorded this year':vaTooSoon?'Next Vitamin A after '+next(lastVa.visit_date,120):lastVa?'Eligible for dose '+Math.min(2,vaCount+1):'No dose recorded - eligible now'
  const dwHint=!dw?'Available from 24 months':dwCount>=2?'Two deworming doses already recorded this year':dwTooSoon?'Next deworming after '+next(lastDw.visit_date,365):lastDw?'Eligible for dose '+Math.min(2,dwCount+1):'No dose recorded - eligible now'

  return <><div className="followup-layout">{msg&&msg!=='Select a child to unlock the form.'&&<p className={'helper followup-toast '+((msg.startsWith('Cannot')||msg.includes('must be')||msg.includes('Check measurements'))?'warning':'info')}>{msg}</p>}<section className="panel form-card"><p className="eyebrow">SEARCH CHILD</p><F label="Name, CIN code or phone" value={q} onChange={e=>{setQ(e.target.value);sessionStorage.removeItem('cinus_follow_child');setChild(null)}}/>{matches.length>0&&<div className="search-results">{matches.map(c=><button type="button" key={c.id} onClick={()=>chooseChild(c)}><b>{c.first_name} {c.last_name}</b><small>{c.child_code} · DOB {c.date_of_birth}</small></button>)}</div>}{!child&&<div className="select-alert"><b>Select a child to begin</b><span>The complete follow-up form is locked until a registered child is selected.</span><div className="quick-child-list">{children.slice(0,8).map(c=><button type="button" key={c.id} onClick={()=>chooseChild(c)}><strong>{c.first_name} {c.last_name}</strong><small>{c.child_code} · {c.woreda||'Registered child'}</small></button>)}</div></div>}{child&&<div className={'selected-child '+(editing?'editing-visit':'')}><b>{child.first_name} {child.last_name}</b><span>{editing?'Editing visit '+f.visit_date:child.child_code+' · '+age+' months'}</span></div>}<form onSubmit={save}><fieldset disabled={!child}><div className="followup-entry-grid"><div className="entry-column"><div className="section-title">Measurements</div><div className="form-grid compact-two"><F label="Visit date" type="date" name="visit_date" value={f.visit_date} onChange={u}/><F label="Health worker" name="health_worker" value={f.health_worker} onChange={u}/><F label="Weight (kg)" type="number" step=".1" name="weight" value={f.weight} onChange={u}/><F label="Length / height (cm)" type="number" step=".1" name="height" value={f.height} onChange={u}/><F label="MUAC (cm)" type="number" step=".1" name="muac" value={f.muac} onChange={u}/></div><div className="section-title">Automatic WHO assessment</div><div className="z-score-main compact"><article className={calculating?'pending':zClass(scores?.whz)}><span>Z-score value</span><b>{calculating?'...':zValue(scores?.whz)}</b><small>{calculating?'Calculating from latest measurements':primaryZName(age)+' weight-for-'+(age!=null&&age<24?'length':'height')+' · '+zLabel(scores?.whz)}</small></article><article className={nutritionFromMuac.level}><span>MUAC</span><b>{nutritionFromMuac.label}</b><small>{nutritionFromMuac.text}</small></article></div><p className="z-score-support">Weight-for-age {zValue(scores?.waz)} · Height-for-age {zValue(scores?.haz)}</p><div className="checks"><label><input type="checkbox" name="edema" checked={f.edema} onChange={u}/><span>Bilateral pitting oedema (SAM)</span></label></div></div><div className="entry-column"><div className="section-title">Services and notes</div><div className="form-grid compact-two"><S label="Nutrition" name="nutrition_result" value={f.edema?'sam':f.nutrition_result} disabled={f.edema} onChange={u} options={[['normal','Normal'],['mam','MAM'],['sam','SAM']]}/><S label="Vitamin A" name="vitamin_a_dose" value={f.vitamin_a_dose} disabled={!va} onChange={u} options={[[0,'No dose'],[1,'Dose 1',vaLocked],[2,'Dose 2',vaLocked]]}/><S label="Deworming" name="deworming_dose" value={f.deworming_dose} disabled={!dw} onChange={u} options={[[0,'No dose'],[1,'Dose 1',dwLocked],[2,'Dose 2',dwLocked]]}/><S label="Development" name="developmental_result" value={f.developmental_result} onChange={u} options={[['ndd','NDD'],['sdd','SDD'],['cdd','CDD']]}/><F label="Referral / action" name="referral" value={f.referral} onChange={u}/><F label="Development notes" name="development_notes" value={f.development_notes} onChange={u}/></div><div className="dose-hints"><span className={vaLocked?'locked':'open'}>{vaHint}</span><span className={dwLocked?'locked':'open'}>{dwHint}</span></div></div></div><button className="primary followup-save">{editing?'Update visit for '+f.visit_date:'Save new follow-up'}</button></fieldset></form></section><aside className="panel child-insight"><p className="eyebrow">HISTORY & RECOMMENDATIONS</p>{child&&<><div className="recommendations"><p><b>Vitamin A:</b> {vaHint}</p><p><b>Deworming:</b> {dwHint}</p></div><F label="Filter history by visit date" type="date" value={historyDate} onChange={e=>{setHistoryDate(e.target.value);setHistoryPage(1)}}/>{shown.map(v=><article className="history-card detailed" key={v.id} onClick={()=>setF(x=>({...x,visit_date:v.visit_date}))}><b>{v.visit_date}</b><span>Weight {v.weight} kg · Height {v.height} cm · MUAC {v.muac} cm</span><span>Z-score {zValue(v.whz)} · Weight-for-age {zValue(v.waz)} · Height-for-age {zValue(v.haz)}</span><small>{(v.nutrition_result||'--').toUpperCase()} · Development {(v.developmental_result||'--').toUpperCase()}</small><small>Vitamin A {v.vitamin_a_dose||'--'} · Deworming {v.deworming_dose||'--'} · {v.health_worker||'No worker'}</small></article>)}<div className="pagination compact-pages"><span>{historyPage}/{pages}</span><div><button disabled={historyPage===1} onClick={()=>setHistoryPage(historyPage-1)}>←</button><button disabled={historyPage===pages} onClick={()=>setHistoryPage(historyPage+1)}>→</button></div></div></>}</aside></div><div className="followup-help-row"><WHOHelp/></div></>
}

