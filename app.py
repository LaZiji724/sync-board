import eventlet
eventlet.monkey_patch()

import os, threading, time
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laziji-whisper-v6'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 核心数据结构
state = {
    "public_boxes": [""], # 公共区内容
    "whispers": {},       # 格式: {frozenset({a, b}): {"content": "", "history": []}}
    "users": {},          # sid: {"name": name}
    "cleanup_timers": {}  # 存储延迟任务
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>辣子鸡同步框</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: system-ui, sans-serif; margin: 0; padding: 20px; background: #f4f7f9; }
        .container { max-width: 800px; margin: 0 auto; padding-bottom: 100px; }
        .header h1 { color: #e63946; text-align: center; font-size: 24px; }
        .toolbar { display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; background: white; padding: 12px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); z-index: 100; }
        
        button { padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear { background: #264653; color: white; }
        .btn-whisper { background: #e76f51; color: white; margin-top: 5px; }
        .btn-close { background: #6c757d; color: white; }

        .card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #eee; }
        .card-title { font-weight: bold; color: #555; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        
        /* 悄悄话框特殊颜色 */
        .whisper-card { border: 2px dashed #e76f51; background: #fffcfb; }
        
        textarea { width: 100%; height: 120px; border: 1px solid #ddd; border-radius: 8px; padding: 10px; font-size: 15px; box-sizing: border-box; outline: none; background: #fafafa; }
        
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 15px 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; overflow-x: auto; }
        .user-chip { background: #e9ecef; padding: 4px 10px; border-radius: 15px; font-size: 12px; white-space: nowrap; cursor: pointer; border: 1px solid transparent; }
        .user-chip:hover { border-color: #e76f51; color: #e76f51; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>🌶️ 辣子鸡同步框</h1></div>
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {'action':'add'})">＋ 增加公共区</button>
            <button class="btn-clear" onclick="if(confirm('全清公共区？')) socket.emit('manage_box', {'action':'clear_all'})">🗑️ 全清公共区</button>
        </div>
        
        <div id="public-container"></div>
        <div id="whisper-container"></div>
    </div>

    <div class="footer">
        <span style="font-size:12px; color:#999; min-width:60px;">点击发悄悄话:</span>
        <div id="user-list" style="display:flex; gap:8px;"></div>
    </div>

    <script>
        const socket = io();
        let myName = "";
        while(!myName || myName.trim() === "") { myName = prompt("请输入你的名字:"); }
        
        socket.on('connect', () => { socket.emit('user_join', { name: myName }); });

        socket.on('sync_all', (data) => {
            renderPublic(data.public_boxes);
            renderWhispers(data.whispers);
            updateUserList(data.online_users);
        });

        function renderPublic(boxes) {
            const container = document.getElementById('public-container');
            container.innerHTML = '';
            boxes.forEach((content, i) => {
                const div = document.createElement('div');
                div.className = 'card';
                div.innerHTML = `
                    <div class="card-title">公共区 ${i+1} 
                        <button style="font-size:10px; background:#ddd;" onclick="socket.emit('manage_box', {action:'clear_single', index:${i}})">清空</button>
                    </div>
                    <textarea oninput="socket.emit('text_change', {index:${i}, text:this.value})">${content}</textarea>`;
                container.appendChild(div);
            });
        }

        function renderWhispers(whispers) {
            const container = document.getElementById('whisper-container');
            container.innerHTML = '';
            for (let pairKey in whispers) {
                const names = pairKey.split('|');
                if (!names.includes(myName)) continue;
                const other = names.find(n => n !== myName) || myName;
                
                const div = document.createElement('div');
                div.className = 'card whisper-card';
                div.innerHTML = `
                    <div class="card-title">🤐 ${names[0]} 和 ${names[1]} 的悄悄话
                        <div>
                            <button class="btn-clear" style="font-size:10px; padding:2px 5px;" onclick="socket.emit('whisper_action', {target:'${other}', action:'clear'})">清屏</button>
                            <button class="btn-close" style="font-size:10px; padding:2px 5px;" onclick="socket.emit('whisper_action', {target:'${other}', action:'close'})">关闭</button>
                        </div>
                    </div>
                    <textarea oninput="socket.emit('whisper_send', {target:'${other}', text:this.value})">${whispers[pairKey]}</textarea>`;
                container.appendChild(div);
            }
        }

        function updateUserList(users) {
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
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

def get_pair_key(n1, n2):
    return "|".join(sorted([n1, n2]))

def broadcast_all():
    user_names = {sid: u['name'] for sid, u in state["users"].items()}
    socketio.emit('sync_all', {
        "public_boxes": state["public_boxes"],
        "whispers": state["whispers"],
        "online_users": user_names
    })

@socketio.on('user_join')
def handle_join(data):
    name = data.get('name', '匿名')
    state["users"][request.sid] = {"name": name}
    # 取消可能的清屏定时器
    if "global_cleanup" in state["cleanup_timers"]:
        state["cleanup_timers"]["global_cleanup"].cancel()
    broadcast_all()

@socketio.on('disconnect')
def handle_disconnect():
    user = state["users"].get(request.sid)
    if not user: return
    name = user['name']
    del state["users"][request.sid]
    
    # 30秒后删除该用户的私聊框
    def cleanup_whisper():
        active_names = [u['name'] for u in state["users"].values()]
        to_delete = []
        for key in state["whispers"]:
            names = key.split('|')
            if name in names:
                if not any(n in active_names for n in names if n != name):
                    to_delete.append(key)
        for k in to_delete: state["whispers"].pop(k, None)
        broadcast_all()

    threading.Timer(30.0, cleanup_whisper).start()

    # 如果没人了，1分钟后全清
    if not state["users"]:
        t = threading.Timer(60.0, lambda: state.update({"public_boxes": [""], "whispers": {}}))
        state["cleanup_timers"]["global_cleanup"] = t
        t.start()
    
    broadcast_all()

@socketio.on('text_change')
def handle_text(data):
    idx = data['index']
    if idx < len(state["public_boxes"]):
        state["public_boxes"][idx] = data['text']
        broadcast_all()

@socketio.on('whisper_send')
def handle_whisper(data):
    me = state["users"][request.sid]['name']
    key = get_pair_key(me, data['target'])
    state["whispers"][key] = data['text']
    broadcast_all()

@socketio.on('whisper_action')
def handle_whisper_action(data):
    me = state["users"][request.sid]['name']
    key = get_pair_key(me, data['target'])
    if data['action'] == 'open':
        if key not in state["whispers"]: state["whispers"][key] = ""
    elif data['action'] == 'clear':
        state["whispers"][key] = ""
    elif data['action'] == 'close':
        state["whispers"].pop(key, None)
    broadcast_all()

@socketio.on('manage_box')
def handle_manage(data):
    action = data['action']
    if action == 'add': state["public_boxes"].append("")
    elif action == 'clear_all': state["public_boxes"] = [""]
    elif action == 'clear_single': state["public_boxes"][data['index']] = ""
    broadcast_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
