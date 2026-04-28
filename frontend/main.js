/**
 * PicoRESQ-Kids クイズシステム - Electron メインプロセス
 * 
 * Electronアプリケーションのエントリーポイントです。
 * ブラウザウィンドウの作成・管理、NFC CLI実行、クイズデータ読み込みを行います。
 * 
 * 最終更新: 2026-01-21 - パフォーマンス最適化（キャッシュ、タイムアウト統一）
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const { execFile, spawn } = require('child_process');
const { promisify } = require('util');
const path = require('path');
const fs = require('fs');

const execFileAsync = promisify(execFile);

let mainWindow;
const DEFAULT_API_BASE_URL = 'http://localhost:8000';

// ========================================
// 設定値（集中管理）
// ========================================
const CONFIG = {
    // NFC CLI タイムアウト（ミリ秒）
    NFC_DETECT_TIMEOUT: 5000,      // 検出: 短め
    NFC_READ_TIMEOUT: 10000,       // 読み取り
    NFC_WRITE_TIMEOUT: 30000,      // 書き込み: 長め
    // バッファサイズ
    MAX_BUFFER: 1024 * 1024,
    // キャッシュ有効期間（ミリ秒）
    CACHE_TTL: 60000,              // 1分
};

// プロジェクトルートとパス
const projectRoot = path.join(__dirname, '..');
const nfcCliPath = path.join(projectRoot, 'scripts', 'nfc_cli.py');
const backendVenvPython = path.join(projectRoot, 'backend', 'venv', 'bin', 'python');
const backendVenvPythonWin = path.join(projectRoot, 'backend', 'venv', 'Scripts', 'python.exe');
const quizDataPath = path.join(projectRoot, 'backend', 'quiz_data.json');
const adminCardsPath = path.join(projectRoot, 'backend', 'admin_cards.json');
const quizLogDir = path.join(projectRoot, 'quiz_logs');

// ========================================
// キャッシュ（パフォーマンス向上）
// ========================================
const cache = {
    quizData: null,
    quizDataTime: 0,
    adminCards: null,
    adminCardsTime: 0,
    pythonPath: null,  // Pythonパスは変わらないので永続キャッシュ
};

function getPythonChildEnv() {
    return {
        ...process.env,
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8'
    };
}

/**
 * Pythonパスを解決する（キャッシュ付き）
 */
function resolvePythonPath() {
    // キャッシュがあれば使用
    if (cache.pythonPath) {
        return cache.pythonPath;
    }
    
    let pythonPath = 'python3';
    if (process.env.PICORESQ_PYTHON) {
        pythonPath = process.env.PICORESQ_PYTHON;
    } else if (fs.existsSync(backendVenvPython)) {
        pythonPath = backendVenvPython;
    } else if (fs.existsSync(backendVenvPythonWin)) {
        pythonPath = backendVenvPythonWin;
    }
    
    // キャッシュに保存
    cache.pythonPath = pythonPath;
    console.log(`Python path resolved: ${pythonPath}`);
    return pythonPath;
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
        case 'write':
        case 'write-cleared':
        case 'set-booth-cleared':
        case 'erase':
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
    
    const options = {
        timeout,
        maxBuffer: CONFIG.MAX_BUFFER,
        encoding: 'utf8',
        env: getPythonChildEnv()
    };
    try {
        const { stdout } = await execFileAsync(pythonPath, [nfcCliPath, ...args], options);
        return JSON.parse(stdout);
    } catch (error) {
        // タイムアウトの場合は明確なメッセージを返す
        if (error.killed) {
            return { ok: false, error: 'タイムアウト: カードが検知できませんでした' };
        }
        console.error('NFC CLI Error:', error.message);
        return { ok: false, error: error.message };
    }
}

/**
 * NFC CLIをstdin入力付きで実行する（spawnを使用）
 */
function runNfcCliWithStdin(args, inputText, timeout = CONFIG.NFC_WRITE_TIMEOUT) {
    return new Promise((resolve) => {
        const pythonPath = resolvePythonPath();
        const proc = spawn(pythonPath, [nfcCliPath, ...args], {
            timeout,
            env: getPythonChildEnv()
        });
        
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
            stdout += data.toString('utf8');
        });
        
        proc.stderr.on('data', (data) => {
            stderr += data.toString('utf8');
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

/**
 * ディレクトリを作成（なければ）
 */
function ensureDir(dirPath) {
    if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
    }
}

/**
 * クイズログを追記する
 */
function appendQuizLog(entry) {
    ensureDir(quizLogDir);
    const date = new Date();
    const name = date.toISOString().slice(0, 10);
    const filePath = path.join(quizLogDir, `${name}.jsonl`);
    const line = JSON.stringify(entry, null, 0) + '\n';
    fs.appendFileSync(filePath, line, 'utf-8');
    return filePath;
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

function createWindow() {
    // ブラウザウィンドウを作成
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            enableRemoteModule: false,
            preload: path.join(__dirname, 'preload.js')
        },
        icon: path.join(__dirname, 'icon.png'), // アイコンファイルがあれば使用
        title: 'NFC防災ヒーロー育成ラリー'
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

// IPC ハンドラー: NFC操作
ipcMain.handle('nfc:detect', async () => {
    return await runNfcCli(['detect']);
});

ipcMain.handle('nfc:read', async () => {
    return await runNfcCli(['read']);
});

ipcMain.handle('nfc:write', async (event, payload) => {
    return await runNfcCli(['write', '--json', '-'], JSON.stringify(payload));
});

ipcMain.handle('nfc:writeCleared', async (event, count) => {
    return await runNfcCli(['write-cleared', '--count', String(count)]);
});

ipcMain.handle('nfc:setBoothCleared', async (event, boothId) => {
    return await runNfcCli(['set-booth-cleared', '--booth-id', String(boothId)]);
});

// IPC ハンドラー: クイズデータ読み込み（キャッシュ付き）
ipcMain.handle('quiz:loadData', async () => {
    const now = Date.now();
    
    // キャッシュが有効なら使用
    if (cache.quizData && (now - cache.quizDataTime) < CONFIG.CACHE_TTL) {
        return cache.quizData;
    }
    
    try {
        const data = fs.readFileSync(quizDataPath, 'utf-8');
        cache.quizData = JSON.parse(data);
        cache.quizDataTime = now;
        return cache.quizData;
    } catch (error) {
        console.error('Quiz data load error:', error.message);
        return null;
    }
});

ipcMain.handle('quiz:loadAdminCards', async () => {
    const now = Date.now();
    
    // キャッシュが有効なら使用
    if (cache.adminCards && (now - cache.adminCardsTime) < CONFIG.CACHE_TTL) {
        return cache.adminCards;
    }
    
    try {
        const data = fs.readFileSync(adminCardsPath, 'utf-8');
        cache.adminCards = JSON.parse(data);
        cache.adminCardsTime = now;
        return cache.adminCards;
    } catch (error) {
        console.error('Admin cards load error:', error.message);
        return { admin_card_ids: [] };
    }
});

ipcMain.handle('quiz:appendLog', async (event, entry) => {
    try {
        const filePath = appendQuizLog(entry);
        return { ok: true, path: filePath };
    } catch (error) {
        console.error('Quiz log error:', error.message);
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
