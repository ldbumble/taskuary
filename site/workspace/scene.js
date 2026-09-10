import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { RoundedBoxGeometry } from './vendor/RoundedBoxGeometry.js';
import { createWorkspaceMotion } from './motion.js';

const $ = (id) => document.getElementById(id);
const world = $('world');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
} catch (error) {
  $('loading').textContent = 'This preview needs a browser with WebGL enabled.';
  throw error;
}
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.7));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
world.prepend(renderer.domElement);
renderer.domElement.setAttribute('aria-label', '3D miniature office. Drag to rotate, scroll to zoom. Click the floor to take the room apart and rebuild it. Click agents, the door, window, plants or clock. Press Home to reset the view.');
const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-8, 8, 6, -6, .1, 100);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enablePan = false;
controls.enableZoom = true;
controls.minZoom = .85;
controls.maxZoom = 1.65;
controls.enableDamping = true;
controls.minAzimuthAngle = -.7;
controls.maxAzimuthAngle = 1.2;
controls.minPolarAngle = .7;
controls.maxPolarAngle = 1.2;
controls.touches.ONE = THREE.TOUCH.ROTATE;
function resetCamera() { camera.position.set(11, 10, 15); controls.target.set(0, 1, 0); camera.zoom = 1; camera.updateProjectionMatrix(); controls.update(); }
resetCamera();
scene.add(new THREE.HemisphereLight(0xfffbef, 0xb4bab1, 2.0));
const sunlight = new THREE.DirectionalLight(0xffe8c8, 3.2);
sunlight.position.set(-4, 11, 6); sunlight.castShadow = true;
sunlight.shadow.mapSize.set(2048, 2048);
Object.assign(sunlight.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: .1, far: 35 });
sunlight.shadow.bias = -.0005; sunlight.shadow.normalBias = .035; sunlight.shadow.radius = 4;
scene.add(sunlight);
const fill = new THREE.DirectionalLight(0xe4edff, 1.0); fill.position.set(6, 5, -4); scene.add(fill);
const mats = {};
function mat(color, roughness = .85) { const key = color + ':' + roughness; return mats[key] ||= new THREE.MeshStandardMaterial({ color, roughness }); }
const C = { wall: '#e8e0d1', trim: '#b99b73', wood: '#c5a47b', cream: '#e8e6dc', sage: '#799077', slate: '#637d8d', wine: '#8a3646', dark: '#424b45' };
const roundedCache = new Map();
function box(parent, w, h, d, color, x = 0, y = 0, z = 0, radius = .04) {
  const key = [w,h,d,radius].join(',');
  if (!roundedCache.has(key)) roundedCache.set(key, new RoundedBoxGeometry(w,h,d,2,Math.min(radius,w/3,h/3,d/3)));
  const m = new THREE.Mesh(roundedCache.get(key), mat(color));
  m.position.set(x,y,z); m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
}
const ballGeo = new THREE.SphereGeometry(1, 20, 14);
function ball(parent, sx, sy, sz, color, x=0,y=0,z=0) { const m = new THREE.Mesh(ballGeo,mat(color)); m.scale.set(sx,sy,sz);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m; }
function cylinder(parent, rt, rb, h, color, x=0,y=0,z=0) {const m=new THREE.Mesh(new THREE.CylinderGeometry(rt,rb,h,20),mat(color));m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
function group(parent,x=0,y=0,z=0) {const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);return g;}
function textTexture(lines, bg, fg, size=30) {
  const canvas=document.createElement('canvas');canvas.width=512;canvas.height=256;const ctx=canvas.getContext('2d');ctx.fillStyle=bg;ctx.fillRect(0,0,512,256);ctx.fillStyle=fg;ctx.textAlign='center';ctx.font=`500 ${size}px Segoe UI, sans-serif`;lines.forEach((line,i)=>ctx.fillText(line,256,128+(i-(lines.length-1)/2)*size*1.4));const t=new THREE.CanvasTexture(canvas);t.colorSpace=THREE.SRGBColorSpace;return t;
}
function art(parent,x,y,z,lines,w=1.25,h=.85) {box(parent,w+.1,h+.1,.09,C.trim,x,y,z);const p=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshStandardMaterial({map:textTexture(lines,'#f2ece0','#676b5d',27),roughness:1}));p.position.set(x,y,z+.052);parent.add(p);}
const room=group(scene);
const shadowCanvas=document.createElement('canvas');shadowCanvas.width=128;shadowCanvas.height=128;const sc=shadowCanvas.getContext('2d');const gradient=sc.createRadialGradient(64,64,12,64,64,64);gradient.addColorStop(0,'rgba(70,60,45,.20)');gradient.addColorStop(1,'rgba(70,60,45,0)');sc.fillStyle=gradient;sc.fillRect(0,0,128,128);const ground=new THREE.Mesh(new THREE.PlaneGeometry(15,12),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(shadowCanvas),transparent:true,depthWrite:false}));ground.rotation.x=-Math.PI/2;ground.position.y=-.315;scene.add(ground);
box(room,10.3,.35,8.25,'#ddd3c2',0,-.13,0,.15);
const floorSurface=box(room,10.08,.08,8.05,'#ede5d7',0,.08,0,.06);
// Subtle seams give the miniature's oak floor a readable scale.
for(let i=0;i<17;i++)box(room,.012,.003,7.9,'#d9cfbd',-4.8+i*.6,.123,0,.001);
// Back wall is built around an actual doorway and arched window opening.
box(room,.8,3.95,.19,C.wall,-4.6,2.04,-3.95);
box(room,.8,3.95,.19,C.wall,-2.05,2.04,-3.95);
box(room,1.75,.65,.19,C.wall,-3.33,3.69,-3.95);
box(room,2.05,3.95,.19,C.wall,3.95,2.04,-3.95);
box(room,4.0,1.0,.19,C.wall,.7,.64,-3.95);
// Arched plaster section above the glass.
const arch=new THREE.Shape();arch.moveTo(-1.65,4.02);arch.lineTo(3,4.02);arch.lineTo(3,1.14);arch.lineTo(2.45,1.14);arch.lineTo(2.45,2.55);arch.absarc(.7,2.55,1.75,0,Math.PI,false);arch.lineTo(-1.05,1.14);arch.lineTo(-1.65,1.14);arch.closePath();
const archMesh=new THREE.Mesh(new THREE.ExtrudeGeometry(arch,{depth:.19,bevelEnabled:false}),mat(C.wall));archMesh.position.z=-4.045;archMesh.castShadow=true;archMesh.receiveShadow=true;room.add(archMesh);
// Window: pale blue glass and slender warm wood framing.
const glassShape=new THREE.Shape();glassShape.moveTo(-1.03,1.14);glassShape.lineTo(2.43,1.14);glassShape.lineTo(2.43,2.55);glassShape.absarc(.7,2.55,1.73,0,Math.PI,false);glassShape.closePath();
const glass=new THREE.Mesh(new THREE.ShapeGeometry(glassShape),new THREE.MeshStandardMaterial({color:'#cddcda',roughness:.3,metalness:.03}));glass.position.z=-3.94;room.add(glass);
const arcPoints=[];for(let i=0;i<=48;i++){let a=i/48*Math.PI;arcPoints.push(new THREE.Vector3(.7+1.75*Math.cos(a),2.55+1.75*Math.sin(a),-3.79));}
const archTrim=new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(arcPoints),48,.047,8,false),mat(C.trim));room.add(archTrim);
for(const x of [-1.05,.7,2.45])box(room,.075,x===.7?3.1:1.5,.15,C.trim,x,x===.7?2.68:1.85,-3.8);
box(room,3.58,.075,.15,C.trim,.7,2.55,-3.8);box(room,3.8,.12,.42,'#d3b68e',.7,1.18,-3.78);
for(const x of [-4.19,-2.46])box(room,.13,3.2,.3,C.trim,x,1.72,-3.89);
box(room,1.86,.13,.3,C.trim,-3.33,3.31,-3.89);
const doorPivot=group(room,-4.15,.16,-3.88);doorPivot.rotation.y=-1.12;
box(doorPivot,1.57,3.03,.13,'#b99468',.79,1.51,0,.045);
box(doorPivot,1.23,1.7,.035,'#c5a67d',.79,1.91,.078);box(doorPivot,1.23,.7,.035,'#c5a67d',.79,.58,.078);
ball(doorPivot,.055,.055,.055,'#72664b',1.35,1.45,.13);
box(room,.17,.8,3.3,C.wall,-5, .54,2.25);
box(room,.17,1.5,1.8,C.wall,5,.89,-3.1);
art(room,3.9,2.5,-3.81,['SMALL TEAM.','BIG PROGRESS.'],1.23,.85);
// Wall clock.
const clockFace=cylinder(room,.34,.34,.07,'#eae5d7',-2.04,2.8,-3.8);clockFace.rotation.x=Math.PI/2;
const clockRim=new THREE.Mesh(new THREE.TorusGeometry(.35,.028,8,48),mat(C.trim));clockRim.position.set(-2.04,2.8,-3.74);room.add(clockRim);
box(room,.023,.2,.025,'#686d5d',-2.04,2.88,-3.73);const hand=box(room,.17,.022,.025,'#686d5d',-1.97,2.78,-3.73);hand.rotation.z=-.4;
function plant(x,z,scale=1) {const g=group(room,x,.14,z);g.scale.setScalar(scale);cylinder(g,.24,.17,.43,'#d5d2c0',0,.23,0);cylinder(g,.205,.205,.018,'#6b5e47',0,.452,0);for(let i=0;i<8;i++){const a=i*2.4;const y=.67+(i%3)*.18;const stem=cylinder(g,.014,.018,y-.4,'#738160',Math.cos(a)*.08,.4+(y-.4)/2,Math.sin(a)*.08);stem.rotation.z=Math.cos(a)*.25;const leaf=ball(g,.13,.34,.065,i%2?'#879569':'#657d59',Math.cos(a)*.22,y,Math.sin(a)*.22);leaf.rotation.set(Math.sin(a)*.65, a,Math.cos(a)*.65);}return g;}
const plants=[plant(-4.5,2.4,1.6),plant(4.5,-3.05,1.7),plant(-1.6,-3.2,.8)];
// Low cabinet and the small things that make this a lived-in workspace.
box(room,2,.92,.6,'#bca17a',-4,.62,1.15);for(let x=-4.5;x<=-3.5;x+=1)box(room,.018,.74,.025,'#947e5f',x, .62,1.46);
for(let i=0;i<3;i++)box(room,.65,.09,.34,['#7d8d86','#dbd4c1','#aeb7ad'][i],-3.7,1.13+i*.09,1.16);
art(room,-4.03,1.63,1.13,['MAKE ROOM','FOR GOOD WORK'],.74,.65);
// Woven-looking rug, with quiet edge stitches.
box(room,6.5,.014,3.5,'#c7c4af',.35,.139,1.05,.12);
for(let i=0;i<36;i++)box(room,.023,.005,3.3,'#d6d1bd',-2.7+i*.175,.15,1.05,.001);

