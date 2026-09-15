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
const shots = [
  ['01-timeline','timeline','Everything lands in one Timeline.',[14,61,720,730],'01 / ARRIVE'],
  ['02-task','task','A request becomes a task.',[410,70,776,523],'02 / ORGANIZE'],
  ['03-agent','agent','The agent does the work.',[426,255,760,675],'03 / WORK'],
  ['04-review','review','The last word is yours.',[200,125,800,525],'04 / APPROVE'],
  ['05-assistant','assistant','One conversation. One next step.',[528,61,658,635],'05 / YOUR ASSISTANT'],
  ['06-morning','digest','Your day, before it gets busy.',[528,61,658,638],'06 / MORNING BRIEF'],
  ['07-coding-clis','cli','Your tools. Your choice.',[110,65,980,440],'KEY FEATURE / CODING CLIS'],
  ['08-hub','hub','Good discoveries stay useful.',[250,65,936,514],'KEY FEATURE / SHARED KNOWLEDGE'],
  ['09-handoffs','handoffs','Leave the next agent a head start.',[210,145,780,490],'KEY FEATURE / LIVE HANDOFFS'],
  ['11-learned-memory','learned','Memory you can read and change.',[338,121,848,625],'KEY FEATURE / LEARNED.MD'],
];
const browser = await launch();
const page = await browser.newPage();
const escape = text => text.replaceAll('&','&amp;').replaceAll('<','&lt;');
try {
  for (const [name,source,title,clip,kicker] of shots) {
    if (process.argv.includes('--timeline-only') && source !== 'timeline') continue;
    if (process.argv.includes('--memory-update') && !['timeline','learned'].includes(source)) continue;
    const data = (await readFile(path.join(scratch,source+'.png'))).toString('base64');
    const [x,y,w,h] = clip, scale = 1120/w, cropH = Math.round(h*scale);
    const height = cropH + 202;
    await page.setViewport({width:1200,height,deviceScaleFactor:1});
    await page.setContent(`<!doctype html><html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',sans-serif;background:#eaf0eb;color:#233e3b}
      main{padding:30px 40px 20px;background:radial-gradient(ellipse at top right,#d1e4d8,transparent 65%),linear-gradient(135deg,#f2f4ee,#e7eeea);}
      .eyebrow{font-size:13px;font-weight:700;letter-spacing:2px;display:flex;align-items:center;color:#57726a}
      .eyebrow span{margin-left:auto;font-size:13px;letter-spacing:1px;color:#678078}
      h1{font-size:34px;letter-spacing:-1.2px;font-weight:650;line-height:1.2;margin:12px 0 25px}
      .crop{position:relative;overflow:hidden;width:1120px;height:${cropH}px;border-radius:12px;background:#fcfbf9;box-shadow:0 14px 32px #24483a18,0 0 0 1px #506d5826}
      .crop img{position:absolute;max-width:none;width:${1200*scale}px;height:auto;left:${-x*scale}px;top:${-y*scale}px}
      footer{display:flex;align-items:center;justify-content:space-between;height:57px;font-size:12px;color:#637b72;letter-spacing:.25px}
      footer b{font-size:13px;font-weight:600;color:#3c5a51} .dot{color:#6a886e;margin-right:6px}
    </style><main><div class="eyebrow">${escape(kicker)}<span>TASKUARY</span></div><h1>${escape(title)}</h1><div class="crop"><img src="data:image/png;base64,${data}"></div><footer><b><span class="dot">●</span> ${source==='digest'?'A brief. A calendar. A clear next step.':'Connected work. Your approval.'}</b><span>Real app · fictional demo data</span></footer></main></html>`);
    await page.evaluate(() => Promise.all([...document.images].map(i => i.decode())));
    await page.screenshot({path:path.join(out,name+'.png')});
    if (source === 'digest') {
      // A complete first frame also serves as the thumbnail when animation is disabled.
      const frames = [`file '${path.join(out,name+'.png').replaceAll('\\','/')}'\nduration 1.2`];
      for (let i=0; i<25; i++) {
        const png = (await readFile(path.join(scratch,`morning-${String(i).padStart(2,'0')}.png`))).toString('base64');
        await page.evaluate(async png => { const img=document.querySelector('.crop img'); img.src='data:image/png;base64,'+png; await img.decode(); },png);
        const frame = path.join(scratch,`framed-morning-${String(i).padStart(2,'0')}.png`);
        await page.screenshot({path:frame});
        frames.push(`file '${frame.replaceAll('\\','/')}'\nduration ${i===24 ? 3 : 0.08}`);
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
