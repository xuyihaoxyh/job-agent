const $ = selector => document.querySelector(selector);
const form = $('#analysisForm'), button = $('#submitButton'), buttonLabel = $('#submitButton span');
const placeholder = $('#placeholder'), loading = $('#loading'), result = $('#result'), errorBox = $('#errorBox');
const value = id => $(`#${id}`).value.trim();
const splitList = text => text.split(/[,，]/).map(item => item.trim()).filter(Boolean);
const clear = element => { while (element.firstChild) element.removeChild(element.firstChild); };
const addText = (parent, tag, text, className) => { const node=document.createElement(tag); node.textContent=text; if(className) node.className=className; parent.appendChild(node); return node; };
const money = amount => amount == null ? null : `${Math.round(amount / 1000)}K`;
const confidenceText = { high:'高可信度', medium:'中可信度', low:'低可信度' };
const sourceTypeText = {official:'官网',recruitment:'招聘平台',media:'媒体',community:'社区',other:'其他'};
const qualityText = {high:'高质量',medium:'中等质量',low:'低质量'};
const sectionStatusText = {completed:'已完成',not_requested:'未请求',insufficient:'信息不足',degraded:'已降级',failed:'失败'};
const nodeLabels = {intake:'输入校验',jd:'JD 解析',supervisor:'Supervisor',planner:'Planner',company:'公司检索',salary:'薪资检索',match:'匹配计算',report:'报告生成'};
let currentUser=null,currentProfile=null;

async function api(url,options={}) { const response=await fetch(url,{...options,credentials:'same-origin'});let body=null;if(response.status!==204){try{body=await response.json();}catch{body={};}}if(!response.ok){const error=new Error(body?.detail||`请求失败（${response.status}）`);error.status=response.status;throw error;}return body; }
function initials(user){return (user?.display_name||user?.username||'U').trim().slice(0,1).toUpperCase();}
function renderAccount(user){currentUser=user;$('#topAvatar').textContent=initials(user);$('#topAccountName').textContent=user.display_name;$('#profileAvatar').textContent=initials(user);$('#profileUsername').textContent=`@${user.username}`;$('#profileEmail').textContent=user.email;$('#displayName').value=user.display_name;}
function profilePayloadFromCenter(){const years=Number(value('profileExperience'));return{preferred_locations:splitList(value('profileLocations')),preferred_roles:splitList(value('profileRoles')),skills:splitList(value('profileSkills')),education:value('profileEducation')||null,years_of_experience:value('profileExperience')&&Number.isFinite(years)?years:null,experiences:$('#profileExperiences').value.split(/\r?\n/).map(item=>item.trim()).filter(Boolean)};}
function applyProfile(profile){currentProfile=profile||null;const data=profile||{preferred_locations:[],preferred_roles:[],skills:[],education:null,years_of_experience:null,experiences:[]};$('#skills').value=(data.skills||[]).join(', ');$('#education').value=data.education||'';$('#experience').value=data.years_of_experience??'';$('#location').value=data.preferred_locations?.[0]||'';$('#profileSkills').value=(data.skills||[]).join(', ');$('#profileEducation').value=data.education||'';$('#profileExperience').value=data.years_of_experience??'';$('#profileLocations').value=(data.preferred_locations||[]).join(', ');$('#profileRoles').value=(data.preferred_roles||[]).join(', ');$('#profileExperiences').value=(data.experiences||[]).join('\n');const state=$('#profileState');state.textContent=profile?'已从账户加载':'首次分析后自动保存';state.classList.toggle('saved',Boolean(profile));}
async function loadProfile(){try{const body=await api('/api/v1/profile');applyProfile(body.profile);}catch(error){if(error.status===401)showAuth();}}
function showApp(user){renderAccount(user);$('#authScreen').classList.add('hidden');$('#appShell').classList.remove('hidden');loadProfile();}
function resetWorkspace(){applyProfile(null);['companyName','jobTitle','jdText'].forEach(id=>{$(`#${id}`).value='';});$('#employmentType').value='social';result.classList.add('hidden');loading.classList.add('hidden');errorBox.classList.add('hidden');placeholder.classList.remove('hidden');}
function showAuth(){currentUser=null;resetWorkspace();selectAuthMode('login');$('#appShell').classList.add('hidden');$('#profileModal').classList.add('hidden');$('#accountMenu').classList.add('hidden');$('#accountButton').setAttribute('aria-expanded','false');$('#authScreen').classList.remove('hidden');}
function authError(message){const node=$('#authError');node.textContent=message;node.classList.toggle('hidden',!message);}
function selectAuthMode(mode){const login=mode==='login';$('#loginTab').classList.toggle('active',login);$('#registerTab').classList.toggle('active',!login);$('#loginForm').classList.toggle('hidden',!login);$('#registerForm').classList.toggle('hidden',login);$('#authTitle').textContent=login?'欢迎回来':'创建账户';$('#authSubtitle').textContent=login?'登录后开始你的岗位分析':'创建账户并保存个人分析资料';authError('');}

