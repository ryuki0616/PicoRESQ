/**
 * PicoRESQ-Kids 受付システム - Electron メインプロセス
 * 
 * Electronアプリケーションのエントリーポイントです。
 * ブラウザウィンドウの作成・管理、NFC CLI実行を行います。
 * 
 * 最終更新: 2026-01-21 - パフォーマンス最適化（タイムアウト統一、エラーハンドリング改善）
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const { execFile, spawn } = require('child_process');
const { promisify } = require('util');
const path = require('path');
const fs = require('fs');

const execFileAsync = promisify(execFile);

const DEFAULT_API_BASE_URL = 'http://localhost:8000';

// ========================================
// 設定値（集中管理）
// ========================================
const CONFIG = {
    // NFC CLI タイムアウト（ミリ秒）
    NFC_DETECT_TIMEOUT: 5000,      // 検出: 短め
    NFC_READ_TIMEOUT: 10000,       // 読み取り
    NFC_WRITE_TIMEOUT: 30000,      // 書き込み: 長め
    NFC_ERASE_TIMEOUT: 15000,      // 削除
    // バッファサイズ
    MAX_BUFFER: 1024 * 1024,
};

// プロジェクトルートとNFC CLIパス
const projectRoot = path.join(__dirname, '..');
const nfcCliPath = path.join(projectRoot, 'scripts', 'nfc_cli.py');
const backendVenvPython = path.join(projectRoot, 'backend', 'venv', 'bin', 'python');
const backendVenvPythonWin = path.join(projectRoot, 'backend', 'venv', 'Scripts', 'python.exe');
const backendUvPython = path.join(projectRoot, 'backend', '.venv', 'bin', 'python');
const backendUvPythonWin = path.join(projectRoot, 'backend', '.venv', 'Scripts', 'python.exe');

// キャッシュ
let cachedPythonPath = null;

/**
 * Pythonパスを解決する（キャッシュ付き）
 * 優先順位: PICORESQ_PYTHON環境変数 > backend/venv > backend/.venv > python3
 */
function resolvePythonPath() {
    if (cachedPythonPath) {
        return cachedPythonPath;
    }
    
    if (process.env.PICORESQ_PYTHON) {
        cachedPythonPath = process.env.PICORESQ_PYTHON;
    } else if (fs.existsSync(backendVenvPython)) {
        cachedPythonPath = backendVenvPython;
    } else if (fs.existsSync(backendVenvPythonWin)) {
        cachedPythonPath = backendVenvPythonWin;
    } else if (fs.existsSync(backendUvPython)) {
        cachedPythonPath = backendUvPython;
    } else if (fs.existsSync(backendUvPythonWin)) {
        cachedPythonPath = backendUvPythonWin;
    } else {
        cachedPythonPath = 'python3';
    }
    
    console.log(`Python path resolved: ${cachedPythonPath}`);
    return cachedPythonPath;
}

/**
 * コマンドごとの適切なタイムアウトを取得
 */
function getTimeoutForCommand(args) {
    const cmd = args[0];
    switch (cmd) {
        case 'detect':
            return CONFIG.NFC_DETECT_TIMEOUT;
        case 'read':
            return CONFIG.NFC_READ_TIMEOUT;
        case 'erase':
            return CONFIG.NFC_ERASE_TIMEOUT;
        case 'write':
            return CONFIG.NFC_WRITE_TIMEOUT;
        default:
            return CONFIG.NFC_READ_TIMEOUT;
    }
}

/**
 * NFC CLIを実行する
 */
async function runNfcCli(args, inputText = null) {
    const pythonPath = resolvePythonPath();
    const timeout = getTimeoutForCommand(args);
    
    // stdinにデータを渡す場合はspawnを使用
    if (inputText !== null) {
        return runNfcCliWithStdin(args, inputText, timeout);
    }
    
    // stdinなしの場合はexecFileを使用
    const options = { timeout, maxBuffer: CONFIG.MAX_BUFFER };
    try {
        const { stdout } = await execFileAsync(pythonPath, [nfcCliPath, ...args], options);
        return JSON.parse(stdout);
    } catch (error) {
        // タイムアウトの場合は明確なメッセージを返す
        if (error.killed) {
            return { ok: false, error: 'タイムアウト: カードが検知できませんでした' };
        }
        // CLIが正常に返した通信エラーは、そのメッセージを画面に渡す。
        try {
            const result = JSON.parse(error.stdout);
            if (result.ok === false) return result;
        } catch (_) {
            // JSON応答がない異常終了は、従来のエラー情報を使用する。
        }
        return { ok: false, error: error.stderr || error.message };
    }
}

/**
 * NFC CLIをstdin入力付きで実行する（spawnを使用）
 */
