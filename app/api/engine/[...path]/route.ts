import { env } from "cloudflare:workers";
import { getChatGPTUser } from "@/app/chatgpt-auth";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{path:string[]}> };
const allowed = (path:string,method:string) =>
  (path === "health" && method === "GET") ||
  (path === "publishing/connections" && method === "GET") ||
  (/^publishing\/connections\/(instagram|youtube)\/(connect|disconnect)$/.test(path) && method === "POST") ||
  (path === "publishing/jobs" && ["GET","POST"].includes(method)) ||
  (/^publishing\/jobs\/\d+\/(cancel|retry)$/.test(path) && method === "POST") ||
  (path === "publishing/automation" && ["GET","PUT"].includes(method)) ||
  (path === "content" && ["GET","POST"].includes(method)) ||
  (/^content\/\d+$/.test(path) && ["GET","PATCH"].includes(method)) ||
  (/^content\/\d+\/(approve|render|reopen)$/.test(path) && method === "POST") ||
  (/^content\/\d+\/video$/.test(path) && method === "GET");
function json(data:unknown,status=200) { return Response.json(data,{status,headers:{"Cache-Control":"no-store"}}); }

async function proxy(request:Request,context:Context) {
  const {path:parts}=await context.params;
  const path=parts.join("/");
  if(!allowed(path,request.method)) return json({detail:"Route nicht verfügbar."},404);
  const vars=env as unknown as Record<string,string|undefined>;
  const configured=!!(vars.CONTENT_ENGINE_URL && vars.CONTENT_ENGINE_TOKEN);
  if(!configured) return path === "health" ? json({configured:false,available:false,detail:"Die Python-Engine ist noch nicht verbunden."}) : json({detail:"Bitte zuerst die Python-Engine verbinden."},503);
  // Private Sites gateway owns authorization. Require its signed-in identity as defense in depth.
  if(!await getChatGPTUser()) return json({detail:"Bitte mit deinem ChatGPT-Konto anmelden."},401);
  if(request.method !== "GET") {
    const origin=request.headers.get("origin");
    if(origin && origin !== new URL(request.url).origin) return json({detail:"Anfrage von fremdem Ursprung abgelehnt."},403);
  }
  let base:URL;
  try { base=new URL(vars.CONTENT_ENGINE_URL!); } catch { return json({detail:"Engine-Adresse ist ungültig."},503); }
  if(base.protocol !== "https:" || base.username || base.password || base.search || base.hash) return json({detail:"Die Engine braucht eine gültige HTTPS-Adresse ohne Zugangsdaten."},503);
  const target=new URL(base.toString().replace(/\/$/,"") + "/" + path);
  if(new URL(request.url).searchParams.get("download") === "1") target.searchParams.set("download","1");
  const headers=new Headers({Authorization:"Bearer " + vars.CONTENT_ENGINE_TOKEN});
  let body:string|undefined;
  if(request.method !== "GET") {
    if(!request.headers.get("content-type")?.includes("application/json")) return json({detail:"JSON erwartet."},415);
    body=await request.text();
    if(body.length>32000) return json({detail:"Die Eingabe ist zu groß."},413);
    if(body) { try { JSON.parse(body); } catch { return json({detail:"Ungültiges JSON."},400); } }
    headers.set("Content-Type","application/json");
  }
  if(request.headers.get("range")) headers.set("Range",request.headers.get("range")!);
  try {
    // Workers support manual redirects; never forward the engine token to a redirect target.
    const upstream=await fetch(target,{method:request.method,headers,body,redirect:"manual",signal:AbortSignal.timeout(path.endsWith("/render")?300000:60000)});
    if(upstream.status >= 300 && upstream.status < 400) {
      await upstream.body?.cancel();
      throw new Error("Engine redirects are not allowed");
    }
    if(path === "health") {
      if(!upstream.ok) return json({configured:true,available:false,detail:"Engine antwortet nicht korrekt. Server und Zugriffstoken prüfen."});
      const health=await upstream.json() as {mode?:string;ffmpeg_available?:boolean};
      return json({configured:true,available:true,mode:health.mode,ffmpeg_available:health.ffmpeg_available});
    }
    if(!upstream.ok) {
      if(path.startsWith("publishing/") && upstream.status === 409) {
        const problem=await upstream.json().catch(()=>({})) as {detail?:unknown};
        return json({detail:typeof problem.detail === "string" ? problem.detail : "Veröffentlichung noch nicht verfügbar."},409);
      }
      const detail=upstream.status === 409 ? "Dieser Schritt ist im aktuellen Status nicht möglich. Inhalt neu auswählen und erneut versuchen." : upstream.status === 422 ? "Bitte Eingaben prüfen; mindestens ein Feld ist ungültig." : upstream.status === 404 ? "Inhalt oder Video nicht gefunden." : "Die Engine konnte den Auftrag nicht abschließen. Serverprotokoll und Konfiguration prüfen.";
      return json({detail},upstream.status>=500?502:upstream.status);
    }
    const responseHeaders=new Headers({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"});
    for(const name of ["Content-Type","Content-Length","Content-Range","Accept-Ranges","Content-Disposition"]) { const value=upstream.headers.get(name); if(value) responseHeaders.set(name,value); }
    return new Response(upstream.body,{status:upstream.status,headers:responseHeaders});
  } catch {
    if(path === "health") return json({configured:true,available:false,detail:"Engine nicht erreichbar. HTTPS-Adresse und Server prüfen."});
    return json({detail:"Verbindung zur Engine unterbrochen. Der Auftrag kann weiterlaufen. Inhalt neu auswählen, bevor du erneut startest."},502);
  }
}
export const GET=proxy;
export const POST=proxy;
export const PATCH=proxy;
export const PUT=proxy;
