// electron/main.js
const { app, BrowserWindow,screen } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

let mainWindow;
let pythonProcess = null;

// ---------- 读取 Flask 端口 ----------
function getFlaskPort() {
    const configPath = path.join(__dirname, '..', 'config.py');
    try {
        const content = fs.readFileSync(configPath, 'utf-8');
        const match = content.match(/FLASK_PORT\s*=\s*(\d+)/);
        if (match) return parseInt(match[1], 10);
    } catch (e) {
        console.warn('读取 config.py 失败，将使用默认端口 5000');
    }
    return 5000;
}

const FLASK_PORT = getFlaskPort();
const SERVER_URL = `http://127.0.0.1:${FLASK_PORT}`;
const isDev = !app.isPackaged;

// 图标路径
const iconPath = isDev
    ? path.join(__dirname, '..', 'static', 'ryfit-scale-icon.ico')
    : path.join(process.resourcesPath, 'static', 'ryfit-scale-icon.ico');

// 后端启动方式
const BACKEND_CONFIG = isDev
    ? { cmd: 'python', args: ['app.py'], cwd: path.join(__dirname, '..') }
    : {
        cmd: path.join(process.resourcesPath, 'backend', 'app.exe'),
        args: [],
        cwd: path.dirname(path.join(process.resourcesPath, 'backend', 'app.exe'))
    };

// ---------- 服务就绪检测 ----------
function checkServerReady() {
    return new Promise((resolve) => {
        const retry = setInterval(() => {
            http.get(SERVER_URL, (res) => {
                if (res.statusCode === 200) { clearInterval(retry); resolve(); }
            }).on('error', () => { });
        }, 500);
    });
}

// ---------- 启动后端 ----------
function startPythonBackend() {
    const { cmd, args, cwd } = BACKEND_CONFIG;
    console.log(`启动后端: ${cmd} ${args.join(' ')} (工作目录: ${cwd})`);

    pythonProcess = spawn(cmd, args, {
        cwd,
        stdio: 'pipe',
        windowsHide: true
    });

    pythonProcess.stdout.on('data', (data) => console.log(`[PY] ${data.toString().trimEnd()}`));
    pythonProcess.stderr.on('data', (data) => console.error(`[PY-ERR] ${data.toString().trimEnd()}`));
    pythonProcess.on('error', (err) => {
        console.error('启动后端失败:', err);
        app.quit();
    });
    pythonProcess.on('exit', (code) => {
        console.log('后端进程退出，代码:', code);
        pythonProcess = null;
    });

    return checkServerReady();
}

// ---------- 杀死后端进程 ----------
function killPythonProcess() {
    if (pythonProcess && !pythonProcess.killed) {
        console.log('正在关闭后端服务...');
        pythonProcess.kill();
        pythonProcess = null;
    }
}

// ---------- 创建窗口 ----------
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1100,
        height: 850,
        title: 'RyFit 智能体质分析仪',
        icon: iconPath,
        autoHideMenuBar: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                'Content-Security-Policy': [
                    `default-src 'self' http://127.0.0.1:${FLASK_PORT}; ` +
                    `script-src 'self' 'unsafe-inline' http://127.0.0.1:${FLASK_PORT}; ` +
                    `connect-src ws://127.0.0.1:${FLASK_PORT} http://127.0.0.1:${FLASK_PORT}; ` +
                    "style-src 'self' 'unsafe-inline';"
                ]
            }
        });
    });

    mainWindow.loadURL(SERVER_URL);
    mainWindow.on('closed', () => { mainWindow = null; });
}

// ---------- 应用生命周期 ----------
app.commandLine.appendSwitch('disable-http-cache');
if (process.platform === 'win32') {
    app.setAppUserModelId('com.ryfit.scale');
}

app.whenReady().then(async () => {
    console.log('正在启动后端服务...');
    await startPythonBackend();
    console.log('后端已就绪，打开窗口');
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

// 正常关闭时确保杀死后端
app.on('window-all-closed', () => {
    killPythonProcess();
    if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
    killPythonProcess();
});

// 捕获主进程退出（包括意外崩溃）时杀死子进程
// 注意：exit 事件只能执行同步操作，无法执行异步 I/O
process.on('exit', () => {
    killPythonProcess();
});