// Record the built static demo. Node 22+, an installed Chromium browser and FFmpeg.
// Narration WAVs are generated separately by product-demo-voice.ps1 on Windows.
import puppeteer from 'puppeteer-core';
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir, stat } from 'node:fs/promises';
import { spawn, execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const site = path.join(root, 'site');
const output = path.join(root, 'docs/product-demo');
const scratch = path.join(root, '.codex-tmp/product-demo');
const scenes = JSON.parse(await readFile(path.join(output, 'scenes.json'), 'utf8'));
const ffmpeg = process.env.FFMPEG_PATH || execFileSync('python', ['-c', 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'], { encoding: 'utf8', windowsHide: true }).trim();
const executablePath = process.env.TASKUARY_BROWSER_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const dry = process.argv.includes('--check');
const fromScene = Number(process.argv.find(arg=>arg.startsWith('--from='))?.split('=')[1] || 1);
const onlyScene = process.argv.find(arg=>arg.startsWith('--only='))?.split('=')[1];
const previousRecording = await readFile(path.join(output, 'recording.json'), 'utf8').then(JSON.parse).catch(()=>null);
await mkdir(scratch, { recursive: true });
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  const target = path.resolve(site, '.' + decodeURIComponent(url.pathname), url.pathname.endsWith('/') ? 'index.html' : '');
  if (!target.startsWith(site + path.sep)) { response.writeHead(403).end(); return; }
  try {
    const data = await readFile(target);
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png' };
    response.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream' }).end(data);
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await puppeteer.launch({ executablePath, headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
const errors = [], chapters = [];
let activeRecorder;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const run = (command, args) => new Promise((resolve, reject) => {
  const process = spawn(command, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let tail = ''; process.stderr.on('data', data => { tail = (tail + data).slice(-3000); });
  process.on('error', reject); process.on('exit', code => code === 0 ? resolve() : reject(Error(tail)));
});
try {
  const page = await browser.newPage();
  page.on('pageerror', e => errors.push(e.message));
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.evaluateOnNewDocument(() => {
    // Keep the invented September 3 workday coherent; this does not change the app bundle.
    const NativeDate = Date, start = performance.now(), base = new NativeDate('2026-09-03T10:24:00').getTime();
    window.Date = class extends NativeDate {
      constructor(...args) { super(...(args.length ? args : [base + performance.now() - start])); }
      static now() { return base + performance.now() - start; }
    };
    localStorage.setItem('tq-term-size-rev', '2'); localStorage.setItem('tq-term-size', '14');
  });
  await page.goto(`${origin}/demo/?workflow=numbers`, { waitUntil: 'networkidle0' });
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{margin:0;background:#142b30;color:#fff;font-family:'Segoe UI',sans-serif}
    header{height:82px;display:flex;align-items:center;padding:0 34px;gap:24px}strong{font-size:27px;letter-spacing:-1px}
    #title{font-size:24px;font-weight:500;border-left:1px solid #527077;padding-left:24px}#label{margin-left:auto;color:#b8ccbe;font-size:15px}
    iframe{display:block;width:1856px;height:870px;margin:0 32px;border:1px solid #728984;border-radius:12px;background:#f6f4ef}
    footer{padding:20px 36px;display:flex;gap:26px;align-items:center;height:111px}#step{color:#b8ccbe;font-size:15px;letter-spacing:2px}#caption{font-size:26px;font-weight:500;flex:1}
    #note{font-size:14px;color:#b8ccbe}#progress{height:4px;background:#9ebba0;width:0;transition:width 1s}
    #cursor{position:fixed;z-index:100000;left:0;top:0;pointer-events:none;width:20px;height:20px;border:3px solid #fff;background:#36685d;border-radius:50%;box-shadow:0 0 0 6px #9abc9855;transform:translate(-50%,-50%)}
    #cursor.click{box-shadow:0 0 0 17px #9abc9866;background:#d4e7b9}
    #end{display:none;position:fixed;inset:82px 32px 128px;background:#142b30f5;border-radius:12px;align-items:center;justify-content:center;flex-direction:column;text-align:center}
    #end h1{font-size:66px;max-width:1100px;line-height:1.1;margin:0 0 35px}#end p{font-size:30px;color:#d1ded3}#end small{font-size:20px;color:#a6c9aa}
    </style></head><body><header><strong>Taskuary</strong><div id="title"></div><div id="label">PRODUCT WALKTHROUGH · FICTIONAL WORKDAY</div></header>
    <iframe src="${origin}/demo/?workflow=numbers"></iframe><footer><span id="step"></span><span id="caption"></span><span id="note">Scripted demo · nothing sends or runs</span></footer><div id="progress"></div><div id="cursor"></div>
    <div id="end"><small>YOUR INBOX, STAFFED BY AI AGENTS</small><h1>Keep the work moving.<br>Keep the decisions yours.</h1><p>Request → Context → Agent work → Your review</p><small>Explore Taskuary at taskuary.com/demo/</small></div></body></html>`);
  await page.waitForFunction(() => document.querySelector('iframe')?.contentDocument?.body.innerText.includes('Latest vendor spend numbers'));
  const frame = page.frames().find(f => f.parentFrame());
  await Promise.race([frame.evaluate(() => document.fonts.ready), delay(5000)]);
  const visible = async (selector, text, includes = false) => {
    await frame.waitForFunction(({selector,text,includes}) => [...document.querySelectorAll(selector)].some(e => e.getBoundingClientRect().height && (includes ? e.textContent.trim().includes(text) : e.textContent.trim() === text)), {}, {selector,text,includes});
    const handle = await frame.evaluateHandle(({selector,text,includes}) => [...document.querySelectorAll(selector)].find(e => e.getBoundingClientRect().height && (includes ? e.textContent.trim().includes(text) : e.textContent.trim() === text)), {selector,text,includes});
    return handle.asElement();
  };
  const point = async element => {
    await element.scrollIntoView(); const b = await element.boundingBox();
    const x = b.x + b.width / 2, y = b.y + b.height / 2;
    await page.mouse.move(x, y, { steps: 22 });
    await page.evaluate(({x,y}) => { const c=document.querySelector('#cursor'); c.style.left=x+'px'; c.style.top=y+'px'; }, {x,y});
    await delay(dry ? 20 : 400);
  };
  const click = async (text, selector = 'button', includes = false) => {
    const element = await visible(selector, text, includes); await point(element);
    await page.evaluate(() => document.querySelector('#cursor').classList.add('click'));
    await element.click(); await delay(dry ? 100 : 350);
    await page.evaluate(() => document.querySelector('#cursor').classList.remove('click'));
    await element.dispose();
  };
  const nav = async text => {
    const handle = await frame.evaluateHandle(text => [...document.querySelectorAll('#tqTopNav div')].find(e => e.getBoundingClientRect().height && e.textContent.replace(/\d+/g,'').trim() === text), text);
    const element = handle.asElement(); assert.ok(element, `nav ${text}`); await point(element); await element.click(); await element.dispose(); await delay(550);
  };
  const task = async ref => { await nav('Tasks'); await click(ref, '[data-tq-task-row]', true); await delay(650); };
  const text = () => frame.evaluate(() => document.body.innerText);
  let seconds = 0;
  for (let i = 0; i < scenes.length; i++) {
    const scene = scenes[i];
    await page.evaluate(({scene,i,n}) => { document.querySelector('#title').textContent=scene.title; document.querySelector('#caption').textContent=scene.caption; document.querySelector('#step').textContent=`${String(i+1).padStart(2,'0')} / ${String(n).padStart(2,'0')}`; document.querySelector('#progress').style.width=((i+1)/n*100)+'%'; }, {scene,i,n:scenes.length});
    const raw = path.join(scratch, `${scene.id}.webm`);
    const reuse = !dry && (i + 1 < fromScene || (onlyScene && scene.id !== onlyScene));
    const recorder = dry || reuse ? null : await page.screencast({ path: raw, ffmpegPath: ffmpeg, fps: 25, format: 'webm' });
    activeRecorder = recorder;
    const started = performance.now();
    const searchConnections = async query => {
      const search = await frame.waitForSelector('input[placeholder^="Search connectors"]'); await point(search); await search.click({clickCount:3});
      await page.keyboard.down('Control'); await page.keyboard.press('A'); await page.keyboard.up('Control'); await search.type(query,{delay:dry?1:75}); await delay(550);
    };
    if (i === 0) {
      await delay(dry ? 50 : 200);
      await click('Walk me through my tasks');
      await frame.waitForFunction(()=>document.body.innerText.includes('Open TQ-0018'));
    }
    if (i === 1) { await nav('Connections'); await searchConnections('Outlook'); await click('Outlook mail','p'); }
    if (i === 2) { await nav('Connections'); await searchConnections('SQL Server'); await click('Microsoft SQL Server','p'); }
    if (i === 3) {
      await nav('Connections'); await searchConnections('AI CLI agents'); await click('AI CLI agents','p');
      await frame.waitForSelector('[data-connection="claude"]'); assert.match(await text(), /Codex/);
      await delay(dry?100:4500);
      await nav('Connections'); await searchConnections('Ollama'); await click('Local models (Ollama)','p');
    }
    if (i === 4) {
      await task('TQ-0018'); await frame.waitForFunction(() => document.body.innerText.includes('latest August vendor spend'));
      await delay(dry?100:1800); await click('Agent work','p,span,div'); await click('Send to agent');
    }
    if (i === 5) {
      await frame.waitForFunction(() => document.body.innerText.includes('August vendor spend is ready for review'), {timeout:30000}); assert.match(await text(), /192,600/);
      await (await visible('h2','August vendor spend is ready for review')).scrollIntoView();
    }
    if (i === 6) {
      await nav('Review'); await frame.waitForFunction(() => [...document.querySelectorAll('textarea')].some(e=>e.value.includes('August vendor spend was')));
      if (!dry) {
        await delay(5500);
        const editor = (await frame.evaluateHandle(()=>[...document.querySelectorAll('textarea')].find(e=>e.getBoundingClientRect().height && e.value.includes('August vendor spend was')))).asElement();
        await point(editor); await page.mouse.wheel({deltaY:140});
      }
    }
    if (i === 7) {
      await click('Approve & send');
      await frame.waitForFunction(() => ![...document.querySelectorAll('textarea')].some(e=>e.value.includes('August vendor spend was')));
      await delay(dry?100:4500);
      await page.evaluate(() => { document.querySelector('#end').style.display='flex'; document.querySelector('#cursor').style.display='none'; });
    }
    assert.doesNotMatch(await text(), /Something in this view failed to draw/);
    await page.screenshot({ path: path.join(scratch, `${scene.id}.png`) });
    if (!dry) {
      if (reuse) {
        const clip = path.join(scratch, `${scene.id}.mp4`);
        const length = Number(execFileSync('python',['-c','import imageio_ffmpeg,sys; r=imageio_ffmpeg.read_frames(sys.argv[1]); print(next(r)["duration"]); r.close()',clip],{encoding:'utf8',windowsHide:true}).trim());
        const earlier = previousRecording?.chapters.find(c=>c.id===scene.id);
        chapters.push({...scene,start:seconds,duration:length,capturedBuild:earlier?.capturedBuild || previousRecording?.demoIndex}); seconds+=length;
        console.log(`REUSED ${scene.id}: ${scene.title}`); continue;
      }
      const wav = path.join(scratch, 'audio', `${scene.id}.wav`);
      const duration = Number(execFileSync('python', ['-c', 'import wave,sys; w=wave.open(sys.argv[1]); print(w.getnframes()/w.getframerate())', wav], { encoding: 'utf8', windowsHide: true }).trim());
      const length = Math.max(duration + 1.3, (performance.now() - started) / 1000 + 1);
      await delay(Math.max(0, length * 1000 - (performance.now() - started)));
      await recorder.stop();
      activeRecorder = null;
      const clip = path.join(scratch, `${scene.id}.mp4`);
      await run(ffmpeg, ['-y','-i',raw,'-i',wav,'-map','0:v:0','-map','1:a:0','-vf','fps=25,format=yuv420p','-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-b:a','160k','-af','adelay=350|350,apad','-t',String(length),'-movflags','+faststart',clip]);
      chapters.push({ ...scene, start: seconds, duration: length }); seconds += length;
    }
    console.log(`${dry ? 'CHECK' : 'RECORDED'} ${scene.id}: ${scene.title}`);
  }
  assert.deepEqual(errors, []);
  if (!dry) {
    const concat = path.join(scratch, 'concat.txt');
    await writeFile(concat, scenes.map(s => `file '${path.join(scratch, `${s.id}.mp4`).replaceAll('\\','/')}'`).join('\n'));
    await run(ffmpeg, ['-y','-f','concat','-safe','0','-i',concat,'-c','copy','-movflags','+faststart',path.join(output,'taskuary-workflow.mp4')]);
    await run(ffmpeg, ['-y','-ss','0.1','-i',path.join(output,'taskuary-workflow.mp4'),'-frames:v','1','-update','1',path.join(output,'poster.jpg')]);
    const stamp = seconds => new Date(Math.round(seconds * 1000)).toISOString().slice(11,23);
    const cues = chapters.flatMap(s => {
      const sentences = s.voice.match(/[^.!?]+[.!?]+/g) || [s.voice];
      let offset = s.start + .35;
      return sentences.map(sentence => { const end = offset + (s.duration - 1.3) * sentence.length / sentences.reduce((n,x)=>n+x.length,0); const cue=`${stamp(offset)} --> ${stamp(end)}\n${sentence.trim()}\n`; offset=end; return cue; });
    });
    await writeFile(path.join(output,'captions.vtt'), 'WEBVTT\n\n' + cues.join('\n'));
    await writeFile(path.join(output,'recording.json'), JSON.stringify({ recordedAt:new Date().toISOString(), commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8',windowsHide:true}).trim(), demoIndex:await readFile(path.join(site,'demo/index.html'),'utf8').then(s=>s.match(/assets\/index-[^" ]+\.js/)?.[0]), scenarioClock:'2026-09-03 10:24 local; advances during playback', duration:seconds, chapters },null,2));
    console.log(`VIDEO ${seconds.toFixed(1)} seconds; ${((await stat(path.join(output,'taskuary-workflow.mp4'))).size/1024/1024).toFixed(1)} MB`);
  }
} catch (error) {
  const page = (await browser.pages()).at(-1);
  await page?.screenshot({path:path.join(scratch,'failure.png')});
  console.error(await page?.frames().find(f=>f.parentFrame())?.evaluate(()=>document.body.innerText));
  throw error;
} finally { await activeRecorder?.stop().catch(()=>{}); await browser.close(); await new Promise(resolve => server.close(resolve)); }
