// PicoRESQ 受付システム - Electron レンダラープロセス（デモ用簡易版）
// 名前・アレルギー・配慮項目のみを扱う

let lastDetectedIdm = null;
let currentMode = 'read'; // 'read' or 'write'
let isScanningForWrite = false;
let isWriting = false; // 書き込み処理中フラグ
let currentResidentData = null; // 現在表示中の避難者データ
let currentCardIdm = null; // 現在検知中のカードIDm
let pollIntervalId = null; // ポーリングのインターバルID
const INPUT_LIMITS = {
    nameBytes: 24,
    allergyBytes: 21
};

function getUtf8ByteLength(value) {
    return new TextEncoder().encode(value).length;
}

function truncateUtf8ToMaxBytes(value, maxBytes) {
    if (getUtf8ByteLength(value) <= maxBytes) {
        return value;
    }
    let trimmed = value;
    while (trimmed && getUtf8ByteLength(trimmed) > maxBytes) {
        trimmed = trimmed.slice(0, -1);
    }
    return trimmed;
}

function enforceInputByteLimit(input, maxBytes) {
    if (!input) return;
    const trimmed = truncateUtf8ToMaxBytes(input.value, maxBytes);
    if (trimmed !== input.value) {
        input.value = trimmed;
    }
}

function setupInputLimits() {
    const nameInput = document.querySelector('input[name="name"]');
    const allergyInput = document.querySelector('input[name="allergy"]');
    if (nameInput) {
        nameInput.addEventListener('input', () => {
            enforceInputByteLimit(nameInput, INPUT_LIMITS.nameBytes);
        });
    }
}

// ポーリングを開始
function startPolling() {
    if (pollIntervalId) return; // 既に開始済み
    pollIntervalId = setInterval(pollCard, 700);
    console.log('ポーリング開始');
}

// ポーリングを停止
function stopPolling() {
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
        console.log('ポーリング停止');
    }
}

function getNfcApi() {
    const api = window.picoResqNfc;
    if (!api || typeof api.detect !== 'function') {
        updateReaderStatus('NFCリーダーエラー: NFC APIが初期化されていません', true);
        return null;
    }
    return api;
}

// NFCリーダー状態をUIに表示
function updateReaderStatus(message, isError = false) {
    const statusElement = document.getElementById('ws-status');
    if (!statusElement) {
        const header = document.querySelector('header');
        if (header && !document.getElementById('ws-status')) {
            const statusDiv = document.createElement('div');
            statusDiv.id = 'ws-status';
            statusDiv.style.cssText = 'padding: 8px; margin: 10px 0; border-radius: 4px; font-size: 0.9em;';
            header.appendChild(statusDiv);
        }
    }

    const statusEl = document.getElementById('ws-status');
    if (statusEl) {
        statusEl.textContent = message;
        if (isError) {
            statusEl.style.backgroundColor = '#f44336';
            statusEl.style.color = 'white';
        } else {
            statusEl.style.backgroundColor = '#4caf50';
            statusEl.style.color = 'white';
        }
    }
}

async function pollCard() {
    // 書き込み中はポーリングをスキップ（カードリーダー競合防止）
    if (isWriting) {
        return;
    }
    try {
        const api = getNfcApi();
        if (!api) {
            return;
        }
        const result = await api.detect();
        if (!result.ok) {
            updateReaderStatus(`NFCリーダーエラー: ${result.error}`, true);
            return;
        }
        const idm = result.idm;
        if (idm && idm !== lastDetectedIdm) {
            lastDetectedIdm = idm;
            updateReaderStatus(`カード検知: ${idm}`);
            handleNfcDetected(idm);
        } else if (!idm && lastDetectedIdm) {
            const prev = lastDetectedIdm;
            lastDetectedIdm = null;
            updateReaderStatus('カードをタッチしてください');
            handleNfcRemoved(prev);
        } else if (!idm) {
            updateReaderStatus('カードをタッチしてください');
        }
    } catch (error) {
        updateReaderStatus(`NFCリーダーエラー: ${error.message}`, true);
    }
}

// 初期化時にポーリング開始
startPolling();
setupInputLimits();

// Tab Switching
function openTab(mode) {
    currentMode = mode;
    
    // UI Update
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    document.getElementById(mode).classList.add('active');
    document.querySelector(`.tab-btn[onclick="openTab('${mode}')"]`).classList.add('active');

    if (mode === 'read') {
        resetRead();
    } else if (mode === 'erase') {
        resetErase();
    }
}

