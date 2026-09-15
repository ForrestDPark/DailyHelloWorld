const $ = id => document.getElementById(id);
let currentStatus = null;
let timeProfileInitialized = false;
let notificationItems = [];
let completionAudioContext = null;
const videoTransferStates = new Map();
let currentSubtitleExtraction = {state:"idle"};
// ★ 2026-09-15: "db 에있는 영상을 하나씩 하는게 아니라 전부 여러개를 클릭해서
// 다운받거나 사진에 저장 원본 삭제, 삭제 가능하게 해줘" — 개별 파일 카드의
// 다운로드/사진저장/삭제 버튼을 없애고 체크박스 다중 선택 + 하단 일괄 처리
// 바(video-library-bulk)로 옮겼다. selectedVideoIds는 3초 폴링으로
// renderVideoLibrary가 다시 그려져도(예전엔 카드의 .selected 클래스만 썼는데
// 매번 DOM을 새로 만들어 선택이 풀렸다) 선택 상태가 유지되도록 모듈
// 스코프에 둔다.
let selectedVideoIds = new Set();
let lastVideoItems = [];
// Safari 단축어(다운로드·사진 저장)는 클립보드→shortcuts:// 이동이라 완료
// 여부를 코드로 알 수 없어서, 여러 개를 고르면 한 번에 하나씩만 진행하고
// 사용자가 "다음 파일 받기"를 눌러야 다음으로 넘어가는 큐로 처리한다.
let bulkQueue = null;
function notice(message, error=false){const el=$("notice");el.textContent=message;el.classList.remove("hidden","error");if(error)el.classList.add("error");else setTimeout(()=>el.classList.add("hidden"),3500)}
async function api(url,options={}){const response=await fetch(url,{credentials:"same-origin",...options,headers:{"Content-Type":"application/json",...(options.headers||{})}});if(response.status===401){location.href="/";throw new Error("로그인이 필요합니다")}const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||"요청을 처리하지 못했습니다");return data}
function renderNotifications(data){notificationItems=data.items||[];const badge=$("notification-count"),list=$("notification-list"),count=Number(data.unread_count)||0;badge.textContent=count>99?"99+":String(count);badge.classList.toggle("hidden",count===0);list.replaceChildren();if(!notificationItems.length){const emptyState=document.createElement("div");emptyState.className="notification-empty";emptyState.textContent="새 알림이 없습니다.";list.append(emptyState);return}notificationItems.forEach(item=>{const button=document.createElement("button"),dot=document.createElement("span"),copy=document.createElement("span"),title=document.createElement("b"),body=document.createElement("span"),kind=document.createElement("span");button.type="button";button.className=`notification-item${item.unread?" unread":""}`;dot.className="notification-dot";copy.className="notification-copy";title.textContent=item.title;body.textContent=item.body||"";kind.className="notification-kind";kind.textContent=item.type==="chat"?"채팅":"업데이트";copy.append(title,body);button.append(dot,copy,kind);button.addEventListener("click",async()=>{try{if(item.type==="system"&&item.unread){await api("/api/notifications/read",{method:"PUT",body:JSON.stringify({notification_id:item.id})});item.unread=false;await loadNotifications()}location.href=item.url}catch(e){notice(e.message,true)}});list.append(button)})}
async function loadNotifications(){try{renderNotifications(await api("/api/notifications"))}catch(e){notice(e.message,true)}}
function metric(label,value,detail=""){const el=document.createElement("article"),small=document.createElement("small"),strong=document.createElement("strong"),span=document.createElement("span");el.className="metric";small.textContent=label;strong.className="value";strong.textContent=value??"—";span.className="detail";span.textContent=detail;el.append(small,strong,span);return el}
function checkRow(label,checked,time,onToggle=null,onDelete=null){const row=document.createElement("div"),dot=document.createElement(onToggle?"button":"span"),text=document.createElement("span");row.className=`check-row${checked?" done":""}`;dot.className="check-dot";dot.textContent=checked?"✓":"";if(onToggle){dot.type="button";dot.setAttribute("aria-label",`${label} ${checked?"체크 해제":"체크"}`);dot.addEventListener("click",()=>onToggle(!checked,row))}text.textContent=label;row.append(dot,text);if(time){const clock=document.createElement("time");clock.textContent=time;row.append(clock)}if(onDelete){const del=document.createElement("button");del.type="button";del.className="check-delete";del.textContent="삭제";del.setAttribute("aria-label",`${label} 삭제`);del.addEventListener("click",()=>onDelete(row));row.append(del);let startX=null;row.addEventListener("touchstart",e=>{startX=e.touches[0].clientX},{passive:true});row.addEventListener("touchmove",e=>{if(startX!==null&&e.touches[0].clientX-startX<-35)row.classList.add("swiping")},{passive:true});row.addEventListener("touchend",e=>{const delta=startX===null?0:e.changedTouches[0].clientX-startX;startX=null;row.classList.remove("swiping");if(delta<-80)onDelete(row)},{passive:true})}return row}
function empty(text){const el=document.createElement("div");el.className="empty";el.textContent=text;return el}
function render(data){currentStatus=data;$("summary").replaceChildren(
  metric("오늘 근무",data.shift||"미정",data.shift_day_number?`${data.shift_day_number}일차${data.shift_is_last_day?" · 마지막 날":""}`:""),
  metric("오늘 날씨",data.weather||"확인 중",data.storage_free_gb==null?"저장공간 확인 중":`저장공간 ${data.storage_free_gb}GB`),
  metric("Codex",data.codex_percent==null?"—":`${data.codex_percent}%`,data.codex_window_day?`${data.codex_window_day}/${data.codex_window_days}일차`:"사용량"),
  metric("Claude",data.claude_percent==null?"—":`${data.claude_percent}%`,data.earnings_short||"사용량"));
 const today=$("today-reminders");today.replaceChildren();const details=data.reminders_detailed||(data.reminders||[]).map(label=>({label,checked:Boolean((data.reminders_checked||{})[label]),time:null}));if(!details.length)today.append(empty("오늘 예정된 리마인더가 없습니다."));details.forEach(item=>{let busy=false;const toggle=async(next,row)=>{if(busy)return;busy=true;row.querySelectorAll("button").forEach(button=>button.disabled=true);try{await api("/api/shift-alarm/reminder-check",{method:"PUT",body:JSON.stringify({label:item.label,checked:next})});item.checked=next;render(data)}catch(e){notice(e.message,true);row.querySelectorAll("button").forEach(button=>button.disabled=false);busy=false}};const remove=async row=>{if(busy||!confirm("이 리마인더를 오늘 목록에서 삭제할까요? 반복 설정은 유지됩니다."))return;busy=true;row.querySelectorAll("button").forEach(button=>button.disabled=true);try{await api(`/api/shift-alarm/reminder?label=${encodeURIComponent(item.label)}`,{method:"DELETE"});data.reminders_detailed=details.filter(entry=>entry!==item);render(data);notice("오늘의 리마인더에서 삭제했습니다.")}catch(e){notice(e.message,true);row.classList.remove("swiping");row.querySelectorAll("button").forEach(button=>button.disabled=false);busy=false}};today.append(checkRow(item.label,item.checked,item.time,toggle,remove))});
 const routine=$("routine");routine.replaceChildren();const routines=data.daily_routine||[];if(!routines.length)routine.append(empty("Shift Alarm에서 일일 루틴을 불러오는 중입니다."));routines.forEach(item=>routine.append(checkRow(item.label,item.checked)));$("routine-count").textContent=`(${routines.filter(item=>item.checked).length}/${routines.length})`;$("check-all").disabled=!routines.some(item=>!item.checked);
 const profileSelect=$("time-profile");if(!timeProfileInitialized){const preferred=data.reminder_time_profile||data.shift||"시각";if([...profileSelect.options].some(option=>option.value===preferred))profileSelect.value=preferred;timeProfileInitialized=true}const profile=profileSelect.value;const schedule=$("schedule");schedule.replaceChildren();(data.reminder_schedule||[]).forEach(item=>{const row=document.createElement("tr"),label=document.createElement("td"),timeCell=document.createElement("td"),input=document.createElement("input"),enabled=document.createElement("td"),action=document.createElement("td"),save=document.createElement("button");label.textContent=item.label;input.type="time";input.value=(item.times||{})[profile]||item.time||"";input.setAttribute("aria-label",`${item.label} ${profile} 시각`);input.disabled=item.editable===false;timeCell.append(input);enabled.textContent=item.editable===false?"자동":item.enabled?"켜짐":"꺼짐";enabled.className=item.enabled?"status-on":"status-off";save.type="button";save.textContent="저장";if(item.editable===false){save.disabled=true;save.title="근무표와 전환 날짜에 따라 자동 계산됩니다"}else{save.addEventListener("click",async()=>{save.disabled=true;try{await api("/api/shift-alarm/reminder-time",{method:"PUT",body:JSON.stringify({label:item.label,time:input.value,profile})});item.times=item.times||{};item.times[profile]=input.value;if(profile==="시각")item.time=input.value;notice(`${profile} 시각을 저장했습니다. Shift Alarm이 곧 동기화합니다.`)}catch(e){notice(e.message,true)}finally{save.disabled=false}})}action.append(save);row.append(label,timeCell,enabled,action);schedule.append(row)});if(!(data.reminder_schedule||[]).length){const row=document.createElement("tr"),cell=document.createElement("td");cell.colSpan=4;cell.className="empty";cell.textContent="Shift Alarm을 재시작하면 전체 시각표가 표시됩니다.";row.append(cell);schedule.append(row)}
 const notion=$("notion-link");if(data.reminder_notion_url)notion.href=data.reminder_notion_url;else notion.classList.add("hidden");$("updated").textContent=data.updated_at?`Shift Alarm 최종 갱신 ${new Date(data.updated_at).toLocaleString("ko-KR")}`:""}
