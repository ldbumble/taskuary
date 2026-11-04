// Record the real static demo, with fictional fixtures, into a narrated H.264 MP4.
// See docs/product-demo/README.md. Does not change or deploy the website.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawn, execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { launch } from './browser.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(root, '.codex-tmp/tq1299');
const build = path.join(scratch, 'build');
const output = process.env.TASKUARY_OUTPUTS;
const check = process.argv.includes('--check');
const scenes = [
  { id: '01', title: 'Your work, at a glance', caption: 'Workload, response times, and progress in one dashboard.',
    voice: 'Here is Taskuary at a glance. See what came in, how much became a task, what is still open, and how quickly replies go out. One dashboard brings the work into focus.' },
  { id: '02', title: 'Look closer', caption: 'Filter by channel. Switch a chart to its underlying table.',
    voice: 'Want a closer look? Filter by channel, or change the time range. Switch a chart to a table to see the numbers behind the picture.' },
  { id: '03', title: 'Catch the quiet threads', caption: 'The Advisor brings a forgotten follow-up back into view.',
    voice: 'The Advisor also catches work that has gone quiet. Here, a supplier quote is running out, and nobody has replied. The idea explains why it was raised and links back to the original message.' },
  { id: '04', title: 'Keep the context with the task', caption: 'The original request and the next steps stay together.',
    voice: 'Open a task and the request is already there. You can see what arrived, why it became work, and where the agent and close out steps belong. No rebuilding the context in another chat.' },
  { id: '05', title: 'Review the reply before it goes', caption: 'A prepared draft. Your edits. Your decision to send.',
    voice: 'When a reply is ready, read it right beside the request. Edit the draft, add someone, or ask for another version. The send button stays yours. In this demo, nothing is sent.' },
  { id: '06', title: 'See the work. Decide what happens next.', caption: 'Dashboards · Advisor ideas · Tasks · Review',
    voice: 'See the work. Catch the quiet threads. Keep the decisions yours. That is Taskuary.' },
];
await mkdir(scratch, { recursive: true });
await writeFile(path.join(scratch, 'scenes.json'), JSON.stringify(scenes, null, 2));
if (process.argv.includes('--prepare')) {
  console.log(path.join(scratch, 'scenes.json'));
  process.exit(0);
}
assert.ok(output || check, 'Set TASKUARY_OUTPUTS to the destination folder.');
if (output) await mkdir(output, { recursive: true });
const ffmpeg = process.env.FFMPEG_PATH || execFileSync('python', ['-c', 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'], { encoding: 'utf8', windowsHide: true }).trim();
const run = (cmd, args) => new Promise((resolve, reject) => {
  const child = spawn(cmd, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let tail = ''; child.stderr.on('data', d => { tail = (tail + d).slice(-3000); });
  child.on('error', reject); child.on('exit', code => code === 0 ? resolve() : reject(Error(tail)));
});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const target = path.resolve(build, '.' + decodeURIComponent(url.pathname), url.pathname.endsWith('/') ? 'index.html' : '');
  if (!target.startsWith(build + path.sep)) return res.writeHead(403).end();
  try {
    const data = await readFile(target);
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.woff2': 'font/woff2' };
    res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream' }).end(data);
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser, activeRecorder;
const errors = [], blocked = [], chapters = [];
try {
  browser = await launch();
  const page = await browser.newPage();
  page.on('pageerror', e => errors.push(e.message));
  await page.setRequestInterception(true);
  page.on('request', req => {
    const url = new URL(req.url());
    if (['http:', 'https:'].includes(url.protocol) && (url.origin !== origin || url.pathname.startsWith('/api/'))) {
      blocked.push(url.pathname); req.abort();
    } else req.continue();
  });
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(origin, { waitUntil: 'networkidle0' });
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{margin:0;background:#142b30;color:#f7f6ef;font-family:'Segoe UI',sans-serif}
    header{height:76px;display:flex;align-items:center;padding:0 34px;gap:28px}header strong{font-size:28px;letter-spacing:-1px}
    #title{border-left:1px solid #6a8585;padding-left:28px;font-size:26px}#label{margin-left:auto;color:#c3d4c8;font-size:16px}
    iframe{display:block;width:1856px;height:874px;margin:0 32px;border:1px solid #718782;border-radius:12px;background:#f6f4ef}
    footer{height:126px;padding:20px 36px;display:flex;align-items:center;gap:26px}#step{color:#b5cdbb;font-size:17px;letter-spacing:2px}
    #caption{font-size:28px;max-width:1370px;line-height:1.35}#note{margin-left:auto;font-size:15px;color:#b5cdbb;max-width:180px;line-height:1.5}
    #progress{height:4px;background:#adc9aa;width:0}#cursor{position:fixed;z-index:9999;pointer-events:none;width:20px;height:20px;border:3px solid white;border-radius:50%;background:#36685d;box-shadow:0 0 0 6px #9abc9855;transform:translate(-50%,-50%)}
    #cursor.click{box-shadow:0 0 0 18px #9abc9877;background:#d4e7b9}
    #end{display:none;position:fixed;inset:76px 32px 130px;background:#142b30f8;border-radius:12px;align-items:center;justify-content:center;flex-direction:column;text-align:center}
    #end small{color:#b5d0b7;font-size:22px;letter-spacing:3px}#end h1{font-size:78px;line-height:1.15;letter-spacing:-3px;font-weight:500;margin:35px 0}#end p{font-size:28px;color:#c9dacf}
    </style></head><body><header><strong>Taskuary</strong><div id="title"></div><div id="label">PRODUCT TOUR · FICTIONAL DATA</div></header>
    <iframe src="${origin}/"></iframe><footer><span id="step"></span><span id="caption"></span><span id="note">Scripted demo<br>Nothing sends or runs</span></footer><div id="progress"></div><div id="cursor"></div>
    <div id="end"><small>TASKUARY</small><h1>See the work.<br>Keep the decisions yours.</h1><p>Dashboards &nbsp;·&nbsp; Advisor ideas &nbsp;·&nbsp; Tasks &nbsp;·&nbsp; Review</p><small>taskuary.com</small></div></body></html>`);
  await page.waitForFunction(() => document.querySelector('iframe')?.contentDocument?.querySelector('.tq-pile-row .card'));
  const frame = page.frames().find(f => f.parentFrame());
  await frame.evaluate(() => document.fonts.ready);
  const point = async element => {
    await element.scrollIntoView(); const box = await element.boundingBox(); assert.ok(box);
    const x = box.x + box.width / 2, y = box.y + box.height / 2;
    await page.mouse.move(x, y, { steps: check ? 1 : 18 });
    await page.evaluate(({x,y}) => Object.assign(document.querySelector('#cursor').style,{left:x+'px',top:y+'px'}),{x,y});
    await delay(check ? 20 : 400);
  };
  const click = async element => {
    assert.ok(element, 'Missing click target'); await point(element);
    await page.evaluate(() => document.querySelector('#cursor').classList.add('click'));
    await element.click(); await delay(check ? 100 : 450);
    await page.evaluate(() => document.querySelector('#cursor').classList.remove('click'));
  };
  const find = async (selector, text) => {
    await frame.waitForFunction(({selector,text}) => [...document.querySelectorAll(selector)].some(e=>e.offsetParent && e.textContent.includes(text)),{}, {selector,text});
    return (await frame.evaluateHandle(({selector,text}) => [...document.querySelectorAll(selector)].find(e=>e.offsetParent && e.textContent.includes(text)),{selector,text})).asElement();
  };
  const row = async title => { await click(await find('.tq-pile-row .card',title)); await delay(700); };
  const body = () => frame.evaluate(() => document.body.innerText);
  await row('Taskuary at a glance');
  await frame.waitForFunction(()=>document.body.innerText.includes('Median reply time'));
  let seconds=0;
  for (let i=0;i<scenes.length;i++) {
    const scene=scenes[i];
    await page.evaluate(({scene,i,n}) => {
      document.querySelector('#title').textContent=scene.title; document.querySelector('#caption').textContent=scene.caption;
      document.querySelector('#step').textContent=String(i+1).padStart(2,'0')+' / '+String(n).padStart(2,'0');
      document.querySelector('#progress').style.width=((i+1)/n*100)+'%';
    },{scene,i,n:scenes.length});
    const raw=path.join(scratch,scene.id+'.webm');
    const recorder=check?null:await page.screencast({path:raw,ffmpegPath:ffmpeg,fps:25,format:'webm'});
    activeRecorder=recorder; const started=performance.now();
    if (i===0) { assert.match(await body(),/How far it got/); }
    if (i===1) {
      await delay(check?50:700);
      const select=await frame.$('select'); assert.ok(select); await point(select); await select.select('email');
      await delay(check?100:2100);
      assert.equal(await select.evaluate(e=>e.value),'email');
      await click(await find('button','30 days'));
      await delay(check?100:1800);
      await click(await find('button','Table'));
      await delay(check?100:2000);
      await select.select('');
    }
    if (i===2) {
      await row('badge printer'); assert.match(await body(),/no reply since Monday/);
      await delay(check?100:6000);
      await click(await find('[data-tq-idea-from] a, [data-tq-idea-from] button',"Paula Vance"));
      await click(await find('.tq-item-msg-h','Paula Vance'));
      await frame.waitForFunction(()=>document.body.innerText.includes('valid until Friday'),{timeout:10000}).catch(async error=>{
        await page.screenshot({path:path.join(scratch,'source-failure.png')});
        await writeFile(path.join(scratch,'source-failure.txt'),await body()); throw error;
      });
      assert.match(await body(),/Paula Vance/);
    }
    if (i===3) { await row('Month-end close'); assert.match(await body(),/bank feed disagree/); }
    if (i===4) {
      await row('Invoice 88213');
      await frame.waitForSelector('textarea');
      const draft=await frame.$$eval('textarea',els=>els.find(e=>e.offsetParent && e.value.length>30)?.value || '');
      assert.ok(draft.length>30,'The reply draft is empty');
      await delay(check?100:3500);
      const editor=(await frame.evaluateHandle(()=>[...document.querySelectorAll('textarea')].find(e=>e.offsetParent && e.value.length>30))).asElement();
      await point(editor);
    }
    if (i===5) await page.evaluate(()=>{document.querySelector('#end').style.display='flex';document.querySelector('#cursor').style.display='none';});
    assert.doesNotMatch(await body(),/Something in this view failed to draw/);
    await page.screenshot({path:path.join(scratch,`scene-${scene.id}.png`)});
    if (!check) {
      const wav=path.join(scratch,'audio',scene.id+'.wav');
      const duration=Number(execFileSync('python',['-c','import wave,sys; w=wave.open(sys.argv[1]); print(w.getnframes()/w.getframerate())',wav],{encoding:'utf8',windowsHide:true}).trim());
      const length=Math.max(duration+1.4,(performance.now()-started)/1000+1);
      await delay(Math.max(0,length*1000-(performance.now()-started)));
      await recorder.stop(); activeRecorder=null;
      await run(ffmpeg,['-y','-i',raw,'-i',wav,'-map','0:v:0','-map','1:a:0','-vf','fps=25,format=yuv420p','-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-b:a','160k','-af','adelay=350|350,apad','-t',String(length),'-movflags','+faststart',path.join(scratch,scene.id+'.mp4')]);
      chapters.push({...scene,start:seconds,duration:length}); seconds+=length;
    }
    console.log(`${check?'CHECK':'RECORDED'} ${scene.id}: ${scene.title}`);
  }
  assert.deepEqual(errors,[]); assert.deepEqual(blocked,[]);
  if (!check) {
    const concat=path.join(scratch,'concat.txt');
    await writeFile(concat,scenes.map(s=>`file '${path.join(scratch,s.id+'.mp4').replaceAll('\\','/')}'`).join('\n'));
    const stamp=s=>new Date(Math.round(s*1000)).toISOString().slice(11,23).replace('.',',');
    let cue=0;
    const subtitles=chapters.flatMap(s=>{
      const sentences=s.voice.match(/[^.!?]+[.!?]+/g) || [s.voice];
      const count=sentences.reduce((n,t)=>n+t.length,0); let at=s.start+.35;
      return sentences.map(sentence=>{
        const end=at+(s.duration-1.4)*sentence.length/count;
        const text=`${++cue}\n${stamp(at)} --> ${stamp(end)}\n${sentence.trim()}\n`; at=end; return text;
      });
    }).join('\n');
    const srt=path.join(scratch,'captions.srt'); await writeFile(srt,subtitles);
    const metadata=path.join(scratch,'chapters.txt');
    await writeFile(metadata,';FFMETADATA1\ntitle=Taskuary — Dashboards and Advisor ideas\ncomment=Real static demo; fictional data; synthetic narration; nothing sends or runs.\n'+chapters.map(s=>`[CHAPTER]\nTIMEBASE=1/1000\nSTART=${Math.round(s.start*1000)}\nEND=${Math.round((s.start+s.duration)*1000)}\ntitle=${s.title}\n`).join(''));
    const final=path.join(output,'taskuary-showcase.mp4');
    await run(ffmpeg,['-y','-f','concat','-safe','0','-i',concat,'-i',srt,'-i',metadata,'-map','0:v','-map','0:a','-map','1:s','-map_metadata','2','-map_chapters','2','-c','copy','-c:s','mov_text','-metadata:s:s:0','language=eng','-movflags','+faststart',final]);
    await writeFile(path.join(scratch,'recording.json'),JSON.stringify({recordedAt:new Date().toISOString(),commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),duration:seconds,chapters,errors,blocked,output:final},null,2));
    console.log(JSON.stringify({output:final,seconds,errors,blocked}));
  }
} finally {
  if (activeRecorder) await activeRecorder.stop().catch(()=>{});
  if (browser) await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