// Read Mode Logic
function resetRead() {
    document.getElementById('read-status').style.display = 'block';
    document.getElementById('read-result').style.display = 'none';
    document.getElementById('detail-button-container').style.display = 'none';
    currentCardIdm = null;
    currentResidentData = null;
    closeDetailInfo();
}

// 表示用のユーティリティ
function formatUnset(value) {
    if (value === null || value === undefined || value === '') {
        return '未設定';
    }
    return value;
}

function formatVulnerabilities(vul) {
    if (!vul) {
        return '該当なし';
    }
    const labels = {
        eld: '高齢者',
        inf: '乳幼児',
        prg: '妊産婦',
        dis: '障がい',
        for: '外国人'
    };
    const items = [];
    Object.keys(labels).forEach(key => {
        if (vul[key]) {
            items.push(labels[key]);
        }
    });
    return items.length > 0 ? items.join('、') : '該当なし';
}

function formatAllergyDisplay(data) {
    const allergy = formatUnset(data.allergy);
    if (data.allergy_overflow && allergy !== '未設定') {
        return `${allergy} etc`;
    }
    return allergy;
}

function handleNfcDetected(idm) {
    console.log("NFC Detected:", idm);
    currentCardIdm = idm;

    if (currentMode === 'read') {
        // In read mode, show success and fetch info
        document.getElementById('read-status').style.display = 'none';
        document.getElementById('read-result').style.display = 'block';
        document.getElementById('resident-info').innerHTML = `<p>IDm: ${idm}</p><p>読み込み中...</p>`;
        
        fetchResidentInfo(idm);

    } else if (currentMode === 'write' && isScanningForWrite) {
        // In write mode, proceed with registration
        submitRegistration(idm);
    }
}

function handleNfcRemoved(idm) {
    console.log("NFC Removed:", idm);
    
    if (currentCardIdm === idm) {
        currentCardIdm = null;
        
        if (currentMode === 'read') {
            resetRead();
        } else if (currentMode === 'write' && isScanningForWrite) {
            cancelScan();
        }
    }
}

// Write Mode Logic
async function startRegistration() {
    const form = document.getElementById('register-form');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }
    
    isScanningForWrite = true;
    isWriting = true;
    stopPolling(); // ポーリングを完全停止
    document.getElementById('scan-overlay').style.display = 'flex';
    
    // writeコマンドが自動でカードを待機するので、直接書き込み開始
    await submitRegistrationDirect();
}

function cancelScan() {
    isScanningForWrite = false;
    isWriting = false;
    document.getElementById('scan-overlay').style.display = 'none';
    startPolling(); // ポーリング再開
}

// 直接書き込み（writeコマンドがカード待機を行う）
async function submitRegistrationDirect() {
    const form = document.getElementById('register-form');
    const formData = new FormData(form);
    const allergyRaw = formData.get('allergy') || '';
    const allergyOverflow = getUtf8ByteLength(allergyRaw) > INPUT_LIMITS.allergyBytes;
    const allergyStored = truncateUtf8ToMaxBytes(allergyRaw, INPUT_LIMITS.allergyBytes);

    // デモ用：名前、アレルギー、配慮項目のみ（idmはwriteコマンドが自動取得）
    const data = {
        name: formData.get('name') || '',
        allergy: allergyStored,
        allergy_overflow: allergyOverflow ? 1 : 0,
        vulnerabilities: {
            eld: formData.get('vul_eld') === 'on' ? 1 : 0,
            inf: formData.get('vul_inf') === 'on' ? 1 : 0,
            prg: formData.get('vul_prg') === 'on' ? 1 : 0,
            dis: formData.get('vul_dis') === 'on' ? 1 : 0,
            for: formData.get('vul_for') === 'on' ? 1 : 0
        },
        registered_at: new Date().toISOString()
    };

    try {
        const api = getNfcApi();
        if (!api) {
            alert('NFC APIが初期化されていません。アプリを再起動してください。');
            cancelScan();
            return;
        }
        console.log('書き込み開始:', data);
        const result = await api.write(data);
        console.log('書き込み結果:', result);
        if (!result.ok) {
            alert('書き込みエラー: ' + result.error);
            cancelScan();
            return;
        }
        alert('NFCカードへの書き込みが完了しました！');
        form.reset();
        cancelScan();
        openTab('read');
    } catch (error) {
        console.error('Write card error:', error);
        alert('書き込みエラーが発生しました: ' + error.message);
        cancelScan();
    }
}

