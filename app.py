import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laziji-v5-focus'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 存储内容、最后编辑者、以及当前正在编辑的人
state = {
    "boxes": [""],
    "last_editor": [""],
    "editing_now": {}, # 格式: {box_index: username}
    "users": {}        # sid: username
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>辣子鸡同步框</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; background: #f4f7f9; }
        .container { max-width: 800px; margin: 0 auto; padding-bottom: 80px; }
        .header h1 { color: #e63946; text-align: center; font-size: 24px; }
        .toolbar { display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; background: rgba(255,255,255,0.9); padding: 12px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); z-index: 100; }
        button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear { background: #264653; color: white; }
        .box-card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #e1e4e8; transition: 0.3s; }
        .editor-info { font-size: 11px; color: #999; margin-bottom: 5px; user-select: none; }
        .editor-name { color: #e63946; font-weight: bold; background: #fff1f2; padding: 1px 6px; border-radius: 4px; }
        .is-editing { color: #1877f2; background: #e7f3ff; } /* 正在编辑时的颜色 */
        textarea { width: 100%; height: 180px; border: 1px solid #eee; border-radius: 8px; padding: 12px; font-size: 16px; line-height: 1.6; box-sizing: border-box; outline: none; background: #fafafa; }
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 12px 20px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; }
        .user-chip { background: #e9ecef; padding: 4px 12px; border-radius: 20px; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>🌶️ 辣子鸡同步框</h1></div>
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {'action':'add'})">＋ 增加区</button>
            <button class="btn-clear" onclick="if(confirm('清空全部？')) socket.emit('manage_box', {'action':'clear_all'})">🗑️ 全清</button>
        </div>
        <div id="editor-container"></div>
    </div>
    <div class="footer">
        <span style="font-size:13px; color:#666;">在线：</span>
        <div id="user-list" style="display:flex; gap:8px;"></div>
    </div>
    <script>
        const socket = io();
        let myName = "";
        while(!myName || myName.trim() === "") { myName = prompt("请输入你的名字:"); }
        
        socket.on('connect', () => { socket.emit('user_join', { name: myName }); });

        socket.on('sync_all', (data) => {
            const container = document.getElementById('editor-container');
            container.innerHTML = '';
            data.boxes.forEach((content, index) => {
                const activeUser = data.editing_now[index];
                const lastUser = data.last_editor[index] || '无';
                
                const card = document.createElement('div');
                card.className = 'box-card';
                card.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span class="editor-info" id="info-${index}">
                            ${activeUser ? `正在编辑: <span class="editor-name is-editing">[${activeUser}]</span>` : `最后编辑: <span class="editor-name">[${lastUser}]</span>`}
                        </span>
                        <button style="background:#f4a261; color:white; font-size:11px; padding:3px 8px; border:none; border-radius:4px;" onclick="socket.emit('manage_box', {'action':'clear_single', 'index': ${index}})">清空</button>
                    </div>
                    <textarea id="box-${index}" 
                        onfocus="socket.emit('focus_box', {'index': ${index}, 'user': myName})" 
                        onblur="socket.emit('blur_box', {'index': ${index}})"
                        oninput="socket.emit('text_change', {'index': ${index}, 'text': this.value, 'user': myName})">${content}</textarea>`;
                container.appendChild(card);
            });
        });

        socket.on('update_box', (data) => {
            const el = document.getElementById('box-' + data.index);
            if(el && el.value !== data.text) {
                const s = el.selectionStart, e = el.selectionEnd;
                el.value = data.text;
                el.setSelectionRange(s, e);
            }
        });

        socket.on('update_status', (data) => {
            const info = document.getElementById('info-' + data.index);
            if(info) {
                if(data.active_user) {
                    info.innerHTML = `正在编辑: <span class="editor-name is-editing">[${data.active_user}]</span>`;
                } else {
                    info.innerHTML = `最后编辑: <span class="editor-name">[${data.last_user || '无'}]</span>`;
                }
            }
        });

        socket.on('user_list_update', (users) => {
            const list = document.getElementById('user-list');
            list.innerHTML = '';
            users.forEach(u => {
                const s = document.createElement('span'); s.className = 'user-chip'; s.innerText = u;
                list.appendChild(s);
            });
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@socketio.on('user_join')
def handle_join(data):
    state["users"][request.sid] = data.get('name', '匿名')
    socketio.emit('user_list_update', list(set(state["users"].values())))
    emit('sync_all', {"boxes": state["boxes"], "last_editor": state["last_editor"], "editing_now": state["editing_now"]})

@socketio.on('disconnect')
def handle_disconnect():
    # 如果断开连接的人正在编辑，先清除他的状态
    for idx, user in list(state["editing_now"].items()):
        if user == state["users"].get(request.sid):
            del state["editing_now"][idx]
            socketio.emit('update_status', {'index': idx, 'active_user': None, 'last_user': state["last_editor"][idx]})
    
    if request.sid in state["users"]: del state["users"][request.sid]
    socketio.emit('user_list_update', list(set(state["users"].values())))

@socketio.on('focus_box')
def handle_focus(data):
    idx = data['index']
    state["editing_now"][idx] = data['user']
    socketio.emit('update_status', {'index': idx, 'active_user': data['user']}, broadcast=True)

@socketio.on('blur_box')
def handle_blur(data):
    idx = data['index']
    if idx in state["editing_now"]:
        del state["editing_now"][idx]
    socketio.emit('update_status', {'index': idx, 'active_user': None, 'last_user': state["last_editor"][idx]}, broadcast=True)

@socketio.on('text_change')
def handle_text(data):
    idx = data['index']
    if idx < len(state["boxes"]):
        state["boxes"][idx] = data['text']
        state["last_editor"][idx] = data['user']
        emit('update_box', data, broadcast=True, include_self=False)

@socketio.on('manage_box')
def handle_manage(data):
    action = data['action']
    if action == 'add':
        state["boxes"].append(""); state["last_editor"].append("")
    elif action == 'clear_all':
        state["boxes"] = [""]; state["last_editor"] = [""]; state["editing_now"] = {}
    elif action == 'clear_single':
        idx = data.get('index')
        if idx is not None and idx < len(state["boxes"]):
            state["boxes"][idx] = ""; state["last_editor"][idx] = ""
    socketio.emit('sync_all', {"boxes": state["boxes"], "last_editor": state["last_editor"], "editing_now": state["editing_now"]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
