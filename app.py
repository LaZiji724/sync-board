import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sync-pro-2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 存储各框的内容
state = {"boxes": [""]}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>实名多端同步板</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; }
        .toolbar { 
            display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; 
            background: white; padding: 12px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        button { padding: 8px 15px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .btn-add { background: #007bff; color: white; }
        .btn-clear { background: #6c757d; color: white; }
        .box-card { background: white; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #ddd; }
        textarea { 
            width: 100%; height: 200px; border: 1px solid #ccc; border-radius: 5px; 
            padding: 10px; font-size: 15px; line-height: 1.5; box-sizing: border-box; resize: vertical;
        }
        .user-tag { color: #007bff; font-size: 12px; margin-bottom: 5px; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {action:'add'})">＋ 增加同步区</button>
            <button class="btn-clear" onclick="confirm('确定清空所有内容吗？') && socket.emit('manage_box', {action:'clear_all'})">🗑️ 全员清屏</button>
        </div>
        <div id="editor-container"></div>
    </div>

    <script>
        const socket = io();
        let userName = "";

        // 进入页面强制要求输入名字
        while(!userName || userName.trim() === "") {
            userName = prompt("请输入你的名字 (用于发言标记):");
        }

        socket.on('sync_all', function(data) {
            const container = document.getElementById('editor-container');
            container.innerHTML = '';
            data.boxes.forEach((content, index) => {
                const card = document.createElement('div');
                card.className = 'box-card';
                card.innerHTML = `
                    <span class="user-tag">正在以 [${userName}] 的身份输入...</span>
                    <textarea id="box-${index}" onkeydown="handleKey(event, ${index})" placeholder="输入内容点击发送...">${content}</textarea>
                    <div style="text-align:right; margin-top:5px;">
                        <small style="color:#999">按回车(Enter)发送新消息</small>
                    </div>
                `;
                container.appendChild(card);
            });
        });

        // 接收新消息追加
        socket.on('append_text', function(data) {
            const el = document.getElementById('box-' + data.index);
            if (el) {
                const prefix = `\\n[${data.user}]: `;
                // 如果是空的，就不加换行符
                const finalMsg = el.value === "" ? `[${data.user}]: ${data.text}` : `${el.value}\\n[${data.user}]: ${data.text}`;
                el.value = finalMsg;
                el.scrollTop = el.scrollHeight; // 滚动到底部
            }
        });

        function handleKey(e, index) {
            // 当按下回车键时发送，避免多人冲突
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const text = e.target.value.split('\\n').pop(); // 简易逻辑：只拿最后一行尝试
                // 这里我们直接弹窗输入模式不太友好，改为整段提交模式
                // 但为了满足你的“不可删除前缀”和“防冲突”，我们采取“回车即发送”的模式
                const inputVal = e.target.value;
                // 我们把当前输入框最后一行的内容提取出来（去掉可能已有的前缀）
                const lines = inputVal.split('\\n');
                let currentInput = lines[lines.length - 1];
                
                if (currentInput.trim() !== "") {
                    socket.emit('send_msg', {
                        index: index,
                        user: userName,
                        text: currentInput
                    });
                    // 发送后清空当前输入行（模拟聊天室感）或保持。这里采取直接广播模式。
                }
            }
        }
        
        // 核心：实时同步逻辑改为“追加消息”
        socket.on('update_box', function(data) {
            const el = document.getElementById('box-' + data.index);
            if(el) { el.value = data.full_text; }
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

@socketio.on('send_msg')
def handle_message(data):
    idx = data['index']
    user = data['user']
    content = data['text']
    
    if idx < len(state["boxes"]):
        prefix = f"[{user}]: "
        # 构造新的一行
        new_line = f"{prefix}{content}"
        
        if state["boxes"][idx] == "":
            state["boxes"][idx] = new_line
        else:
            state["boxes"][idx] += f"\\n{new_line}"
            
        # 广播给所有人完整内容（包含你刚发的那行）
        emit('update_box', {'index': idx, 'full_text': state["boxes"][idx]}, broadcast=True)

@socketio.on('manage_box')
def handle_management(data):
    action = data['action']
    if action == 'add':
        state["boxes"].append("")
    elif action == 'clear_all':
        state["boxes"] = ["" for _ in state["boxes"]]
    emit('sync_all', state, broadcast=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
