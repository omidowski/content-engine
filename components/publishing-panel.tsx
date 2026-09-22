"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CalendarClock, Check, ExternalLink, Camera, Link2, Loader2, RefreshCw, Video } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Content } from "@/lib/content";

type Platform = "instagram_reel" | "instagram_story" | "youtube";
type Connection = {provider:string;configured:boolean;connected:boolean;label:string|null;account_type:string|null};
type Job = {id:number;content_id:number;title:string;platform:Platform;status:string;scheduled_at:string;error:string|null;remote_url:string|null;attempts:number};
type Automation = {enabled:boolean;mode:"after_approval"|"fully_automatic";platforms:Platform[];timezone:string;times:string[];made_for_kids:boolean;synthetic_media:boolean;next_run?:string|null;last_error?:string|null;worker_enabled?:boolean};
const defaults:Automation = {enabled:false,mode:"after_approval",platforms:["instagram_reel","youtube"],timezone:"Europe/Berlin",times:["09:00"],made_for_kids:false,synthetic_media:false};
const names:Record<Platform,string> = {instagram_reel:"Instagram Reel",instagram_story:"Instagram Story",youtube:"YouTube / Short"};
const statuses:Record<string,string> = {QUEUED:"Geplant",RUNNING:"In Arbeit",PUBLISHED:"Veröffentlicht",UPLOADED:"Hochgeladen · Sichtbarkeit prüfen",FAILED:"Fehlgeschlagen",UNCERTAIN:"Ergebnis prüfen",CANCELLED:"Storniert"};
const dateLabel = (value:string) => new Date(value).toLocaleString("de-DE",{dateStyle:"medium",timeStyle:"short"});

