import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minimal-sync-v1'

# 使用原生线程模式，内存占用最低，避开 Python 3.14 异步死锁
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 仅保留公共同步框数据
state = {"public_boxes": [""]}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌶️ 辣子鸡同步框</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; background: #f4f7f9; color: #333; }
        .container { max-width: 800px; margin: 0 auto; padding-bottom: 50px; }
        .toolbar { display: flex; gap: 10px; margin-bottom: 20px; position: sticky; top: 10px; background: rgba(255,255,255,0.9); backdrop-filter: blur(10px); padding: 12px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); z-index: 100; border: 1px solid rgba(255,255,255,0.3); }
        button { padding: 8px 16px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.2s; }
        .btn-add { background: #2a9d8f; color: white; }
        .btn-clear { background: #e63946; color: white; }
        .card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #eee; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
        .card-title { font-weight: bold; color: #555; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
        textarea { width: 100%; height: 200px; border: 1px solid #ddd; border-radius: 10px; padding: 14px; font-size: 16px; box-sizing: border-box; outline: none; background: #fafafa; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="toolbar">
            <button class="btn-add" onclick="socket.emit('manage_box', {action:'add'})">＋ 增加同步框</button>
            <button class="btn-clear" onclick="if(confirm('确定清空所有框吗？')) socket.emit('manage_box', {action: 'clear_all'})">🗑️ 全部清空</button>
        </div>
        <div id="box-container"></div>
    </div>

    <script>
        const socket = io();
        let isComposing = false;
        let lockUntil = 0; 
        
        socket.on('sync_structure', (data) => {
            const container = document.getElementById('box-container');
            container.innerHTML = '';
            data.public_boxes.forEach((content, i) => {
                const div = document.createElement('div');
                div.className = 'card';
                div.innerHTML = `
                    <div class="card-title">
                        <span>同步框 ${i+1}</span>
                        <button style="background:#eee; color:#666;" onclick="socket.emit('manage_box', {action:'clear_single', index:${i}})">清空</button>
                    </div>
                    <textarea id="box-${i}" 
                        oncompositionstart="isComposing=true" 
                        oncompositionend="isComposing=false; lockUntil=Date.now()+500; handleInput(${i},this.value)" 
                        oninput="handleInput(${i},this.value)">${content}</textarea>`;
                container.appendChild(div);
            });
        });

        function handleInput(idx, val) {
            if (isComposing) return;
            socket.emit('text_change', {index: idx, text: val});
        }

        socket.on('update_content', (data) => {
            const el = document.getElementById(`box-${data.id}`);
            if (!el) return;
            // 如果用户正在输入或刚完成拼音输入，拒绝服务器旧数据覆盖本地
            if (document.activeElement === el && (isComposing || Date.now() < lockUntil)) return;
            
            if (el.value !== data.text) {
                const start = el.selectionStart, end = el.selectionEnd;
                el.value = data.text;
                if(document.activeElement === el) el.setSelectionRange(start, end);
            }
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
    emit('sync_structure', {"public_boxes": state["public_boxes"]})

@socketio.on('text_change')
def handle_text(data):
    idx = int(data['index'])
    if idx < len(state["public_boxes"]):
        state["public_boxes"][idx] = data['text']
        # 广播给除自己以外的所有人
        emit('update_content', {'id': idx, 'text': data['text']}, broadcast=True, include_self=False)

@socketio.on('manage_box')
def handle_manage(data):
    if data['action'] == 'add':
        state["public_boxes"].append("")
    elif data['action'] == 'clear_all':
        state["public_boxes"] = ["" for _ in state["public_boxes"]]
    elif data['action'] == 'clear_single':
        idx = int(data['index'])
        if idx < len(state["public_boxes"]):
            state["public_boxes"][idx] = ""
    # 更新所有人的结构
    emit('sync_structure', {"public_boxes": state["public_boxes"]}, broadcast=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
