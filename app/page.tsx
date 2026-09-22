"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, Check, CheckCheck, ChevronRight, Clapperboard, Clock3, Copy, ExternalLink, FileText, Film, Link2, Loader2, Pause, Play, Plus, Radio, RotateCcw, Save, Settings2, ShieldCheck, Sparkles, WandSparkles, X } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Toaster, toast } from "sonner";
import type { Content, EngineHealth } from "@/lib/content";
import { EXAMPLE, demoDraft, spokenText, statusLabel } from "@/lib/content";
import { PublishingPanel } from "@/components/publishing-panel";
import { useStudioTools } from "@/lib/studio-tools";

export default function Studio() {
  const [items, setItems] = useState<Content[]>([EXAMPLE]);
  const [selected, setSelected] = useState(EXAMPLE.id);
  const [edited, setEdited] = useState<Content>(EXAMPLE);
  const [mode, setMode] = useState<"demo" | "engine">("demo");
  const [health, setHealth] = useState<EngineHealth | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [publishingOpen, setPublishingOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState("de");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceNote, setSourceNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [checked, setChecked] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [videoShown, setVideoShown] = useState(false);
  const [tab, setTab] = useState("script");
  const actionLock = useRef(false);
  const saved = items.find(item => item.id === selected);
  const dirty = !!saved && JSON.stringify(saved) !== JSON.stringify(edited);
  const editable = edited.status === "REVIEW";
  const words = spokenText(edited).trim().split(/\s+/).length;
  const duration = Math.ceil(words / 2.5);
  const segments = spokenText(edited).match(/\S+(?:\s+\S+){0,6}/g) || [];
  const subtitle = segments[Math.min(Math.floor(seconds / Math.max(duration / segments.length, 1)), segments.length - 1)];
  const stage = edited.status === "VIDEO_READY" ? 3 : edited.status === "REVIEW" ? 1 : 2;

  async function request<T = Content>(path: string, method = "GET", body?: unknown): Promise<T> {
    const response = await fetch("/api/engine/" + path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const problem = data as {detail?:unknown}; throw new Error(typeof problem.detail === "string" ? problem.detail : "Die Anfrage konnte nicht abgeschlossen werden."); }
    return data as T;
  }
  async function checkConnection() {
    try { const result = await request<EngineHealth>("health"); setHealth(result); return result; }
    catch { const result = { configured: false, available: false, detail: "Verbindung konnte nicht geprüft werden." }; setHealth(result); return result; }
  }
  useEffect(() => {
    void checkConnection();
    const result = new URLSearchParams(window.location.search).get("social");
    if (result) {
      setPublishingOpen(true);
      window.history.replaceState(null, "", "/");
      if (result === "connected") { toast.success("Kontoanmeldung abgeschlossen"); void connectEngine(); }
      else toast.error("Kontoanmeldung fehlgeschlagen. Verbindung und Anbieter-Konfiguration prüfen.");
    }
  }, []);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setSeconds(value => {
      if (value >= duration) { setPlaying(false); return 0; }
      return value + 0.25;
    }), 250);
    return () => clearInterval(timer);
  }, [playing, duration]);
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  function choose(item: Content) {
    setSelected(item.id); setEdited(item); setChecked(false); setPlaying(false); setSeconds(0); setVideoShown(false); setError(""); setTab("script");
  }
  function replace(item: Content) {
    setItems(all => all.map(old => old.id === item.id ? item : old)); setEdited(item);
  }
  async function perform(label: string, action: () => Promise<void>) {
    if (actionLock.current) return;
    actionLock.current = true; setBusy(label); setError("");
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Ein Fehler ist aufgetreten. Bitte erneut versuchen."); }
    finally { actionLock.current = false; setBusy(""); }
  }
  async function saveDraft() {
    if (!edited.hook.trim() || edited.script.trim().length < 20 || !edited.title.trim() || !edited.caption.trim() || !edited.cta.trim()) throw new Error("Bitte alle Textfelder ausfüllen. Das Skript braucht mindestens 20 Zeichen.");
    if (mode === "demo") { replace(edited); return edited; }
    const updated = await request("content/" + edited.id, "PATCH", { hook: edited.hook, script: edited.script, title: edited.title, caption: edited.caption, cta: edited.cta });
    replace(updated); return updated as Content;
  }
  async function createDraft(event: React.FormEvent) {
    event.preventDefault();
    await perform("Entwurf wird erstellt …", async () => {
      const input = { topic: topic.trim(), language, sources: sourceUrl || sourceNote ? [{ title: sourceUrl ? new URL(sourceUrl).hostname : "Eigene Notizen", url: sourceUrl || null, note: sourceNote || null }] : [] };
      const item = mode === "demo" ? demoDraft(input.topic, language, input.sources) : await request("content", "POST", input);
      setItems(all => [item, ...all]); choose(item); setNewOpen(false); setTopic(""); setSourceUrl(""); setSourceNote("");
      toast.success(mode === "demo" ? "Beispielentwurf erstellt · nur in dieser Sitzung" : "Entwurf erstellt");
    });
  }
  async function approve() {
    if (!checked) return;
    await perform("Freigabe wird gespeichert …", async () => {
      const item = dirty ? await saveDraft() : edited;
      const next = mode === "demo" ? { ...item, status: "APPROVED" as const } : await request("content/" + item.id + "/approve", "POST", { approved: true });
      replace(next); setPlaying(false); toast.success("Skript freigegeben");
    });
  }
  async function renderVideo() {
    await perform(mode === "demo" ? "Beispiel wird geöffnet …" : "Voice-over und Video werden erstellt …", async () => {
      if (mode === "demo") { setVideoShown(true); toast.info("Festes, stummes Beispielvideo – kein Render deines Entwurfs."); return; }
      const result = await request("content/" + edited.id + "/render", "POST");
      replace(result); setVideoShown(true); toast.success("Dein Video ist fertig");
    });
  }
  async function connectEngine() {
    await perform("Verbindung wird geprüft …", async () => {
      const connection = await checkConnection();
      if (!connection.available) throw new Error(connection.detail || "Die Python-Engine ist noch nicht verbunden.");
      const data = await request<Content[]>("content");
      setMode("engine"); setItems(data); setSettingsOpen(false);
      if (data.length) choose(data[0]); else { setSelected(-1); setNewOpen(true); }
      toast.success("Python-Engine verbunden");
    });
  }
  function editField(key: keyof Content, value: string) { setEdited(item => ({ ...item, [key]: value })); setChecked(false); setVideoShown(false); }
  const videoUrl = mode === "demo" ? "/demo-short.mp4" : "/api/engine/content/" + edited.id + "/video";
  const hasItem = items.length > 0 && !!saved;
  useStudioTools({ mode, items, selected, busy: !!busy, dirty, start: (nextTopic) => { setTopic(nextTopic); setNewOpen(true); } });

  return <div className="studio">
    <Toaster position="top-center" richColors />
    <header className="masthead"><a className="wordmark" href="/" aria-label="Omid Content Studio" onClick={event => { if(dirty) { event.preventDefault(); toast.info("Bitte Änderungen zuerst speichern."); } }}><span className="brand-icon"><Clapperboard size={23}/></span><span>omid<span className="brand-period">.</span><span className="brand-product">content studio</span></span></a><div className="header-right"><span className="private-label"><ShieldCheck size={15}/>Privater Workspace</span><button className="connection-button" onClick={() => setSettingsOpen(true)}><Settings2 size={16}/><span>{mode === "demo" ? "Demo-Modus" : "Engine verbunden"}</span></button><span className="avatar" aria-label="Omid Moraveji">OM</span></div></header>
    <main className="studio-main">
      <div className="page-heading"><div><div className="eyebrow">DEIN CREATOR-WORKSPACE</div><h1>Aus Ideen wird Content<span>.</span></h1><p>Entwerfen. Prüfen. Produzieren.</p></div><button className="button primary new-top" onClick={() => setNewOpen(true)} disabled={!!busy || dirty}><Plus size={19}/>Neuer Short</button></div>
      <div className="demo-notice"><span className="notice-icon"><Radio size={17}/></span><p>{mode === "demo" ? <><strong>Dein Studio zum Ausprobieren.</strong> Beispielinhalte bleiben nur in dieser Sitzung. Noch keine AI-Produktion.</> : <><strong>Deine Engine ist verbunden.</strong> {health?.mode === "live" ? "Skripte und Videos werden auf deinem Server erstellt." : "Die Engine nutzt mindestens einen Demo-Fallback."}</>}</p><button onClick={() => setSettingsOpen(true)}>{mode === "demo" ? "Engine verbinden" : "Verbindung prüfen"}<ArrowRight size={15}/></button></div>
      <nav className="workspace-navigation" aria-label="Arbeitsbereich"><button className={!publishingOpen?"selected":""} onClick={()=>setPublishingOpen(false)}>Content erstellen</button><button className={publishingOpen?"selected":""} onClick={()=>setPublishingOpen(true)}>Veröffentlichen & planen</button></nav>
      {publishingOpen && <PublishingPanel connected={mode === "engine"} items={items} onConnect={()=>setSettingsOpen(true)}/>}
      <div className="workbench" hidden={publishingOpen}>
        <aside className="drafts-panel" aria-label="Entwürfe"><div className="panel-heading"><h2>Deine Shorts <span>{items.length}</span></h2><button className="icon-button" aria-label="Neuen Short erstellen" disabled={!!busy || dirty} onClick={() => setNewOpen(true)}><Plus size={18}/></button></div><div className="draft-list">{items.map((item, index) => <button className={"draft-card " + (selected === item.id ? "selected" : "")} key={item.id} disabled={!!busy || (dirty && selected !== item.id)} onClick={() => { if (!dirty) void perform("Inhalt laden …", async () => choose(mode === "engine" ? await request("content/" + item.id) : item)); }}><span className="draft-topline"><span className="draft-number">{String(items.length - index).padStart(2,"0")}</span><span className={"status-pill " + item.status.toLowerCase()}>{statusLabel(item.status)}</span></span><strong>{item.title}</strong><span className="draft-meta"><Film size={13}/>9:16 Short<span>·</span>{item.language === "de" ? "Deutsch" : "English"}</span></button>)}</div><div className="draft-footnote"><ShieldCheck size={21}/><p>Du behältst die Kontrolle.<br/><span>Veröffentlichungen steuerst du im Zeitplan.</span></p></div></aside>
        {hasItem ? <>
          <section className="editor-panel" aria-label="Content bearbeiten"><div className="editor-heading"><div className="eyebrow">SHORT / {String(items.findIndex(x => x.id === selected) + 1).padStart(2,"0")}</div><span className="save-state">{busy ? <Loader2 size={13} className="spin"/> : dirty ? <span className="unsaved-dot"/> : <CheckCheck size={14}/>} {busy ? "In Arbeit" : dirty ? "Nicht gespeichert" : mode === "demo" ? "In dieser Sitzung" : "Gespeichert"}</span></div><h2 className="content-title">{edited.topic}</h2>
            <ol className="workflow-steps" aria-label="Produktionsstatus">{["Skript","Freigabe","Video"].map((label,index) => <li key={label} className={stage === index + 1 ? "active" : stage > index + 1 ? "complete" : ""}><span>{stage > index + 1 ? <Check size={13}/> : index + 1}</span>{label}{index < 2 && <ChevronRight className="step-chevron" size={14}/>}</li>)}</ol>
            {error && <div role="alert" className="error-message">{error}<button className="icon-button" aria-label="Fehlermeldung schließen" onClick={() => setError("")}><X size={16}/></button></div>}
            <Tabs value={tab} onValueChange={setTab} className="editor-tabs"><TabsList variant="line" className="tab-bar"><TabsTrigger value="script"><FileText size={15}/>Skript</TabsTrigger><TabsTrigger value="post">Beitrag</TabsTrigger><TabsTrigger value="sources">Quellen <span className="tab-count">{edited.sources.length}</span></TabsTrigger></TabsList>
              <TabsContent value="script" className="script-tab"><div className="field-heading"><label htmlFor="hook">Der Hook</label><span>Die ersten 3 Sekunden</span></div><div className="hook-field"><Sparkles size={17}/><textarea id="hook" rows={2} maxLength={400} value={edited.hook} disabled={!editable || !!busy} onChange={e => editField("hook",e.target.value)}/></div><div className="field-heading"><label htmlFor="script">Dein Skript</label><span>Hauptteil</span></div><textarea className="script-field" id="script" maxLength={4000} value={edited.script} disabled={!editable || !!busy} onChange={e => editField("script",e.target.value)}/><div className="script-metrics"><span>{words} Wörter inkl. Hook & CTA</span><span><Clock3 size={13}/>ca. {duration} Sek.</span></div><div className="field-heading"><label htmlFor="cta">Call to Action</label><span>Ein klarer nächster Schritt</span></div><textarea className="standard-field cta-field" id="cta" rows={2} maxLength={300} value={edited.cta} disabled={!editable || !!busy} onChange={e => editField("cta",e.target.value)}/></TabsContent>
              <TabsContent value="post" className="post-tab"><label className="field-label" htmlFor="title">Titel</label><input className="standard-field" id="title" maxLength={250} value={edited.title} disabled={!editable || !!busy} onChange={e => editField("title",e.target.value)}/><label className="field-label" htmlFor="caption">Caption</label><textarea className="standard-field caption-field" id="caption" rows={8} maxLength={4000} value={edited.caption} disabled={!editable || !!busy} onChange={e => editField("caption",e.target.value)}/><button className="button secondary" onClick={() => { void navigator.clipboard.writeText(edited.caption).then(() => toast.success("Caption kopiert")).catch(() => toast.error("Bitte Text markieren und manuell kopieren.")); }}><Copy size={16}/>Caption kopieren</button><p className="helper-text">Fertige Videos kannst du unter „Veröffentlichen & planen“ einplanen.</p></TabsContent>
              <TabsContent value="sources" className="sources-tab"><div className="source-explainer"><ShieldCheck size={22}/><div><h3>Quellen zuerst prüfen.</h3><p>Links werden nicht automatisch abgerufen. Prüfe jede Aussage im Original, bevor du das Skript freigibst.</p></div></div>{edited.sources.length ? edited.sources.map((source,index) => <div className="source-card" key={index}><span className="source-number">{String(index + 1).padStart(2,"0")}</span><div><strong>{source.title}</strong>{source.url && /^https?:\/\//.test(source.url) && <a href={source.url} target="_blank" rel="noopener noreferrer">Quelle öffnen<ExternalLink size={13}/></a>}{source.note && <p>{source.note}</p>}</div></div>) : <div className="empty-source"><Link2 size={27}/><h3>Noch keine Quellen hinterlegt</h3><p>Dieser Entwurf ist nicht faktengeprüft. Quellen und eigene Notizen kannst du beim Erstellen eines Shorts hinzufügen.</p></div>}</TabsContent>
            </Tabs>
            <div className="review-actions">{editable ? <><label className="review-check" htmlFor="review-check"><Checkbox id="review-check" checked={checked} onCheckedChange={value => setChecked(value === true)} disabled={!!busy}/><span>Ich habe Aussagen, Quellen und Nutzungsrechte geprüft.</span></label><div className="action-row"><button className="button secondary" disabled={!!busy || !dirty} onClick={() => void perform("Speichern …", async () => { await saveDraft(); toast.success(mode === "demo" ? "In dieser Sitzung gespeichert" : "Gespeichert"); })}><Save size={16}/>Speichern</button><button className="button primary" disabled={!checked || !!busy} onClick={() => void approve()}>{busy ? <Loader2 size={17} className="spin"/> : <ShieldCheck size={17}/>}Skript freigeben<ArrowRight size={16}/></button></div></> : <><div className="approved-label"><ShieldCheck size={17}/>{edited.status === "VIDEO_READY" ? "Video fertig · Veröffentlichung im Zeitplan prüfen" : "Skript geprüft und freigegeben"}</div><div className="action-row"><button className="button secondary" disabled={!!busy} onClick={() => void perform("Zurück zum Entwurf …", async () => { const next = mode === "demo" ? { ...edited,status:"REVIEW" as const } : await request("content/" + edited.id + "/reopen","POST"); replace(next); setChecked(false); setVideoShown(false); })}><RotateCcw size={15}/>Bearbeiten</button><button className="button primary" disabled={!!busy} onClick={() => edited.status === "VIDEO_READY" ? setVideoShown(true) : void renderVideo()}>{busy ? <Loader2 className="spin" size={17}/> : <Film size={17}/>} {mode === "demo" ? "Beispielvideo ansehen" : edited.status === "VIDEO_READY" ? "Video ansehen" : "Video erstellen"}</button></div>{busy && <p className="helper-text" role="status">{busy} Das kann einige Minuten dauern.</p>}{mode === "demo" && <p className="helper-text">Festes Beispielvideo. Eigene MP4s benötigen die verbundene Engine.</p>}</>}</div>
          </section>
          <section className="preview-panel" aria-label="Video-Vorschau"><div className="panel-heading"><h2>Vorschau</h2><span className="format-badge">9:16</span></div><div className="preview-frame">{videoShown ? <video key={videoUrl} src={videoUrl} controls playsInline preload="metadata" aria-label={mode === "demo" ? "Stummes Beispielvideo" : "Dein gerendertes Video"} onError={() => setError("Das Video konnte nicht geladen werden. Bitte Verbindung prüfen.")}/> : <div className="preview-content"><div className="preview-brand"><span className="mini-brand">o.</span>OMID AI<span className="preview-label">TEXTVORSCHAU</span></div><div className="preview-topic"><span className="preview-category">AI & AUTOMATION</span><h3>{edited.hook}</h3><span className="preview-line"/></div><div className="preview-subtitle">{playing ? subtitle : edited.cta}</div><div className="preview-bottom"><span>@omid.ai</span><span>9:16 SHORT</span></div></div>}</div>{!videoShown && <div className="playback"><button aria-label={playing ? "Textvorschau pausieren" : "Textvorschau abspielen"} onClick={() => setPlaying(!playing)}>{playing ? <Pause size={16} fill="currentColor"/> : <Play size={16} fill="currentColor"/>}</button><span>{Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2,"0")}</span><div className="playback-track"><div style={{width:Math.min(seconds / duration * 100,100) + "%"}}/></div><span>{Math.floor(duration / 60) + ":" + String(duration % 60).padStart(2,"0")}</span></div>}<p className="preview-disclaimer">{videoShown ? mode === "demo" ? "Festes Beispiel · ohne Voice-over · nicht dein bearbeiteter Entwurf" : "Dein gerendertes Video" : "Textvorschau ohne Ton. Das finale Video wird separat gerendert."}</p><div className="export-details"><div><span>Format</span><strong>1080 × 1920</strong></div><div><span>Sprache</span><strong>{edited.language === "de" ? "Deutsch" : "English"}</strong></div><div><span>Untertitel</span><strong>Im Video</strong></div></div>{videoShown && <a className="button download-button" href={videoUrl + (mode === "engine" ? "?download=1" : "")} download={mode === "demo" ? "beispiel-short.mp4" : "short-" + edited.id + ".mp4"}><ArrowDownToLine size={17}/>{mode === "demo" ? "Beispiel-MP4 laden" : "MP4 herunterladen"}</a>}<button className="text-export" onClick={() => { const blob = new Blob([JSON.stringify(edited,null,2)],{type:"application/json"}); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href=url; link.download="short-" + edited.id + ".json"; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); }}><ArrowDownToLine size={14}/>Entwurf als JSON exportieren</button></section>
        </> : <section className="workspace-empty"><WandSparkles size={40}/><h2>Dein erster Short beginnt hier.</h2><p>Gib ein Thema ein und erstelle einen Entwurf.</p><button className="button primary" onClick={() => setNewOpen(true)}><Plus size={18}/>Neuer Short</button></section>}
      </div><footer className="studio-footer"><span>OMID CONTENT STUDIO <span> / </span> V1.2</span><span>Deine Expertise. Dein Content.</span></footer>
    </main>
    <Dialog open={newOpen} onOpenChange={value => !busy && setNewOpen(value)}><DialogContent className="new-dialog"><DialogHeader><div className="dialog-icon"><WandSparkles size={24}/></div><DialogTitle>Woraus machen wir einen Short?</DialogTitle><DialogDescription>{mode === "demo" ? "Teste den Ablauf mit einer lokalen Textvorlage. Keine AI-Anfrage, keine automatische Recherche." : "Die Engine erstellt einen Entwurf. Du prüfst ihn, bevor ein Video entsteht."}</DialogDescription></DialogHeader><form onSubmit={event => void createDraft(event)}><label className="field-label" htmlFor="new-topic">Dein Thema</label><textarea id="new-topic" className="standard-field" placeholder="z. B. So wird aus einem Podcast eine Woche Content" minLength={3} maxLength={250} required value={topic} onChange={e => setTopic(e.target.value)} rows={3}/><label className="field-label" htmlFor="language">Sprache</label><Select value={language} onValueChange={setLanguage}><SelectTrigger id="language" className="language-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="de">Deutsch</SelectItem><SelectItem value="en">English</SelectItem></SelectContent></Select><label className="field-label" htmlFor="source-url">Quellenlink <span>optional</span></label><input id="source-url" className="standard-field" type="url" pattern="https?://.*" placeholder="https://…" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)}/><label className="field-label" htmlFor="source-note">Geprüfte Fakten & Notizen <span>optional</span></label><textarea id="source-note" className="standard-field" maxLength={2000} placeholder="Welche Kernaussagen soll dein Video enthalten?" value={sourceNote} onChange={e => setSourceNote(e.target.value)} rows={3}/>{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary create-button" disabled={!!busy || topic.trim().length < 3}>{busy ? <Loader2 className="spin" size={18}/> : <Sparkles size={18}/>} {busy ? "Wird erstellt …" : mode === "demo" ? "Beispielentwurf erstellen" : "Skript erstellen"}<ArrowRight size={17}/></button></form></DialogContent></Dialog>
    <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}><SheetContent className="connection-sheet"><SheetHeader><div className="dialog-icon"><Settings2 size={23}/></div><SheetTitle>Deine Produktions-Engine</SheetTitle><SheetDescription>Die Oberfläche ist bereit. Deine Python-Engine übernimmt AI und Video-Rendering.</SheetDescription></SheetHeader><div className="connection-content"><div className="connection-status"><span className={"connection-indicator " + (health?.available ? "available" : "")}/><div><strong>{health === null ? "Verbindung wird geprüft" : health.available ? "Engine erreichbar" : health.configured ? "Engine nicht erreichbar" : "Noch nicht verbunden"}</strong><p>{health?.available ? "Du kannst auf deine gespeicherten Inhalte zugreifen." : "Aktuell nutzt du den Demo-Modus ohne AI-Aufrufe."}</p></div></div><h3>So verbindest du V1</h3><ol className="setup-list"><li><span>1</span><div><strong>Engine starten</strong><p>Die mitgelieferte Python-Engine auf einem Server mit FFmpeg starten.</p></div></li><li><span>2</span><div><strong>Sichere Verbindung hinterlegen</strong><p>Serverseitig CONTENT_ENGINE_URL und CONTENT_ENGINE_TOKEN setzen. Die gleiche Zeichenfolge gehört als ENGINE_API_TOKEN in die Python-Engine.</p></div></li><li><span>3</span><div><strong>AI-Zugänge ergänzen</strong><p>OpenAI- und ElevenLabs-Keys nur in der Engine speichern, niemals im Browser.</p></div></li></ol><p className="connection-safety"><ShieldCheck size={18}/>Die Web-App speichert keine API-Keys im Browser. Demo-Entwürfe werden nicht an deine Engine übertragen.</p>{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary connect-action" disabled={!!busy || dirty} onClick={() => void connectEngine()}>{busy ? <Loader2 size={17} className="spin"/> : <Link2 size={17}/>}Verbindung prüfen & verbinden</button><p className="helper-text">Demo-Entwürfe vorher bei Bedarf als JSON exportieren.</p><a className="button secondary connect-action" href="/content-engine-v1.2.zip" download><ArrowDownToLine size={16}/>Aktuelle Engine herunterladen</a></div></SheetContent></Sheet>
  </div>;
}
