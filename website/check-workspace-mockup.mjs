import { launch } from './browser.mjs';
import assert from 'node:assert/strict';
const browser=await launch({args:['--no-sandbox','--enable-unsafe-swiftshader']});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
try {
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setViewport({width:1536,height:1000,deviceScaleFactor:1});
  await page.goto('http://127.0.0.1:8766/docs/mockups/animated-workspace/',{waitUntil:'networkidle0'});
  await page.waitForFunction(()=>window.workspaceMockup?.state.motion.phase==='assembling');
  await page.screenshot({path:'../docs/mockups/animated-workspace/preview-assembly.png'});
  await page.waitForFunction(()=>window.workspaceMockup?.state.approvalState==='waiting',{timeout:45000});
  const state=()=>page.evaluate(()=>window.workspaceMockup.state);
  async function assertWalkingForward(){
    const a=await state();await delay(300);const b=await state();
    assert.equal(a.arrival,true);assert.equal(b.arrival,true);
    const movement=b.walker.position.map((n,i)=>n-a.walker.position[i]);
    const length=Math.hypot(...movement);
    assert.ok(length>.05,'agent actually moves');
    const alignment=movement.reduce((sum,n,i)=>sum+n*b.walker.forward[i],0)/length;
    assert.ok(alignment>.97,'agent faces travel direction; dot='+alignment);
  }
  await assertWalkingForward();
  assert.equal(await page.$('.intro'),null);
  assert.equal(await page.$eval('#incoming-draft',el=>el.dataset.stage),'waiting');
  assert.equal(await page.$eval('#incoming-task',el=>el.dataset.stage),'entering');
  const layout=await page.evaluate(()=>({room:document.querySelector('#world').getBoundingClientRect().right,feed:document.querySelector('.incoming-rail').getBoundingClientRect().left}));
  assert.ok(layout.room<=layout.feed,'feed does not cover the room');
  async function findSurface(id){
    const p=await page.evaluate(id=>window.workspaceMockup.points[id],id);
    for(const [dx,dy] of [[0,0],[0,8],[0,-8],[8,0],[-8,0],[0,16],[16,0],[-16,0],[0,-16],[24,8],[-24,8],[0,24]]){
      await page.mouse.move(p.x+dx,p.y+dy);await delay(30);
      if((await state()).hovered===id)return {x:p.x+dx,y:p.y+dy};
    }
    throw new Error('No visible interactive surface: '+id+' near '+JSON.stringify(p));
  }
  async function clickObject(id){const p=await findSurface(id);await page.mouse.click(p.x,p.y);await delay(80);return p;}
  assert.equal(await page.$('#new-task'),null);
  assert.equal(await page.$('#review'),null);
  await page.screenshot({path:'../docs/mockups/animated-workspace/preview-desktop.png'});
  await clickObject('agent-2');assert.equal(await page.$eval('#draft-dialog',d=>d.open),true);
  await page.click('#approve');assert.equal((await state()).approvalState,'approved');
  await page.waitForFunction(()=>document.querySelector('#incoming-draft').dataset.stage==='approved');
  await page.click('#incoming-task');assert.equal((await state()).selected,'agent-3');
  await page.keyboard.press('Escape');
  await clickObject('agent-0');assert.equal((await state()).selected,'agent-0');
  assert.equal(await page.$eval('#desk-detail',d=>d.hidden),false);
  await page.keyboard.press('Escape');assert.equal(await page.$eval('#desk-detail',d=>d.hidden),true);
  await clickObject('window');assert.equal((await state()).evening,true);
  await clickObject('window');assert.equal((await state()).evening,false);
  await clickObject('plant-0');
  await clickObject('clock');assert.equal((await state()).paused,true);
  const before=(await state()).time;await delay(300);assert.equal((await state()).time,before);
  await clickObject('clock');assert.equal((await state()).paused,false);
  await page.waitForFunction(()=>!window.workspaceMockup.state.arrival,{timeout:45000});
  assert.equal((await state()).motion.deskPhase,'ready');
  assert.equal(await page.$eval('#incoming-task',el=>el.dataset.stage),'working');
  await clickObject('door');assert.equal((await state()).arrival,true);assert.equal((await state()).arrivalPhase,'leaving');
  await assertWalkingForward();
  await page.waitForFunction(()=>window.workspaceMockup.state.motion.deskPhase==='packing',{timeout:10000});
  await page.waitForFunction(()=>window.workspaceMockup.state.arrivalPhase==='entering',{timeout:30000});
  await assertWalkingForward();
  assert.equal((await state()).motion.deskPhase,'assembling');
  await page.waitForFunction(()=>window.workspaceMockup.state.motion.deskPhase==='ready',{timeout:10000});
  await clickObject('studio');assert.equal((await state()).motion.phase,'disassembling');
  const storyTime=(await state()).time;await delay(350);assert.equal((await state()).time,storyTime);
  await page.screenshot({path:'../docs/mockups/animated-workspace/preview-exploded.png'});
  await page.waitForFunction(()=>window.workspaceMockup.state.motion.phase==='vanished',{timeout:10000});
  await page.waitForFunction(()=>window.workspaceMockup.state.motion.phase==='ready',{timeout:10000});
  assert.equal((await state()).motion.settled,true);
  await page.focus('#hotspot-studio');await page.keyboard.press('Enter');
  assert.equal((await state()).motion.phase,'disassembling');
  await page.keyboard.press('Escape');assert.equal((await state()).motion.settled,true);
  const p=await findSurface('agent-2'),camera=(await state()).camera;
  await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+65,p.y+8,{steps:12});await page.mouse.up();await delay(500);
  assert.notDeepEqual((await state()).camera,camera);
  assert.equal(await page.$eval('#draft-dialog',d=>d.open),false);
  assert.equal((await state()).selected,null);
  const zoom=(await state()).zoom;
  await page.mouse.wheel({deltaY:-120});await delay(300);assert.ok((await state()).zoom>zoom);
  await page.focus('#hotspot-clock');await page.keyboard.press('Enter');assert.equal((await state()).paused,true);
  await page.keyboard.press('Home');await delay(200);assert.equal((await state()).zoom,1);
  await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
  await page.setViewport({width:390,height:844,deviceScaleFactor:1});
  await page.reload({waitUntil:'networkidle0'});
  await page.waitForFunction(()=>window.workspaceMockup?.state.frames>2);
  assert.equal((await state()).paused,true);assert.equal((await state()).approvalState,'waiting');
  assert.equal((await state()).motion.phase,'ready');assert.equal((await state()).motion.deskPhase,'ready');
  await page.focus('#hotspot-studio');await page.keyboard.press('Enter');assert.equal((await state()).motion.phase,'ready');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'../docs/mockups/animated-workspace/preview-mobile.png',fullPage:true});
  const mobilePoint=await findSurface('agent-2');await page.touchscreen.tap(mobilePoint.x,mobilePoint.y);
  await page.waitForFunction(()=>document.querySelector('#draft-dialog').open);
  await page.click('#approve');assert.equal((await state()).approvalState,'approved');
  await page.click('#incoming-task');assert.equal((await state()).selected,'agent-3');
  assert.deepEqual(errors,[]);
  console.log('PASS: room assembly, disappearance/rebuild, repeated rebuild/skip, desk expansion/packing, forward walking, feed sync, 3D picking, approval, camera, keyboard, mobile touch, reduced motion; no page errors.');
}finally{await browser.close();}
