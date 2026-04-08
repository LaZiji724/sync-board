import eventlet
eventlet.monkey_patch()

import os, threading
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laziji-smooth-v8'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 数据存储
state = {
    "public_boxes": [""],
    "whispers": {},
    "users": {},
    "cleanup_timers": {}
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>辣子鸡同步框</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 20px; background: #f4f7f9; }
        .container { max-width: 800px; margin: 0 auto; padding-bottom: 120px; }
        .header h1 { color: #e63946; text-align: center; font-size: 22px; margin-bottom: 20px; }
        .toolbar { display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; background: rgba(255,255,255,0.9); backdrop-filter: blur(8px); padding: 12px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); z-index: 100; }
        button { padding: 8px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear { background: #264653; color: white; }
        .card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #eee; }
        .whisper-card { border: 2px dashed #e76f51; background: #fffcfb; }
        .card-title { font-weight: bold; color: #555; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
        textarea { width: 100%; height: 160px; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-size: 16px; box-sizing: border-box; outline: none; background: #fafafa; line-height: 1.6; -webkit-appearance: none; }
        textarea:focus { border-color: #2a9d8f; background: #fff; }
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 15px 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; overflow-x: auto; z-index: 1000; }
        .user-chip { background: #e9ecef; padding: 6px 14px; border-radius: 20px; font-size: 13px; white-space: nowrap; cursor: pointer; }
        .user-chip:hover { background: #dee2e6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>🌶️ 辣子鸡同步框</h1></div>
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {action:'add'})">＋ 增加区</button>
            <button class="btn-clear" onclick="if(confirm('清空公共区？')) socket.emit('manage_box', {action:'clear_all'})">🗑️ 全清</button>
        </div>
        <div id="box-container"></div>
    </div>
    <div class="footer">
        <span style="font-size:12px; color:#999;">私聊:</span>
        <div id="user-list" style="display:flex; gap:8px;"></div>
    </div>

    <script>
        const socket = io();
        let myName = "";
        while(!myName || myName.trim() === "") { myName = prompt("请输入你的名字:"); }
        
        socket.on('connect', () => { socket.emit('user_join', { name: myName }); });

        // 记录当前是否有正在进行的中文输入（IME）
        let isComposing = false;

        socket.on('sync_structure', (data) => {
            const container = document.getElementById('box-container');
            // 只在数量改变时重构DOM
            const currentBoxCount = container.querySelectorAll('.card').length;
            const newBoxCount = data.public_boxes.length + Object.keys(data.whispers).filter(k => k.split('|').includes(myName)).length;
            
            if (currentBoxCount !== newBoxCount) {
                container.innerHTML = '';
                data.public_boxes.forEach((content, i) => createBox(container, `公共区 ${i+1}`, 'pub', i, content));
                for (let key in data.whispers) {
                    const names = key.split('|');
                    if (!names.includes(myName)) continue;
                    const other = names.find(n => n !== myName) || myName;
                    createBox(container, `🤐 ${names[0]} & ${names[1]}`, 'whi', other, data.whispers[key]);
                }
            }
        });

        function createBox(container, title, type, id, content) {
            const div = document.createElement('div');
            div.className = 'card' + (type === 'whi' ? ' whisper-card' : '');
            const action = type === 'pub' ? `socket.emit('manage_box', {action:'clear_single', index:${id}})` : `socket.emit('whisper_action', {target:'${id}', action:'close'})`;
            
            div.innerHTML = `
                <div class="card-title"><span>${title}</span><button style="background:#ddd;" onclick="${action}">清空/关闭</button></div>
                <textarea id="${type}-${id}" 
                    oncompositionstart="isComposing=true"
                    oncompositionend="isComposing=false; sendData('${type}', '${id}', this.value)"
                    oninput="if(!isComposing) sendData('${type}', '${id}', this.value)">${content}</textarea>`;
            container.appendChild(div);
        }

        function sendData(type, id, val) {
            if(type === 'pub') socket.emit('text_change', {index: id, text: val});
            else socket.emit('whisper_send', {target: id, text: val});
        }

        socket.on('update_content', (data) => {
            const el = document.getElementById(`${data.type}-${data.id}`);
            // 丝滑核心：如果是我在输入，或者我正处于焦点且在打中文，严禁服务器覆盖我的文字
            if (el && document.activeElement !== el) {
                el.value = data.text;
            } else if (el && document.activeElement === el && !isComposing) {
                // 如果是别人在改，且我没在打字，才同步
                const start = el.selectionStart, end = el.selectionEnd;
                if(el.value !== data.text) {
                    el.value = data.text;
                    el.setSelectionRange(start, end);
                }
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
    socketio.emit('sync_structure', {
        "public_boxes": state["public_boxes"],
        "whispers": state["whispers"]
    })
    socketio.emit('user_list_update', user_names)

@socketio.on('user_join')
def handle_join(data):
    state["users"][request.sid] = {"name": data.get('name', '匿名')}
    if "global_cleanup" in state["cleanup_timers"]: state["cleanup_timers"]["global_cleanup"].cancel()
    sync_struct()

@socketio.on('disconnect')
def handle_disconnect():
    user = state["users"].get(request.sid)
    if not user: return
    name = user['name']
    del state["users"][request.sid]
    
    def cleanup():
        active = [u['name'] for u in state["users"].values()]
        changed = False
        for k in list(state["whispers"].keys()):
            if name in k.split('|') and not any(n in active for n in k.split('|') if n != name):
                state["whispers"].pop(k, None); changed = True
        if changed: sync_struct()
    threading.Timer(30.0, cleanup).start()

    if not state["users"]:
        t = threading.Timer(60.0, lambda: state.update({"public_boxes": [""], "whispers": {}}))
        state["cleanup_timers"]["global_cleanup"] = t
        t.start()
    sync_struct()

@socketio.on('text_change')
def handle_text(data):
    idx = int(data['index'])
    state["public_boxes"][idx] = data['text']
    emit('update_content', {'type': 'pub', 'id': idx, 'text': data['text']}, broadcast=True, include_self=False)

@socketio.on('whisper_send')
def handle_whisper(data):
    me = state["users"][request.sid]['name']
    target = data['target']
    key = "|".join(sorted([me, target]))
    state["whispers"][key] = data['text']
    # 找到目标用户的sid并发送
    for sid, info in state["users"].items():
        if info['name'] == target or info['name'] == me:
            socketio.emit('update_content', {'type': 'whi', 'id': me if info['name']==target else target, 'text': data['text']}, room=sid)

@socketio.on('whisper_action')
def handle_whisper_action(data):
    me = state["users"][request.sid]['name']
    key = "|".join(sorted([me, data['target']]))
    if data['action'] == 'open': state["whispers"].setdefault(key, "")
    elif data['action'] == 'close': state["whispers"].pop(key, None)
    sync_struct()

@socketio.on('manage_box')
def handle_manage(data):
    if data['action'] == 'add': state["public_boxes"].append("")
    elif data['action'] == 'clear_all': state["public_boxes"] = [""]
    elif data['action'] == 'clear_single': state["public_boxes"][data['index']] = ""
    sync_struct()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
