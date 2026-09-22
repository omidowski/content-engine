"use client";
import { useEffect, useRef } from "react";
import { flushSync } from "react-dom";
import type { Content } from "./content";
type State = {mode:string;items:Content[];selected:number;busy:boolean;dirty:boolean;start:(topic:string)=>void};
type Registry = { registerTool:(tool:{name:string;title:string;description:string;inputSchema:object;annotations:object;execute:(input:unknown)=>unknown},options:{signal:AbortSignal})=>void|Promise<void> };
export function useStudioTools(state:State) {
  const latest=useRef(state); latest.current=state;
  useEffect(()=>{
    const registry=(document as Document & {modelContext?:Registry}).modelContext;
    if(!registry?.registerTool) return;
    const controller=new AbortController();
    const tools=[{
      name:"read_content_studio",title:"Content-Studio lesen",description:"Read the selected draft, current mode and draft summaries. Does not mutate data.",
      inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},
      execute:(input:unknown)=>{if(!input || typeof input!=="object" || Object.keys(input).length) throw new Error("Expected an empty object"); const s=latest.current; return {mode:s.mode,selectedId:s.selected,drafts:s.items.map(x=>({id:x.id,title:x.title,status:x.status})),unsavedChanges:s.dirty};}
    },{
      name:"start_short_draft",title:"Short-Entwurf vorbereiten",description:"Open the new-short form with a topic. Does not create, approve or render content. User submits the form.",
      inputSchema:{type:"object",properties:{topic:{type:"string",minLength:3,maxLength:250}},required:["topic"],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},
      execute:(input:unknown)=>{const x=input as {topic?:unknown};if(!x || typeof x.topic!=="string" || x.topic.trim().length<3 || x.topic.length>250 || Object.keys(x).some(k=>k!=="topic")) throw new Error("A topic of 3–250 characters is required");if(latest.current.busy || latest.current.dirty) throw new Error("Save current changes first");flushSync(()=>latest.current.start((x.topic as string).trim()));return {formOpened:true,created:false};}
    }];
    for(const tool of tools) { try { void Promise.resolve(registry.registerTool(tool,{signal:controller.signal})).catch(()=>{}); } catch {} }
    return ()=>controller.abort();
  },[]);
}