const screenTextures=[];
function screenTexture(type) {
  const canvas=document.createElement('canvas');canvas.width=384;canvas.height=240;
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
  const draw=(t)=>{const c=canvas.getContext('2d');c.fillStyle=type==='code'?'#293c42':'#eef0e9';c.fillRect(0,0,384,240);c.fillStyle=type==='code'?'#4b6265':'#d2dbd2';c.fillRect(0,0,384,25);c.fillStyle='#8fac99';for(let i=0;i<3;i++){c.beginPath();c.arc(15+i*14,12,3,0,7);c.fill();}if(type==='code'){for(let i=0;i<11;i++){c.fillStyle=['#86bcb0','#cad2bd','#c4ae80'][i%3];c.fillRect(20+(i%3)*13,43+i*16,70+((i*47)%210),5);}c.fillStyle='#abc9a1';c.fillRect(22,224,8+Math.floor(t)%2*6,6);}else{c.fillStyle='#5c716b';c.font='bold 18px sans-serif';c.fillText('Weekly overview',22,57);for(let i=0;i<6;i++){let h=35+i*16+Math.sin(t+i)*6;c.fillStyle=i===5?'#5e7c69':'#9cb2aa';c.fillRect(28+i*53,195-h,30,h);}c.fillStyle='#ced6cc';c.fillRect(22,211,330,2);}};
  draw(0);screenTextures.push({texture,draw});return texture;
}
function desk(x,z,angle,type='code') {
  const g=group(room,x,0,z);g.rotation.y=angle;
  box(g,2.1,.14,1.06,C.wood,0,1.13,0,.06);
  for(const a of [-.89,.89])for(const b of [-.38,.38])box(g,.1,1,.1,'#a98d6b',a,.62,b);
  box(g,.43,.72,.76,'#c1a37b',.73,.75,0);
  for(let i=0;i<3;i++){box(g,.39,.015,.016,'#aa8c64',.73,.65+i*.22,.389);box(g,.12,.025,.025,'#88795f',.73,.72+i*.22,.41);}
  box(g,.42,.045,.28,'#697572',-.1,1.23,-.2);box(g,.075,.29,.075,'#697572',-.1,1.39,-.27);
  box(g,1.03,.68,.07,'#435357',-.1,1.77,-.27,.035);
  const screen=new THREE.Mesh(new THREE.PlaneGeometry(.93,.57),new THREE.MeshBasicMaterial({map:screenTexture(type)}));screen.position.set(-.1,1.77,-.226);g.add(screen);
  box(g,.66,.035,.23,'#d9dbd1',-.15,1.226,.25,.024);
  for(let r=0;r<3;r++)for(let k=0;k<10;k++)box(g,.04,.008,.037,'#b5bdb2',-.43+k*.06,1.248,.18+r*.06,.005);
  ball(g,.065,.025,.095,'#d9dbd1',.36,1.24,.28);
  cylinder(g,.095,.075,.18,'#7a907c',-.77,1.29,-.12);const handle=new THREE.Mesh(new THREE.TorusGeometry(.065,.017,8,16),mat('#7a907c'));handle.position.set(-.88,1.30,-.12);g.add(handle);
  box(g,.3,.05,.39,'#e6dfcc',.74,1.24,-.2);box(g,.3,.028,.39,'#74888b',.74,1.28,-.2);
  // Chair is behind the keyboard, toward the viewer.
  cylinder(g,.045,.045,.46,'#72776b',0,.44,.93);
  for(let i=0;i<5;i++){const a=i/5*Math.PI*2;const leg=box(g,.055,.055,.55,'#666e64',Math.sin(a)*.2,.23,.93+Math.cos(a)*.2);leg.rotation.y=a;ball(g,.065,.065,.065,'#575d55',Math.sin(a)*.45,.2,.93+Math.cos(a)*.45);}
  box(g,.69,.16,.66,'#c8c6b4',0,.74,.93,.12);box(g,.69,.73,.14,'#c8c6b4',0,1.1,1.25,.12);
  return g;
}
const desks=[desk(-1.45,-1.9,.12,'chart'),desk(2.05,-1.25,-.23),desk(2.5,2.12,Math.PI+.6,'chart'),desk(-1.65,3.7,-.12)];
const extension=group(room,-1.65,0,4.15);
box(extension,3.05,.35,2.65,'#ddd3c2',0,-.13,0,.13);
box(extension,2.91,.08,2.5,'#ede5d7',0,.08,0,.05);
for(let i=0;i<6;i++)box(extension,.012,.003,2.38,'#d9cfbd',-1.25+i*.5,.123,0,.001);

