import eventlet
eventlet.monkey_patch()  # 必须放在最开头，解决多线程补丁报错

import os
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-sync-key'
# 强制使用 eventlet 模式以确保实时同步稳定
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 全局状态，存储在内存中
state = {
    "boxes": [""]  # 初始一个框
}

# 这里的 HTML 保持了你之前的专业样式
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>私人云端同步板</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; color: #333; }
        .container { max-width: 900px; margin: 0 auto; }
        .toolbar { 
            display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; 
            background: white; padding: 15px; border-radius: 12px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); z-index: 100;
        }
        button { 
            padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; 
            font-weight: 600; transition: all 0.2s;
        }
        .btn-add { background: #28a745; color: white; }
        .btn-del { background: #dc3545; color: white; }
        .btn-clear { background: #343a40; color: white; }
        .box-wrapper { 
            background: white; padding: 18px; border-radius: 10px; 
            margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid #eee;
        }
        textarea {
            width: 100%; height: 160px; padding: 12px; border: 1px solid #dee2e6;
            border-radius: 6px; font-size: 16px; box-sizing: border-box; outline: none;
        }
        .status { font-size: 12px; text-align: center; color: #adb5bd; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="toolbar">
            <button class="btn-add" onclick="manage('add')">＋ 增加框</button>
            <button class="btn-del" onclick="manage('remove')">－ 减少框</button>
            <button class="btn-clear" onclick="manage('clear_all')">🗑️ 全员清屏</button>
        </div>
        <div id="editor-container"></div>
        <div class="status" id="status">正在检查云端同步状态...</div>
    </div>

    <script>
        const socket = io();
        const container = document.getElementById('editor-container');
        const status = document.getElementById('status');

        socket.on('sync_all', function(data) {
            container.innerHTML = '';
            data.boxes.forEach((content, index) => {
                const wrapper = document.createElement('div');
                wrapper.className = 'box-wrapper';
                wrapper.innerHTML = `
                    <div style="margin-bottom:10px; color:#666; font-weight:bold;">同步区 #${index + 1}</div>
                    <textarea id="textarea-${index}" oninput="sendUpdate(${index}, this.value)">${content}</textarea>
                `;
                container.appendChild(wrapper);
            });
        });

        socket.on('update_box', function(data) {
            const el = document.getElementById('textarea-' + data.index);
            if (el && el.value !== data.text) {
                const start = el.selectionStart;
                const end = el.selectionEnd;
                el.value = data.text;
                el.setSelectionRange(start, end);
            }
        });

        function sendUpdate(index, text) { socket.emit('text_change', {index: index, text: text}); }
        function manage(action) { socket.emit('manage_box', {action: action}); }

        socket.on('connect', () => { status.innerText = "🟢 云端同步已就绪"; status.style.color = "#28a745"; });
        socket.on('disconnect', () => { status.innerText = "🔴 同步连接中断"; status.style.color = "#dc3545"; });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on('connect')
def handle_connect():
    emit('sync_all', state)

@socketio.on('text_change')
def handle_text_change(data):
    idx = data['index']
    if idx < len(state["boxes"]):
        state["boxes"][idx] = data['text']
        emit('update_box', data, broadcast=True, include_self=False)

@socketio.on('manage_box')
def handle_management(data):
    action = data['action']
    if action == 'add':
        state["boxes"].append("")
    elif action == 'remove' and len(state["boxes"]) > 1:
        state["boxes"].pop()
    elif action == 'clear_all':
        state["boxes"] = ["" for _ in state["boxes"]]
    emit('sync_all', state, broadcast=True)

if __name__ == "__main__":
    # Render 会自动通过环境变量 PORT 告诉我们该用哪个端口
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
