"use client";

import { useEffect, useRef, useState } from "react";

type Phase = "upload" | "camera" | "align" | "calibrate" | "ready" | "view" | "survey" | "result";
type Point = { x: number; y: number; t: number };
type WebGazer = {
  setRegression: (name: string) => WebGazer;
  setTracker: (name: string) => WebGazer;
  saveDataAcrossSessions: (value: boolean) => WebGazer;
  showPredictionPoints: (value: boolean) => WebGazer;
  showVideoPreview: (value: boolean) => WebGazer;
  setCameraConstraints: (constraints: MediaStreamConstraints) => Promise<void>;
  setGazeListener: (listener: (data: { x: number; y: number } | null) => void) => WebGazer;
  clearData: () => void;
  begin: () => Promise<WebGazer>;
  end: () => void;
};

const calibrationPositions = [
  [8, 12], [50, 12], [92, 12], [8, 50], [50, 50], [92, 50], [8, 88], [50, 88], [92, 88],
];

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraHostRef = useRef<HTMLDivElement>(null);
  const artworkRef = useRef<HTMLImageElement>(null);
  const gazeRef = useRef<Point[]>([]);
  const recordingRef = useRef(false);
  const webgazerRef = useRef<WebGazer | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("upload");
  const [cameraError, setCameraError] = useState("");
  const [calibration, setCalibration] = useState<number[]>(Array(9).fill(0));
  const [seconds, setSeconds] = useState(15);
  const [points, setPoints] = useState<Point[]>([]);
  const [rating, setRating] = useState({ liking: 5, interest: 5, clarity: 5 });
  const [isMobile, setIsMobile] = useState(false);
  const [isPortrait, setIsPortrait] = useState(true);

  useEffect(() => () => webgazerRef.current?.end(), []);

  useEffect(() => {
    const updateDevice = () => {
      setIsMobile(window.matchMedia("(pointer: coarse)").matches || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent));
      setIsPortrait(window.innerHeight >= window.innerWidth);
    };
    updateDevice();
    window.addEventListener("resize", updateDevice);
    window.addEventListener("orientationchange", updateDevice);
    return () => { window.removeEventListener("resize", updateDevice); window.removeEventListener("orientationchange", updateDevice); };
  }, []);

  useEffect(() => {
    if (phase !== "view") return;
    if (seconds <= 0) {
      recordingRef.current = false;
      setPoints([...gazeRef.current]);
      setPhase("survey");
      return;
    }
    const timer = window.setTimeout(() => setSeconds((v) => v - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [phase, seconds]);

  function chooseImage(file?: File) {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => { setImage(String(reader.result)); setPhase("camera"); };
    reader.readAsDataURL(file);
  }

  async function connectCamera() {
    setCameraError("");
    try {
      const module = await import("webgazer");
      const loaded = module as unknown as { webgazer?: WebGazer; default?: WebGazer | { webgazer?: WebGazer } };
      const defaultExport = loaded.default;
      const webgazer = (loaded.webgazer ??
        (defaultExport && "begin" in defaultExport ? defaultExport : defaultExport?.webgazer)) as WebGazer;
      if (!webgazer) throw new Error("시선 추정 모듈을 불러오지 못했습니다.");
      webgazerRef.current = webgazer;
      if (isMobile) await webgazer.setCameraConstraints({ video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      webgazer
        .setRegression("ridge")
        .setTracker("TFFacemesh")
        .saveDataAcrossSessions(false)
        .showPredictionPoints(false)
        .showVideoPreview(true)
        .setGazeListener((data) => {
          if (!data || !recordingRef.current || !artworkRef.current) return;
          const rect = artworkRef.current.getBoundingClientRect();
          if (data.x < rect.left || data.x > rect.right || data.y < rect.top || data.y > rect.bottom) return;
          gazeRef.current.push({ x: (data.x - rect.left) / rect.width, y: (data.y - rect.top) / rect.height, t: performance.now() });
        });
      await webgazer.begin();
      setPhase("align");
      window.setTimeout(mountCameraPreview, 50);
    } catch (error) {
      setCameraError(error instanceof Error ? error.message : "카메라를 연결할 수 없습니다. Chrome에서 권한을 확인해 주세요.");
    }
  }

  function mountCameraPreview() {
    const preview = document.getElementById("webgazerVideoContainer");
    if (preview && cameraHostRef.current) cameraHostRef.current.appendChild(preview);
  }

  function beginCalibration() {
    const preview = document.getElementById("webgazerVideoContainer");
    if (preview) document.body.appendChild(preview);
    setPhase("calibrate");
  }

  function returnToAlignment() {
    setPhase("align");
    window.setTimeout(mountCameraPreview, 50);
  }

  function hitCalibration(index: number) {
    setCalibration((current) => {
      const next = [...current];
      next[index] = Math.min(5, next[index] + 1);
      if (next.every((count) => count >= 5)) window.setTimeout(() => { webgazerRef.current?.showVideoPreview(false); setPhase("ready"); }, 350);
      return next;
    });
  }

  function startViewing() {
    gazeRef.current = [];
    setSeconds(15);
    recordingRef.current = true;
    setPhase("view");
  }

  function restart() {
    gazeRef.current = [];
    setPoints([]);
    setCalibration(Array(9).fill(0));
    webgazerRef.current?.clearData();
    setPhase("calibrate");
    webgazerRef.current?.showVideoPreview(true);
  }

  const heatPoints = points.filter((_, i) => i % Math.max(1, Math.floor(points.length / 100)) === 0).slice(0, 100);
  const first = points[0];
  const mean = points.length ? points.reduce((a, p) => ({ x: a.x + p.x / points.length, y: a.y + p.y / points.length }), { x: 0, y: 0 }) : null;
  const quality = points.length >= 180 ? "높음" : points.length >= 70 ? "보통" : "낮음";
  const dominant = dominantArea(points);
  const spread = gazeSpread(points, mean);
  const analysisCopy = points.length
    ? `첫 시선은 ${first ? areaName(first.x, first.y) : "작품 내부"}에서 시작했고, 전체 시선은 ${dominant.label}에 가장 많이 모였습니다${dominant.percent ? `(${dominant.percent}%)` : ""}. 시선 탐색 범위는 ${spread}으로 나타났습니다.`
    : "작품 내부에서 인식된 시선 좌표가 없어 위치 분석을 만들 수 없습니다. 카메라 연결과 얼굴 위치를 확인한 뒤 다시 시도해 주세요.";

  if (phase === "calibrate") return <><Calibration counts={calibration} onHit={hitCalibration} onCancel={returnToAlignment} isMobile={isMobile}/>{isMobile && !isPortrait && <OrientationGate/>}</>;

  return (
    <main>
      <header className="topbar"><a className="brand" href="#" onClick={() => location.reload()}>MUSE TRACE <span>β</span></a><p>예술가를 위한 시선 연구실</p><button className="ghost" onClick={() => alert(isMobile ? "휴대폰을 세로로 거치하고 얼굴과 35–45cm 거리를 유지하세요. 시선 데이터는 이 브라우저 안에서만 처리됩니다." : "밝은 곳에서 화면과 50–70cm 거리를 유지하세요. 시선 데이터는 이 브라우저 안에서만 처리됩니다.")}>실험 안내</button></header>
      {phase === "upload" && <>
        <section className="hero"><div><p className="eyebrow">WEBCAM EYE STUDY · MAC & MOBILE</p><div className="device-badge">{isMobile ? "MOBILE MODE · 전면 카메라" : "DESKTOP MODE · 웹캠"}</div><h1>관객의 시선이<br />작품 위에 남긴 흔적</h1><p className="lede">이미지 한 장과 카메라면 충분합니다. 관객이 무엇을 먼저 보고, 어디에 머물며, 무엇을 놓치는지 확인하세요.</p></div><div className="signal" aria-hidden="true"><i/><i/><i/><i/></div></section>
        <section className="workspace"><UploadPanel image={image} inputRef={inputRef} chooseImage={chooseImage}/><Protocol image={image}/></section>
      </>}

      {phase === "camera" && <section className="center-panel"><p className="eyebrow">STEP 02 · {isMobile ? "FRONT CAMERA" : "CAMERA"}</p><h1 className="section-title">{isMobile ? "휴대폰을 세로로 세워주세요" : "웹캠을 연결합니다"}</h1><p className="lede centered">{isMobile ? "손에 들지 말고 눈높이에 거치한 뒤 얼굴과 35–45cm 거리를 유지하세요. 전면 카메라를 사용합니다." : "카메라를 연결한 다음 실제 영상에서 얼굴 위치를 확인합니다. 영상은 녹화하거나 서버로 보내지 않습니다."}</p><div className="camera-icon" aria-hidden="true"><span/></div><div className="privacy-chip">영상 저장 안 함 · 좌표만 기기에서 계산</div>{cameraError && <p className="error">{cameraError}</p>}<button className="primary compact" onClick={connectCamera}>{isMobile ? "전면 카메라 허용" : "웹캠 권한 허용"} <span>→</span></button><button className="text-button" onClick={() => setPhase("upload")}>이전으로</button></section>}

      {phase === "align" && <section className="center-panel align-panel"><p className="eyebrow">STEP 02 · FACE POSITION</p><h1 className="section-title">얼굴을 선 안에<br/>맞춰주세요</h1><p className="lede centered">눈과 얼굴 전체가 보이고 초록색 테두리가 나타나면 준비된 것입니다.</p><div ref={cameraHostRef} className={`camera-frame live-camera ${isMobile ? "mobile-frame" : ""}`}><div className="face-guide">얼굴을 중앙에 유지하세요</div></div><button className="primary compact" onClick={beginCalibration}>얼굴 위치 확인 완료 <span>→</span></button></section>}

      {phase === "ready" && <section className="center-panel"><p className="eyebrow">CALIBRATION COMPLETE · {isMobile ? "MOBILE" : "DESKTOP"}</p><h1 className="section-title">15초 동안 자유롭게<br/>감상해 주세요</h1><p className="lede centered">{isMobile ? "휴대폰을 움직이지 말고 화면 중앙을 유지하세요. 작품은 화면에 맞춰 자동 조정됩니다." : "작품이 나타나면 평소처럼 바라보세요. 마우스를 움직이거나 화면 크기를 바꾸지 않는 것이 좋습니다."}</p><button className="primary compact" onClick={startViewing}>감상 시작 <span>15 SEC</span></button></section>}

      {phase === "view" && image && <section className="viewing"><div className="timer"><b>{seconds}</b><span>SEC</span></div><img ref={artworkRef} src={image} alt="감상 중인 작품" /></section>}

      {phase === "survey" && <section className="survey center-panel"><p className="eyebrow">STEP 05 · RESPONSE</p><h1 className="section-title">어떤 경험이었나요?</h1>{([['liking','마음에 들었다'],['interest','흥미로웠다'],['clarity','의도가 명확했다']] as const).map(([key,label]) => <label className="rating" key={key}><span>{label}</span><input type="range" min="1" max="10" value={rating[key]} onChange={(e)=>setRating({...rating,[key]:Number(e.target.value)})}/><b>{rating[key]}</b></label>)}<button className="primary compact" onClick={() => setPhase("result")}>결과 만들기 <span>→</span></button></section>}

      {phase === "result" && image && <section className="results"><div className="result-head"><div><p className="eyebrow">GAZE REPORT · {isMobile ? "MOBILE" : "DESKTOP"} · SINGLE VIEWER</p><h1 className="section-title">시선 리포트</h1></div><button className="ghost" onClick={restart}>다시 실험하기</button></div><div className="result-grid"><div className="heatmap"><div className="heat-art"><img src={image} alt="분석한 작품"/>{heatPoints.map((p,i)=><i key={i} style={{left:`${p.x*100}%`,top:`${p.y*100}%`}}/>)}{first&&<span className="first" style={{left:`${first.x*100}%`,top:`${first.y*100}%`}}>1</span>}</div></div><aside className="metrics"><p className="eyebrow">OBSERVATIONS</p><Metric value={quality} label="측정 신뢰도"/><Metric value={String(points.length)} label="유효 시선 샘플"/><Metric value={first ? areaName(first.x, first.y) : "—"} label="최초 포착 영역"/><Metric value={dominant.label} label={`최다 응시 영역${dominant.percent ? ` · ${dominant.percent}%` : ""}`}/><Metric value={spread} label="시선 탐색 범위"/><Metric value={mean ? areaName(mean.x,mean.y) : "측정 없음"} label="시선 중심 영역"/><Metric value={`${rating.liking}/10`} label="관객 선호도"/><div className="insight"><b>{points.length < 70 ? "잠정 분석" : "분석 결과"}</b><p>{analysisCopy}</p><small>{points.length < 70 ? "표본이 적어 방향성만 참고하세요. 데이터가 추가되면 결과가 달라질 수 있습니다." : isMobile ? "모바일 결과는 큰 영역 중심으로 해석하세요." : "여러 관객의 결과를 합치면 작품 경향을 더 안정적으로 판단할 수 있습니다."}</small></div></aside></div></section>}
      {isMobile && !isPortrait && phase !== "result" && <OrientationGate/>}
    </main>
  );
}

function UploadPanel({image,inputRef,chooseImage}:{image:string|null;inputRef:React.RefObject<HTMLInputElement|null>;chooseImage:(f?:File)=>void}) { return <div className="stage-card"><div className="card-head"><span>01</span><h2>작품 선택</h2><b>LOCAL ONLY</b></div><button className={`dropzone ${image?"has-image":""}`} onClick={()=>inputRef.current?.click()}>{image?<img src={image} alt="선택한 작품"/>:<><span className="plus">＋</span><strong>작품 이미지를 올려주세요</strong><small>JPG, PNG, WEBP · 이미지는 이 기기에서만 처리됩니다</small></>}</button><input ref={inputRef} type="file" accept="image/*" hidden onChange={(e)=>chooseImage(e.target.files?.[0])}/></div> }
function Protocol({image}:{image:string|null}) { return <aside className="protocol"><div className="card-head"><span>PROTOCOL</span><h2>실험 흐름</h2></div>{[["01","작품 준비","분석할 이미지를 선택합니다"],["02","웹캠 연결","얼굴 영상은 저장하지 않습니다"],["03","9점 보정","각 점을 다섯 번 클릭합니다"],["04","15초 감상","시선 좌표만 기기에 기록됩니다"],["05","결과 확인","히트맵과 관찰 지표를 봅니다"]].map(([n,t,d])=><div className="step" key={n}><b>{n}</b><div><strong>{t}</strong><small>{d}</small></div></div>)}<button className="primary" disabled={!image}>{image?"작품이 준비되었습니다":"먼저 작품을 선택하세요"}<span>✓</span></button><p className="privacy">카메라 접근은 실험 중에만 사용되며 언제든 중단할 수 있습니다.</p></aside> }
function Calibration({counts,onHit,onCancel,isMobile}:{counts:number[];onHit:(i:number)=>void;onCancel:()=>void;isMobile:boolean}) { const done=counts.reduce((a,b)=>a+b,0); return <main className={`calibration ${isMobile?"mobile-calibration":""}`}><div className="calibration-copy"><p className="eyebrow">STEP 03 · 9-POINT CALIBRATION</p><h2>점을 바라본 채<br/>각각 5번 {isMobile?"터치":"클릭"}하세요</h2><p>{done} / 45</p></div>{calibrationPositions.map(([x,y],i)=><button key={i} aria-label={`보정점 ${i+1}`} className={counts[i]>=5?"cal-dot done":"cal-dot"} style={{left:`${x}%`,top:`${y}%`}} onClick={()=>onHit(i)}><span>{counts[i]||""}</span></button>)}<button className="cancel" onClick={onCancel}>취소</button></main> }
function OrientationGate() { return <div className="orientation-gate"><div className="phone-glyph">↻</div><h2>휴대폰을 세로로 돌려주세요</h2><p>정확한 보정과 작품 표시를 위해 세로 모드가 필요합니다.</p></div> }
function Metric({value,label}:{value:string;label:string}) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div> }
function areaName(x:number,y:number) { const horizontal=x<.34?"왼쪽":x>.66?"오른쪽":"중앙"; const vertical=y<.34?"상단":y>.66?"하단":"중앙"; return horizontal===vertical?"화면 중앙":`${vertical} ${horizontal}`; }
function dominantArea(points:Point[]) { if (!points.length) return {label:"측정 없음",percent:0}; const counts=new Map<string,number>(); points.forEach((p)=>{const label=areaName(p.x,p.y);counts.set(label,(counts.get(label)||0)+1)}); const [label,count]=[...counts.entries()].sort((a,b)=>b[1]-a[1])[0]; return {label,percent:Math.round(count/points.length*100)}; }
function gazeSpread(points:Point[],mean:{x:number;y:number}|null) { if (!points.length||!mean) return "측정 없음"; const distance=points.reduce((sum,p)=>sum+Math.hypot(p.x-mean.x,p.y-mean.y),0)/points.length; return distance<.12?"집중됨":distance<.25?"균형 있게 탐색":"넓게 탐색"; }