// 旧API互換（handleNfcDetectedから呼ばれる場合用）
async function submitRegistration(idm) {
    await submitRegistrationDirect();
}

async function fetchResidentInfo(idm) {
    try {
        document.getElementById('resident-info').innerHTML = '<p>カードから読み取り中...</p>';
        const api = getNfcApi();
        if (!api) {
            throw new Error('NFC APIが初期化されていません');
        }
        const result = await api.read();
        if (!result.ok) {
            throw new Error(result.error || 'カード読み取りに失敗しました');
        }

        const data = result.reception || {};
        currentResidentData = data;

        // デモ用：名前、配慮項目、アレルギーのみ表示
        let infoHtml = `
            <table class="info-table">
                <tr>
                    <th>氏名</th>
                    <td>${formatUnset(data.name)}</td>
                </tr>
                <tr>
                    <th>配慮項目</th>
                    <td>${formatVulnerabilities(data.vulnerabilities)}</td>
                </tr>
                <tr>
                    <th>アレルギー</th>
                    <td style="color: ${data.allergy ? '#ffca28' : 'inherit'};">${formatAllergyDisplay(data) || 'なし'}</td>
                </tr>
            </table>
            <p style="color: #2196f3; font-size: 0.9em; margin-top: 15px;">カードから読み取りました</p>
        `;

        document.getElementById('resident-info').innerHTML = infoHtml;
        document.getElementById('detail-button-container').style.display = 'block';
    } catch (error) {
        console.error('Error fetching resident info:', error);
        currentResidentData = null;
        document.getElementById('resident-info').innerHTML = 
            `<p style="color: #f44336;">読み取りエラー: ${error.message}</p>`;
        document.getElementById('detail-button-container').style.display = 'none';
    }
}

// 詳細情報を表示
function showDetailInfo() {
    if (!currentResidentData) {
        alert('詳細情報がありません');
        return;
    }
    
    const data = currentResidentData;
    let detailHtml = '<div class="detail-section">';
    
    // 基本情報
    detailHtml += '<h3>基本情報</h3>';
    detailHtml += `<p><strong>IDm:</strong> ${formatUnset(data.idm)}</p>`;
    detailHtml += `<p><strong>氏名:</strong> ${formatUnset(data.name)}</p>`;
    detailHtml += '</div>';
    
    // アレルギー
    detailHtml += '<div class="detail-section">';
    detailHtml += '<h3>アレルギー情報</h3>';
    detailHtml += `<p style="color: #ffca28; font-weight: bold;">${formatAllergyDisplay(data) || 'なし'}</p>`;
    detailHtml += '</div>';
    
    // 配慮項目
    detailHtml += '<div class="detail-section">';
    detailHtml += '<h3>配慮項目</h3>';
    detailHtml += `<p>${formatVulnerabilities(data.vulnerabilities)}</p>`;
    detailHtml += '</div>';
    
    // クイズ進捗（読み取れた場合）
    if (data.quiz_clearance_flags !== undefined) {
        detailHtml += '<div class="detail-section">';
        detailHtml += '<h3>クイズ進捗</h3>';
        const flags = data.quiz_clearance_flags || 0;
        const boothNames = ['ブース1', 'ブース2', 'ブース3', 'ブース4', 'ブース5'];
        const progress = boothNames.map((name, i) => {
            const cleared = (flags & (1 << i)) !== 0;
            return `${name}: ${cleared ? 'クリア' : '未クリア'}`;
        }).join('<br>');
        detailHtml += `<p>${progress}</p>`;
        detailHtml += '</div>';
    }
    
    document.getElementById('detail-info-content').innerHTML = detailHtml;
    document.getElementById('detail-modal').style.display = 'flex';
}