function character(parent,{shirt,skin,hair,name}, seated=false) {
  const root=group(parent);const torso=group(root,0,seated?.76:.85,0);
  ball(torso,.245,.34,.18,shirt,0,.31,0);box(torso,.33,.16,.29,'#5d655f',0,-.01,0,.07);
  cylinder(torso,.082,.09,.15,skin,0,.64,0);
  const head=group(torso,0,.86,0);ball(head,.245,.28,.22,skin);
  ball(head,.253,.19,.222,hair,0,.14,-.025);
  for(let i=0;i<5;i++)ball(head,.092,.08,.08,hair,-.17+i*.078,.18+Math.sin(i)*.025,.16);
  for(const x of [-.24,.24])ball(head,.049,.07,.045,skin,x,0,0);
  for(const x of [-.083,.083])ball(head,.019,.025,.012,'#333c35',x,.01,.208);
  ball(head,.035,.028,.035,skin,0,-.049,.222);
  const smile=new THREE.Mesh(new THREE.TorusGeometry(.047,.006,5,14,Math.PI*.7),mat('#8e6350'));smile.position.set(0,-.078,.208);smile.rotation.z=Math.PI*1.15;head.add(smile);
  const arms=[];
  for(const sign of [-1,1]) {const pivot=group(torso,sign*.225,.5,0);ball(pivot,.09,.18,.105,shirt,sign*.035,-.14,0);ball(pivot,.072,.14,.072,skin,sign*.045,-.37,0);ball(pivot,.065,.075,.044,skin,sign*.045,-.50,0);for(let f=0;f<4;f++)ball(pivot,.012,.052-Math.abs(f-1.5)*.008,.015,skin,sign*.045-.043+f*.027,-.574,0);ball(pivot,.025,.043,.02,skin,sign*.045+.071,-.495,0);arms.push(pivot);}
  const legs=[];
  for(const sign of [-1,1]) {const leg=group(torso,sign*.115,-.02,0);ball(leg,.095,.22,.10,'#5d655f',0,-.19,0);const shin=group(leg,0,-.37,0);ball(shin,.083,.19,.083,'#5d655f',0,-.14,0);box(shin,.17,.11,.27,'#e5ddcc',0,-.33,.055,.05);legs.push({leg,shin});}
  // Little chest badge makes the agents a family without provider logos.
  box(torso,.07,.08,.013,'#dadfd3',-.10,.36,.169,.01);
  const a={root,torso,head,arms,legs,seated,name,baseY:torso.position.y};setSeat(a,seated);return a;
}
function setSeat(a,seated){a.seated=seated;a.baseY=seated?.76:.85;a.torso.position.y=a.baseY;for(const {leg,shin} of a.legs){leg.rotation.x=seated?-Math.PI/2:0;shin.rotation.x=seated?Math.PI/2:0;}for(const arm of a.arms)arm.rotation.x=seated?-1.1:0;}
const agents=[
  character(desks[0],{shirt:C.sage,skin:'#bc8d6d',hair:'#49433a',name:'Ada'},true),
  character(desks[1],{shirt:C.slate,skin:'#d6a985',hair:'#544b3e',name:'Leo'},true),
  character(desks[2],{shirt:'#e7e3d5',skin:'#e0b793',hair:'#765442',name:'Nora'},true),
  character(room,{shirt:'#93a08b',skin:'#d7ac83',hair:'#655540',name:'Milo'})
];
for(let i=0;i<3;i++){agents[i].root.position.set(0,0,.86);agents[i].root.rotation.y=Math.PI;}
const milo=agents[3],nora=agents[2];
const taskCard=box(milo.root,.36,.45,.035,'#f0ebde',0,1.12,.28,.025);for(let i=0;i<4;i++)box(taskCard,.22,.013,.008,'#859180',0,.1-i*.06,.022,.002);
const halo=new THREE.Mesh(new THREE.RingGeometry(.35,.40,48),new THREE.MeshBasicMaterial({color:C.wine,transparent:true,opacity:.55,side:THREE.DoubleSide}));halo.rotation.x=-Math.PI/2;halo.position.set(0,.162,0);desks[2].add(halo);
const path=[[-3.33,-4.7],[-3.33,-2.85],[-3.5,.8],[-3.45,3.25],[-1.75,4.56]];
const pathLengths=path.slice(1).map((p,i)=>Math.hypot(p[0]-path[i][0],p[1]-path[i][1]));const pathLength=pathLengths.reduce((a,b)=>a+b,0);
let time=0,paused=reducedMotion.matches,arrivalAt=0,arrival=false,arrivalPhase='entering',nextArrival=Infinity;
let approvalState='working',approvalAt=5,completeAt=-100,tick=0,lastScreen=-1,evening=false;
let hovered=null,selected=null,focused=null,pointerDown=null,dragged=false,multiTouch=false;
const activePointers=new Set();
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2(),v=new THREE.Vector3();
const targets=new Map();
const tasks=[
  ['Reconciling the weekly report','Ada is checking the figures and highlighting what changed.'],
  ['Fixing the import','Leo is tracing the issue and checking the fix.'],
  ['Preparing your weekly update','Nora is putting the finishing touches on a draft.'],
  ['Taking care of the next task','Milo brings work in and gets it underway.']
];
const incomingWork=[
  {channel:'GITHUB',from:'priya-dev · pull request',subject:'Fix rounding in the weekly report',detail:'Milo is checking the rounding and running the report again.'},
  {channel:'REPORT',from:'Nightly check · scheduled',subject:'Three balances need a closer look',detail:'Milo is comparing the balances and tracing the differences.'},
  {channel:'EMAIL',from:'Jordan · Payroll',subject:'The timesheet import stopped working',detail:'Milo is checking the import and finding where it went wrong.'}
];
let incomingIndex=-1,flightAt=-100,feedSignature='',deskPackedForArrival=false;
function updateFeed(){
  const work=incomingWork[Math.max(0,incomingIndex)%incomingWork.length];
  const stage=arrival?arrivalPhase:'working';
  const signature=[incomingIndex,stage,approvalState].join(':');
  if(signature===feedSignature)return;
  feedSignature=signature;
  $('task-channel').textContent=work.channel;$('task-from').textContent=work.from;$('task-subject').textContent=work.subject;
  $('task-route').textContent=stage==='working'?'in progress':stage==='leaving'?'task → an agent':'picked up';
  $('task-route').className='route-pill'+(stage==='working'?' done':'');
  $('task-explanation').textContent=stage==='working'?'Milo is on it at his desk.':stage==='leaving'?'Milo is heading over to collect it.':'Milo is bringing it into the studio.';
  $('incoming-task').dataset.stage=stage;
  const waiting=approvalState==='waiting',approved=approvalState==='approved';
  $('draft-route').textContent=waiting?'over to you':approved?'approved ✓':'drafting';
  $('draft-route').className='route-pill'+(waiting?' waiting':approved?' done':'');
  $('draft-explanation').textContent=waiting?'Nora has a draft ready. See her raised hand?':approved?'You gave the go-ahead. Nora has it from here.':'Nora is putting an answer together.';
  $('incoming-draft').dataset.stage=approvalState;
}
function animateHandoff(){
  const age=time-flightAt,slip=$('handoff-slip');
  slip.hidden=paused||age<0||age>1.65;
  if(slip.hidden)return;
  const card=$('incoming-task').getBoundingClientRect(),main=document.querySelector('main').getBoundingClientRect(),roomRect=world.getBoundingClientRect();
  const end=project(doorAnchor,new THREE.Vector3()),p=age/1.65,ease=p*p*(3-2*p);
  const startX=card.left-main.left+18,startY=card.top-main.top+card.height/2;
  const endX=roomRect.left-main.left+end.x,endY=roomRect.top-main.top+end.y;
  slip.style.left=(startX+(endX-startX)*ease)+'px';
  slip.style.top=(startY+(endY-startY)*ease-Math.sin(p*Math.PI)*65)+'px';
  slip.style.transform='translate(-50%,-50%) scale('+(1-p*.65)+') rotate('+(-p*8)+'deg)';
  slip.style.opacity=String(Math.min(1,p*8,(1-p)*6));
}
function say(s){if($('activity-text').textContent!==s)$('activity-text').textContent=s;}
function startTask(initial=false){
  if(arrival){say('Milo is already on his way.');return;}
  incomingIndex++;
  const work=incomingWork[incomingIndex%incomingWork.length];
  tasks[3]=[work.subject,work.detail];
  if(initial)flightAt=time+.4;
  arrival=true;arrivalAt=time;arrivalPhase=initial?'entering':'leaving';
  deskPackedForArrival=false;
  if(initial)motion.deploy();
  room.attach(milo.root);setSeat(milo,false);taskCard.visible=initial;
  if(initial)milo.root.position.set(path[0][0],0,path[0][1]);
  say(initial?'Milo is bringing in a new task.':'Milo is heading to the door for the next task.');
  if(paused)seatMilo();
}
function seatMilo(){
  arrival=false;nextArrival=time+18;
  desks[3].attach(milo.root);milo.root.position.set(0,0,.86);milo.root.rotation.set(0,Math.PI,0);
  setSeat(milo,true);taskCard.visible=false;
  say(approvalState==='waiting'?'Nora has a draft ready. Click her raised hand.':'Milo picked up the weekly report.');
}
function moveMilo(){
  let distance=(time-arrivalAt)*.9;
  if(arrivalPhase==='leaving'&&!deskPackedForArrival&&time-arrivalAt>2){motion.pack();deskPackedForArrival=true;}
  if(distance>=pathLength){
    if(arrivalPhase==='leaving'){arrivalPhase='entering';arrivalAt=time;flightAt=time;taskCard.visible=true;motion.deploy();say('A new task. Making room for Milo.');distance=0;}
    else{seatMilo();return;}
  }
  let dist=arrivalPhase==='leaving'?pathLength-distance:distance;
  let i=0;while(i<pathLengths.length-1&&dist>pathLengths[i]){dist-=pathLengths[i];i++;}
  const u=dist/pathLengths[i],a=path[i],b=path[i+1];
  milo.root.position.set(THREE.MathUtils.lerp(a[0],b[0],u),0,THREE.MathUtils.lerp(a[1],b[1],u));
  // attach() preserves the seated world orientation, which can decompose into
  // PI rotations on X/Z. Reset all axes so local +Z faces the walking direction.
  milo.root.rotation.set(0,Math.atan2(b[0]-a[0],b[1]-a[1])+(arrivalPhase==='leaving'?Math.PI:0),0);
  milo.torso.position.y=milo.baseY+Math.abs(Math.sin(time*6))*.035;
  for(let n=0;n<2;n++){milo.legs[n].leg.rotation.x=Math.sin(time*6+n*Math.PI)*.38;milo.arms[n].rotation.x=-.5+Math.sin(time*6+n*Math.PI)*.16;}
}
function requestApproval(){approvalState='waiting';say('Nora has a draft ready. Click her raised hand.');}
function register(id,object,anchor,offset,label,hint,action){
  object.userData.interaction=id;
  const button=document.createElement('button');
  button.id='hotspot-'+id;button.className='scene-hotspot';button.type='button';
  button.setAttribute('aria-label',label+' — '+hint);button.textContent=label;
  world.append(button);
  const target={id,object,anchor,offset,button,label,hint,action,meshes:[]};
  targets.set(id,target);
  // Each interactive object gets its own material, so the hover tint never leaks into the room.
  object.traverse(o=>{if(o.isMesh&&o.material.emissive){o.material=o.material.clone();target.meshes.push(o);}});
  button.addEventListener('click',()=>activate(id));
  button.addEventListener('focus',()=>{focused=id;showHint(id);});
  button.addEventListener('blur',()=>{focused=null;showHint(hovered);});
}
function activate(id){
  if(motion.busy&&id!=='clock')return;
  const target=targets.get(id);if(!target)return;
  $('desk-detail').hidden=true;selected=null;target.action();showHint(id);
}
function showHint(id){
  const t=targets.get(id);$('hover-hint').hidden=!t;
  if(!t)return;
  $('hover-hint').querySelector('strong').textContent=t.label;
  $('hover-hint').querySelector('span').textContent=typeof t.hint==='function'?t.hint():t.hint;
}
function inspectAgent(i){
  if(i===2&&approvalState==='waiting'){
    $('draft-dialog').showModal();$('hover-hint').hidden=true;return;
  }
  selected='agent-'+i;
  const panel=$('desk-detail');
  panel.querySelector('small').textContent=agents[i].name.toUpperCase()+' / '+(i===3&&arrival?'ON THE MOVE':'AT WORK');
  panel.querySelector('strong').textContent=i===2&&approvalState==='approved'?'Your draft is approved':tasks[i][0];
  panel.querySelector('p').textContent=tasks[i][1];
  panel.hidden=false;agents[i].helloAt=time;
  say(agents[i].name+' has this covered.');
}
const doorAnchor=group(doorPivot,.8,1.6,.1);
register('door',doorPivot,doorAnchor,new THREE.Vector3(),'The doorway','Click to see what comes in next',()=>startTask());
desks.forEach((d,i)=>register('agent-'+i,d,agents[i].head,new THREE.Vector3(0,.1,0),agents[i].name,
  i===2?'Click her raised hand to review the draft':'Click to peek at the work',()=>inspectAgent(i)));