function runNfcCliWithStdin(args, inputText, timeout = CONFIG.NFC_WRITE_TIMEOUT) {
    return new Promise((resolve) => {
        const pythonPath = resolvePythonPath();
        const proc = spawn(pythonPath, [nfcCliPath, ...args], { timeout });
        
        let stdout = '';
        let stderr = '';
        let resolved = false;
        
        // タイムアウト処理
        const timeoutId = setTimeout(() => {
            if (!resolved) {
                resolved = true;
                proc.kill();
                resolve({ ok: false, error: 'タイムアウト: 処理が完了しませんでした' });
            }
        }, timeout);
        
        proc.stdout.on('data', (data) => {
            stdout += data.toString();
        });
        
        proc.stderr.on('data', (data) => {
            stderr += data.toString();
        });
        
        proc.on('close', (code) => {
            clearTimeout(timeoutId);
            if (resolved) return;
            resolved = true;
            
            if (code !== 0) {
                resolve({ ok: false, error: stderr || `処理に失敗しました (code: ${code})` });
                return;
            }
            
            try {
                resolve(JSON.parse(stdout));
            } catch (e) {
                resolve({ ok: false, error: '応答の解析に失敗しました' });
            }
        });
        
        proc.on('error', (err) => {
            clearTimeout(timeoutId);
            if (resolved) return;
            resolved = true;
            resolve({ ok: false, error: err.message });
        });
        
        // stdinにデータを書き込んで閉じる
        proc.stdin.write(inputText);
        proc.stdin.end();
    });
}

function getApiBaseUrl() {
    return process.env.API_BASE_URL || DEFAULT_API_BASE_URL;
}

function getWsBaseUrl(apiBaseUrl) {
    const url = new URL(apiBaseUrl);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
}

function buildCsp(apiBaseUrl) {
    const wsBaseUrl = getWsBaseUrl(apiBaseUrl);
    return `default-src 'self' 'unsafe-inline' ${apiBaseUrl} ${wsBaseUrl}; connect-src 'self' ${apiBaseUrl} ${wsBaseUrl}`;
}

let mainWindow;

function createWindow() {
    // ブラウザウィンドウを作成
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            enableRemoteModule: false,
            webSecurity: true,
            preload: path.join(__dirname, 'preload.js')
        },
        title: 'PicoRESQ-Kids 受付システム'
    });
    
    // Content Security Policyを設定（接続先の環境変数に対応）
    const apiBaseUrl = getApiBaseUrl();
    const cspValue = buildCsp(apiBaseUrl);
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                'Content-Security-Policy': [cspValue]
            }
        });
    });

    // index.htmlを読み込む
    mainWindow.loadFile('index.html');

    // 開発者ツールを開く（開発時のみ）
    if (process.argv.includes('--dev')) {
        mainWindow.webContents.openDevTools();
    }

    // ウィンドウが閉じられた時の処理
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// IPC ハンドラー: NFC操作をメインプロセスで実行
ipcMain.handle('nfc:detect', async () => {
    return await runNfcCli(['detect']);
});

ipcMain.handle('nfc:read', async () => {
    return await runNfcCli(['read']);
});

ipcMain.handle('nfc:write', async (event, payload) => {
    return await runNfcCli(['write', '--json', '-'], JSON.stringify(payload));
});

ipcMain.handle('nfc:erase', async () => {
    return await runNfcCli(['erase']);
});

// 削除ログ用ディレクトリ
const eraseLogDir = path.join(projectRoot, 'erase_logs');

/**
 * ディレクトリを作成（なければ）
 */
function ensureDir(dirPath) {
    if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
    }
}

/**
 * 削除ログを追記する
 */
function appendEraseLog(entry) {
    ensureDir(eraseLogDir);
    const date = new Date();
    const name = date.toISOString().slice(0, 10);
    const filePath = path.join(eraseLogDir, `${name}.jsonl`);
    const line = JSON.stringify(entry, null, 0) + '\n';
    fs.appendFileSync(filePath, line, 'utf-8');
    return filePath;
}

ipcMain.handle('erase:appendLog', async (event, entry) => {
    try {
        const filePath = appendEraseLog(entry);
        return { ok: true, path: filePath };
    } catch (error) {
        console.error('Erase log error:', error.message);
        return { ok: false, error: error.message };
    }
});

// アプリケーションの準備ができた時の処理
app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        // macOSで、ドックアイコンがクリックされた時にウィンドウを再作成
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

// すべてのウィンドウが閉じられた時の処理
app.on('window-all-closed', () => {
    // macOS以外では、すべてのウィンドウが閉じられたらアプリを終了
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// セキュリティ: 新しいウィンドウの作成を防ぐ
app.on('web-contents-created', (event, contents) => {
    contents.on('new-window', (event, navigationUrl) => {
        event.preventDefault();
    });
});
