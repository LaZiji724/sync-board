import os
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
from pyngrok import ngrok

# ================= 配置区 =================
PORT = 8000
NGROK_TOKEN = "3BfLjOMWBMRsy7P7xflbpzPsr58_TyF9SysJ7fiqPWVPY4bp"
# ==========================================

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 全局状态
state = {
    "boxes": [""]  # 初始一个框
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>专业版同步复写板</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; color: #333; }
        .container { max-width: 900px; margin: 0 auto; }
        
        /* 工具栏 */
        .toolbar { 
            display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; 
            background: white; padding: 15px; border-radius: 12px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); z-index: 100;
            flex-wrap: wrap;
        }
        
        button { 
            padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; 
            font-weight: 600; transition: all 0.2s; font-size: 14px;
            display: flex; align-items: center; gap: 5px;
        }
        .btn-add { background: #28a745; color: white; }
        .btn-del { background: #dc3545; color: white; }
        .btn-clear-all { background: #343a40; color: white; }
        .btn-clear-single { background: #e7f1ff; color: #0d6efd; border: 1px solid #0d6efd; padding: 4px 10px; font-size: 12px; }
        
        button:hover { opacity: 0.8; transform: translateY(-1px); box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        button:active { transform: translateY(0); }

        /* 输入框卡片 */
        .box-wrapper { 
            background: white; padding: 18px; border-radius: 10px; 
            margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            border: 1px solid #eee;
        }
        .box-header { 
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px dashed #eee;
        }
        .box-title { font-weight: bold; color: #666; }
        
        textarea {
            width: 100%; height: 160px; padding: 12px; border: 1px solid #dee2e6;
            border-radius: 6px; font-size: 16px; box-sizing: border-box;
            resize: vertical; outline: none; line-height: 1.6; font-family: inherit;
        }
        textarea:focus { border-color: #0d6efd; box-shadow: 0 0 0 3px rgba(13,110,253,0.1); }

        .status { font-size: 12px; text-align: center; color: #adb5bd; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="toolbar">
            <button class="btn-add" onclick="manage('add')">＋ 增加同步框</button>
            <button class="btn-del" onclick="manage('remove')">－ 减少同步框</button>
            <button class="btn-clear-all" onclick="manage('clear_all')">🗑️ 全员清屏</button>
        </div>

        <div id="editor-container"></div>
        <div class="status" id="status">正在同步网络状态...</div>
    </div>

    <script>
        const socket = io();
        const container = document.getElementById('editor-container');
        const status = document.getElementById('status');

        // 接收全量更新
        socket.on('sync_all', function(data) {
            container.innerHTML = '';
            data.boxes.forEach((content, index) => {
                createBoxElement(index, content);
            });
        });

        // 接收单框更新
        socket.on('update_box', function(data) {
            const el = document.getElementById('textarea-' + data.index);
            if (el && el.value !== data.text) {
                const start = el.selectionStart;
                const end = el.selectionEnd;
                el.value = data.text;
                el.setSelectionRange(start, end);
            }
        });

        function createBoxElement(index, content) {
            const wrapper = document.createElement('div');
            wrapper.className = 'box-wrapper';
            wrapper.innerHTML = `
                <div class="box-header">
                    <span class="box-title">同步区 #${index + 1}</span>
                    <button class="btn-clear-single" onclick="clearSingle(${index})">清空此框</button>
                </div>
                <textarea id="textarea-${index}" oninput="sendUpdate(${index}, this.value)" placeholder="请输入内容...">${content}</textarea>
            `;
            container.appendChild(wrapper);
        }

        function sendUpdate(index, text) {
            socket.emit('text_change', {index: index, text: text});
        }

        function clearSingle(index) {
            socket.emit('manage_box', {action: 'clear_single', index: index});
        }

        function manage(action) {
            if(action === 'clear_all' && !confirm('确定要清空所有框吗？')) return;
            socket.emit('manage_box', {action: action});
        }

        socket.on('connect', () => { 
            status.innerText = "🟢 实时同步中"; 
            status.style.color = "#28a745"; 
        });
        socket.on('disconnect', () => { 
            status.innerText = "🔴 已断开连接"; 
            status.style.color = "#dc3545"; 
        });
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
    elif action == 'remove':
        if len(state["boxes"]) > 1:
            state["boxes"].pop()
    elif action == 'clear_all':
        state["boxes"] = ["" for _ in state["boxes"]]
    elif action == 'clear_single':
        idx = data.get('index')
        if idx is not None and idx < len(state["boxes"]):
            state["boxes"][idx] = ""
            # 单框清空也可以复用 update_box 事件通知所有人
            emit('update_box', {'index': idx, 'text': ""}, broadcast=True)
            return # 这种情况下不需要重绘整个列表，直接返回

    # 结构改变（增/减/全局清空）时，通知所有人重绘
    emit('sync_all', state, broadcast=True)

def run():
    ngrok.set_auth_token(NGROK_TOKEN)
    try:
        print("[*] 正在启动实时同步服务...")
        conf = ngrok.PyngrokConfig(region="ap")
        tunnel = ngrok.connect(PORT, pyngrok_config=conf)
        print(f"\n🌍 实时同步板地址: \033[1;32m{tunnel.public_url}\033[0m")
        print("[*] 功能：单框清空、全局清空、动态增减框已就绪。")
        
        socketio.run(app, host="0.0.0.0", port=PORT, log_output=False)
    except Exception as e:
        print(f"[-] 启动失败: {e}")

if __name__ == "__main__":
    run()