// Frame the browser captures at a readable README size. No UI text is redrawn.
// npm exec --yes --package=node@22 -- node website/render-readme.mjs
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { launch } from './browser.mjs';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(root, '.codex-tmp/readme');
const out = path.join(root, 'docs/readme');
await mkdir(out, { recursive: true });
// clip: [x,y,w,h] in the capture's CSS pixels, null = the capture is already the card (capture-readme's card()), or a file of one
const shots = [
  // 01-06 walk Ruth's request through the Chat and Task views; the rail on the left is the Timeline
  ['01-timeline-sources-and-times','home','Everything lands in one place.',[0,46,1200,954],'01 / ARRIVE'],
  ['02-task','task','A request becomes a task.',[350,66,835,360],'02 / ORGANIZE'],
  ['03-agent','agent','The agent works inside the chat.',null,'03 / WORK'],
  ['04-review','review','The last word is yours.',null,'04 / APPROVE'],
  ['05-assistant','assistant','One conversation. One next step.',[350,110,835,600],'05 / YOUR ASSISTANT'],
  ['06-morning','home','Your day, before it gets busy.','morning.json','06 / MORNING BRIEF'],
  ['07-coding-clis-chinese','cli','Your tools. Your choice.',null,'KEY FEATURE / CODING CLIS'],
  ['08-hub','hub','Good discoveries stay useful.',null,'KEY FEATURE / SHARED KNOWLEDGE'],
  ['09-handoffs','handoffs','Leave the next agent a head start.',null,'KEY FEATURE / LIVE HANDOFFS'],
  ['11-learned-memory','learned','Memory you can read and change.',null,'KEY FEATURE / LEARNED.MD'],
];
const browser = await launch();
const page = await browser.newPage();
const escape = text => text.replaceAll('&','&amp;').replaceAll('<','&lt;');
try {
  for (let [name,source,title,clip,kicker] of shots) {
    if (process.argv.includes('--cli-only') && source !== 'cli') continue;
    if (process.argv.includes('--home-only') && !name.startsWith('01-')) continue;
    if (process.argv.includes('--timeline-only') && source !== 'timeline') continue;
    if (process.argv.includes('--walk') && !/^0[1-6]-/.test(name)) continue;
    if (process.argv.includes('--memory-update') && !['timeline','learned'].includes(source)) continue;
    const buf = await readFile(path.join(scratch,(name==='06-morning' ? 'morning-24' : source)+'.png')), data = buf.toString('base64');
    const full = [buf.readUInt32BE(16)/2, buf.readUInt32BE(20)/2];       // the PNG's own size, at the capture's 2x
    if (typeof clip === 'string') clip = JSON.parse(await readFile(path.join(scratch,clip),'utf8'));
    const [x,y,w,h] = clip || [0,0,...full], scale = 1120/w, cropH = Math.round(h*scale);
    const height = cropH + 202;
    await page.setViewport({width:1200,height,deviceScaleFactor:1});
    await page.setContent(`<!doctype html><html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',sans-serif;background:#fff;color:#1f2328}
      main{padding:30px 40px 20px;background:#fff}
      .eyebrow{font-size:13px;font-weight:700;letter-spacing:2px;display:flex;align-items:center;color:#59636e}
      .eyebrow span{margin-left:auto;font-size:13px;letter-spacing:1px;color:#818b98}
      h1{font-size:34px;letter-spacing:-1.2px;font-weight:650;line-height:1.2;margin:12px 0 25px}
      .crop{position:relative;overflow:hidden;width:1120px;height:${cropH}px;border-radius:12px;background:#fcfbf9;box-shadow:0 8px 24px #1f232814,0 0 0 1px #d1d9e0}
      .crop img{position:absolute;max-width:none;width:${full[0]*scale}px;height:auto;left:${-x*scale}px;top:${-y*scale}px}
      footer{display:flex;align-items:center;justify-content:space-between;height:57px;font-size:12px;color:#59636e;letter-spacing:.25px}
      footer b{font-size:13px;font-weight:600;color:#1f2328} .dot{color:#818b98;margin-right:6px}
    </style><main><div class="eyebrow">${escape(kicker)}<span>TASKUARY</span></div><h1>${escape(title)}</h1><div class="crop"><img src="data:image/png;base64,${data}"></div><footer><b><span class="dot">●</span> ${name==='06-morning'?'A brief. A calendar. A clear next step.':'Connected work. Your approval.'}</b><span>Real app · fictional demo data</span></footer></main></html>`);
    await page.evaluate(() => Promise.all([...document.images].map(i => i.decode())));
    await page.screenshot({path:path.join(out,name+'.png')});
    if (name === '06-morning') {
      // the still is the digest open (the thumbnail when animation is off); the GIF starts on the card as it opens
      const frames = [];
      for (let i=0; i<25; i++) {
        const png = (await readFile(path.join(scratch,`morning-${String(i).padStart(2,'0')}.png`))).toString('base64');
        await page.evaluate(async png => { const img=document.querySelector('.crop img'); img.src='data:image/png;base64,'+png; await img.decode(); },png);
        const frame = path.join(scratch,`framed-morning-${String(i).padStart(2,'0')}.png`);
        await page.screenshot({path:frame});
        frames.push(`file '${frame.replaceAll('\\','/')}'\nduration ${i===0 ? 1.2 : i===24 ? 3 : 0.08}`);
      }
      frames.push(`file '${path.join(scratch,'framed-morning-24.png').replaceAll('\\','/')}'`);
      const list = path.join(scratch,'morning-concat.txt');
      await writeFile(list,frames.join('\n'));
      const ffmpeg = process.env.FFMPEG_PATH || execFileSync('python',['-c','import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],{encoding:'utf8',windowsHide:true}).trim();
      execFileSync(ffmpeg,['-y','-v','error','-f','concat','-safe','0','-i',list,'-filter_complex','split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3','-loop','0',path.join(out,'06-morning.gif')],{windowsHide:true});
    }
    console.log(name);
  }
  await writeFile(path.join(scratch,'crops.json'),JSON.stringify(shots,null,2));
} finally { await browser.close(); }
