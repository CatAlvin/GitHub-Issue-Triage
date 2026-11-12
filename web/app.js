"use strict";
const $ = (selector, root=document) => root.querySelector(selector);
const esc = (value="") => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const readStore = (store, key, fallback) => {try{return JSON.parse(store.getItem(key)) ?? fallback;}catch{return fallback;}};
const writeStore = (store,key,value) => {try{store.setItem(key,JSON.stringify(value));}catch{/* UI remains usable with storage disabled. */}};
const state={data:null,view:"overview",query:"",filter:"",status:"",taskFilter:"all",answer:null,question:"",asking:false,brief:null,busy:false,done:{},periodDays:7};
const content=$("#content");
const detail=$("#detail-dialog");
let toastTimer;
function toast(message){$("#toast").textContent=message;$("#toast").hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$("#toast").hidden=true,3200);}
function date(value, time=false){if(!value)return "";const normalized=value.replace("Z","").split("T");return normalized[0].replaceAll("-",".")+(time&&normalized[1]?" · "+normalized[1].slice(0,5):"");}
function short(value,limit=125){return value.length>limit?value.slice(0,limit).trimEnd()+"…":value;}
function taskKey(task){return [task.task,task.owner,task.due].join("|");}
function complete(task){return !!state.done[taskKey(task)];}
function team(){return state.data?.kind==="team";}
function record(id){return state.data.records.find(r=>r.id===String(id));}
function tag(value,cls=""){return '<span class="tag '+cls+'">'+esc(value)+'</span>';}
function sourceName(source){return source.split("#")[0];}
function safeLink(url){try{const u=new URL(url);return u.protocol==="https:"&&u.hostname==="github.com"?u.href:null;}catch{return null;}}
async function api(path,options={}){
  const headers={"Content-Type":"application/json",...options.headers};
  const token=readStore(sessionStorage,"workspace-token","");
  if(token)headers.Authorization="Bearer "+token;
  const response=await fetch(path,{...options,headers,signal:AbortSignal.timeout(90000)});
  if(response.status===401){const error=new Error("请连接工作区后继续");error.auth=true;throw error;}
  if(!response.ok)throw new Error(response.status===422?"请检查输入内容后再试一次":"这次请求未完成，请重试");
  return response.json();
}
function errorState(message){return '<div class="panel empty-state"><strong>重新连接工作区</strong><p>'+esc(message)+'</p><button class="button primary" data-action="reload">重新加载</button></div>';}
async function load(){
  $("#refresh-button").disabled=true;$("#export-button").disabled=true;content.innerHTML='<div class="loading-state"><span class="spinner"></span>正在整理工作区…</div>';
  try{
    state.data=await api("/workspace");state.done=readStore(localStorage,"workbench-done-"+state.data.kind,{});
    $("#project-title").textContent=state.data.title;document.title=state.data.title+" · 协作工作台";
    $("#project-select").innerHTML=state.data.projects.map(p=>'<option value="'+esc(p.url)+'"'+(p.id===state.data.kind?" selected":"")+'>'+esc(p.title)+'</option>').join("");
    $("#data-date").textContent="数据日期  "+date(state.data.period_end);
    $("#records-nav").textContent=team()?"消息记录":"Issue 记录";$("#actions-nav").textContent=team()?"行动项":"风险关注";
    $("#action-count").textContent=(team()?state.data.tasks.length:state.data.risks.length)||"";
    $("#footer-project").textContent=state.data.title+" / ChengLan";$("#footer-count").textContent=state.data.records.length+(team()?" 条消息":" 条 Issue")+" · "+state.data.documents.length+" 份资料";
    render();$("#export-button").disabled=false;
  }catch(error){content.innerHTML=errorState(error.message);if(error.auth&&!$("#auth-dialog").open)$("#auth-dialog").showModal();}
  finally{$("#refresh-button").disabled=false;}
}
const views={
  overview:["项目概览","工作概况"],
  records:["消息记录","内容浏览"],
  actions:["行动项","工作跟进"],
  knowledge:["知识问答","资料检索"]
};
function render(){
  if(!state.data)return;
  state.view=location.hash.slice(1)||"overview";if(!views[state.view])state.view="overview";
  document.querySelectorAll("[data-view]").forEach(a=>{if(a.dataset.view===state.view)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");});
  let title=views[state.view][0];if(!team()&&state.view==="records")title="Issue 记录";if(!team()&&state.view==="actions")title="风险关注";
  $("#page-title").textContent=title;$("#section-label").textContent=views[state.view][1];
  const descriptions={
    overview:team()?"汇总频道动态，查看行动项与关注事项。":"查看 Issue 动态、标签分布与本期重点。",
    records:team()?"按频道浏览消息，展开查看完整上下文。":"按状态与标签查找 Issue，查看问题详情。",
    actions:team()?"跟进负责人、完成日期与处理进度。":"查看规则命中与对应的 Issue 证据。",
    knowledge:"输入问题，从项目资料中查找答案与出处。"
  };
  $("#page-description").textContent=descriptions[state.view];
  content.innerHTML=({overview:overview,records:recordsPage,actions:actionsPage,knowledge:knowledgePage}[state.view])();
}
function stats(){
  const d=state.data;
  const entries=team()?[
    ["消息总数",d.records.length,"覆盖 "+Object.keys(d.groups).length+" 个频道"],
    ["行动项",d.tasks.length, d.tasks.filter(t=>complete(t)).length+" 项已完成"],
    ["关注事项",d.risks.length,"按优先级整理"],
    ["知识资料",d.documents.length,"来源随答案呈现"]
  ]:[
    ["Issue 总数",d.records.length,"microsoft/vscode"],
    ["处理中",d.records.filter(r=>r.state==="open").length,"当前状态为 Open"],
    ["风险关注",d.risks.length,"已完成规则检查"],
    ["标签类型",Object.keys(d.groups).length,"按现有标签归类"]
  ];
  return '<div class="stats">'+entries.map(([label,value,note])=>'<div class="stat"><span class="stat-label">'+label+'</span><div class="stat-value">'+value+'</div><span class="stat-note">'+esc(note)+'</span></div>').join("")+'</div>';
}
function panelHead(title,subtitle="",action=""){return '<div class="panel-head"><div><h2>'+esc(title)+'</h2>'+(subtitle?'<p class="muted">'+esc(subtitle)+'</p>':"")+'</div>'+action+'</div>';}
function chart(){
  const groups=Object.entries(state.data.groups).sort((a,b)=>b[1]-a[1]).slice(0,6);
  const max=Math.max(...groups.map(g=>g[1]),1);
  return '<section class="panel">'+panelHead(team()?"频道分布":"标签分布",team()?"当前消息按频道统计":"按出现次数排序")+'<div class="panel-body progress-list">'+groups.map(([name,n])=>'<div><div class="bar-label"><span>'+esc(name)+'</span><span>'+n+'</span></div><div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:'+(n/max*100)+'%"></div></div></div>').join("")+'</div></section>';
}
function briefPanel(){
  if(!team())return '<section class="panel">'+panelHead("近期 Issue","按 Issue 创建时间排序",'<button class="button quiet" data-action="navigate" data-view="records">查看全部</button>')+state.data.records.slice(0,5).map(r=>recordRow(r,true)).join("")+'</section>';
  return '<section class="panel">'+panelHead("频道摘要",date(state.data.period_start)+" 至 "+date(state.data.period_end),'<button id="generate-button" class="button quiet" data-action="generate">生成简报</button>')+
    state.data.briefs.map(group=>'<div class="brief-channel"><div class="channel-title"><strong>'+esc(group.title)+'</strong><span>'+group.count+' 条消息</span></div>'+
    (state.brief?.summaries?.[group.title]?'<div class="generated-summary">'+esc(state.brief.summaries[group.title].replace(/^Offline extractive summary:\n/,""))+'</div>':'<ul class="excerpt-list">'+group.items.slice(0,3).map(item=>'<li class="excerpt-item"><button data-action="record" data-id="'+esc(item.id)+'">'+esc(short(item.text,160))+'</button></li>').join("")+'</ul>')+'</div>').join("")+'</section>';
}
function taskRow(task,index){
  const done=complete(task);
  return '<div class="task-row '+(done?"done":"")+'"><label class="task-check-label"><input class="task-check" type="checkbox" data-task="'+index+'" '+(done?"checked":"")+' aria-label="完成任务：'+esc(task.task)+'"></label><div class="task-text"><p>'+esc(task.task)+'</p><div class="task-meta"><span>'+esc(task.owner||"待分配")+'</span><span>'+esc(task.due||"待安排")+'</span>'+tag(done?"已完成":"待跟进",done?"green":"")+'</div></div><span class="task-side">'+esc(({high:"高优先级",medium:"中优先级",low:"低优先级"})[task.priority]||"")+'</span></div>';
}
function tasksPanel(compact=false){
  const tasks=state.data.tasks.map((t,i)=>({t,i})).filter(({t})=>state.taskFilter==="all"||(state.taskFilter==="done"?complete(t):!complete(t)));
  return '<section class="panel">'+(compact?panelHead("行动项",state.data.tasks.length+" 项已整理",'<button class="button quiet" data-action="navigate" data-view="actions">查看全部</button>'):'<div class="task-progress"><span>'+state.data.tasks.filter(complete).length+' / '+state.data.tasks.length+' 项已完成</span><span>按负责人跟进</span></div>')+
    (tasks.length?tasks.map(({t,i})=>taskRow(t,i)).join(""):'<div class="empty-state"><strong>'+(state.taskFilter==="done"?"从一项任务开始":"当前列表已整理完成")+'</strong><p>'+(state.taskFilter==="done"?"勾选任务后，可在这里查看完成记录。":"可以切换列表继续查看。")+'</p></div>')+'</section>';
}
function riskRows(limit=100){
  const risks=state.data.risks.slice(0,limit);
  return risks.length?risks.map((risk,index)=>'<div class="risk-preview"><div class="risk-meta">'+tag(team()?(risk.severity==="high"?"重点关注":"持续跟进"):ruleName(risk.rule),"attention")+'<span>'+esc(risk.channel||"#"+risk.thread_id)+'</span></div><button data-action="risk" data-index="'+index+'">'+esc(risk.text||risk.evidence)+'</button></div>').join(""):'<div class="empty-state"><strong>检查完成</strong><p>当前 '+state.data.records.length+' 条 Issue 无规则命中。</p><button class="button quiet" data-action="navigate" data-view="records">查看 Issue 记录</button></div>';
}
function ruleName(name){return ({unaddressed_security:"安全问题跟进",severity_keyword_match:"严重问题关注",fast_escalating_regression:"回归问题跟进"})[name]||name;}
function riskPanel(){return '<section class="panel">'+panelHead("关注事项",team()?"按消息信号整理":"检查结果与证据",'<button class="button quiet" data-action="'+(team()?"risks":"navigate")+'" data-view="actions">查看全部</button>')+riskRows(3)+'</section>';}
function overview(){
  return stats()+'<div class="overview-grid"><div class="stack">'+briefPanel()+(team()?tasksPanel(true):'<section class="panel">'+panelHead("本期简报","汇总时间窗口内的 Issue 与风险")+'<div class="panel-body"><div class="toolbar"><label for="period-select" class="small muted">时间窗口</label><select id="period-select">'+[7,30,90].map(days=>'<option value="'+days+'" '+(state.periodDays===days?"selected":"")+'>最近 '+days+' 天</option>').join("")+'</select><button class="button primary" data-action="generate">生成简报</button></div><p class="small muted">统计日期 '+date(state.data.reference_time)+'</p></div></section>')+'</div><div class="stack">'+chart()+riskPanel()+'</div></div>';
}
function recordRow(r,compact=false){
  const title=team()?short(r.text,compact?150:190):r.title;
  return '<div class="record-row"><div><button class="record-title" data-action="record" data-id="'+esc(r.id)+'">'+esc(title)+'</button><div class="record-meta"><span>'+esc(r.author)+'</span>'+
    (team()?tag(r.channel):(tag(r.state==="open"?"处理中":"已关闭",r.state==="open"?"green":"")+r.labels.slice(0,2).map(l=>tag(l)).join("")))+'</div></div><div class="record-right"><span class="record-id">'+(team()?esc(r.id):"#"+esc(r.id))+'</span><span>'+date(r.time,!compact)+'</span></div></div>';
}
function filteredRecords(){return state.data.records.filter(r=>{
  const q=state.query.trim().toLowerCase();
  return (!q||(r.text+" "+r.id+" "+r.author).toLowerCase().includes(q))&&(!state.filter||(team()?r.channel===state.filter:r.labels.includes(state.filter)))&&(!state.status||r.state===state.status);
});}
function recordList(){
  const rows=filteredRecords();
  const count=$("#filter-count");if(count)count.textContent=rows.length+" 条结果";
  return rows.length?rows.map(r=>recordRow(r)).join(""):'<div class="empty-state"><strong>试试其他关键词</strong><p>调整搜索或筛选条件，继续查找内容。</p><button class="button secondary" data-action="clear-filters">清除筛选</button></div>';
}
function recordsPage(){
  const options=Object.keys(state.data.groups).sort();
  const rows=filteredRecords();
  return '<div class="toolbar"><label class="search-field"><span class="sr-only">搜索记录</span><input id="record-search" type="search" placeholder="'+(team()?"搜索消息、成员或编号":"搜索 Issue、作者或编号")+'" value="'+esc(state.query)+'"></label><label class="sr-only" for="group-filter">筛选'+(team()?"频道":"标签")+'</label><select id="group-filter"><option value="">全部'+(team()?"频道":"标签")+'</option>'+options.map(g=>'<option '+(g===state.filter?"selected":"")+' value="'+esc(g)+'">'+esc(g)+'</option>').join("")+'</select>'+
    (!team()?'<label class="sr-only" for="state-filter">筛选状态</label><select id="state-filter"><option value="">全部状态</option><option value="open" '+(state.status==="open"?"selected":"")+'>处理中</option><option value="closed" '+(state.status==="closed"?"selected":"")+'>已关闭</option></select>':"")+
    '<span class="filter-count" id="filter-count">'+rows.length+' 条结果</span></div><section class="panel" id="record-list">'+recordList()+'</section>';
}
function actionsPage(){
  if(!team())return '<section class="panel">'+panelHead("风险检查",state.data.records.length+" 条 Issue · 3 项规则")+riskRows()+'</section>';
  return '<div class="toolbar"><div class="tabs" aria-label="任务状态">'+[["all","全部任务"],["pending","待跟进"],["done","已完成"]].map(([key,label])=>'<button data-action="task-filter" data-filter="'+key+'" aria-pressed="'+(state.taskFilter===key)+'">'+label+'</button>').join("")+'</div></div>'+tasksPanel();
}
function knowledgePage(){
  const suggestions=team()?["Are webhooks signed?","Were customers double charged?","How do we handle incidents?"]:["How do I report a bug?","How can I contribute?","How do I submit a pull request?"];
  return '<div class="knowledge-grid"><section class="panel"><div class="question-intro"><h2>查找项目资料</h2><p>选择常见问题，或输入具体内容。</p><div class="suggestions">'+suggestions.map(q=>'<button class="suggestion" data-action="suggest" data-question="'+esc(q)+'">'+esc(q)+'</button>').join("")+'</div></div><form id="ask-form" class="ask-form"><label for="question">你的问题</label><textarea id="question" name="question" placeholder="例如：'+esc(suggestions[0])+'" minlength="3" maxlength="2000" required>'+esc(state.question)+'</textarea><div class="form-bottom"><span class="form-note">'+state.data.documents.length+' 份项目资料可供检索</span><button class="button primary" id="ask-button" type="submit" '+(state.asking?"disabled":"")+'>'+(state.asking?"正在查找…":"查找答案")+'</button></div></form><div id="answer-area" class="answer-area">'+answerContent()+'</div></section><section class="panel">'+panelHead("项目资料",state.data.documents.length+" 份文档")+state.data.documents.map(d=>'<button class="document-row" data-action="document" data-source="'+esc(d.name)+'"><span class="document-name">'+esc(d.title)+'</span><span class="document-file">'+esc(d.name)+'</span></button>').join("")+'</section></div>';
}
function answerContent(){
  if(state.asking)return '<div class="loading-state"><span class="spinner"></span>正在查找相关资料…</div>';
  if(!state.answer)return "";
  const answer=state.answer;
  if(answer.error)return '<div class="empty-state"><strong>再试一次</strong><p>'+esc(answer.error)+'</p><button class="button secondary" data-action="ask-again">重新查找</button></div>';
  if(answer.refused)return '<div class="empty-state"><strong>换个问法继续查找</strong><p>可以加入具体的功能名称，或从上方问题开始。</p></div>';
  return '<div class="answer-question">'+esc(answer.question)+'</div><div class="answer-heading"><strong>相关内容</strong><button class="button quiet" data-action="copy-answer">复制内容</button></div><div class="answer-body markdown">'+WorkbenchMarkdown.render(answer.answer)+'</div><div class="source-links">'+answer.sources.map(s=>'<button class="source-link" data-action="document" data-source="'+esc(sourceName(s))+'">查看来源 · '+esc(s)+'</button>').join("")+'</div>';
}
function openDetail(title,label,body){
  $("#detail-title").textContent=title;$("#detail-label").textContent=label;$("#detail-content").innerHTML=body;
  if(!detail.open)detail.showModal();
}
function showRecord(id){
  const r=record(id);if(!r)return;
  const link=safeLink(r.url);
  openDetail(team()?r.id:r.title,team()?"消息详情":"Issue #"+r.id,'<div class="detail-meta"><span>'+esc(r.author)+'</span><span>'+date(r.time,true)+'</span>'+tag(r.channel)+'</div><div class="detail-text">'+esc(r.text)+'</div>'+(link?'<div class="detail-footer"><a class="button primary" target="_blank" rel="noopener noreferrer" href="'+esc(link)+'">打开 GitHub Issue ↗</a></div>':""));
}
async function showDocument(name){
  openDetail(name,"项目资料",'<div class="loading-state"><span class="spinner"></span>正在打开资料…</div>');
  try{const doc=await api("/workspace/documents/"+encodeURIComponent(name));if(detail.open&&$("#detail-title").textContent===name)$("#detail-content").innerHTML='<div class="detail-text markdown">'+WorkbenchMarkdown.render(doc.text)+'</div>';}
  catch(error){$("#detail-content").innerHTML='<div class="empty-state"><p>'+esc(error.message)+'</p><button class="button secondary" data-action="document" data-source="'+esc(name)+'">重新打开</button></div>';}
}
async function askQuestion(){
  if(state.asking)return;
  const question=$("#question")?.value.trim()||state.question;
  if(question.length<3||question.length>2000){toast("请输入 3 至 2000 个字符的问题");return;}
  state.question=question;state.asking=true;state.answer=null;
  if(state.view==="knowledge")render();
  try{state.answer=await api("/workspace/ask",{method:"POST",body:JSON.stringify({question})});}
  catch(error){state.answer={error:error.message};}
  finally{state.asking=false;if(state.view==="knowledge"){render();$("#answer-area").scrollIntoView({block:"nearest",behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});}}
}
async function generateBrief(show=true){
  if(state.busy)return null;state.busy=true;
  const button=$('[data-action="generate"]');if(button){button.disabled=true;button.textContent="正在整理…";}
  const days=state.periodDays;
  try{
    const result=await api("/workspace/brief",{method:"POST",body:JSON.stringify({days})});state.brief=result;
    if(team()){state.data.tasks=result.tasks;state.data.risks=result.alerts;$("#action-count").textContent=result.tasks.length||"";}
    if(show){
      if(team()){render();toast("简报已整理完成");}
      else openDetail("本期简报","最近 "+days+" 天",'<p class="muted small">'+result.issue_count+' 条 Issue · '+date(result.reference_time)+'</p><div class="detail-text">'+result.items.map(i=>'<p style="margin-bottom:15px">#'+esc(i.id)+' · '+esc(i.title)+'</p>').join("")+'</div>');
    }
    return result;
  }catch(error){toast(error.message);return null;}
  finally{state.busy=false;const current=$('[data-action="generate"]');if(current){current.disabled=false;current.textContent="生成简报";}}
}
async function exportBrief(){
  const button=$("#export-button");button.disabled=true;button.textContent="正在导出…";
  try{
    const result=state.brief||await generateBrief(false);if(!result)return;
    const output={project:state.data.title,data_date:state.data.period_end,...result};
    if(team())output.review_state=state.data.tasks.map(t=>({task:t.task,completed:complete(t)}));
    const url=URL.createObjectURL(new Blob([JSON.stringify(output,null,2)],{type:"application/json;charset=utf-8"}));
    const a=document.createElement("a");a.href=url;a.download=state.data.kind+"-brief-"+state.data.period_end.slice(0,10)+".json";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);toast("简报已导出");
  }finally{button.disabled=false;button.innerHTML='导出简报 <span aria-hidden="true">↗</span>';}
}
content.addEventListener("input",event=>{
  if(event.target.id==="record-search"){state.query=event.target.value;$("#record-list").innerHTML=recordList();}
  if(event.target.id==="question")state.question=event.target.value;
});
content.addEventListener("change",event=>{
  const el=event.target;
  if(el.id==="period-select"){state.periodDays=Number(el.value);state.brief=null;}
  if(el.id==="group-filter"||el.id==="state-filter"){if(el.id==="group-filter")state.filter=el.value;else state.status=el.value;$("#record-list").innerHTML=recordList();}
  if(el.matches("[data-task]")){
    const task=state.data.tasks[Number(el.dataset.task)];state.done[taskKey(task)]=el.checked;
    writeStore(localStorage,"workbench-done-"+state.data.kind,state.done);
    const activeIndex=el.dataset.task;render();$('[data-task="'+activeIndex+'"]')?.focus();
    toast(el.checked?"任务已完成":"任务已恢复跟进");
  }
});
document.addEventListener("submit",event=>{if(event.target.id==="ask-form"){event.preventDefault();askQuestion();}});
document.addEventListener("click",async event=>{
  const control=event.target.closest("[data-action]");if(!control)return;
  const action=control.dataset.action;
  if(action==="reload")load();
  if(action==="navigate")location.hash=control.dataset.view;
  if(action==="record")showRecord(control.dataset.id);
  if(action==="document")showDocument(control.dataset.source);
  if(action==="task-filter"){state.taskFilter=control.dataset.filter;render();}
  if(action==="clear-filters"){state.query="";state.filter="";state.status="";render();$("#record-search")?.focus();}
  if(action==="generate")generateBrief();
  if(action==="suggest"){$("#question").value=control.dataset.question;state.question=control.dataset.question;$("#question").focus();}
  if(action==="ask-again")askQuestion();
  if(action==="copy-answer"){
    try{await navigator.clipboard.writeText(state.answer.answer);toast("内容已复制");}catch{toast("请选中回答内容后复制");}
  }
  if(action==="risk"){const risk=state.data.risks[Number(control.dataset.index)];showRecord(risk.message_id||risk.thread_id);}
  if(action==="risks")openDetail("关注事项","全部 "+state.data.risks.length+" 项",riskRows());
});
function setTheme(theme){document.documentElement.dataset.theme=theme;writeStore(localStorage,"workbench-theme",theme);$("#theme-button").textContent=theme==="dark"?"切换浅色":"切换深色";const mobile=$("#theme-mobile");if(mobile)mobile.textContent=theme==="dark"?"浅色":"深色";}
$("#theme-button").addEventListener("click",()=>setTheme(document.documentElement.dataset.theme==="dark"?"light":"dark"));
$("#theme-mobile")?.addEventListener("click",()=>setTheme(document.documentElement.dataset.theme==="dark"?"light":"dark"));
$("#refresh-button").addEventListener("click",()=>{state.brief=null;load();});
$("#export-button").addEventListener("click",exportBrief);
$("#project-select").addEventListener("change",event=>{location.href=event.target.value;});
$("[data-close]",detail).addEventListener("click",()=>detail.close());
detail.addEventListener("click",event=>{if(event.target===detail){const box=detail.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)detail.close();}});
$("#auth-form").addEventListener("submit",async event=>{
  event.preventDefault();const token=$("#access-token").value;writeStore(sessionStorage,"workspace-token",token);
  try{await api("/workspace");$("#auth-dialog").close();$("#auth-error").textContent="";$("#access-token").value="";load();}
  catch{$("#auth-error").textContent="请检查令牌后重新连接";}
});
window.addEventListener("hashchange",()=>{render();window.scrollTo({top:0,behavior:"instant"});});
$(".skip-link").addEventListener("click",event=>{event.preventDefault();$("#main").focus();$("#main").scrollIntoView();});
setTheme(readStore(localStorage,"workbench-theme","light"));
load();

