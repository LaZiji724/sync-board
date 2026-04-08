import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laziji-sync-v3'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 数据存储
state = {
    "boxes": [""],      # 内容
    "last_editor": [""], # 记录每个框最后是谁在写
    "users": {}         # sid: username
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>辣子鸡同步框</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 20px; background: #f4f7f9; color: #333; }
        .container { max-width: 850px; margin: 0 auto; padding-bottom: 80px; }
        
        .header { text-align: center; margin-bottom: 20px; }
        .header h1 { color: #e63946; margin: 0; font-size: 24px; letter-spacing: 1px; }

        .toolbar { 
            display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; 
            background: rgba(255,255,255,0.9); backdrop-filter: blur(10px);
            padding: 12px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); z-index: 100;
        }
        
        button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; transition: 0.2s; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear-all { background: #264653; color: white; }
        .btn-clear-box { background: #f4a261; color: white; padding: 4px 10px; font-size: 11px; }

        .box-card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #e1e4e8; position: relative; }
        .box-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        
        /* 核心：动态名字标签，不可选中，不可删除 */
        .editor-info { 
            font-size: 11px; color: #999; margin-bottom: 4px; display: block;
            pointer-events: none; user-select: none;
        }
        .editor-name { color: #e63946; font-weight: bold; background: #fff1f2; padding: 1px 6px; border-radius: 4px; }

        textarea { 
            width: 100%; height: 180px; border: 1px solid #eee; border-radius: 8px; 
            padding: 12px; font-size: 16px; /* 正常字号 */
            line-height: 1.6; box-sizing: border-box; resize: vertical; outline: none;
            background: #fafafa; transition: 0.3s;
        }
        textarea:focus { border-color: #2a9d8f; background: #fff; box-shadow: 0 0 0 3px rgba(42,157,143,0.1); }

        .footer { 
            position: fixed; bottom: 0; left: 0; right: 0; background: rgba(255,255,255,0.95); 
            padding: 12px 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; z-index: 1000;
        }
        .user-chip { background: #e9ecef; color: #495057; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 500; }
        .online-dot { width: 8px; height: 8px; background: #2a9d8f; border-radius: 50%; display: inline-block; animation: pulse 2s infinite; }
        
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>🌶️ 辣子鸡同步框</h1></div>
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {action:'add'})">＋ 增加区</button>
            <button class="btn-clear-all" onclick="handleClearAll()">🗑️ 全清</button>
        </div>
        <div id="editor-container"></div>
    </div>

    <div class="footer">
        <div class="online-dot"></div>
        <span style="font-size:13px; color:#666;">在线：</span>
        <div id="user-list" style="display:flex; gap:8px; flex-wrap:wrap;"></div>
    </div>

    <script>
        const socket = io();
        let myName = "";

        while(!myName || myName.trim() === "") {
            myName = prompt("🌶️ 欢迎！请输入你的名字:");
        }

        socket.on('connect', () => {
            socket.emit('user_join', { name: myName });
        });

        socket.on('sync_all', function(data) {
            const container = document.getElementById('editor-container');
            container.innerHTML = '';
            data.boxes.forEach((content, index) => {
                const lastUser = data.last_editor[index] || "暂无";
                const card = document.createElement('div');
                card.className = 'box-card';
                card.innerHTML = `
                    <div class="box-header">
                        <span class="editor-info">最后编辑: <span class="editor-name">[${lastUser}]</span></span>
                        <button class="btn-clear-box" onclick="handleClearBox(${index})">清空</button>
                    </div>
                    <textarea id="box-${index}" oninput="handleInput(${index}, this.value)">${content}</textarea>
                `;
                container.appendChild(card);
            });
        });

        socket.on('user_list_update', function(users) {
            const listDiv = document.getElementById('user-list');
            listDiv.innerHTML = '';
            users.forEach(u => {
                const span = document.createElement('span');
                span.className = 'user-chip';
                span.innerText = u;
                listDiv.appendChild(span);
            });
        });

        socket.on('update_box', function(data) {
            const el = document.getElementById('box-' + data.index);
            const info = el.parentElement.querySelector('.editor-name');
            if(el && el.value !== data.text) {
                const start = el.selectionStart;
                const end = el.selectionEnd;
                el.value = data.text;
                el.setSelectionRange(start, end);
            }
            if(info) info.innerText = `[${data.user}]`;
        });

        function handleInput(index, text) {
            socket.emit('text_change', { index: index, text: text, user: myName });
        }

        function handleClearAll() {
            if(confirm('清空所有？')) socket.emit('manage_box', {action:'clear_all'});
        }

        function handleClearBox(index) {
            if(confirm('清空此框？')) socket.emit('manage_box', {action:'clear_single', index: index});
        }
    </script>
</body>
</html>
# 接上面的 app.py 后端部分

@socketio.on('user_join')
def handle_join(data):
    state["users"][request.sid] = data.get('name', '匿名')
    send_user_list()
    emit('sync_all', {
        "boxes": state["boxes"], 
        "last_editor": state["last_editor"]
    })

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in state["users"]:
        del state["users"][request.sid]
    send_user_list()

def send_user_list():
    names = list(set(state["users"].values()))
    socketio.emit('user_list_update', names)

@socketio.on('text_change')
def handle_text_change(data):
    idx = data['index']
    if idx < len(state["boxes"]):
        state["boxes"][idx] = data['text']
        state["last_editor"][idx] = data['user']
        # 实时广播内容和最后编辑者名字
        emit('update_box', {
            'index': idx, 
            'text': data['text'], 
            'user': data['user']
        }, broadcast=True, include_self=False)

@socketio.on('manage_box')
def handle_management(data):
    action = data['action']
    if action == 'add':
        state["boxes"].append("")
        state["last_editor"].append("")
    elif action == 'clear_all':
        state["boxes"] = ["" for _ in state["boxes"]]
        state["last_editor"] = ["" for _ in state["last_editor"]]
    elif action == 'clear_single':
        idx = data.get('index')
        if idx is not None and idx < len(state["boxes"]):
            state["boxes"][idx] = ""
            state["last_editor"][idx] = ""
    emit('sync_all', {
        "boxes": state["boxes"], 
        "last_editor": state["last_editor"]
    }, broadcast=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
