export type Status = "REVIEW" | "APPROVED" | "REJECTED" | "AUDIO_READY" | "VIDEO_READY";
export type Source = { title: string; url: string | null; note: string | null };
export type Content = { id: number; topic: string; language: string; title: string; hook: string; script: string; caption: string; cta: string; status: Status; sources: Source[]; audio_path: string | null; video_path: string | null; created_at: string; updated_at: string };
export type EngineHealth = { configured: boolean; available: boolean; mode?: string; ffmpeg_available?: boolean; detail?: string };
export const EXAMPLE: Content = {
  id:1, topic:"Ein Video. Eine Woche Content.", language:"de", title:"Dein Content arbeitet weiter.",
  hook:"Dein nächster Content steckt schon in deinem letzten Video.",
  script:"Du brauchst nicht jeden Tag eine neue Idee. Nimm ein Video, in dem du ein Problem wirklich löst.\n\nFinde drei Aussagen, die für sich allein verständlich sind. Aus jeder machst du einen kurzen Clip: ein klarer Einstieg, ein konkretes Beispiel und eine hilfreiche Erkenntnis.\n\nAI kann dir beim Transkribieren und beim ersten Skript helfen. Aber du prüfst, ob der Kontext stimmt.\n\nSo wird aus einer guten Aufnahme eine kleine Content-Serie. Deine Expertise bleibt. Das Format verändert sich.",
  cta:"Speichere dir den Workflow für dein nächstes Video.",
  caption:"Eine Aufnahme. Mehrere Perspektiven.\n\nStarte mit drei eigenständigen Aussagen aus deinem letzten Video. Prüfe den Kontext und mach daraus eine kleine Serie.\n\n#ContentCreation #AIAutomation #Repurposing",
  status:"REVIEW", sources:[], audio_path:null, video_path:null, created_at:"2026-09-21T10:00:00Z", updated_at:"2026-09-21T10:00:00Z"
};
export function spokenText(content: Content) { return [content.hook,content.script,content.cta].join(" "); }
export function statusLabel(status: Status) { return ({REVIEW:"Entwurf",APPROVED:"Freigegeben",REJECTED:"Abgelehnt",AUDIO_READY:"Audio fertig",VIDEO_READY:"Video fertig"})[status]; }
export function demoDraft(topic: string,language: string,sources: Source[]): Content {
  const german = language === "de";
  return {...EXAMPLE,id:Date.now(),topic,language,title:topic,sources,status:"REVIEW",
    hook:german ? "Was steckt hinter „" + topic + "“?" : "What is behind “" + topic + "”?",
    script:german ? "Starte mit dem konkreten Problem hinter deinem Thema. Beschreibe, wie der Prozess heute funktioniert.\n\nZeige dann an einem eigenen Beispiel, welcher kleine Schritt sich verbessern lässt. Ergänze hier deine geprüften Fakten und deine Erfahrung.\n\nBeende dein Video mit einer klaren Erkenntnis. Verzichte auf Versprechen, die du nicht belegen kannst.\n\nDas ist eine bearbeitbare Demo-Vorlage – noch kein recherchiertes oder AI-generiertes Skript." : "Start with the practical problem behind your topic. Describe the current process.\n\nShow one small improvement using your own example. Add verified facts and your experience here.\n\nFinish with one clear takeaway. Avoid promises you cannot support.\n\nThis is an editable demo template, not a researched or AI-generated script.",
    caption:german ? "Meine Gedanken zu: " + topic : "My thoughts on: " + topic,
    cta:german ? "Speichere dir diese Idee für später." : "Save this idea for later.",
    created_at:new Date().toISOString(),updated_at:new Date().toISOString()
  };
}
