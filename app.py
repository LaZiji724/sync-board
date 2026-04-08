import eventlet
eventlet.monkey_patch()

import os, threading
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laziji-whisper-pro-v11'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 后端数据存储
state = {
    "public_boxes": [""],
    "whispers": {}, # 存储格式 {"名字A|名字B": "内容"}
    "users": {},    # 存储格式 {sid: {"name": "名字"}}
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
        
        button { padding: 8px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear { background: #264653; color: white; }
        
        .card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #eee; }
        .whisper-card { border: 2px dashed #e76f51; background: #fffcfb; }
        .card-title { font-weight: bold; color: #555; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
        
        textarea { width: 100%; height: 160px; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-size: 16px; box-sizing: border-box; outline: none; background: #fafafa; line-height: 1.6; transition: border 0.2s; }
        textarea:focus { border-color: #2a9d8f; background: white; }
        
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 15px 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; overflow-x: auto; z-index: 1000; }
        .user-chip { background: #e9ecef; padding: 6px 14px; border-radius: 20px; font-size: 13px; white-space: nowrap; cursor: pointer; border: 1px solid transparent; }
        .user-chip:hover { border-color: #e76f51; color: #e76f51; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>🌶️ 辣子鸡同步框</h1></div>
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {action:'add'})">＋ 增加区</button>
            <button class="btn-clear" onclick="handleGlobalClear()">🗑️ 清除我可见的内容</button>
        </div>
        <div id="box-container"></div>
    </div>
    <div class="footer">
        <span style="font-size:12px; color:#999; white-space:nowrap;">在线可私聊：</span>
        <div id="user-list" style="display:flex; gap:8px;"></div>
    </div>

    <script>
        const socket = io();
        let myName = "";
        let isComposing = false; // 中文输入法锁定
        while(!myName || myName.trim() === "") { myName = prompt("请输入你的名字:"); }
        
        socket.on('connect', () => { socket.emit('user_join', { name: myName }); });

        // 仅在结构变化（增减框）时执行重绘
        socket.on('sync_structure', (data) => {
            const container = document.getElementById('box-container');
            const currentIds = Array.from(container.querySelectorAll('textarea')).map(t => t.id).sort().join(',');
            
            let newIdsArr = data.public_boxes.map((_, i) => `pub-${i}`);
            for (let key in data.whispers) {
                const names = key.split('|');
                if (names.includes(myName)) {
                    const other = names.find(n => n !== myName) || myName;
                    newIdsArr.push(`whi-${other}`);
                }
            }
            const newIds = newIdsArr.sort().join(',');

            if (currentIds !== newIds) {
                container.innerHTML = '';
                // 渲染公共区
                data.public_boxes.forEach((content, i) => createBox(container, `公共区 ${i+1}`, 'pub', i, content));
                // 渲染私聊区
                for (let key in data.whispers) {
                    const names = key.split('|');
                    if (names.includes(myName)) {
                        const other = names.find(n => n !== myName) || myName;
                        createBox(container, `🤐 ${names[0]} & ${names[1]}`, 'whi', other, data.whispers[key]);
                    }
                }
            }
        });

        function createBox(container, title, type, id, content) {
            const div = document.createElement('div');
            div.className = 'card' + (type === 'whi' ? ' whisper-card' : '');
            
            const clearCmd = type === 'pub' ? `socket.emit('manage_box', {action:'clear_single', index:${id}})` : `socket.emit('whisper_action', {target:'${id}', action:'clear'})`;
            const closeBtn = type === 'whi' ? `<button style="background:#666; color:white; font-size:10px; margin-left:5px;" onclick="socket.emit('whisper_action', {target:'${id}', action:'close'})">关闭</button>` : '';

            div.innerHTML = `
                <div class="card-title">
                    <span>${title}</span>
                    <div><button style="background:#ddd; font-size:10px;" onclick="${clearCmd}">清空</button>${closeBtn}</div>
                </div>
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

        function handleGlobalClear() {
            if(confirm('确定清空你能看到的所有公共区和私聊框吗？')) {
                socket.emit('manage_box', {action: 'clear_visible_all'});
            }
        }

        // 核心丝滑逻辑：仅更新内容，不重绘DOM
        socket.on('update_content', (data) => {
            const el = document.getElementById(`${data.type}-${data.id}`);
            if (el && document.activeElement !== el) {
                el.value = data.text;
            } else if (el && document.activeElement === el && !isComposing && el.value !== data.text) {
                const start = el.selectionStart, end = el.selectionEnd;
                el.value = data.text;
                el.setSelectionRange(start, end);
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
    if "global_cleanup" in state["cleanup_timers"]:
        state["cleanup_timers"]["global_cleanup"].cancel()
    sync_struct()

@socketio.on('disconnect')
def handle_disconnect():
    user = state["users"].get(request.sid)
    if not user: return
    name = user['name']
    del state["users"][request.sid]
    
    # 私聊延迟销毁
    def cleanup():
        active = [u['name'] for u in state["users"].values()]
        changed = False
        for k in list(state["whispers"].keys()):
            names = k.split('|')
            if name in names and not any(n in active for n in names if n != name):
                state["whispers"].pop(k, None); changed = True
        if changed: sync_struct()
    threading.Timer(30.0, cleanup).start()

    # 全员退出延迟清零
    if not state["users"]:
        t = threading.Timer(60.0, lambda: state.update({"public_boxes": [""], "whispers": {}}))
        state["cleanup_timers"]["global_cleanup"] = t
        t.start()
    sync_struct()

@socketio.on('text_change')
def handle_text(data):
    idx = int(data['index'])
    if idx < len(state["public_boxes"]):
        state["public_boxes"][idx] = data['text']
        emit('update_content', {'type': 'pub', 'id': idx, 'text': data['text']}, broadcast=True, include_self=False)

@socketio.on('whisper_send')
def handle_whisper(data):
    me = state["users"][request.sid]['name']
    target = data['target']
    key = "|".join(sorted([me, target]))
    state["whispers"][key] = data['text']
    # 精准通知私聊双方，不重绘DOM
    for sid, info in state["users"].items():
        if info['name'] == target:
            socketio.emit('update_content', {'type': 'whi', 'id': me, 'text': data['text']}, room=sid)
        elif info['name'] == me:
            socketio.emit('update_content', {'type': 'whi', 'id': target, 'text': data['text']}, room=sid)

@socketio.on('whisper_action')
def handle_whisper_action(data):
    me = state["users"][request.sid]['name']
    target = data['target']
    key = "|".join(sorted([me, target]))
    if data['action'] == 'open':
        state["whispers"].setdefault(key, "")
    elif data['action'] == 'clear':
        state["whispers"][key] = ""
        # 特殊处理：清空时为了让双方UI同步置空内容，直接触发内容更新指令
        socketio.emit('update_content', {'type': 'whi', 'id': me, 'text': ""}, broadcast=True) # 这里由于结构较多，简单触发全量同步内容
    elif data['action'] == 'close':
        state["whispers"].pop(key, None)
    sync_struct()

@socketio.on('manage_box')
def handle_manage(data):
    me = state["users"][request.sid]['name']
    if data['action'] == 'add':
        state["public_boxes"].append("")
    elif data['action'] == 'clear_visible_all':
        state["public_boxes"] = ["" for _ in state["public_boxes"]]
        for k in list(state["whispers"].keys()):
            if me in k.split('|'): state["whispers"][k] = ""
    elif data['action'] == 'clear_single':
        idx = int(data['index'])
        if idx < len(state["public_boxes"]): state["public_boxes"][idx] = ""
    sync_struct()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