async function api<T>(path:string, method="GET", body?:unknown):Promise<T> {
  const response = await fetch("/api/engine/publishing/"+path,{method,headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const value = await response.json().catch(()=>({})) as {detail?:unknown};
  if(!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "Bitte Eingaben und Verbindung prüfen.");
  return value as T;
}

function Platforms({value,onChange,disabled=false}:{value:Platform[];onChange:(value:Platform[])=>void;disabled?:boolean}) {
  return <div className="platform-choices">{(Object.keys(names) as Platform[]).map(platform=><label key={platform} className={value.includes(platform)?"chosen":""}><Checkbox checked={value.includes(platform)} disabled={disabled} onCheckedChange={checked=>onChange(checked===true?[...value,platform]:value.filter(x=>x!==platform))}/><span>{names[platform]}</span></label>)}</div>;
}

export function PublishingPanel({connected,items,onConnect}:{connected:boolean;items:Content[];onConnect:()=>void}) {
  const [connections,setConnections]=useState<Connection[]>([]);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [saved,setSaved]=useState<Automation>(defaults);
  const [form,setForm]=useState<Automation>(defaults);
  const [times,setTimes]=useState("09:00");
  const [selected,setSelected]=useState("");
  const [platforms,setPlatforms]=useState<Platform[]>(["instagram_reel","youtube"]);
  const [when,setWhen]=useState("");
  const [kids,setKids]=useState(false);
  const [synthetic,setSynthetic]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [tab,setTab]=useState("schedule");
  const initialized=useRef(false);
  const actionLock=useRef(false);
  const ready=items.filter(item=>item.status==="VIDEO_READY");
  const refresh=useCallback(async()=>{
    const [accounts,queue,automation]=await Promise.all([api<Connection[]>("connections"),api<Job[]>("jobs"),api<Automation>("automation")]);
    setConnections(accounts);setJobs(queue);setSaved(automation);
    if(!initialized.current){setForm(automation);setTimes(automation.times.join(", "));initialized.current=true;}
  },[]);
  useEffect(()=>{
    if(!connected)return;
    let active=true;
    const load=()=>{void refresh().catch(cause=>{if(active)setError(cause.message);});};
    load();const timer=setInterval(load,15000);
    return()=>{active=false;clearInterval(timer);};
  },[connected,refresh]);
  async function run(action:()=>Promise<void>){
    if(actionLock.current)return;
    actionLock.current=true;setBusy(true);setError("");setMessage("");
    try{await action();}catch(cause){setError(cause instanceof Error?cause.message:"Vorgang fehlgeschlagen.");}
    finally{setBusy(false);actionLock.current=false;}
  }
  async function save(enabled:boolean){
    await run(async()=>{
      if(!connected){setMessage("Demo-Einstellungen nur in dieser Ansicht. Zum Speichern die Engine verbinden.");return;}
      const {next_run,last_error,worker_enabled,...input}=form;
      const result=await api<Automation>("automation","PUT",{...input,enabled,times:times.split(",").map(x=>x.trim()).filter(Boolean)});
      setForm(result);setSaved(result);setTimes(result.times.join(", "));
      setMessage(enabled?"Automatik aktiviert. Der nächste passende Inhalt wird zum geplanten Zeitpunkt verarbeitet.":"Zeitplan gespeichert · Automatik pausiert. Bereits geplante Einzelaufträge bleiben bestehen.");
    });
  }
  return <section className="publishing-panel" aria-label="Veröffentlichungen">
    <div className="publishing-heading"><div><div className="eyebrow">VERÖFFENTLICHEN</div><h2>Dein Content. Zur richtigen Zeit.</h2><p>{connected?"Plane fertige Videos oder lasse vorhandene Inhalte automatisch verarbeiten.":"Plane den Ablauf. Zum Veröffentlichen brauchst du die verbundene Live-Engine und deine Konten."}</p></div><span className={"automation-badge "+(saved.enabled?"active":"")}><CalendarClock size={17}/>{connected&&saved.enabled?"Automatik aktiv":"Automatik pausiert"}</span></div>
    {!connected&&<div className="publishing-notice"><div><strong>Noch keine Live-Veröffentlichung</strong><p>Hier kannst du die Einstellungen ausprobieren. Es wird nichts gespeichert oder gepostet.</p></div><button className="button secondary" onClick={onConnect}><Link2 size={16}/>Engine verbinden</button></div>}
    {connected&&!saved.worker_enabled&&<p className="publishing-notice">Der Veröffentlichungsdienst muss auf deinem Server noch eingeschaltet werden.</p>}
    {error&&<p className="error-message" role="alert">{error}</p>}{message&&<p className="publishing-message" role="status"><Check size={17}/>{message}</p>}
    <Tabs value={tab} onValueChange={setTab}><TabsList variant="line" className="publishing-tabs"><TabsTrigger value="schedule">Zeitplan</TabsTrigger><TabsTrigger value="queue">Warteschlange <span>{jobs.length}</span></TabsTrigger><TabsTrigger value="accounts">Konten</TabsTrigger></TabsList>
      <TabsContent value="schedule"><div className="publishing-grid">
        <form className="publishing-card" onSubmit={event=>{event.preventDefault();void save(form.enabled);}}><div className="publishing-card-title"><CalendarClock size={21}/><h3>Tägliche Automatik</h3></div><p>Pro Uhrzeit ein Inhalt auf allen gewählten Plattformen. Älteste passende Inhalte zuerst.</p>
          <label className="field-label" htmlFor="automatic-mode">Betriebsart</label><Select value={form.mode} onValueChange={value=>setForm({...form,mode:value as Automation["mode"]})} disabled={busy}><SelectTrigger id="automatic-mode" className="language-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="after_approval">Nach meiner Freigabe</SelectItem><SelectItem value="fully_automatic">Vollautomatisch</SelectItem></SelectContent></Select>
          <p className="helper-text">{form.mode==="fully_automatic"?"Auch vorhandene ungeprüfte Live-Entwürfe werden gerendert und veröffentlicht. Keine neue Recherche oder Skripterstellung.":"Nur freigegebene Inhalte werden gerendert und veröffentlicht."}</p>
          <span className="field-label">Plattformen</span><Platforms value={form.platforms} onChange={value=>setForm({...form,platforms:value})} disabled={busy}/>
          <label className="field-label" htmlFor="daily-times">Uhrzeiten</label><input id="daily-times" className="standard-field" value={times} onChange={event=>setTimes(event.target.value)} placeholder="09:00, 18:00" required disabled={busy}/><p className="helper-text">Bis zu fünf Zeiten, durch Kommas getrennt.</p>
          <label className="field-label" htmlFor="publish-zone">Zeitzone</label><Select value={form.timezone} onValueChange={value=>setForm({...form,timezone:value})} disabled={busy}><SelectTrigger id="publish-zone" className="language-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="Europe/Berlin">Deutschland · Europe/Berlin</SelectItem><SelectItem value="UTC">UTC</SelectItem><SelectItem value="Asia/Tehran">Iran · Asia/Tehran</SelectItem><SelectItem value="America/New_York">New York</SelectItem></SelectContent></Select>
          {form.platforms.includes("youtube")&&<div className="youtube-options"><label><Checkbox checked={form.made_for_kids} onCheckedChange={value=>setForm({...form,made_for_kids:value===true})}/><span>Diese Inhalte sind speziell für Kinder erstellt.</span></label><label><Checkbox checked={form.synthetic_media} onCheckedChange={value=>setForm({...form,synthetic_media:value===true})}/><span>Realistisch wirkende veränderte oder synthetische Inhalte kennzeichnen.</span></label></div>}
          <div className="publishing-actions"><button type="submit" className="button secondary" disabled={busy}>{busy?<Loader2 size={17} className="spin"/>:null}Einstellungen speichern</button><button type="button" className="button primary" disabled={!connected||busy||(!saved.enabled&&!form.platforms.length)} onClick={()=>void save(!saved.enabled)}>{saved.enabled?"Automatik pausieren":"Automatik aktivieren"}</button></div>
          {saved.next_run&&<p className="helper-text">Nächster Lauf: {dateLabel(saved.next_run)} (deine Gerätezeit)</p>}{saved.last_error&&<p className="helper-text">{saved.last_error}</p>}
        </form>
        <form className="publishing-card" onSubmit={event=>{event.preventDefault();void run(async()=>{if(!connected)return;await api("jobs","POST",{content_id:Number(selected),platforms,scheduled_at:new Date(when).toISOString(),made_for_kids:kids,synthetic_media:synthetic});await refresh();setMessage("Video eingeplant.");setTab("queue");});}}><div className="publishing-card-title"><CalendarClock size={21}/><h3>Ein Video einplanen</h3></div><p>Ein fertiges Video zu einem bestimmten Zeitpunkt veröffentlichen.</p>
          <label className="field-label" htmlFor="publish-content">Fertiges Video</label><Select value={selected} onValueChange={setSelected} disabled={busy||!ready.length}><SelectTrigger id="publish-content" className="language-select"><SelectValue placeholder={ready.length?"Video auswählen":"Noch kein fertiges Video"}/></SelectTrigger><SelectContent>{ready.map(item=><SelectItem key={item.id} value={String(item.id)}>{item.title}</SelectItem>)}</SelectContent></Select>
          <span className="field-label">Plattformen</span><Platforms value={platforms} onChange={setPlatforms} disabled={busy}/>
          <label className="field-label" htmlFor="publish-time">Datum & Uhrzeit</label><input type="datetime-local" id="publish-time" className="standard-field" required value={when} onChange={event=>setWhen(event.target.value)} disabled={busy}/><p className="helper-text">In der Zeitzone deines Geräts. Veröffentlicht wird frühestens zu diesem Zeitpunkt; Rendering und Verarbeitung können dauern.</p>
          {platforms.includes("youtube")&&<div className="youtube-options"><label><Checkbox checked={kids} onCheckedChange={value=>setKids(value===true)}/><span>Speziell für Kinder erstellt</span></label><label><Checkbox checked={synthetic} onCheckedChange={value=>setSynthetic(value===true)}/><span>Realistische synthetische Inhalte kennzeichnen</span></label></div>}
          <button className="button primary publish-submit" disabled={!connected||busy||!selected||!platforms.length||!when}>Video einplanen</button><p className="helper-text">YouTube kann API-Uploads zunächst privat halten. Das tatsächliche Ergebnis steht in der Warteschlange.</p>
        </form>
      </div></TabsContent>
      <TabsContent value="queue"><div className="queue-heading"><h3>Veröffentlichungen</h3><button className="button secondary" disabled={!connected||busy} onClick={()=>void run(refresh)}><RefreshCw size={16}/>Aktualisieren</button></div>{jobs.length?<div className="publish-jobs">{jobs.map(job=><article className="publish-job" key={job.id}><div><span className="eyebrow">{names[job.platform]}</span><h4>{job.title}</h4><p>{dateLabel(job.scheduled_at)} · {job.attempts} Versuche</p>{job.error&&<p className="job-error">{job.error}</p>}</div><div className="job-actions"><span className={"job-status "+job.status.toLowerCase()}>{statuses[job.status]||job.status}</span>{job.remote_url&&<a className="button secondary" href={job.remote_url} target="_blank" rel="noopener noreferrer">Beitrag öffnen<ExternalLink size={14}/></a>}{["QUEUED","FAILED"].includes(job.status)&&<button className="button secondary" disabled={busy} onClick={()=>void run(async()=>{await api("jobs/"+job.id+"/cancel","POST");await refresh();})}>Stornieren</button>}{["FAILED","CANCELLED"].includes(job.status)&&<button className="button secondary" disabled={busy} onClick={()=>void run(async()=>{await api("jobs/"+job.id+"/retry","POST");await refresh();})}>Erneut starten</button>}{job.status==="UNCERTAIN"&&job.platform==="youtube"&&<button className="button secondary" disabled={busy} onClick={()=>void run(async()=>{await api("jobs/"+job.id+"/retry","POST");await refresh();})}>Upload prüfen & fortsetzen</button>}</div></article>)}</div>:<div className="publishing-empty"><CalendarClock size={32}/><h3>Noch nichts eingeplant</h3><p>{connected?"Wähle ein fertiges Video oder aktiviere die tägliche Automatik.":"Deine Veröffentlichungen erscheinen hier, sobald die Engine verbunden ist."}</p></div>}</TabsContent>
      <TabsContent value="accounts"><div className="publishing-grid">{["instagram","youtube"].map(provider=>{const account=connections.find(x=>x.provider===provider);return <article className="publishing-card" key={provider}><div className="publishing-card-title">{provider==="instagram"?<Camera size={24}/>:<Video size={25}/>}<h3>{provider==="instagram"?"Instagram":"YouTube"}</h3></div><span className="account-state">{account?.connected?account.label:account?.configured?"Bereit zur Anmeldung":"Noch nicht eingerichtet"}</span><p>{provider==="instagram"?"Reels für Business- und Creator-Konten. Stories benötigen ein Business-Konto.":"Verbinde den Kanal, auf dem deine Videos und Shorts erscheinen sollen."}</p><button className="button primary publish-submit" disabled={busy||!connected||!account?.configured} onClick={()=>void run(async()=>{const result=await api<{url:string}>("connections/"+provider+"/connect","POST");window.location.assign(result.url);})}><Link2 size={16}/>{account?.connected?"Konto erneut verbinden":"Konto verbinden"}</button>{account?.connected&&<button className="button secondary publish-submit" disabled={busy} onClick={()=>void run(async()=>{await api("connections/"+provider+"/disconnect","POST");await refresh();setMessage("Konto getrennt, wartende Aufträge storniert und Automatik pausiert. Anbieterzugriff kannst du zusätzlich in deinen Kontoeinstellungen widerrufen.");})}>Verbindung trennen</button>}<p className="helper-text">{account?.configured?"Anmeldung direkt beim Anbieter. Dein Passwort bleibt dort.":"Zuerst muss die Plattform-App auf deinem Server eingerichtet werden. Danach wird die Anmeldung freigeschaltet."}</p></article>;})}</div></TabsContent>
    </Tabs>
  </section>;
}
