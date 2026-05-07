const { app, BrowserWindow, session } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

let mainWindow;
let pythonProcess;

const SERVER_URL = 'http://127.0.0.1:5000';

// 自动判断开发/生产环境
const isDev = !app.isPackaged;

// 生产模式：使用打包好的 exe（extraResources 将其复制到 resources/backend/app.exe）
const BACKEND_EXE = isDev
    ? path.join(__dirname, '..', 'dist', 'app.exe')
    : path.join(process.resourcesPath, 'backend', 'app.exe');

function checkServerReady() {
    return new Promise((resolve) => {
        const retry = setInterval(() => {
            http.get(SERVER_URL, (res) => {
                if (res.statusCode === 200) {
                    clearInterval(retry);
                    resolve();
                }
            }).on('error', () => {});
        }, 500);
    });
}

function startPythonBackend() {
    pythonProcess = spawn(BACKEND_EXE, [], {
        cwd: path.dirname(BACKEND_EXE),
        stdio: 'pipe',
        windowsHide: true
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[PY] ${data.toString().trimEnd()}`);
    });
    pythonProcess.stderr.on('data', (data) => {
        console.error(`[PY-ERR] ${data.toString().trimEnd()}`);
    });
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

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1100,
        height: 850,
        title: 'RyFit 智能体质分析仪',
        autoHideMenuBar: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    // 设置内容安全策略，允许加载本地资源和 WebSocket
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                'Content-Security-Policy': [
                    "default-src 'self' http://127.0.0.1:5000; " +
                    "script-src 'self' 'unsafe-inline' http://127.0.0.1:5000; " +
                    "connect-src ws://127.0.0.1:5000 http://127.0.0.1:5000; " +
                    "style-src 'self' 'unsafe-inline';"
                ]
            }
        });
    });

    mainWindow.loadURL(SERVER_URL);

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// 禁用 HTTP 缓存
app.commandLine.appendSwitch('disable-http-cache');

app.whenReady().then(async () => {
    console.log('正在启动后端服务...');
    await startPythonBackend();
    console.log('后端已就绪，打开窗口');
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    if (pythonProcess) {
        pythonProcess.kill();
        pythonProcess = null;
    }
    if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
    if (pythonProcess) {
        pythonProcess.kill();
        pythonProcess = null;
    }
});