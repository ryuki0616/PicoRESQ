// PicoRESQ-Kids クイズシステム - Electron レンダラープロセス
// 既存のquiz.jsの機能をElectron用に統合

// 非同期で初期化されるデータ
let quizData = { quizzes: [] };
let adminCards = { admin_card_ids: [] };
let dataLoaded = false;

const QUESTIONS_PER_BOOTH = 3;
let currentIdm = null;
let currentBoothId = null;
let currentQuiz = null;
let selectedAnswer = null;
let clearedCount = 0;
let isAdminMode = false;  // 管理者モードフラグ
let wrongAnswers = [];  // 間違えた問題を記録する配列
let currentQuizNumber = 0;  // 現在の問題番号
let totalQuestions = QUESTIONS_PER_BOOTH;  // 総問題数
let lastDetectedIdm = null;
let boothCorrectCounts = {};
let pollIntervalId = null;  // ポーリングのインターバルID
let isNfcOperating = false; // NFC操作中フラグ
let isPolling = false; // 検知・初回読み取りの重複を防ぐ
let isSubmittingAnswer = false;
let needsReadRetry = false;

// ポーリングを開始
function startPolling() {
    if (pollIntervalId) return;
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

// 画面要素
const screens = {
    admin: document.getElementById('admin-screen'),
    home: document.getElementById('home-screen'),
    boothSelect: document.getElementById('booth-select-screen'),
    quiz: document.getElementById('quiz-screen'),
    result: document.getElementById('result-screen'),
    complete: document.getElementById('complete-screen')
};

// 管理者画面用の変数
let selectedBoothId = null;

function updateCardStatus(message, color = '#666', state = 'waiting') {
    const statusText = document.getElementById('card-status-text');
    const indicator = document.getElementById('card-status-indicator');
    
    if (statusText && !currentIdm) {
        statusText.textContent = message;
        statusText.style.color = color;
    }
    
    // インジケーターの状態を更新
    if (indicator) {
        indicator.classList.remove('detected', 'error');
        if (state === 'detected') {
            indicator.classList.add('detected');
        } else if (state === 'error') {
            indicator.classList.add('error');
        }
    }
}

function isAdminCard(idm) {
    return (adminCards.admin_card_ids || []).includes(idm);
}

function getBoothQuizzes(boothId) {
    return (quizData.quizzes || []).filter((quiz) => quiz.booth_id === boothId);
}

function getQuizByNumber(boothId, quizNumber) {
    const boothQuizzes = getBoothQuizzes(boothId);
    return boothQuizzes.find((quiz) => quiz.quiz_number === quizNumber) || null;
}

function canUserAccessBooth(boothId) {
    if (isAdminMode) {
        return true;
    }
    if (!selectedBoothId) {
        return false;
    }
    return boothId === selectedBoothId;
}

async function pollCard() {
    // データが読み込まれていない場合、またはNFC操作中はスキップ
    if (!dataLoaded || isNfcOperating || isPolling) {
        return;
    }
    isPolling = true;
    
    try {
        const result = await window.picoResqNfc.detect();
        if (!result.ok) {
            updateCardStatus('⚠️ リーダー確認', '#dc3545', 'error');
            return;
        }
        const idm = result.idm;
        if (idm && (idm !== lastDetectedIdm || needsReadRetry)) {
            needsReadRetry = false;
            lastDetectedIdm = idm;
            const isAdmin = isAdminCard(idm);
            console.log(`カード検知: ${idm}, 管理者: ${isAdmin}`);
            updateCardStatus('認証OK', '#2e7d32', 'detected');
            await handleCardDetected(idm, isAdmin);
        } else if (!idm && lastDetectedIdm) {
            const prev = lastDetectedIdm;
            lastDetectedIdm = null;
            updateCardStatus('カードをかざしてください', '#666', 'waiting');
            handleCardRemoved(prev);
        } else if (!idm) {
            updateCardStatus('カードをかざしてください', '#666', 'waiting');
        }
    } catch (error) {
        updateCardStatus('⚠️ エラー', '#dc3545', 'error');
    } finally {
        isPolling = false;
    }
}

// カード検知時の処理
async function handleCardDetected(idm, isAdmin) {
    console.log('handleCardDetected呼び出し:', idm, 'isAdmin:', isAdmin);
    
    if (!idm) {
        console.error('カードIDが空です');
        return;
    }
    
    currentIdm = idm;
    const cardIdElement = document.getElementById('card-id');
    const cardStatusText = document.getElementById('card-status-text');
    const indicator = document.getElementById('card-status-indicator');
    
    if (!cardIdElement || !cardStatusText) {
        console.error('必要なDOM要素が見つかりません');
        return;
    }
    
    // コンパクト表示用にカードIDを短縮
    const shortIdm = idm.length > 12 ? idm.slice(-8) : idm;
    cardIdElement.textContent = shortIdm;
    console.log('カードID表示を更新しました');
    
    // インジケーターを検知状態に
    if (indicator) {
        indicator.classList.add('detected');
    }
    
    // 管理者カードかどうかをチェック
    if (isAdmin) {
        console.log('管理者カードとして処理');
        isAdminMode = true;
        cardStatusText.textContent = '管理者';
        cardStatusText.style.color = '#667eea';
        // 管理者画面へのアクセスボタンを表示
        const adminBtn = document.getElementById('user-to-admin-btn');
        if (adminBtn) {
            adminBtn.style.display = 'block';
            adminBtn.style.opacity = '1';
        }
        // 進捗表示と挑戦ボタンを非表示
        document.getElementById('progress-display').style.display = 'none';
        document.getElementById('start-quiz-section').style.display = 'none';
    } else {
        console.log('ユーザーカードとして処理');
        isAdminMode = false;
        cardStatusText.textContent = '認証OK';
        cardStatusText.style.color = '#2e7d32';
        // 管理者画面へのアクセスボタンを非表示
        const adminBtn = document.getElementById('user-to-admin-btn');
        if (adminBtn) {
            adminBtn.style.display = 'none';
        }
        // 進捗を取得して表示（fetchProgress内でcheckAndShowStartButtonも呼ばれる）
        await fetchProgress(idm);
    }
    
    console.log('カード検知処理が完了しました');
}

// 管理者が選択したステージのクイズを開始
async function startSelectedBoothQuiz(idm) {
    try {
        if (!idm) {
            idm = currentIdm;
        }
        
        if (!idm) {
            alert('カードをかざしてください');
            return;
        }
        
        // 現在選択されているステージIDを取得（ローカル）
        if (!selectedBoothId) {
            alert('管理者がステージを選択していません');
            return;
        }
        const boothId = selectedBoothId;
        currentBoothId = boothId;
        boothCorrectCounts[currentBoothId] = 0;
        
        // 間違えた問題の配列をリセット
        wrongAnswers = [];
        currentQuizNumber = 0;
        
        // カードのクリア状態を確認
        const progress = await window.picoResqNfc.read();
        if (!progress.ok) {
            throw new Error(progress.error || 'カード読み取りに失敗しました');
        }
        const clearanceFlags = progress.clearance_flags || [];
        if (clearanceFlags[boothId - 1]) {
            alert('このステージは既に完了しています');
            return;
        }

        currentQuizNumber = 1;
        currentQuiz = getQuizByNumber(boothId, currentQuizNumber);
        if (!currentQuiz) {
            throw new Error('クイズデータが見つかりません');
        }
        
        // クイズ画面を表示
        showQuizScreen(currentQuiz);
    } catch (error) {
        console.error('クイズ開始エラー:', error);
        alert('クイズの取得に失敗しました');
    }
}

// 管理者がステージを選択した時の処理
function handleBoothSelected(boothId) {
    console.log(`管理者がステージ${boothId}を選択しました`);
    // ユーザー画面に通知を表示
    if (!isAdminMode && currentIdm) {
        // カードがかざされている場合、挑戦ボタンを更新
        checkAndShowStartButton();
    }
}

// 管理者がステージの選択を解除した時の処理
function handleBoothUnselected() {
    console.log('管理者がステージの選択を解除しました');
    // 挑戦ボタンを非表示
    if (!isAdminMode && currentIdm) {
        document.getElementById('start-quiz-section').style.display = 'none';
    }
}

// カード離脱時の処理
function handleCardRemoved(idm) {
    // 現在のカードが離れた場合のみリセット
    if (currentIdm === idm) {
        console.log('カードが離れました。状態をリセットします。');
        
        // 状態をリセット
        resetState();
        
        // 管理者モードを解除
        isAdminMode = false;
        
        // すべての画面からホーム画面に戻る
        showScreen('home');
        
        // UIをリセット
        document.getElementById('card-id').textContent = '';
        document.getElementById('card-status-text').textContent = 'カードをかざしてください';
        document.getElementById('progress-display').style.display = 'none';
        document.getElementById('start-quiz-section').style.display = 'none';
        
        // インジケーターをリセット
        const indicator = document.getElementById('card-status-indicator');
        if (indicator) {
            indicator.classList.remove('detected', 'error');
        }
        
        // 管理者画面へのアクセスボタンを非表示
        const adminBtn = document.getElementById('user-to-admin-btn');
        if (adminBtn) {
            adminBtn.style.display = 'none';
        }
    }
}

// 状態をリセットする関数
function resetState() {
    currentIdm = null;
    currentBoothId = null;
    currentQuiz = null;
    selectedAnswer = null;
    clearedCount = 0;
    boothCorrectCounts = {};
    
    // 進捗表示をリセット（コンパクト版と従来版の両方に対応）
    const boothItemsCompact = document.querySelectorAll('.booth-item-compact');
    boothItemsCompact.forEach((item) => {
        item.classList.remove('cleared');
        const statusEl = item.querySelector('.booth-status');
        if (statusEl) statusEl.textContent = '未完了';
    });
    
    const boothItems = document.querySelectorAll('.booth-item');
    boothItems.forEach((item) => {
        item.classList.remove('cleared');
        const statusEl = item.querySelector('.booth-status');
        if (statusEl) statusEl.textContent = '未完了';
    });
    
    const badges = document.querySelectorAll('.booth-status-badge');
    badges.forEach((badge) => {
        const card = badge.closest('.booth-card');
        if (card) card.classList.remove('cleared');
        badge.textContent = '未完了';
    });
}

// 進捗を取得
async function fetchProgress(idm) {
    try {
        const data = await window.picoResqNfc.read();
        if (!data.ok) {
            throw new Error(data.error || 'カード読み取りに失敗しました');
        }
        if (currentIdm !== idm) return;
        if (data.idm !== idm) {
            throw new Error('カードが交換されました。再度読み取ってください');
        }
        
        // 受付済みかどうかチェック（reception.nameが空なら未受付）
        const reception = data.reception || {};
        const isRegistered = reception.name && reception.name.trim() !== '';
        
        if (!isRegistered) {
            // 未受付カードの場合
            const cardStatusText = document.getElementById('card-status-text');
            cardStatusText.textContent = '⚠️ 未受付';
            cardStatusText.style.color = '#dc3545';
            
            // インジケーターをエラー状態に
            const indicator = document.getElementById('card-status-indicator');
            if (indicator) {
                indicator.classList.remove('detected');
                indicator.classList.add('error');
            }
            
            // 進捗表示と挑戦ボタンを非表示
            document.getElementById('progress-display').style.display = 'none';
            document.getElementById('start-quiz-section').style.display = 'none';
            return;
        }
        
        const clearanceFlags = data.clearance_flags || [];
        clearedCount = data.cleared_count || 0;

        // クリア状態を表示
        displayBoothClearanceStatus(clearanceFlags);
        
        document.getElementById('progress-display').style.display = 'block';
        
        // 管理者が選択したステージがある場合、挑戦ボタンを表示
        checkAndShowStartButton();
    } catch (error) {
        console.error('進捗取得エラー:', error);
        if (currentIdm !== idm) return;
        const statusText = document.getElementById('card-status-text');
        statusText.textContent = '⚠️ 読み取り失敗・再試行中';
        statusText.style.color = '#dc3545';
        document.getElementById('start-quiz-section').style.display = 'none';
        // 通信失敗を未受付にせず、同じカードでも読み直す。
        needsReadRetry = true;
    }
}

// 5つのステージのクリア可否を表示
function displayBoothClearanceStatus(clearanceFlags) {
    // コンパクト版と従来版の両方に対応
    const boothItemsCompact = document.querySelectorAll('.booth-item-compact');
    const boothItems = document.querySelectorAll('.booth-item');
    const allItems = boothItemsCompact.length > 0 ? boothItemsCompact : boothItems;
    
    // clearanceFlagsが配列の場合
    if (Array.isArray(clearanceFlags)) {
        allItems.forEach((item, index) => {
            const isCleared = clearanceFlags[index] || false;
            const statusElement = item.querySelector('.booth-status');
            
            if (isCleared) {
                item.classList.add('cleared');
                if (statusElement) {
                    statusElement.textContent = '完了';
                    statusElement.style.color = '';  // CSSに任せる
                }
            } else {
                item.classList.remove('cleared');
                if (statusElement) {
                    statusElement.textContent = '未完了';
                    statusElement.style.color = '';
                }
            }
        });
    } else if (typeof clearanceFlags === 'object') {
        // booth_statusオブジェクトの場合
        allItems.forEach((item, index) => {
            const boothNum = index + 1;
            const isCleared = clearanceFlags[boothNum] || false;
            const statusElement = item.querySelector('.booth-status');
            
            if (isCleared) {
                item.classList.add('cleared');
                if (statusElement) {
                    statusElement.textContent = '完了';
                    statusElement.style.color = '';
                }
            } else {
                item.classList.remove('cleared');
                if (statusElement) {
                    statusElement.textContent = '未完了';
                    statusElement.style.color = '';
                }
            }
        });
    }
}

// 管理者が選択したステージがある場合、挑戦ボタンを表示
async function checkAndShowStartButton() {
    try {
        if (selectedBoothId) {
            const boothId = selectedBoothId;
            const boothLabels = {
                1: 'ステージ1: 地震時の行動',
                2: 'ステージ2: 避難所でのマナー',
                3: 'ステージ3: 非常持ち出し袋',
                4: 'ステージ4: 災害時の連絡方法',
                5: 'ステージ5: 防災グッズ'
            };
            
            // 選択中のステージ情報を表示
            document.getElementById('selected-booth-info').textContent = 
                `現在のステージ: ${boothLabels[boothId] || `ステージ${boothId}`}`;
            
            // 挑戦ボタンを表示
            document.getElementById('start-quiz-section').style.display = 'block';
        } else {
            // 管理者がステージを選択していない場合
            document.getElementById('start-quiz-section').style.display = 'none';
        }
    } catch (error) {
        console.error('ステージ選択状況の取得エラー:', error);
        document.getElementById('start-quiz-section').style.display = 'none';
    }
}

// 進捗表示を更新
function updateProgress(count) {
    clearedCount = count;
    updateProgressDisplay(count);
}

function updateProgressDisplay(count) {
    // ホーム画面の進捗表示を更新
    const boothItems = document.querySelectorAll('.booth-item');
    boothItems.forEach((item, index) => {
        const boothNum = index + 1;
        if (boothNum <= count) {
            item.classList.add('cleared');
            item.querySelector('.booth-status').textContent = 'クリア済み';
        } else {
            item.classList.remove('cleared');
            item.querySelector('.booth-status').textContent = '未クリア';
        }
    });

    // ブース選択画面のバッジを更新
    const badges = document.querySelectorAll('.booth-status-badge');
    badges.forEach((badge, index) => {
        const boothNum = index + 1;
        const card = badge.closest('.booth-card');
        if (boothNum <= count) {
            card.classList.add('cleared');
            badge.textContent = 'クリア済み';
        } else {
            card.classList.remove('cleared');
            badge.textContent = '未クリア';
        }
    });
}

// 画面切り替え
function showScreen(screenName) {
    Object.values(screens).forEach(screen => screen.classList.remove('active'));
    screens[screenName].classList.add('active');
}

// イベントリスナー設定（DOMContentLoaded内で実行されるため、要素の存在確認は不要）
function setupEventListeners() {
    // ホームに戻るボタン
    const backToHomeBtn = document.getElementById('back-to-home-btn');
    if (backToHomeBtn) {
        backToHomeBtn.addEventListener('click', () => {
            showScreen('home');
        });
    }

    const backToHomeCompleteBtn = document.getElementById('back-to-home-complete-btn');
    if (backToHomeCompleteBtn) {
        backToHomeCompleteBtn.addEventListener('click', () => {
            showScreen('home');
        });
    }

    // 問題に挑戦ボタン
    const startQuizBtn = document.getElementById('start-quiz-btn');
    if (startQuizBtn) {
        startQuizBtn.addEventListener('click', () => {
            startSelectedBoothQuiz();
        });
    }

    // 回答送信ボタン
    const submitAnswerBtn = document.getElementById('submit-answer-btn');
    if (submitAnswerBtn) {
        submitAnswerBtn.addEventListener('click', async () => {
            if (isSubmittingAnswer || selectedAnswer === null || !currentIdm || !currentBoothId) {
                return;
            }
            isSubmittingAnswer = true;
            try {
                const correct = selectedAnswer === currentQuiz?.correct_answer;
                const currentCount = boothCorrectCounts[currentBoothId] || 0;
                const newCount = correct
                    ? Math.min(currentCount + 1, QUESTIONS_PER_BOOTH)
                    : currentCount;
                boothCorrectCounts[currentBoothId] = newCount;

                const boothCleared = correct && newCount >= QUESTIONS_PER_BOOTH;
                let allCleared = false;
                let clearedCountFromCard = null;
                if (boothCleared) {
                    // NFC書き込み中はポーリング停止
                    stopPolling();
                    isNfcOperating = true;
                    try {
                        const writeResult = await window.picoResqNfc.setBoothCleared(currentBoothId);
                        if (!writeResult.ok) {
                            throw new Error(writeResult.error || 'クリア情報の保存に失敗しました');
                        }
                        const progress = await window.picoResqNfc.read();
                        if (!progress.ok || progress.idm !== currentIdm ||
                            !progress.clearance_flags?.[currentBoothId - 1]) {
                            throw new Error('カードのクリア情報を確認できませんでした');
                        }
                        const flags = progress.clearance_flags;
                        clearedCountFromCard = flags.filter(Boolean).length;
                        allCleared = flags.length === 5 && flags.every((f) => f);
                    } finally {
                        isNfcOperating = false;
                        startPolling();
                    }
                }

                const logEntry = {
                    timestamp: new Date().toISOString(),
                    idm: currentIdm,
                    booth_id: currentBoothId,
                    quiz_number: currentQuiz?.quiz_number || 0,
                    selected_answer: selectedAnswer,
                    correct_answer: currentQuiz?.correct_answer,
                    correct,
                    correct_count: newCount
                };
                try {
                    window.picoResqQuiz.appendQuizLog(logEntry);
                } catch (error) {
                    console.warn('ログ保存に失敗:', error);
                }

                showResultScreen({
                    correct,
                    explanation: currentQuiz?.explanation || '',
                    correct_count: newCount,
                    booth_cleared: boothCleared,
                    cleared_count: clearedCountFromCard,
                    all_cleared: allCleared,
                    // 正解かつまだ全問正解でない場合、次の問題番号を渡す
                    next_quiz_number: correct && !boothCleared && currentQuizNumber < QUESTIONS_PER_BOOTH ? currentQuizNumber + 1 : null
                });
            } catch (error) {
                console.error('回答送信エラー:', error);
                alert(`${error.message}\nカードを置いたまま、もう一度回答してください。`);
            } finally {
                isSubmittingAnswer = false;
            }
        });
    }

    // 「もう一度挑戦」/「次の問題へ」/「間違えた問題に再挑戦」ボタン
    const nextQuizBtn = document.getElementById('next-quiz-btn');
    if (nextQuizBtn) {
        nextQuizBtn.addEventListener('click', async function() {
            const btn = this;
            if (btn.textContent === 'もう一度挑戦') {
                // 同じ問題を再表示
                if (currentQuiz) {
                    showQuizScreen(currentQuiz);
                }
            } else if (btn.textContent === '間違えた問題に再挑戦') {
                // 間違えた問題を再表示
                showWrongAnswers();
            } else {
                // 次の問題へ進む（既に実装済み）
                if (!currentIdm || !currentBoothId) {
                    return;
                }
                
                try {
                    if (currentQuizNumber >= QUESTIONS_PER_BOOTH) {
                        alert('この試練は既にクリア済みです！');
                        showScreen('home');
                        return;
                    }

                    const nextQuizNumber = currentQuizNumber + 1;
                    const nextQuiz = getQuizByNumber(currentBoothId, nextQuizNumber);
                    if (!nextQuiz) {
                        throw new Error('次の問題が見つかりません');
                    }

                    currentQuizNumber = nextQuizNumber;
                    currentQuiz = nextQuiz;
                    showQuizScreen(currentQuiz);
                } catch (error) {
                    console.error('次の問題取得エラー:', error);
                    alert('次の問題の取得に失敗しました');
                }
            }
        });
    }

    // 試練選択に戻るボタン
    const backToBoothSelectBtn = document.getElementById('back-to-booth-select-btn');
    if (backToBoothSelectBtn) {
        backToBoothSelectBtn.addEventListener('click', () => {
            if (!isAdminMode) {
                showScreen('home');
                return;
            }
            showScreen('boothSelect');
        });
    }

    const backToBoothSelectResultBtn = document.getElementById('back-to-booth-select-result-btn');
    if (backToBoothSelectResultBtn) {
        backToBoothSelectResultBtn.addEventListener('click', () => {
            if (!isAdminMode) {
                showScreen('home');
                return;
            }
            showScreen('boothSelect');
        });
    }

    // ブース選択カード
    document.querySelectorAll('.booth-card').forEach(card => {
        card.addEventListener('click', async () => {
            if (!currentIdm) {
                alert('カードをかざしてください');
                return;
            }

            const boothId = parseInt(card.dataset.booth);
            if (!canUserAccessBooth(boothId)) {
                alert('このステージは管理者が選択したものだけ挑戦できます');
                return;
            }
            currentBoothId = boothId;
            boothCorrectCounts[currentBoothId] = 0;
            
            try {
                const progress = await window.picoResqNfc.read();
                if (!progress.ok) {
                    throw new Error(progress.error || 'カード読み取りに失敗しました');
                }
                const clearanceFlags = progress.clearance_flags || [];
                if (clearanceFlags[boothId - 1]) {
                    alert('このステージは既に完了しています');
                    return;
                }

                currentQuizNumber = 1;
                currentQuiz = getQuizByNumber(boothId, currentQuizNumber);
                if (!currentQuiz) {
                    throw new Error('クイズデータが見つかりません');
                }

                showQuizScreen(currentQuiz);
            } catch (error) {
                console.error('クイズ開始エラー:', error);
                alert('クイズの取得に失敗しました');
            }
        });
    });
}

// ブース選択（setupEventListeners内で設定）

// クイズ画面を表示
function showQuizScreen(quiz) {
    document.getElementById('current-booth').textContent = quiz.booth_id;
    document.getElementById('quiz-question').textContent = quiz.question;
    
    const optionsContainer = document.getElementById('quiz-options');
    optionsContainer.innerHTML = '';
    
    quiz.options.forEach((option, index) => {
        const button = document.createElement('button');
        button.className = 'quiz-option';
        button.textContent = option;
        button.addEventListener('click', () => {
            document.querySelectorAll('.quiz-option').forEach(opt => opt.classList.remove('selected'));
            button.classList.add('selected');
            selectedAnswer = index;
            document.getElementById('submit-answer-btn').disabled = false;
        });
        optionsContainer.appendChild(button);
    });
    
    selectedAnswer = null;
    document.getElementById('submit-answer-btn').disabled = true;
    showScreen('quiz');
}

// 回答送信（setupEventListeners内で設定）

// 結果画面を表示
async function showResultScreen(result) {
    const resultContent = document.getElementById('result-content');
    resultContent.innerHTML = '';

    const icon = document.createElement('div');
    icon.className = `result-icon ${result.correct ? 'correct' : 'incorrect'}`;
    icon.textContent = result.correct ? '✓' : '✗';

    const message = document.createElement('div');
    message.className = 'result-message';
    message.textContent = result.correct ? '正解です！' : '不正解です';

    const explanation = document.createElement('div');
    explanation.className = 'result-explanation';
    explanation.textContent = result.explanation;

    // 進捗表示を追加
    const progressInfo = document.createElement('div');
    progressInfo.className = 'progress-info';
    if (result.correct) {
        progressInfo.textContent = `${result.correct_count || 0}/3問正解`;
        progressInfo.style.marginTop = '15px';
        progressInfo.style.fontSize = '1.1em';
        progressInfo.style.color = '#667eea';
        progressInfo.style.fontWeight = 'bold';
    }

    resultContent.appendChild(icon);
    resultContent.appendChild(message);
    resultContent.appendChild(explanation);
    if (result.correct) {
        resultContent.appendChild(progressInfo);
    }

    // 間違えた問題を記録
    if (!result.correct && currentQuiz) {
        // 既に記録されていない場合のみ追加
        const alreadyRecorded = wrongAnswers.some(wq => 
            wq.quiz_number === currentQuiz.quiz_number && 
            wq.booth_id === currentBoothId
        );
        if (!alreadyRecorded) {
            wrongAnswers.push({
                ...currentQuiz,
                booth_id: currentBoothId
            });
        }
    }

    // 試練がクリアされた場合
    if (result.booth_cleared && !result.all_cleared) {
        updateProgress(result.cleared_count || 0);
        
        // 進捗を再取得して表示（NFCカードから最新の状態を読み取る）
        if (currentIdm) {
            setTimeout(async () => {
                try {
                    await fetchProgress(currentIdm);
                } catch (error) {
                    console.error('進捗取得エラー:', error);
                }
            }, 500);
        }
        
        // 間違えた問題がある場合は再表示
        if (wrongAnswers.length > 0) {
            document.getElementById('next-quiz-btn').style.display = 'block';
            document.getElementById('next-quiz-btn').textContent = '間違えた問題に再挑戦';
        } else {
            document.getElementById('next-quiz-btn').style.display = 'none';
            setTimeout(() => {
                // ホーム画面に戻る
                showScreen('home');
                // 進捗を再取得して表示
                if (currentIdm) {
                    fetchProgress(currentIdm);
                    checkAndShowStartButton();
                }
                alert(`試練${currentBoothId}をクリアしました！`);
            }, 2000);
        }
        showScreen('result');
        return;
    }

    // 全試練クリアの場合
    if (result.all_cleared) {
        // 間違えた問題がある場合は再表示
        if (wrongAnswers.length > 0) {
            document.getElementById('next-quiz-btn').style.display = 'block';
            document.getElementById('next-quiz-btn').textContent = '間違えた問題に再挑戦';
        } else {
            document.getElementById('next-quiz-btn').style.display = 'none';
            setTimeout(() => {
                showCompleteScreen();
            }, 2000);
        }
        showScreen('result');
        return;
    }

    // 正解した場合、次の問題に進む
    if (result.correct && result.next_quiz_number) {
        // 注意: currentQuizNumberはここでは更新しない（次へボタンで更新する）
        document.getElementById('next-quiz-btn').style.display = 'block';
        document.getElementById('next-quiz-btn').textContent = '次の問題へ';
    } else if (result.correct) {
        // 3問すべて正解（既にクリア済み）
        document.getElementById('next-quiz-btn').style.display = 'none';
    } else {
        // 不正解の場合、同じ問題を再表示
        document.getElementById('next-quiz-btn').style.display = 'block';
        document.getElementById('next-quiz-btn').textContent = 'もう一度挑戦';
    }

    showScreen('result');
}

// 間違えた問題を再表示
function showWrongAnswers() {
    if (wrongAnswers.length === 0) {
        // 間違えた問題がない場合、ホーム画面に戻る
        showScreen('home');
        if (currentIdm) {
            fetchProgress(currentIdm);
            checkAndShowStartButton();
        }
        return;
    }
    
    // 最初の間違えた問題を表示
    const wrongQuiz = wrongAnswers[0];
    currentQuiz = wrongQuiz;
    currentBoothId = wrongQuiz.booth_id;
    showQuizScreen(wrongQuiz);
    
    // 表示した問題を配列から削除
    wrongAnswers.shift();
}

// 「もう一度挑戦」ボタンの処理（setupEventListeners内で設定）

// 完了画面を表示
function showCompleteScreen() {
    const date = new Date().toLocaleDateString('ja-JP');
    document.getElementById('certificate-date').textContent = `認定日: ${date}`;
    showScreen('complete');
}

// 試練選択に戻る（setupEventListeners内で設定）

// 管理者画面の初期化
function initAdminScreen() {
    // 管理者画面の試練ボタンにイベントリスナーを設定
    document.querySelectorAll('.admin-booth-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const boothId = parseInt(btn.dataset.booth);
            selectBooth(boothId);
        });
    });

    // 選択解除ボタン
    document.getElementById('clear-selection-btn').addEventListener('click', () => {
        clearBoothSelection();
    });

    // ユーザー画面への切り替えボタン
    document.getElementById('admin-to-user-btn').addEventListener('click', () => {
        showScreen('home');
    });

    // 管理者画面への切り替えボタン（ホーム画面から）
    const adminBtn = document.getElementById('user-to-admin-btn');
    if (adminBtn) {
        adminBtn.addEventListener('click', () => {
            if (isAdminMode) {
                showScreen('admin');
            } else {
                alert('管理者カードが必要です。');
            }
        });
        // 初期状態では非表示
        adminBtn.style.display = 'none';
    }
}

