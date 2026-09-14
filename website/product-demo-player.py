"""Build an offline video player from the finished recording and its captions."""
import html
import json
from pathlib import Path

out = Path(__file__).resolve().parents[1] / 'docs' / 'product-demo'
recording = json.loads((out / 'recording.json').read_text(encoding='utf-8'))
chapters = recording['chapters']
buttons = '\n'.join(
    f'<button data-time="{c["start"]:.3f}"><span>{int(c["start"])//60}:{int(c["start"])%60:02d}</span>{html.escape(c["title"])}</button>'
    for c in chapters
)
transcript = '\n'.join(f'<p><strong>{html.escape(c["title"])}</strong><br>{html.escape(c["voice"])}</p>' for c in chapters)
captions = json.dumps((out / 'captions.vtt').read_text(encoding='utf-8')).replace('<', '\\u003c')
page = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Taskuary — From request to reviewed reply</title>
<style>*{box-sizing:border-box}body{margin:0;background:#142b30;color:#f5f4ed;font:16px/1.5 system-ui,sans-serif}
main{max-width:1360px;margin:auto;padding:32px}header{display:flex;gap:20px;align-items:center;flex-wrap:wrap}header a{margin-left:auto}
h1{font-size:clamp(26px,4vw,42px);line-height:1.2;letter-spacing:-1px;margin:10px 0}p{color:#c5d6cf}a{color:#d5eac9}
.kicker{color:#a5c4ac;font-size:13px;letter-spacing:2px}video{display:block;width:100%;background:#0c1c20;border-radius:14px;margin:24px 0 20px;box-shadow:0 20px 70px #0005}
nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px}button{font:inherit;text-align:left;color:#edf5eb;background:#234147;border:1px solid #406067;border-radius:8px;padding:12px;cursor:pointer}button:hover,button:focus{background:#345b57}button span{display:inline-block;margin-right:12px;color:#aad2b0;font-variant-numeric:tabular-nums}details{margin-top:28px}summary{cursor:pointer}details p{max-width:900px}.small{font-size:13px;color:#abc2b8}</style></head>
<body><main><header><div><span class="kicker">TASKUARY · PRODUCT DEMO</span><h1>Someone asks for the latest numbers.<br>Your assistant prepares the reply.</h1></div><a href="taskuary-workflow.mp4" download>Download MP4</a></header>
<p>A first-time walkthrough: connect your tools, hand off the request, and review the result.</p>
<button id="playWithSound" type="button">▶ Play with narration</button> <span class="small">Spoken walkthrough · captions available in the player</span>
<video id="video" controls preload="metadata" poster="poster.jpg"><source src="taskuary-workflow.mp4" type="video/mp4"><track id="captions" kind="captions" srclang="en" label="English"></video>
<nav aria-label="Video chapters">BUTTONS</nav><p class="small">Recorded from the rebuilt demo. Fictional data, scripted assistant work, and synthetic narration. Nothing connects or sends.</p>
<details><summary>Read the transcript</summary>TRANSCRIPT</details>
</main><script>const video=document.querySelector('#video');document.querySelector('#playWithSound').addEventListener('click',()=>{video.muted=false;video.volume=1;video.play().catch(()=>{});});document.querySelector('#captions').src=URL.createObjectURL(new Blob([CAPTIONS],{type:'text/vtt'}));document.querySelectorAll('[data-time]').forEach(button=>button.addEventListener('click',()=>{video.currentTime=Number(button.dataset.time);video.play().catch(()=>{});}));</script></body></html>'''
(out / 'index.html').write_text(page.replace('BUTTONS', buttons).replace('TRANSCRIPT', transcript).replace('CAPTIONS', captions), encoding='utf-8')
print(out / 'index.html')