milo.root.userData.interaction='agent-3';
register('window',glass,glass,new THREE.Vector3(.7,2.9,.1),'A change of atmosphere','Click for evening light',()=>{
  evening=!evening;
  sunlight.color.set(evening?'#ffc58f':'#ffe8c8');sunlight.intensity=evening?1.5:3.2;
  fill.color.set(evening?'#b6caff':'#e4edff');fill.intensity=evening?1.8:1;
  glass.material.color.set(evening?'#7c98b3':'#cddcda');
  world.classList.toggle('evening',evening);say(evening?'Evening settles in. Your team keeps going.':'A little more daylight.');
});
plants.forEach((p,i)=>register('plant-'+i,p,p,new THREE.Vector3(0,1.3,0),'A little breathing room','Give the leaves a nudge',()=>{
  p.userData.nudgedAt=time;
  if(paused){p.rotation.z=p.rotation.z?0:.1;}
  say('Even a busy workspace needs a little green.');
}));
register('clock',clockFace,clockFace,new THREE.Vector3(0,0,.1),'The wall clock','Click to pause or resume the little world',()=>{
  paused=!paused;say(paused?'A quiet moment. Click the clock to resume.':'And the work keeps moving.');
});
clockRim.userData.interaction='clock';hand.userData.interaction='clock';
register('studio',floorSurface,floorSurface,new THREE.Vector3(3.8,0,3.5),'Room for anything','Click to take the studio apart and watch it rebuild',()=>{
  if(motion.rebuild())say('A little room for a new possibility.');
});
for(const card of document.querySelectorAll('.incoming-card[data-agent]')){
  const id='agent-'+card.dataset.agent;
  card.addEventListener('click',()=>activate(id));
  card.addEventListener('pointerenter',()=>{hovered=id;});
  card.addEventListener('pointerleave',()=>{hovered=null;});
  card.addEventListener('focus',()=>{focused=id;});
  card.addEventListener('blur',()=>{focused=null;});
}