$('#loginTab').addEventListener('click',()=>selectAuthMode('login'));$('#registerTab').addEventListener('click',()=>selectAuthMode('register'));
$('#loginForm').addEventListener('submit',async event=>{event.preventDefault();authError('');try{const body=await api('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:value('loginIdentity'),password:$('#loginPassword').value})});showApp(body.user);}catch(error){authError(error.message);}});
$('#registerForm').addEventListener('submit',async event=>{event.preventDefault();authError('');try{const body=await api('/api/v1/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:value('registerUsername'),email:value('registerEmail'),password:$('#registerPassword').value})});showApp(body.user);}catch(error){authError(error.message);}});
$('#accountButton').addEventListener('click',()=>{const menu=$('#accountMenu'),open=menu.classList.toggle('hidden')===false;$('#accountButton').setAttribute('aria-expanded',String(open));});
$('#profileButton').addEventListener('click',()=>{$('#accountMenu').classList.add('hidden');$('#accountButton').setAttribute('aria-expanded','false');renderAccount(currentUser);$('#profileModal').classList.remove('hidden');loadHistory();});
const closeProfile=()=>{$('#profileModal').classList.add('hidden');$('#profileError').classList.add('hidden');};$('#closeProfile').addEventListener('click',closeProfile);$('#cancelProfile').addEventListener('click',closeProfile);$('#profileModal').addEventListener('click',event=>{if(event.target===$('#profileModal'))closeProfile();});
$('#profileForm').addEventListener('submit',async event=>{event.preventDefault();const errorNode=$('#profileError');errorNode.classList.add('hidden');try{const [account,profile]=await Promise.all([api('/api/v1/auth/me',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:value('displayName')})}),api('/api/v1/profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(profilePayloadFromCenter())})]);renderAccount(account.user);applyProfile(profile.profile);closeProfile();}catch(error){errorNode.textContent=error.message;errorNode.classList.remove('hidden');}});
$('#logoutButton').addEventListener('click',async()=>{try{await api('/api/v1/auth/logout',{method:'POST'});}finally{showAuth();}});
document.addEventListener('click',event=>{if(!event.target.closest('.account')){$('#accountMenu').classList.add('hidden');$('#accountButton').setAttribute('aria-expanded','false');}});

function formatHistoryTime(value) {
  const date=new Date(value);return Number.isNaN(date.getTime())?'时间未知':date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
}

async function restoreAnalysis(threadId) {
  const historyList=$('#historyList');historyList.setAttribute('aria-busy','true');
  try {
    const body=await api(`/api/v1/threads/${encodeURIComponent(threadId)}`),values=body.values||{};
    renderAnalysis({...values,thread_id:body.thread_id,elapsed_ms:null});
    closeProfile();
    result.scrollIntoView({behavior:'smooth',block:'start'});
  } catch(error) {
    clear(historyList);addText(historyList,'div',error.message||'历史记录恢复失败','error');
  } finally { historyList.removeAttribute('aria-busy'); }
}

async function loadHistory() {
  const container=$('#historyList');clear(container);addText(container,'small','正在加载…');
  try {
    const body=await api('/api/v1/analyses?limit=20');clear(container);
    if(!body.items?.length){addText(container,'div','还没有分析记录','history-empty');return;}
    body.items.forEach(item=>{const entry=addText(container,'button','', 'history-item');entry.type='button';addText(entry,'strong',`${item.company_name}${item.job_title?` · ${item.job_title}`:''}`);addText(entry,'span',item.match_score==null?'未评分':`${item.match_score}/100`);addText(entry,'small',`${formatHistoryTime(item.updated_at)} · ${item.recommendation||item.status}`);entry.addEventListener('click',()=>restoreAnalysis(item.thread_id));});
  } catch(error) {clear(container);addText(container,'div',error.message||'历史记录加载失败','error');}
}

$('#refreshHistory').addEventListener('click',loadHistory);

function setConfidence(selector, level) { const node=$(selector); node.className=`pill confidence ${level || 'low'}`; node.textContent=confidenceText[level] || confidenceText.low; }
function setSectionStatus(selector,status){const value=status?.status||'not_requested',node=$(selector);node.className=`pill section-status ${value}`;node.textContent=sectionStatusText[value]||value;node.title=status?.message||'';}

function appendSourceMeta(parent,source){const meta=addText(parent,'div','', 'source-meta');addText(meta,'span',sourceTypeText[source.source_type]||'其他');addText(meta,'span',qualityText[source.quality]||'质量未知');addText(meta,'span',source.published_at?`发布 ${new Date(source.published_at).toLocaleDateString('zh-CN')}`:'发布时间未知 · 新鲜度未知');if(source.accessed_at)addText(meta,'span',`访问 ${new Date(source.accessed_at).toLocaleDateString('zh-CN')}`);const decision=addText(meta,'span',source.decision==='rejected'?'未采纳':'已采纳','source-decision');decision.title=source.decision_reason||'';}
function appendSource(parent,source,index,className='source'){const link=addText(parent,'a',`${index}. ${source.title}`,`${className}${source.decision==='rejected'?' rejected':''}`);link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';addText(link,'small',source.decision_reason||source.url);appendSourceMeta(link,source);return link;}

function appendInline(parent, text) {
  const pattern=/(\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?:\/\/[^)]+)\))/g; let cursor=0,match;
  while((match=pattern.exec(text))!==null){if(match.index>cursor)parent.appendChild(document.createTextNode(text.slice(cursor,match.index)));if(match[2])addText(parent,'strong',match[2]);else{const link=addText(parent,'a',match[3]);link.href=match[4];link.target='_blank';link.rel='noopener noreferrer';}cursor=pattern.lastIndex;}
  if(cursor<text.length)parent.appendChild(document.createTextNode(text.slice(cursor)));
}

function renderMarkdown(markdown) {
  const container=$('#report');clear(container);const lines=(markdown||'没有生成报告。').split(/\r?\n/);let list=null;
  for(const raw of lines){const line=raw.trim();if(!line){list=null;continue;}const heading=line.match(/^(#{1,3})\s+(.+)$/);if(heading){list=null;const node=document.createElement(`h${heading[1].length}`);appendInline(node,heading[2]);container.appendChild(node);continue;}if(line.startsWith('- ')){if(!list){list=document.createElement('ul');container.appendChild(list);}const item=document.createElement('li');appendInline(item,line.slice(2));list.appendChild(item);continue;}list=null;const paragraph=document.createElement('p');appendInline(paragraph,line);container.appendChild(paragraph);}
}

function renderMatch(match) {
  $('#score').textContent=match?`${match.score}/100`:'—';$('#recommendation').textContent=match?.recommendation||'—';const dimensions=$('#dimensions');clear(dimensions);
  (match?.score_dimensions||[]).forEach(item=>{const row=addText(dimensions,'div','', 'dimension'),head=addText(row,'div','', 'dimension-head');addText(head,'span',item.label);addText(head,'strong',`${item.score}/${item.max_score}`);const bar=addText(row,'div','', 'bar'),fill=addText(bar,'span','');fill.style.width=`${Math.min(100,item.score/item.max_score*100)}%`;addText(row,'small',item.detail);});
  const renderTags=(selector,items,gap=false)=>{const box=$(selector);clear(box);(items?.length?items:[gap?'暂未识别明显缺口':'暂无']).forEach(item=>addText(box,'span',item,`tag${gap?' gap':''}`));};renderTags('#advantages',match?.advantages);renderTags('#gaps',match?.gaps,true);$('#scoringNote').textContent=match?.scoring_note||'该分数仅用于结构化字段的初步比较。';
}

function renderCompany(info) {
  setConfidence('#companyConfidence',info?.confidence);$('#companySummary').textContent=info?.summary||'暂无公司信息。';const facts=$('#companyFacts');clear(facts);
  [['企业性质',info?.company_type],['总部',info?.headquarters],['员工规模',info?.employee_scale]].forEach(([label,text])=>{if(!text)return;const item=addText(facts,'div','', 'fact');addText(item,'span',label);addText(item,'strong',text);});
  const businesses=$('#businesses');clear(businesses);(info?.businesses||[]).forEach(item=>addText(businesses,'span',item));$('#roleRelevance').textContent=info?.role_relevance||'公开信息不足，暂时无法判断岗位所属业务。';const caveats=$('#companyCaveats');clear(caveats);(info?.caveats||[]).forEach(item=>addText(caveats,'div',item,'notice'));
  const evidenceBox=$('#companyEvidence');clear(evidenceBox);if(info?.evidence?.length){const details=addText(evidenceBox,'details','', 'evidence-list');addText(details,'summary',`事实证据 · ${info.evidence.length} 条`);const body=addText(details,'div','', 'details-body'),sourceMap=Object.fromEntries((info.sources||[]).map(source=>[source.id,source]));info.evidence.forEach((fact,index)=>{const item=addText(body,'div','', 'evidence-item');addText(item,'p',`${index+1}. ${fact.claim}`);const links=addText(item,'div','', 'evidence-links');(fact.source_ids||[]).forEach(id=>{const source=sourceMap[id];if(!source)return;const link=addText(links,'a',source.title);link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';});});}renderCompanySearchTrace(evidenceBox,info?.search_attempts||[]);
}

function renderCompanySearchTrace(container,attempts){if(!attempts.length)return;const details=addText(container,'details','', 'search-trace');addText(details,'summary',`公司搜索审计 · ${attempts.length} 次`);const body=addText(details,'div','', 'details-body');attempts.forEach(attempt=>{const item=addText(body,'div','', 'search-attempt'),head=addText(item,'div','', 'attempt-head');addText(head,'span','公司公开信息检索');addText(head,'span',`返回 ${attempt.raw_result_count} · 采纳 ${attempt.accepted_result_count}`);addText(item,'div',attempt.query,'attempt-query');(attempt.sources||[]).forEach((source,index)=>appendSource(item,source,index+1,'raw-source'));});}

function renderSalary(info) {
  setConfidence('#salaryConfidence',info?.confidence);const scopeMap={company:'公司相关',market:'市场降级',insufficient:'信息不足'},scope=info?.data_scope||'insufficient',scopeNode=$('#salaryScope');scopeNode.className=`pill scope ${scope}`;scopeNode.textContent=scopeMap[scope]||scopeMap.insufficient;const range=info?.minimum!=null&&info?.maximum!=null?`${money(info.minimum)}–${money(info.maximum)}`:'数据不足';$('#salaryRange').textContent=range;$('#salaryStat').textContent=range;$('#salaryUnit').textContent=`${info?.currency||'CNY'}/${info?.period==='year'?'年':'月'}`;$('#salarySummary').textContent=info?.summary||'暂无薪资信息。';
  const employmentMap={social:'常规社招',campus:'校园招聘',intern:'实习招聘'},roleSourceMap={user:'用户填写',jd:'JD 提取',inferred:'系统推断'};const meta=$('#salaryMeta');clear(meta);[`检索岗位 ${info?.role_name||'未知'}`,`${roleSourceMap[info?.role_source]||'来源未知'}`,`${employmentMap[info?.employment_type]||'招聘类型未知'}`,`有效区间 ${info?.sample_count||0}`,`公司相关 ${info?.company_specific_samples||0}`,`招聘平台来源 ${info?.trusted_source_count||0}`,`${info?.location||'地区未知'}`].forEach(item=>addText(meta,'span',item));$('#salaryMethod').textContent=`计算方法：${info?.methodology||'未知'}`;const caveats=$('#salaryCaveats');clear(caveats);(info?.caveats||[]).forEach(item=>addText(caveats,'div',item,'notice'));renderSalarySearchTrace(info?.search_attempts||[]);
}

function renderSalarySearchTrace(attempts) {
  const container=$('#salarySearchTrace');clear(container);if(!attempts.length)return;const details=addText(container,'details','', 'search-trace'),summary=addText(details,'summary',`原始搜索过程 · ${attempts.length} 次`),body=addText(details,'div','', 'details-body');
  attempts.forEach((attempt,index)=>{const item=addText(body,'div','', 'search-attempt'),head=addText(item,'div','', 'attempt-head');addText(head,'span',attempt.scope==='company'?'① 公司专属检索':'② 市场降级检索');addText(head,'span',`返回 ${attempt.raw_result_count} · 采纳 ${attempt.accepted_result_count}`);addText(item,'div',attempt.query,'attempt-query');(attempt.sources||[]).forEach((source,sourceIndex)=>appendSource(item,source,sourceIndex+1,'raw-source'));});
}

function renderSources(sources) { const container=$('#sources');clear(container);$('#sourceSummary').textContent=`已采纳信息来源 · ${sources.length} 条`;if(!sources.length){addText(container,'small','当前未获取可用于结论的外部来源。');return;}sources.forEach((item,index)=>appendSource(container,item,index+1)); }

function flowNode(parent,node,byNode,cursors){const entries=byNode[node]||[],cursor=cursors[node]||0,metric=entries[cursor]||entries.at(-1);cursors[node]=cursor+1;const item=addText(parent,'div','',`flow-node${metric?'':' not-run'}`);addText(item,'strong',nodeLabels[node]||node);addText(item,'small',metric?`${metric.latency_ms} ms`:'未执行');return item;}
function flowArrow(parent,text='→'){addText(parent,'span',text,'flow-arrow');}
function formatCost(value,billable){if(value==null)return '无法估算';if(!billable)return '$0.000000';return `$${value.toFixed(value>0&&value<0.000001?8:6)}`;}
function renderCostSummary(summary){const cards=$('#usageSummary'),rows=$('#costBreakdown');clear(cards);clear(rows);$('#costStat').textContent=summary?formatCost(summary.estimated_cost_usd,summary.billable):'—';if(!summary){addText(cards,'small','当前记录没有模型用量数据。');$('#costNote').textContent='';return;}[['模型',summary.model_name],['总 Token',summary.total_tokens.toLocaleString()],['模型调用',`${summary.total_model_calls} 次`],['估算成本',formatCost(summary.estimated_cost_usd,summary.billable)]].forEach(([label,value])=>{const card=addText(cards,'div','', 'usage-card');addText(card,'span',label);addText(card,'strong',value);});const occurrences={};(summary.nodes||[]).forEach(item=>{occurrences[item.node]=(occurrences[item.node]||0)+1;const suffix=(summary.nodes||[]).filter(node=>node.node===item.node).length>1?` #${occurrences[item.node]}`:'';const row=addText(rows,'div','', 'cost-row');addText(row,'strong',`${nodeLabels[item.node]||item.node}${suffix}`);addText(row,'span',`输入 ${item.input_tokens.toLocaleString()}`);addText(row,'span',`输出 ${item.output_tokens.toLocaleString()}`);addText(row,'span',`${item.model_calls} 次调用`);addText(row,'span',formatCost(item.estimated_cost_usd,summary.billable));});const prices=summary.input_price_per_1m==null?'模型单价未配置':`输入 $${summary.input_price_per_1m}/1M · 输出 $${summary.output_price_per_1m}/1M`;$('#costNote').textContent=`${prices} · ${summary.note}`;}
function renderFlow(metrics,elapsed,threadId,errors,routerMode='fixed',routerDecisions=[],analysisPlan=null,routeHistory=[],analysisTargets=[]) {
  const byNode={},cursors={};metrics.forEach(item=>(byNode[item.node]??=[]).push(item));const flow=$('#executionFlow');clear(flow),hybrid=routerMode==='hybrid';
  if(routerMode==='llm'){
    const row=addText(flow,'div','', 'flow-stage'),sequence=['intake','jd'];(routeHistory||[]).filter(node=>!['intake','jd'].includes(node)).forEach(node=>{sequence.push('supervisor',node);});sequence.forEach((node,index)=>{if(index)flowArrow(row);flowNode(row,node,byNode,cursors);});
  }else{
    const top=addText(flow,'div','', 'flow-stage');flowNode(top,'intake',byNode,cursors);flowArrow(top);flowNode(top,'jd',byNode,cursors);if(hybrid){flowArrow(top);flowNode(top,'planner',byNode,cursors);}flowArrow(flow,'↓');addText(flow,'div',hybrid?'Planner 选中节点 · 并行执行':'固定节点 · 并行执行','parallel-label');const branch=addText(flow,'div','', 'flow-stage'),planned=hybrid?(analysisPlan?.final_agents||[]):analysisTargets;planned.forEach(node=>flowNode(branch,node,byNode,cursors));flowArrow(flow,'↓');flowNode(flow,'report',byNode,cursors);
  }
  const decisions=$('#routerDecisions');clear(decisions);if(routerMode==='llm'&&routerDecisions.length){const details=addText(decisions,'details','', 'search-trace');addText(details,'summary',`Supervisor 决策 · ${routerDecisions.length} 次`);const body=addText(details,'div','', 'details-body');routerDecisions.forEach((item,index)=>addText(body,'div',`${index+1}. ${item.next_agent} · ${item.reason}`,'notice'));}if(hybrid&&analysisPlan){const details=addText(decisions,'details','', 'search-trace');addText(details,'summary','Planner 执行计划');const body=addText(details,'div','', 'details-body'),proposed=(analysisPlan.proposed_agents||[]).join('、')||'空计划',finalAgents=(analysisPlan.final_agents||[]).join('、');addText(body,'div',`模型计划：${proposed}`,'notice');addText(body,'div',`最终计划：${finalAgents}${analysisPlan.overridden?'（代码纠正）':''}`,'notice');addText(body,'div',analysisPlan.policy_reason||analysisPlan.reason,'notice');}
  const list=$('#metrics');clear(list);metrics.forEach(item=>{const row=addText(list,'div','', 'metric');addText(row,'span',item.node);addText(row,'strong',`${item.latency_ms} ms`);});const work=metrics.reduce((sum,item)=>sum+item.latency_ms,0),elapsedText=elapsed==null?'历史记录':`实际端到端耗时 ${elapsed} ms`,routingNote=hybrid?'（包含 Planner，并行节点不直接相加）':routerMode==='llm'?'（包含 Supervisor）':'（并行节点不能作为用户等待时间相加）';$('#technicalMeta').textContent=`${elapsedText} · 节点工作量合计 ${work} ms${routingNote} · Thread ${threadId}`;const errorsBox=$('#nodeErrors');clear(errorsBox);(errors||[]).forEach(item=>addText(errorsBox,'div',`${item.node}: ${item.message}`,'error'));
}

function renderAnalysis(body) {
  const elapsed=body.elapsed_ms;
  const routerMode=body.router_mode||'fixed';$('#routerMode').value=routerMode;updateRouterPresentation(routerMode);
  $('#elapsed').textContent=elapsed==null?'已恢复':elapsed>=1000?`${(elapsed/1000).toFixed(1)} s`:`${elapsed} ms`;
  const statuses=body.section_statuses||{match:{status:body.match_result?'completed':'not_requested'},company:{status:body.company_info?(body.company_info.sources?.length?'completed':'insufficient'):'not_requested'},salary:{status:body.salary_info?(body.salary_info.data_scope==='insufficient'?'insufficient':'completed'):'not_requested'}};setSectionStatus('#matchStatus',statuses.match);setSectionStatus('#companyStatus',statuses.company);setSectionStatus('#salaryStatus',statuses.salary);renderMatch(body.match_result);renderCompany(body.company_info);renderSalary(body.salary_info);renderMarkdown(body.final_report);renderSources(body.sources||[]);renderCostSummary(body.cost_summary);renderFlow(body.metrics||[],elapsed,body.thread_id,body.errors||[],routerMode,body.router_decisions||[],body.analysis_plan||null,body.route_history||[],body.analysis_targets||[]);
  placeholder.classList.add('hidden');loading.classList.add('hidden');errorBox.classList.add('hidden');result.classList.remove('hidden');
}

function resetLiveProgress(){clear($('#liveProgress'));$('#loadingText').textContent='请求已提交，等待第一个节点完成…';}
function updateLiveProgress(event){let node=$(`#liveProgress [data-node="${event.node}"]`);if(!node){node=addText($('#liveProgress'),'span',nodeLabels[event.node]||event.node,'live-step');node.dataset.node=event.node;}node.className=`live-step ${event.status||'completed'}`;$('#loadingText').textContent=`${nodeLabels[event.node]||event.node}已${event.status==='degraded'?'降级完成':'完成'}，工作流继续执行…`;}
async function streamAnalysis(payload,onEvent){const response=await fetch('/api/v1/analyze/stream',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},body:JSON.stringify(payload)});if(!response.ok){let detail=`请求失败（${response.status}）`;try{detail=(await response.json()).detail||detail;}catch{}const error=new Error(detail);error.status=response.status;throw error;}if(!response.body)throw new Error('浏览器不支持流式响应');const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',finalResult=null;while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});const chunks=buffer.split(/\r?\n\r?\n/);buffer=chunks.pop()||'';for(const chunk of chunks){let eventName='message',data='';chunk.split(/\r?\n/).forEach(line=>{if(line.startsWith('event:'))eventName=line.slice(6).trim();if(line.startsWith('data:'))data+=line.slice(5).trim();});if(!data)continue;const parsed=JSON.parse(data);onEvent(eventName,parsed);if(eventName==='result')finalResult=parsed;if(eventName==='error')throw new Error(parsed.message||'分析失败');}if(done)break;}if(!finalResult)throw new Error('分析流意外结束');return finalResult;}

form.addEventListener('submit',async event=>{
  event.preventDefault();const targets=[...document.querySelectorAll('input[name="analysisTarget"]:checked')].map(item=>item.value);if(!targets.length){errorBox.textContent='请至少选择一个分析范围';errorBox.classList.remove('hidden');return;}placeholder.classList.add('hidden');result.classList.add('hidden');errorBox.classList.add('hidden');loading.classList.remove('hidden');button.disabled=true;buttonLabel.textContent='分析中…';resetLiveProgress();const years=Number(value('experience')),targetText={match:'岗位匹配度',company:'公司公开信息与业务情况',salary:'岗位薪资待遇'};
  const profile={preferred_locations:value('location')?[value('location')]:(currentProfile?.preferred_locations||[]),preferred_roles:currentProfile?.preferred_roles||[],skills:splitList(value('skills')),education:value('education')||null,years_of_experience:value('experience')&&Number.isFinite(years)?years:null,experiences:currentProfile?.experiences||[]};const payload={company_name:value('companyName'),job_title:value('jobTitle')||null,employment_type:value('employmentType'),target_location:value('location')||null,question:`请分析${targets.map(item=>targetText[item]).join('、')}`,analysis_targets:targets,jd_text:value('jdText'),router_mode:value('routerMode'),user_profile:profile};
  try{const body=await streamAnalysis(payload,(name,data)=>{if(name==='progress')updateLiveProgress(data);});applyProfile(profile);renderAnalysis(body);}
  catch(error){if(error.status===401){showAuth();authError('登录已过期，请重新登录');}else{errorBox.textContent=error.message||String(error);errorBox.classList.remove('hidden');}}finally{loading.classList.add('hidden');button.disabled=false;buttonLabel.textContent='开始分析';}
});
function updateRouterPresentation(mode) {const labels={fixed:'Fixed Router · V1',llm:'LLM Router · V2',hybrid:'Hybrid Planner · V3'},descriptions={fixed:'Company、Salary 与 Match 节点并行执行，结果由 Report Agent 统一汇总。',llm:'Supervisor 根据分析目标逐步选择必要 Agent，并记录每次决策依据。',hybrid:'LLM 一次规划必要 Agent，代码校验后动态并行执行，最后自动汇总。'};$('#routerBadge').lastChild.textContent=labels[mode]||labels.fixed;$('#routerDescription').textContent=descriptions[mode]||descriptions.fixed;}
$('#routerMode').addEventListener('change',()=>updateRouterPresentation(value('routerMode')));
api('/api/v1/auth/me').then(body=>showApp(body.user)).catch(()=>showAuth());