async function load(){$("refresh").disabled=true;try{render(await api("/api/shift-alarm/status"))}catch(e){notice(e.message,true)}finally{$("refresh").disabled=false}}
function elapsedText(seconds){if(seconds==null)return"";const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),secs=seconds%60;return hours?`${hours}시간 ${minutes}분`:`${minutes}분 ${String(secs).padStart(2,"0")}초`}
async function loadSunziStatus(){try{const data=await api("/api/shift-alarm/sunzi-analysis"),button=$("start-sunzi-analysis"),status=$("sunzi-analysis-status"),wrap=$("sunzi-progress-wrap"),progress=Math.max(0,Math.min(100,Number(data.progress)||0)),chapter=data.next_chapter||"구지편",verse=data.running?data.verse:data.next_verse;button.disabled=data.busy;button.textContent=data.running?"분석 진행 중":data.queued?"분석 대기 중":"분석 시작하기";$("sunzi-next-verse").textContent=verse?`${chapter} ${verse}번째 구절 ${data.running?"분석 중":"분석 차례"}`:"다음 분석 구절 확인 필요";status.textContent=data.running?`${data.stage}`:data.queued?"손무가 분석을 시작할 차례를 기다리고 있습니다.":data.state==="failed"?`최근 분석 중단 · ${data.stage}`:data.state==="interrupted"?"이전 분석이 비정상 종료됐습니다. 다시 시작할 수 있습니다.":"다음 미완료 구절을 라이트 모드로 분석합니다.";wrap.classList.toggle("hidden",!(data.running||data.queued));$("sunzi-progress-bar").style.width=`${data.queued?2:progress}%`;$("sunzi-progress-percent").textContent=`${data.queued?0:progress}%`;$("sunzi-progress-elapsed").textContent=data.running?`경과 ${elapsedText(data.elapsed_seconds)}`:"대기 중"}catch(e){$("start-sunzi-analysis").disabled=true;$("sunzi-analysis-status").textContent="분석 상태를 확인하지 못했습니다.";$("sunzi-next-verse").textContent="다음 분석 구절 확인 필요"}}
$("start-sunzi-analysis").addEventListener("click",async()=>{if(!confirm("다음 미완료 구절을 라이트 모드로 분석할까요?"))return;const button=$("start-sunzi-analysis");button.disabled=true;button.textContent="요청 중";try{await api("/api/shift-alarm/sunzi-analysis",{method:"POST"});notice("라이트 모드 분석을 요청했습니다.");await loadSunziStatus()}catch(e){notice(e.message,true);await loadSunziStatus()}});
// ★ 2026-09-14: "채팅창에서 하는게아니라 shift alarm시스템 내부에 버튼만들어줘"
// — shift_alarm 메뉴바의 Elmedia 좋아요/클래식 재생, 그리고 메뉴에는 아예
// 없던 음량 조절을 이 대시보드에서 바로 누르게 한다(서버가 이 Mac에서
// 직접 osascript/Elmedia를 실행 — server/app.py 참고).
function setVolumeUI(percent){$("volume-display").textContent=`${percent}%`;$("volume-slider").value=percent;$("volume-slider").style.setProperty("--val",`${percent}%`)}
async function loadVolume(){try{const data=await api("/api/shift-alarm/media/volume");setVolumeUI(data.percent)}catch(e){$("volume-display").textContent="--%"}}
async function setVolume(body){try{const data=await api("/api/shift-alarm/media/volume",{method:"POST",body:JSON.stringify(body)});setVolumeUI(data.percent)}catch(e){notice(e.message,true);await loadVolume()}}
// ★ 2026-09-14: "클래식/좋아요 재생 중일 때 대시보드에 어느 쪽인지 표시해줘"
// — 메뉴바·채팅·대시보드 중 어디서 재생을 시작했든 서버가 같은 파일을 보고
// 판단하므로(server/app.py 참고), 주기적으로 폴링해서 뱃지에 반영한다.
const NOW_PLAYING_LABELS={favorites:"⭐ 좋아요 재생중",classical:"🎻 클래식 재생중"};
async function loadNowPlaying(){try{const data=await api("/api/shift-alarm/media/now-playing");const label=data.running?NOW_PLAYING_LABELS[data.playlist]:null;$("now-playing-badge").classList.toggle("hidden",!label);if(label)$("now-playing-text").textContent=label}catch(e){$("now-playing-badge").classList.add("hidden")}}
async function playMedia(playlist,button){const original=button.textContent;button.disabled=true;button.textContent="재생 중…";try{const data=await api("/api/shift-alarm/media/play",{method:"POST",body:JSON.stringify({playlist})});notice(data.message);await loadNowPlaying()}catch(e){notice(e.message,true)}finally{button.disabled=false;button.textContent=original}}
// ★ 2026-09-14: "휴대폰 크롬에서 열리게 해줄 수 없나" — 서버는 URL만 골라
// 돌려주고, 여는 건 이 클릭 핸들러에서 한다. await 뒤에 window.open을 부르면
// 모바일 브라우저가 "사용자 동작 없이 뜬 팝업"으로 보고 막아버리므로, 클릭
// 직후(아직 fetch 전, 동기 실행 중) 빈 탭을 먼저 열어두고 URL이 오면
// 그 탭의 location만 바꾼다.
let recommendedSiteUrls=[];
// ★ 2026-09-14: "링크 클릭하면 사파리 말고 크롬 앱에서 열리게 해줘" — iOS는
// googlechrome(s):// 커스텀 URL 스킴으로 열면 크롬 앱이 설치돼 있을 때 그
// 앱으로 바로 넘어간다(Chrome 미설치 시엔 반응 없음). 예전엔 天 북마크가
// 죽은 kr46 미러를 가리키고 있어서 딥링크가 전부 홈 화면으로 튕겨
// 나갔는데, 북마크를 살아있는 kr47로 갱신한 뒤로는 정상 동작해서 클립보드
// 복사와 함께 바로 이동하게 되돌렸다.
async function copyLinkAndOpenChrome(url){
    try{
        await navigator.clipboard.writeText(url);
        notice("링크를 복사했습니다. 크롬으로 이동합니다.");
    }catch(e){
        notice(`링크 복사 실패 — 직접 복사하세요: ${url}`,true);
    }
    window.location.href=url.replace(/^https:/,"googlechromes:").replace(/^http:/,"googlechrome:");
}
// ★ 2026-09-15: "링크 자체보다 링크 끝에 붙어있는 keyword 옆에 단어로 표시해서
// 어떤 사이트가 추천됬는지 대충 알기 편하게 보이면 좋겠어" — 추천 북마크
// 상당수가 `?keyword=...`(또는 `?s=...`, 배우명 검색) 쿼리를 달고 있어서, 그
// 값을 굵은 글씨로 보여주면 링크만 보고도 뭘 추천받았는지 바로 알 수 있다.
// 그런 쿼리가 없는 사이트(홈페이지 등)는 기존처럼 호스트명을 보여준다.
function extractSiteKeyword(parsed){
    for(const key of ["keyword","keywords","s","q","query"]){
        const value=parsed.searchParams.get(key);
        if(value&&value.trim())return value.trim();
    }
    return null;
}
function renderRecommendedSites(urls){recommendedSiteUrls=urls;const panel=$("recommended-sites"),list=$("recommended-sites-list");list.replaceChildren();urls.forEach((url,index)=>{const link=document.createElement("a"),number=document.createElement("span"),copy=document.createElement("span"),host=document.createElement("b"),path=document.createElement("span"),arrow=document.createElement("span"),parsed=new URL(url),keyword=extractSiteKeyword(parsed);link.className="recommended-site";link.href=url;number.className="recommended-site-index";number.textContent=index+1;copy.className="recommended-site-copy";host.textContent=keyword||parsed.hostname;path.textContent=keyword?parsed.hostname:`${parsed.pathname}${parsed.search}`;copy.append(host,path);arrow.className="recommended-site-arrow";arrow.textContent="⧉";link.append(number,copy,arrow);link.addEventListener("click",event=>{event.preventDefault();copyLinkAndOpenChrome(url)});list.append(link)});panel.classList.remove("hidden");$("open-first-site").disabled=!urls.length}
async function loadRecommendedSites(button){const original=button.textContent;button.disabled=true;button.textContent="고르는 중…";try{const data=await api("/api/shift-alarm/media/open-sites",{method:"POST"});renderRecommendedSites(data.urls||[]);notice(`${data.urls?.length||0}개 추천을 골랐습니다.`)}catch(e){notice(e.message,true)}finally{button.disabled=false;button.textContent=original}}
async function sendTransport(action,button){button.disabled=true;try{await api("/api/shift-alarm/media/transport",{method:"POST",body:JSON.stringify({action})})}catch(e){notice(e.message,true)}finally{button.disabled=false}}
$("play-favorites").addEventListener("click",e=>playMedia("favorites",e.currentTarget));
$("play-classical").addEventListener("click",e=>playMedia("classical",e.currentTarget));
$("open-sites").addEventListener("click",e=>loadRecommendedSites(e.currentTarget));
$("reroll-sites").addEventListener("click",e=>loadRecommendedSites(e.currentTarget));
$("open-first-site").addEventListener("click",()=>{if(recommendedSiteUrls[0])copyLinkAndOpenChrome(recommendedSiteUrls[0])});
$("recommended-sites-close").addEventListener("click",()=>$("recommended-sites").classList.add("hidden"));
// ★ 2026-09-14: "재생중일때 일시정지랑 다음곡 이전곡 넘어가는 버튼도있으면
// 좋겠어" — 시스템 미디어 키를 눌러 Elmedia를 제어한다(서버가 shift_alarm.py와
// 같은 인터프리터 신원으로 실행 — server/app.py 참고). Elmedia가 안 떠 있으면
// 서버가 409를 주므로 notice로 그대로 보여준다.
$("transport-previous").addEventListener("click",e=>sendTransport("previous",e.currentTarget));
$("transport-playpause").addEventListener("click",e=>sendTransport("playpause",e.currentTarget));
$("transport-next").addEventListener("click",e=>sendTransport("next",e.currentTarget));
// ★ 2026-09-14: "음량은 숫자로 말고 손으로 미는 아날로그바로 해줘" — 드래그
// 중(input)에는 화면 표시만 바꾸고, 손을 뗄 때(change)만 서버에 실제로 반영한다
// (드래그 한 번에 API를 수십 번 부르지 않도록).
$("volume-slider").addEventListener("input",()=>{$("volume-display").textContent=`${$("volume-slider").value}%`});
$("volume-slider").addEventListener("change",()=>setVolume({percent:Number($("volume-slider").value)}));
const VIDEO_STATE_LABELS={idle:"대기",queued:"대기 중",running:"다운로드 중",syncing:"동기화 중",complete:"완료",failed:"실패"};
function primeCompletionChime(){const AudioContextClass=window.AudioContext||window.webkitAudioContext;if(!AudioContextClass)return;if(!completionAudioContext)completionAudioContext=new AudioContextClass();if(completionAudioContext.state==="suspended")completionAudioContext.resume().catch(()=>{})}
function playCompletionChime(){if(document.visibilityState!=="visible")return;primeCompletionChime();const context=completionAudioContext;if(!context||context.state!=="running")return;const start=context.currentTime+.02;[[880,0],[1174.66,.16]].forEach(([frequency,offset])=>{const oscillator=context.createOscillator(),gain=context.createGain(),at=start+offset;oscillator.type="sine";oscillator.frequency.setValueAtTime(frequency,at);gain.gain.setValueAtTime(.0001,at);gain.gain.exponentialRampToValueAtTime(.12,at+.025);gain.gain.exponentialRampToValueAtTime(.0001,at+.14);oscillator.connect(gain).connect(context.destination);oscillator.start(at);oscillator.stop(at+.15)})}
function observeVideoTransferState(item){const key=item.file_id||item.filename,current=item.transfer_state||"",previous=videoTransferStates.get(key);videoTransferStates.set(key,current);if(previous==="downloading"&&current==="complete"){playCompletionChime();notice(`다운로드 완료 · ${item.ios_filename}`)}}
document.addEventListener("pointerdown",primeCompletionChime,{once:true,passive:true});
function shortcutClipboardUrl(name){return `shortcuts://run-shortcut?name=${encodeURIComponent(name)}&input=clipboard`}
function safariShortcutUrl(){return shortcutClipboardUrl("Safari로 다운로드")}
function renderSubtitleExtraction(info={state:"idle"}){currentSubtitleExtraction=info;const el=$("subtitle-extraction-status"),state=info.state||"idle",percent=Math.max(0,Math.min(100,Number(info.progress)||0));el.dataset.state=state;el.classList.toggle("hidden",state==="idle");const shown=state==="complete"?100:percent;$("subtitle-extraction-percent").textContent=`${Math.round(shown)}%`;$("subtitle-extraction-bar").style.width=`${shown}%`;$("subtitle-extraction-stage").textContent=state==="running"?`🎬 자막 추출 중 — ${info.stage||"Mac에서 처리 중입니다"}`:state==="complete"?"✅ 자막·번역·EPUB·Notion 반영 완료":state==="failed"?`⚠️ ${info.stage||"자막 추출 상태를 확인하지 못했습니다"}`:"";$("subtitle-extraction-file").textContent=info.filename?`${info.filename}${state==="running"?" · 새 터미널 창에서 자세한 로그를 볼 수 있고, 이 화면을 닫아도 계속 진행됩니다.":""}`:""}
function renderVideoLibrary(items=[]){
    lastVideoItems=items;
    const library=$("video-library");
    library.replaceChildren();
    const knownIds=new Set(items.map(item=>item.file_id));
    for(const id of [...selectedVideoIds])if(!knownIds.has(id))selectedVideoIds.delete(id);
    if(!items.length){
        library.append(empty("av4 폴더에 MP4 파일이 없습니다."));
        renderVideoBulkBar();
        return;
    }
    items.forEach(item=>{
        observeVideoTransferState(item);
        const card=document.createElement("article"),head=document.createElement("label"),checkbox=document.createElement("input"),
              copy=document.createElement("div"),name=document.createElement("b"),meta=document.createElement("small"),
              history=document.createElement("div"),
              transfer=document.createElement("div"),transferText=document.createElement("span"),transferBar=document.createElement("i"),
              buttons=document.createElement("div"),
              transferring=item.transfer_state==="downloading",
              percent=item.transfer_total_bytes?Math.min(100,item.transfer_sent_bytes/item.transfer_total_bytes*100):0;
        card.className="video-file";
        head.className="video-file-head";
        checkbox.type="checkbox";
        checkbox.className="video-file-checkbox";
        checkbox.checked=selectedVideoIds.has(item.file_id);
        checkbox.setAttribute("aria-label",`${item.filename} 선택`);
        card.classList.toggle("selected",checkbox.checked);
        checkbox.addEventListener("change",()=>{
            if(checkbox.checked)selectedVideoIds.add(item.file_id);else selectedVideoIds.delete(item.file_id);
            card.classList.toggle("selected",checkbox.checked);
            renderVideoBulkBar();
        });
        copy.className="video-file-copy";
        name.textContent=item.filename;
        meta.textContent=`${byteSize(item.size_bytes)}${item.temporary?" · 24시간 임시 보관":" · av4 보관 파일"}`;
        const saveName=document.createElement("small");
        saveName.className="video-file-savename";
        saveName.textContent=`Files 앱 저장명: ${item.ios_filename}`;
        copy.append(name,meta,saveName);
        history.className="video-file-history";
        if(item.safari_completed_at||item.transfer_state==="complete"){
            const safariDone=document.createElement("span");
            safariDone.className="video-history-badge done";
            safariDone.textContent="✓ Safari 다운로드 완료";
            history.append(safariDone);
        }
        if(item.photo_shortcut_at){
            const photosDone=document.createElement("span");
            photosDone.className="video-history-badge actioned";
            photosDone.textContent=`사진 저장 단축어 실행됨 · ${new Date(item.photo_shortcut_at).toLocaleString("ko-KR",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})}`;
            history.append(photosDone);
        }
        if(history.childElementCount)copy.append(history);
        head.append(checkbox,copy);
        transfer.className=`video-transfer${item.transfer_state?"":" hidden"}`;
        transferText.textContent=transferring?`Safari 다운로드 중 ${percent.toFixed(1)}% · ${byteSize(item.transfer_sent_bytes)} / ${byteSize(item.transfer_total_bytes)}`:item.transfer_state==="complete"?"Safari 다운로드 완료":item.transfer_state==="interrupted"?`다운로드 중단 · ${byteSize(item.transfer_sent_bytes)}까지 전송됨`:"";
        transferBar.style.width=`${item.transfer_state==="complete"?100:percent}%`;
        transfer.append(transferText,transferBar);
        buttons.className="video-file-buttons";
        if(transferring){
            const cancel=document.createElement("button");
            cancel.type="button";
            cancel.textContent="전송 중지";
            cancel.addEventListener("click",()=>videoAction("cancel_transfer",null,item.action_url));
            buttons.append(cancel);
        }
        const extractionRunning=currentSubtitleExtraction.state==="running",isThisExtracting=extractionRunning&&currentSubtitleExtraction.filename===item.filename,
              subtitleState=isThisExtracting?"running":item.subtitle_state||(currentSubtitleExtraction.filename===item.filename?currentSubtitleExtraction.state:null),
              subtitleProgress=isThisExtracting?Number(currentSubtitleExtraction.progress)||5:Number(item.subtitle_progress)||0;
        let subtitleStatus=null;
        if(subtitleState){
            const subtitleLabel=document.createElement("span"),subtitleTrack=document.createElement("i");
            subtitleStatus=document.createElement("div");
            subtitleStatus.className=`video-subtitle-state ${subtitleState}`;
            subtitleLabel.textContent=subtitleState==="complete"?"✓ 자막 추출 완료":subtitleState==="running"?`자막 추출 중 ${Math.round(subtitleProgress)}%`:`자막 추출 실패 · 다시 실행할 수 있습니다`;
            subtitleTrack.style.width=`${subtitleState==="complete"?100:subtitleProgress}%`;
            subtitleStatus.append(subtitleLabel,subtitleTrack);
        }
        const extract=document.createElement("button");
        extract.type="button";
        extract.className="subtitle-extract-btn";
        extract.textContent=isThisExtracting?`자막 추출 중 ${Math.round(subtitleProgress)}%`:subtitleState==="complete"?"✓ 자막 추출 완료":"🎬 자막 추출";
        extract.disabled=extractionRunning||subtitleState==="complete";
        extract.addEventListener("click",()=>videoAction(
            "extract_subtitle",
            "이 영상 하나만 골라 자막·번역·후리가나·Notion·EPUB까지 진행할까요? 운동용 영상 추출은 하지 않으며 시간이 오래 걸릴 수 있습니다.",
            item.action_url,
        ));
        buttons.append(extract);
        card.append(head);
        if(subtitleStatus)card.append(subtitleStatus);
        card.append(transfer,buttons);
        library.append(card);
    });
    renderVideoBulkBar();
}
function renderVideoBulkBar(){
    const bar=$("video-library-bulk");
    bar.classList.toggle("hidden",!lastVideoItems.length);
    const count=selectedVideoIds.size;
    $("video-bulk-count").textContent=`${count}개 선택`;
    $("video-bulk-select-all").textContent=count&&count===lastVideoItems.length?"선택 해제":"전체 선택";
    $("video-bulk-download").disabled=count===0;
    $("video-bulk-save-photos").disabled=count===0;
    $("video-bulk-delete").disabled=count===0;
    renderVideoBulkQueue();
}
function renderVideoBulkQueue(){
    const el=$("video-bulk-queue");
    if(!bulkQueue){el.classList.add("hidden");el.replaceChildren();return}
    el.classList.remove("hidden");
    const{action,items,index}=bulkQueue,label=action==="download"?"Safari로 다운로드":"사진에 저장·원본 삭제";
    el.replaceChildren();
    const text=document.createElement("p");
    text.textContent=`${label} · ${index+1} / ${items.length} · ${items[index]?.filename||""}`;
    const next=document.createElement("button");
    next.type="button";
    next.textContent=index+1<items.length?"다음 파일 받기":"완료";
    next.addEventListener("click",()=>advanceVideoBulkQueue(true));
    const cancel=document.createElement("button");
    cancel.type="button";
    cancel.textContent="중지";
    cancel.addEventListener("click",()=>{bulkQueue=null;renderVideoBulkQueue()});
    el.append(text,next,cancel);
}
async function triggerSafariDownload(item){
    const absolute=new URL(item.download_url,window.location.origin).href;
    try{
        await navigator.clipboard.writeText(absolute);
        notice(`다운로드 주소를 복사했습니다 · ${item.filename}. 단축어가 Safari에서 엽니다.`);
        window.location.href=safariShortcutUrl();
    }catch(e){
        notice("주소를 복사하지 못했습니다.",true);
    }
}
async function triggerPhotosSave(item){
    if(!confirm(`Safari 다운로드가 완료됐나요?\n\n"${item.ios_filename}"을 사진 앱 최근 항목에 저장한 뒤 Downloads 원본을 삭제합니다.`))return;
    try{
        await navigator.clipboard.writeText(item.ios_filename);
        await api(item.action_url,{method:"POST",body:JSON.stringify({action:"mark_photo_shortcut"})});
        notice("파일명을 복사했습니다. 사진 저장 단축어를 실행합니다.");
        window.location.href=shortcutClipboardUrl("다운로드 영상을 사진에 저장");
    }catch(e){
        notice("파일명을 복사하지 못해 단축어를 실행할 수 없습니다.",true);
    }
}
function startVideoBulkQueue(action,items){
    bulkQueue={action,items,index:0};
    advanceVideoBulkQueue(false);
}
async function advanceVideoBulkQueue(fromContinueClick){
    if(!bulkQueue)return;
    if(fromContinueClick){
        bulkQueue.index+=1;
        if(bulkQueue.index>=bulkQueue.items.length){
            notice(`${bulkQueue.items.length}개 파일 처리를 마쳤습니다.`);
            bulkQueue=null;
            renderVideoBulkQueue();
            await loadVideoDownload();
            return;
        }
    }
    renderVideoBulkQueue();
    const item=bulkQueue.items[bulkQueue.index];
    if(bulkQueue.action==="download")await triggerSafariDownload(item);
    else await triggerPhotosSave(item);
}
function byteSize(bytes){if(bytes==null)return"";const gb=bytes/1024/1024/1024;return gb>=1?`${gb.toFixed(2)}GB`:`${(bytes/1024/1024).toFixed(1)}MB`}
function renderVideoDownload(data){const state=data.state||"idle",progress=Math.max(0,Math.min(100,Number(data.progress)||0)),active=["queued","running","syncing"].includes(state),sizes=data.downloaded_bytes?`${byteSize(data.downloaded_bytes)}${data.total_bytes?` / ${byteSize(data.total_bytes)}`:" 내려받음"}`:"";$("video-download-state").textContent=VIDEO_STATE_LABELS[state]||state;$("video-download-state").dataset.state=state;$("video-download-submit").disabled=active;$("video-download-progress").classList.toggle("hidden",state==="idle");$("video-download-stage").textContent=data.stage||"상태를 확인하고 있습니다";$("video-download-percent").textContent=data.total_bytes?`${Math.round(progress)}%`:sizes||`${Math.round(progress)}%`;$("video-download-bar").style.width=`${progress}%`;$("video-download-file").textContent=data.filename?`${data.filename}${data.destination?` · ${data.destination}`:""}${data.size_bytes?` · ${byteSize(data.size_bytes)}`:""}`:active?`Mac에서 작업 중입니다. 이 화면을 닫아도 계속 진행됩니다.${sizes?` · ${sizes}`:""}`:"";renderSubtitleExtraction(data.subtitle_extraction);renderVideoLibrary(data.downloads)}
async function loadVideoDownload(){try{renderVideoDownload(await api("/api/shift-alarm/video-download"))}catch(e){$("video-download-state").textContent="확인 실패"}}
$("video-download-form").addEventListener("submit",async event=>{event.preventDefault();const url=$("video-download-url").value.trim();if(!url)return;if(!confirm("이 영상을 다운로드할 권한이 있으며, Mac 비공개 보관함에 최대 5GB 파일을 24시간 저장할까요?"))return;$("video-download-submit").disabled=true;try{const data=await api("/api/shift-alarm/video-download",{method:"POST",body:JSON.stringify({url,approved:true})});renderVideoDownload(data);notice("Mac에 영상 다운로드를 요청했습니다.")}catch(e){notice(e.message,true);await loadVideoDownload()}finally{await loadVideoDownload()}});
async function videoAction(action,confirmation,actionUrl){if(!actionUrl)return;if(confirmation&&!confirm(confirmation))return;try{const data=await api(actionUrl,{method:"POST",body:JSON.stringify({action})});notice(data.message);if(action==="delete"||action==="cancel_transfer"||action==="extract_subtitle")await loadVideoDownload()}catch(e){notice(e.message,true)}}
$("video-bulk-select-all").addEventListener("click",()=>{
    if(selectedVideoIds.size&&selectedVideoIds.size===lastVideoItems.length)selectedVideoIds.clear();
    else lastVideoItems.forEach(item=>selectedVideoIds.add(item.file_id));
    renderVideoLibrary(lastVideoItems);
});
$("video-bulk-download").addEventListener("click",()=>{
    const targets=lastVideoItems.filter(item=>selectedVideoIds.has(item.file_id)&&item.transfer_state!=="downloading");
    if(!targets.length){notice("다운로드할 수 있는 항목이 없습니다(이미 전송 중인 파일은 제외됩니다).",true);return}
    if(!confirm(`선택한 ${targets.length}개 파일을 순서대로 Safari로 받을까요? 한 번에 하나씩 진행되며, 각 파일을 받은 뒤 '다음 파일 받기'를 눌러야 이어집니다.`))return;
    startVideoBulkQueue("download",targets);
});
$("video-bulk-save-photos").addEventListener("click",()=>{
    const targets=lastVideoItems.filter(item=>selectedVideoIds.has(item.file_id)&&item.transfer_state==="complete");
    if(!targets.length){notice("Safari 전송이 완료된 항목만 사진에 저장할 수 있습니다.",true);return}
    startVideoBulkQueue("photos",targets);
});
$("video-bulk-delete").addEventListener("click",async()=>{
    const targets=lastVideoItems.filter(item=>selectedVideoIds.has(item.file_id));
    if(!targets.length)return;
    if(!confirm(`선택한 ${targets.length}개 파일을 Mac에서 완전히 삭제할까요? iPhone으로 받았어도 그 사본은 지워지지 않지만, 이 Mac 원본은 되돌릴 수 없습니다.`))return;
    const button=$("video-bulk-delete");
    button.disabled=true;
    let failed=0;
    for(const item of targets){
        try{await api(item.action_url,{method:"POST",body:JSON.stringify({action:"delete"})})}
        catch(e){failed++}
    }
    selectedVideoIds.clear();
    notice(failed?`${targets.length-failed}개 삭제, ${failed}개 실패했습니다.`:`${targets.length}개 파일을 DB에서 삭제했습니다.`,Boolean(failed));
    await loadVideoDownload();
});
loadVolume();
loadNowPlaying();
loadVideoDownload();
setInterval(loadNowPlaying,5000);
setInterval(loadVideoDownload,3000);
$("notifications").addEventListener("click",async()=>{const center=$("notification-center"),opening=center.classList.contains("hidden");center.classList.toggle("hidden",!opening);$("notifications").setAttribute("aria-expanded",String(opening));if(opening)await loadNotifications()});$("notification-close").addEventListener("click",()=>{$("notification-center").classList.add("hidden");$("notifications").setAttribute("aria-expanded","false")});document.addEventListener("keydown",event=>{if(event.key==="Escape")$("notification-close").click()});$("refresh").addEventListener("click",()=>{load();loadSunziStatus();loadVideoDownload();loadNotifications()});$("time-profile").addEventListener("change",()=>currentStatus&&render(currentStatus));$("check-all").addEventListener("click",async()=>{if(!currentStatus?.daily_routine?.length||!confirm("남아 있는 오늘의 일일 루틴을 모두 체크할까요?"))return;$("check-all").disabled=true;try{const result=await api("/api/shift-alarm/routine/check-all",{method:"POST"});currentStatus.daily_routine.forEach(item=>item.checked=true);render(currentStatus);notice(`${result.updated}개 루틴을 체크했습니다.`)}catch(e){notice(e.message,true);$("check-all").disabled=false}});load();loadSunziStatus();loadNotifications();setInterval(loadSunziStatus,5000);setInterval(loadNotifications,30000);
