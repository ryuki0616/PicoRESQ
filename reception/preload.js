/**
 * PicoRESQ 受付システム - Preload スクリプト
 * 
 * contextBridge を使って安全に API を公開します。
 * NFC操作はメインプロセス側で実行し、IPC経由で通信します。
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
    erase: () => ipcRenderer.invoke('nfc:erase')
});

// 削除ログ API を公開
contextBridge.exposeInMainWorld('picoResqEraseLog', {
    appendLog: (entry) => ipcRenderer.invoke('erase:appendLog', entry)
});
