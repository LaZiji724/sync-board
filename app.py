import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laziji-ultimate-thread-v1'

# 核心：使用 threading 模式，它不依赖底层打补丁，兼容性最强
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

state = {
    "public_boxes": [""],
    "whispers": {}, 
    "users": {}
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌶️ 辣子鸡同步框🍗</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 20px; background: #f4f7f9; color: #333; }
        .container { max-width: 800px; margin: 0 auto; padding-bottom: 120px; }
        .toolbar { display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; background: rgba(255,255,255,0.9); backdrop-filter: blur(10px); padding: 12px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); z-index: 100; border: 1px solid rgba(255,255,255,0.3); }
        button { padding: 8px 16px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.2s; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear { background: #e63946; color: white; }
        .card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #eee; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
        .whisper-card { border: 2px dashed #e76f51; background: #fffcfb; }
        .card-title { font-weight: bold; color: #555; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
        textarea { width: 100%; height: 160px; border: 1px solid #ddd; border-radius: 10px; padding: 14px; font-size: 16px; box-sizing: border-box; outline: none; background: #fafafa; line-height: 1.6; }
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: rgba(255,255,255,0.95); backdrop-filter: blur(10px); padding: 15px 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; overflow-x: auto; z-index: 1000; }
        .user-chip { background: #e9ecef; padding: 6px 16px; border-radius: 20px; font-size: 13px; white-space: nowrap; cursor: pointer; border: 1px solid transparent; transition: 0.2s; }
        .user-chip:hover { border-color: #e76f51; color: #e76f51; background: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {action:'add'})">＋ 增加区</button>
            <button class="btn-clear" onclick="handleGlobalClear()">🗑️ 清除所有</button>
        </div>
        <div id="box-container"></div>
    </div>
    <div class="footer">
        <span style="font-size:12px; color:#999; white-space:nowrap;">👥 私聊：</span>
        <div id="user-list" style="display:flex; gap:8px;"></div>
    </div>

    <script>
        const socket = io();
        let myName = "";
        let isComposing = false;
        let lastInputTime = 0; 
        
        while(!myName || myName.trim() === "") { myName = prompt("请输入你的名字:"); }
        socket.on('connect', () => { socket.emit('user_join', { name: myName }); });

        socket.on('sync_structure', (data) => {
            const container = document.getElementById('box-container');
            container.innerHTML = '';
            data.public_boxes.forEach((content, i) => createBox(container, `公共区 ${i+1}`, 'pub', i, content));
            for (let key in data.whispers) {
                if (key.includes(myName)) {
                    const other = key.split('|').find(n => n !== myName) || myName;
                    createBox(container, `🤐 与 ${other} 的私聊`, 'whi', other, data.whispers[key]);
                }
            }
        });

        function createBox(container, title, type, id, content) {
            const div = document.createElement('div');
            div.className = 'card' + (type === 'whi' ? ' whisper-card' : '');
            const clearCmd = type === 'pub' ? `socket.emit('manage_box', {action:'clear_single', index:${id}})` : `socket.emit('whisper_action', {target:'${id}', action:'clear'})`;
            div.innerHTML = `<div class="card-title"><span>${title}</span><button style="background:#eee; color:#666;" onclick="${clearCmd}">清空</button></div>
                <textarea id="${type}-${id}" oncompositionstart="isComposing=true" oncompositionend="isComposing=false; handleInput('${type}','${id}',this.value)" oninput="handleInput('${type}','${id}',this.value)">${content}</textarea>`;
            container.appendChild(div);
        }

        function handleInput(type, id, val) {
            if (isComposing) return;
            lastInputTime = Date.now();
            if(type === 'pub') socket.emit('text_change', {index: id, text: val});
            else socket.emit('whisper_send', {target: id, text: val});
        }

        function handleGlobalClear() { if(confirm('确定清屏吗？')) socket.emit('manage_box', {action: 'clear_visible_all'}); }

        socket.on('update_content', (data) => {
            const el = document.getElementById(`${data.type}-${data.id}`);
            if (!el) return;
            if (data.text !== "" && document.activeElement === el && (isComposing || Date.now() - lastInputTime < 800)) return;
            if (el.value !== data.text) {
                const start = el.selectionStart, end = el.selectionEnd;
                el.value = data.text;
                if(document.activeElement === el && data.text !== "") el.setSelectionRange(start, end);
            }
        });

        socket.on('user_list_update', (users) => {
            const list = document.getElementById('user-list');
            list.innerHTML = '';
            for (let sid in users) {
                if (users[sid] === myName) continue;
                const span = document.createElement('span');
                span.className = 'user-chip';
                span.innerText = users[sid];
                span.onclick = () => socket.emit('whisper_action', {target: users[sid], action:'open'});
                list.appendChild(span);
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

def sync_struct():
    user_names = {sid: u['name'] for sid, u in state["users"].items()}
    socketio.emit('sync_structure', {"public_boxes": state["public_boxes"], "whispers": state["whispers"]})
    socketio.emit('user_list_update', user_names)

@socketio.on('user_join')
def handle_join(data):
    state["users"][request.sid] = {"name": data.get('name', '匿名')}
    sync_struct()

@socketio.on('text_change')
def handle_text(data):
    idx = int(data['index'])
    if idx < len(state["public_boxes"]):
        state["public_boxes"][idx] = data['text']
        emit('update_content', {'type': 'pub', 'id': idx, 'text': data['text']}, broadcast=True, include_self=False)

@socketio.on('whisper_send')
def handle_whisper(data):
    me = state["users"].get(request.sid, {}).get('name')
    if not me: return
    target = data['target']
    key = "|".join(sorted([me, target]))
    state["whispers"][key] = data['text']
    for sid, info in state["users"].items():
        if info['name'] in [me, target]:
            other = target if info['name'] == me else me
            socketio.emit('update_content', {'type': 'whi', 'id': other, 'text': data['text']}, room=sid)

@socketio.on('whisper_action')
def handle_whisper_action(data):
    me = state["users"][request.sid]['name']
    target = data['target']
    key = "|".join(sorted([me, target]))
    if data['action'] == 'open': state["whispers"].setdefault(key, "")
    elif data['action'] == 'clear':
        state["whispers"][key] = ""
        for sid, info in state["users"].items():
            if info['name'] in [me, target]:
                other = target if info['name'] == me else me
                socketio.emit('update_content', {'type': 'whi', 'id': other, 'text': ""}, room=sid)
    sync_struct()

@socketio.on('manage_box')
def handle_manage(data):
    if data['action'] == 'add': state["public_boxes"].append("")
    elif data['action'] == 'clear_visible_all':
        state["public_boxes"] = ["" for _ in state["public_boxes"]]
        socketio.emit('update_content', {'type': 'pub', 'id': 'all_clear', 'text': ""}) 
    elif data['action'] == 'clear_single':
        idx = int(data['index'])
        if idx < len(state["public_boxes"]):
            state["public_boxes"][idx] = ""
            socketio.emit('update_content', {'type': 'pub', 'id': idx, 'text': ""})
    sync_struct()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
