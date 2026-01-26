/**
 * PicoRESQ クイズシステム - Preload スクリプト
 * 
 * contextBridge を使って安全に API を公開します。
 * NFC操作・クイズデータ読み込みはメインプロセス側で実行し、IPC経由で通信します。
 */
const { contextBridge, ipcRenderer } = require('electron');

const apiBaseUrl = process.env.API_BASE_URL || 'http://localhost:8000';

function toWebSocketUrl(apiBase) {
    try {
        const url = new URL(apiBase);
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        url.pathname = url.pathname.replace(/\/+$/, '') + '/ws';
        return url.toString();
    } catch (e) {
        return 'ws://localhost:8000/ws';
    }
}

// 設定情報を公開
contextBridge.exposeInMainWorld('picoResqConfig', {
    apiBaseUrl,
    wsBaseUrl: toWebSocketUrl(apiBaseUrl)
});

// NFC API を公開（IPC経由でメインプロセスに通信）
contextBridge.exposeInMainWorld('picoResqNfc', {
    detect: () => ipcRenderer.invoke('nfc:detect'),
    read: () => ipcRenderer.invoke('nfc:read'),
    write: (payload) => ipcRenderer.invoke('nfc:write', payload),
    writeCleared: (count) => ipcRenderer.invoke('nfc:writeCleared', count),
    setBoothCleared: (boothId) => ipcRenderer.invoke('nfc:setBoothCleared', boothId)
});

// クイズ API を公開（IPC経由でメインプロセスに通信）
contextBridge.exposeInMainWorld('picoResqQuiz', {
    loadQuizData: () => ipcRenderer.invoke('quiz:loadData'),
    loadAdminCards: () => ipcRenderer.invoke('quiz:loadAdminCards'),
    appendQuizLog: (entry) => ipcRenderer.invoke('quiz:appendLog', entry)
});