// 詳細情報モーダルを閉じる
function closeDetailInfo() {
    const modal = document.getElementById('detail-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// モーダル外をクリックしたら閉じる
window.onclick = function(event) {
    const detailModal = document.getElementById('detail-modal');
    
    if (event.target === detailModal) {
        closeDetailInfo();
    }
}

// ============================================================================
// カードデータ削除機能（セキュリティ対策）
// ============================================================================

let isErasing = false; // 削除処理中フラグ

// 削除タブを開いたときの初期化
function resetErase() {
    document.getElementById('erase-status').style.display = 'block';
    document.getElementById('erase-result').style.display = 'none';
    isErasing = false;
}

// 削除開始（カードが既に検知されている場合のみ実行）
async function startErase() {
    if (isErasing) {
        return;
    }
    
    // まずカードが検知されているか確認
    const api = getNfcApi();
    if (!api) {
        alert('NFC APIが初期化されていません。アプリを再起動してください。');
        return;
    }
    
    // カード検知を確認
    const detectResult = await api.detect();
    if (!detectResult.ok || !detectResult.idm) {
        alert('カードが検知されていません。\nカードをリーダーにかざしてから、もう一度ボタンを押してください。');
        return;
    }
    
    const cardIdm = detectResult.idm;
    
    // 確認ダイアログ
    const confirmed = confirm(`カードID: ${cardIdm}\n\n本当にこのカードのデータを削除しますか？\n\nこの操作は取り消せません。`);
    if (!confirmed) {
        return;
    }
    
    isErasing = true;
    stopPolling(); // ポーリングを停止
    
    const statusEl = document.getElementById('erase-status');
    statusEl.innerHTML = `
        <h2>削除中...</h2>
        <p>カードID: ${cardIdm}</p>
        <p>カードをリーダーにかざしたままお待ちください。</p>
        <div class="spinner"></div>
        <button type="button" class="btn-secondary" onclick="cancelErase()" style="margin-top: 20px;">キャンセル</button>
    `;
    
    try {
        console.log('カードデータ削除開始:', cardIdm);
        const result = await api.erase();
        console.log('削除結果:', result);
        
        if (!result.ok) {
            throw new Error(result.error || '削除に失敗しました');
        }
        
        // 削除ログを記録
        const logEntry = {
            timestamp: new Date().toISOString(),
            idm: result.idm,
            action: 'erase',
            success: true
        };
        try {
            if (window.picoResqEraseLog) {
                await window.picoResqEraseLog.appendLog(logEntry);
                console.log('削除ログを記録しました');
            }
        } catch (logError) {
            console.warn('削除ログの記録に失敗:', logError);
        }
        
        // 成功表示（2秒後に自動で初期画面に戻る）
        const statusEl = document.getElementById('erase-status');
        statusEl.innerHTML = `
            <div class="success-icon">完了</div>
            <h2 style="color: #4caf50;">削除完了</h2>
            <p>カードID: ${result.idm} のデータが正常に削除されました。</p>
            <p style="color: #888; font-size: 0.9em; margin-top: 20px;">2秒後に自動で戻ります...</p>
        `;
        
        // 2秒後に初期画面に戻る（連続使用のため）
        setTimeout(() => {
            showEraseInitial();
        }, 2000);
        
    } catch (error) {
        console.error('削除エラー:', error);
        showEraseError(error.message);
    } finally {
        isErasing = false;
        startPolling(); // ポーリング再開
    }
}

// 削除をキャンセル
function cancelErase() {
    isErasing = false;
    startPolling();
    resetErase();
    showEraseInitial();
}

// エラー表示
function showEraseError(message) {
    const statusEl = document.getElementById('erase-status');
    statusEl.innerHTML = `
        <h2>カードデータ削除</h2>
        <p style="color: #f44336; font-weight: bold;">エラー: ${message}</p>
        <div class="warning-box">
            <p><strong>注意:</strong> この操作はカード内の全ての避難者情報を削除します。</p>
            <ul>
                <li>氏名、アレルギー情報、配慮項目</li>
                <li>クイズ進捗（クリア状況）</li>
            </ul>
            <p>削除したデータは復元できません。</p>
        </div>
        <p style="margin-top: 20px;">削除するカードをリーダーにかざしてください。</p>
        <button type="button" class="erase-btn" onclick="startErase()">カードデータを削除する</button>
    `;
}

// 削除画面の初期表示
function showEraseInitial() {
    const statusEl = document.getElementById('erase-status');
    statusEl.innerHTML = `
        <h2>カードデータ削除</h2>
        <div class="warning-box">
            <p><strong>注意:</strong> この操作はカード内の全ての避難者情報を削除します。</p>
            <ul>
                <li>氏名、アレルギー情報、配慮項目</li>
                <li>クイズ進捗（クリア状況）</li>
            </ul>
            <p>削除したデータは復元できません。</p>
        </div>
        <p style="margin-top: 20px;">削除するカードをリーダーにかざしてください。</p>
        <button type="button" class="erase-btn" onclick="startErase()">カードデータを削除する</button>
    `;
}