function hitAt(clientX,clientY){
  if(motion.busy)return null;
  const rect=renderer.domElement.getBoundingClientRect();
  pointer.set((clientX-rect.left)/rect.width*2-1,-(clientY-rect.top)/rect.height*2+1);
  raycaster.setFromCamera(pointer,camera);
  // Use the first visible surface: furniture and walls correctly occlude objects behind them.
  const hits=raycaster.intersectObject(room,true);
  for(const hit of hits){
    if(hit.object===halo||hit.object===hoverRing)continue;
    let visible=true;for(let o=hit.object;o&&o!==room;o=o.parent)if(!o.visible)visible=false;
    if(!visible)continue;
    let object=hit.object;
    while(object&&object!==room){if(object.userData.interaction)return object.userData.interaction;object=object.parent;}
    return null;
  }
  return null;
}
const canvas=renderer.domElement;
canvas.addEventListener('pointerdown',e=>{
  activePointers.add(e.pointerId);multiTouch=activePointers.size>1;
  pointerDown={x:e.clientX,y:e.clientY,id:e.pointerId};dragged=false;
  $('desk-detail').hidden=true;selected=null;$('hover-hint').hidden=true;
});
canvas.addEventListener('pointermove',e=>{
  if(pointerDown){if(Math.hypot(e.clientX-pointerDown.x,e.clientY-pointerDown.y)>6)dragged=true;return;}
  hovered=hitAt(e.clientX,e.clientY);canvas.style.cursor=hovered?'pointer':'grab';showHint(hovered);
});
canvas.addEventListener('pointerup',e=>{
  const down=pointerDown;
  if(down&&down.id===e.pointerId&&!dragged&&!multiTouch&&Math.hypot(e.clientX-down.x,e.clientY-down.y)<=6){
    const id=hitAt(e.clientX,e.clientY);if(id)activate(id);
  }
  activePointers.delete(e.pointerId);pointerDown=null;
  if(!activePointers.size)multiTouch=false;
});
canvas.addEventListener('pointercancel',e=>{activePointers.delete(e.pointerId);pointerDown=null;hovered=null;showHint(null);});
canvas.addEventListener('pointerleave',()=>{hovered=null;if(!focused)showHint(null);});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){if(motion.busy)motion.skip();selected=null;$('desk-detail').hidden=true;$('hover-hint').hidden=true;}
  if(e.key==='Home'&&world.contains(document.activeElement)){e.preventDefault();resetCamera();}
});
$('approve').addEventListener('click',()=>{
  approvalState='approved';completeAt=time;$('draft-dialog').close();say('Draft approved. Nora is taking care of the rest.');
});
$('draft-dialog').addEventListener('close',()=>{hovered=null;showHint(null);});
reducedMotion.addEventListener('change',e=>{paused=e.matches;});
const hoverRing=new THREE.Mesh(new THREE.RingGeometry(.49,.53,48),new THREE.MeshBasicMaterial({color:'#849781',transparent:true,opacity:.7,side:THREE.DoubleSide,depthWrite:false}));
hoverRing.rotation.x=-Math.PI/2;hoverRing.visible=false;room.add(hoverRing);
const motion=createWorkspaceMotion({room,desks,agents,extension,reduced:reducedMotion.matches});
function project(obj,offset){
  obj.getWorldPosition(v);v.add(offset);v.project(camera);
  return {x:(v.x*.5+.5)*world.clientWidth,y:(-v.y*.5+.5)*world.clientHeight};
}
function pin(id,obj,offset,yLift=0){
  const node=$(id),p=project(obj,offset),half=node.offsetWidth/2+10;
  node.style.left=Math.max(half,Math.min(world.clientWidth-half,p.x))+'px';
  node.style.top=Math.min(world.clientHeight-15,Math.max(node.offsetHeight+8,p.y-yLift))+'px';
}
function resize(){
  const w=world.clientWidth,h=world.clientHeight;renderer.setSize(w,h);
  const aspect=w/h,span=aspect<1?14.9/aspect:12.7;
  camera.left=-span*aspect/2;camera.right=span*aspect/2;camera.top=span/2;camera.bottom=-span/2;camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(world);resize();
startTask(true);if(paused)requestApproval();
$('loading').hidden=true;
const clock=new THREE.Clock();
function animate(){
  requestAnimationFrame(animate);
  const dt=Math.min(clock.getDelta(),.05);
  motion.update(document.hidden?0:dt,paused);
  world.classList.toggle('assembling',motion.busy);
  $('construction-cue').hidden=!motion.busy&&motion.state.deskPhase!=='assembling'&&motion.state.deskPhase!=='packing';
  $('construction-cue').textContent=motion.busy?(motion.state.phase==='disassembling'?'A little space to reimagine.':'A workspace, coming together.'):(motion.state.deskPhase==='packing'?'All done. Making space.':'More work? A little more room.');
  if(!paused&&!document.hidden&&!motion.busy){
    time+=dt;
    if(arrival)moveMilo();else if(time>=nextArrival)startTask();
    if(approvalState==='working'&&time>=approvalAt)requestApproval();
    for(const a of agents){
      if(!a.seated)continue;
      a.torso.position.y=a.baseY+Math.sin(time*2+agents.indexOf(a))*.012;
      const hello=time-(a.helloAt??-100);
      a.head.rotation.y=hello<3?Math.sin(hello*3)*.25:Math.sin(time*.75+agents.indexOf(a))*.075;
      for(let i=0;i<2;i++)a.arms[i].rotation.x=-1.12+Math.sin(time*8+i*2)*.065;
    }
    plants.forEach(p=>{
      const age=time-(p.userData.nudgedAt??-100);
      p.rotation.z=age<5?Math.sin(age*8)*Math.exp(-age)*.2:Math.sin(time*.7)*.008;
    });
    doorPivot.rotation.y=THREE.MathUtils.damp(doorPivot.rotation.y,arrival||hovered==='door'?-1.32:-.8,3,dt);
    hand.rotation.z=-.4-time*.035;
    if(Math.floor(time*3)!==lastScreen){
      lastScreen=Math.floor(time*3);screenTextures.forEach(({texture,draw})=>{draw(time);texture.needsUpdate=true;});
    }
  }
  const waiting=approvalState==='waiting';
  nora.arms[0].rotation.z=waiting?-2.65+(paused?0:Math.sin(time*2.6)*.07):.12;
  nora.arms[0].rotation.x=waiting?-.1:-1.12;nora.arms[0].scale.y=waiting?1.4:1;nora.arms[0].position.y=waiting?.65:.5;
  halo.visible=waiting;halo.scale.setScalar(1+(paused?0:Math.sin(time*2)*.06));
  $('approval').hidden=!waiting;$('arrival-label').hidden=!arrival;$('complete').hidden=approvalState!=='approved'||time-completeAt>7;
  $('working-count').textContent=(4-Number(arrival)-Number(waiting))+' agents working';
  controls.update();scene.updateMatrixWorld();
  updateFeed();animateHandoff();if(motion.busy)$('handoff-slip').hidden=true;
  pin('working-label',desks[0],new THREE.Vector3(0,2.65,-.7));
  pin('arrival-label',milo.root,new THREE.Vector3(-.4,2.25,0));
  pin('approval',nora.head,new THREE.Vector3(0,.65,0));
  pin('complete',nora.root,new THREE.Vector3(0,2.4,0));
  const active=focused||hovered;
  for(const t of targets.values()){
    const amount=t.id===active?.10:0;
    for(const mesh of t.meshes){mesh.material.emissive.set('#9dba8a');mesh.material.emissiveIntensity=amount;}
    const p=project(t.anchor,t.offset);
    t.button.style.left=p.x+'px';t.button.style.top=p.y+'px';
    const stateHint=t.id==='clock'?(paused?'Click to resume motion':'Click to pause motion'):t.hint;
    t.button.setAttribute('aria-label',t.label+' — '+stateHint);
  }
  hoverRing.visible=!!active&&active.startsWith('agent-');
  if(hoverRing.visible){agents[Number(active.slice(-1))].root.getWorldPosition(v);hoverRing.position.set(v.x,.165,v.z);}
  if(active&&targets.has(active)&&!$('hover-hint').hidden){
    const t=targets.get(active);pin('hover-hint',t.anchor,t.offset,48);
  }
  if(selected){const t=targets.get(selected);pin('desk-detail',t.anchor,new THREE.Vector3(0,1,0),10);}
  renderer.render(scene,camera);tick++;
}
window.workspaceMockup={
  get state(){return {time,paused,arrival,arrivalPhase,approvalState,evening,hovered,selected,frames:tick,zoom:camera.zoom,motion:motion.state,
    agents:agents.map(a=>({name:a.name,seated:a.seated})),camera:camera.position.toArray(),
    walker:{position:milo.root.getWorldPosition(new THREE.Vector3()).toArray(),forward:new THREE.Vector3(0,0,1).transformDirection(milo.root.matrixWorld).toArray()}};},
  // Read-only projected locations let browser checks click actual rendered surfaces.
  get points(){
    const rect=canvas.getBoundingClientRect();
    return Object.fromEntries([...targets].map(([id,t])=>{
      const p=project(t.anchor,t.offset);return [id,{x:p.x+rect.left,y:p.y+rect.top}];
    }));
  }
};
animate();
