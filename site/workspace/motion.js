import * as THREE from 'three';

const clamp = x => Math.max(0, Math.min(1, x));
const smooth = x => x*x*(3-2*x);
const back = x => 1+2.3*Math.pow(x-1,3)+1.3*Math.pow(x-1,2);

// Transform wrappers keep animation offsets separate from the objects' real poses,
// including the walking agent, chair orientation, clock hands and door hinge.
function wrap(object, index, small=false) {
  const parent=object.parent, wrapper=new THREE.Group();
  parent.add(wrapper);wrapper.add(object);
  const seed=index*2.399963,position=object.position;
  const offset=new THREE.Vector3(
    small?Math.sin(seed)*(1.2+index%3*.3):position.x*.35+Math.sin(seed)*1.3,
    small?1.4+(index%4)*.3:2.1+(index%5)*.35,
    small?Math.cos(seed)*1.3:position.z*.3+Math.cos(seed)*1.1
  );
  return {wrapper,object,offset,spin:new THREE.Vector3(Math.sin(seed)*.45,Math.cos(seed)*.55,Math.sin(seed+.8)*.35),
    delay:small?Math.min(1,Math.max(0,position.y-.2)/1.7)*.40+(index%3)*.025:(position.y<.16?.02:Math.min(.40,.15+index%8*.035))};
}
function pose(track, amount, scale) {
  track.wrapper.visible=scale>.001;
  track.wrapper.position.copy(track.offset).multiplyScalar(amount);
  track.wrapper.rotation.set(track.spin.x*amount,track.spin.y*amount,track.spin.z*amount);
  track.wrapper.scale.setScalar(Math.max(.001,scale));
}
function arrive(tracks, progress) {
  for(const t of tracks){const p=clamp((progress-t.delay)/(1-t.delay));const e=back(p);pose(t,1-e,p===0?0:e);}
}
function leave(tracks, progress) {
  for(const t of tracks){const delay=(.7-t.delay)*.45;const p=clamp((progress-delay)/(1-delay));const e=p*p*p;pose(t,e,1-smooth(p));}
}
function settle(tracks){for(const t of tracks)pose(t,0,1);}

export function createWorkspaceMotion({room,desks,agents,extension,reduced}) {
  const movable=new Set(agents.map(a=>a.root));
  const pieces=desks[3].children.filter(o=>!movable.has(o)).map((o,i)=>wrap(o,i,true));
  const architecture=room.children.filter(o=>!movable.has(o)&&(o.isMesh||o.isGroup));
  const roomTracks=architecture.map((o,i)=>{
    const track=wrap(o,i),deskIndex=desks.indexOf(o);
    if(deskIndex>=0)track.delay=.42+deskIndex*.07;
    else if(o.isGroup)track.delay=.30;
    return track;
  });
  let phase=reduced?'ready':'assembling',elapsed=0,mode='opening',cycles=0;
  let deskPhase=reduced?'ready':'packed',deskElapsed=0,pendingDesk=!reduced;
  let revision=0;
  const reducedNow=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  function finish(){
    phase='ready';elapsed=0;settle(roomTracks);
    for(const a of agents)a.root.visible=true;
    room.rotation.y=0;
  }
  function deploy(){
    if(reducedNow()){deskPhase='ready';settle(pieces);extension.scale.set(1,1,1);return;}
    pendingDesk=true;
    if(phase==='ready'){deskPhase='assembling';deskElapsed=0;pendingDesk=false;revision++;}
  }
  function pack(){
    if(reducedNow())return;
    deskPhase='packing';deskElapsed=0;revision++;
  }
  function rebuild(){
    if(phase!=='ready')return false;
    if(reducedNow()){finish();return false;}
    phase='disassembling';mode='rebuild';elapsed=0;cycles++;return true;
  }
  function skip(){finish();deskPhase='ready';pendingDesk=false;settle(pieces);extension.scale.set(1,1,1);}
  function update(dt,paused){
    if(reducedNow()){skip();return;}
    if(paused)return;
    if(phase!=='ready'){
      elapsed+=dt;
      if(mode==='opening'){
        arrive(roomTracks,clamp(elapsed/3.7));
        if(elapsed>=3.7)finish();
      }else if(elapsed<1.65){phase='disassembling';leave(roomTracks,elapsed/1.65);}
      else if(elapsed<2.1){phase='vanished';leave(roomTracks,1);}
      else if(elapsed<5.8){phase='assembling';arrive(roomTracks,(elapsed-2.1)/3.7);}
      else finish();
      // A walking character has no furniture parent. Keep it out of the construction.
      for(const a of agents)if(a.root.parent===room)a.root.visible=phase==='ready';
    }
    if(phase==='ready'&&pendingDesk)deploy();
    if(phase==='ready')deskElapsed+=dt;
    if(deskPhase==='assembling'){
      const p=clamp(deskElapsed/2.5);arrive(pieces,p);
      const floor=back(clamp(p*2));extension.scale.set(Math.max(.001,floor),Math.max(.001,floor),Math.max(.001,floor));
      if(p===1){deskPhase='ready';settle(pieces);}
    }else if(deskPhase==='packing'){
      const p=clamp(deskElapsed/1.65);leave(pieces,p);
      const floor=1-smooth(clamp((p-.3)/.7));extension.scale.set(Math.max(.001,floor),Math.max(.001,floor),Math.max(.001,floor));
      if(p===1)deskPhase='packed';
    }else if(deskPhase==='packed'){
      leave(pieces,1);extension.scale.setScalar(.001);
    }
  }
  update(0,false);
  return {update,deploy,pack,rebuild,skip,
    get busy(){return phase!=='ready';},
    get state(){return {phase,deskPhase,cycles,revision,
      settled:phase==='ready'&&roomTracks.every(t=>t.wrapper.position.length()<1e-6&&Math.abs(t.wrapper.scale.x-1)<1e-6),
      pieces:pieces.length};}
  };
}