// ステージを選択する
function selectBooth(boothId) {
    selectedBoothId = boothId;

    // すべてのボタンからselectedクラスを削除
    document.querySelectorAll('.admin-booth-btn').forEach(btn => {
        btn.classList.remove('selected');
    });

    // 選択されたボタンにselectedクラスを追加
    const selectedBtn = document.querySelector(`.admin-booth-btn[data-booth="${boothId}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('selected');
    }

    // 選択中のステージ情報を表示
    const boothLabels = {
        1: 'ステージ1: 地震時の行動',
        2: 'ステージ2: 避難所でのマナー',
        3: 'ステージ3: 非常持ち出し袋',
        4: 'ステージ4: 災害時の連絡方法',
        5: 'ステージ5: 防災グッズ'
    };

    document.getElementById('selected-booth-number').textContent = boothId;
    document.getElementById('selected-booth-label').textContent = boothLabels[boothId] || `ステージ${boothId}`;
    document.getElementById('admin-selected-booth').style.display = 'block';

    console.log(`管理者がステージ${boothId}を選択しました`);
}

// ステージの選択を解除する
function clearBoothSelection() {
    selectedBoothId = null;

    // すべてのボタンからselectedクラスを削除
    document.querySelectorAll('.admin-booth-btn').forEach(btn => {
        btn.classList.remove('selected');
    });

    // 選択中のステージ情報を非表示
    document.getElementById('admin-selected-booth').style.display = 'none';

    console.log('管理者がステージの選択を解除しました');
}

// データを非同期で読み込む
async function loadData() {
    try {
        if (window.picoResqQuiz) {
            const [quiz, admin] = await Promise.all([
                window.picoResqQuiz.loadQuizData(),
                window.picoResqQuiz.loadAdminCards()
            ]);
            quizData = quiz || { quizzes: [] };
            adminCards = admin || { admin_card_ids: [] };
            console.log('クイズデータ読み込み完了:', quizData.quizzes?.length || 0, '問');
            console.log('管理者カード読み込み完了:', adminCards.admin_card_ids?.length || 0, '枚');
        }
        dataLoaded = true;
    } catch (error) {
        console.error('データ読み込みエラー:', error);
        dataLoaded = true; // エラーでもポーリングは開始
    }
}

// 初期化
document.addEventListener('DOMContentLoaded', async function() {
    console.log('DOM読み込み完了');
    
    // イベントリスナーを設定
    setupEventListeners();

    // 管理者画面の初期化
    initAdminScreen();

    updateCardStatus('データ読み込み中...', '#666');
    
    // データを非同期で読み込み
    await loadData();

    updateCardStatus('NFCカードをリーダーにかざしてください', '#666');
    // ポーリング開始
    startPolling();
});
