// 実画面の処理を疑似DOMとNFC応答で検証する。実カードへのアクセスは行わない。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function createUi(app) {
    const elements = new Map();
    const timers = [];
    const alerts = [];
    function element(id) {
        if (!elements.has(id)) {
            elements.set(id, {
                style: {}, textContent: '', innerHTML: '',
                classList: { add() {}, remove() {} },
                addEventListener(event, callback) { this[event] = callback; },
                appendChild() {}
            });
        }
        return elements.get(id);
    }
    const context = vm.createContext({
        console: { log() {}, warn() {}, error() {} }, TextEncoder,
        document: {
            getElementById: element, querySelector: () => null,
            querySelectorAll: () => [], addEventListener() {},
            createElement: () => element(Symbol())
        },
        window: {
            picoResqNfc: { detect: async () => ({ ok: true, idm: null }) },
            picoResqQuiz: { appendQuizLog() {} }
        },
        setInterval: () => 1, clearInterval() {},
        setTimeout(callback) { timers.push(callback); },
        alert(message) { alerts.push(message); }
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', app, 'renderer.js'), 'utf8'), context);
    return { context, element, timers, alerts, run: code => vm.runInContext(code, context) };
}

function card(flags = [false, false, false, false, false]) {
    return {
        ok: true, idm: 'A', reception: { name: 'テスト', quiz_clearance_flags: 0 },
        clearance_flags: flags, cleared_count: flags.filter(Boolean).length
    };
}

test('クイズは読み取り失敗を未受付にせず、同じカードで再試行する', async () => {
    const ui = createUi('frontend');
    let reads = 0;
    ui.context.window.picoResqNfc.detect = async () => ({ ok: true, idm: 'A' });
    ui.context.window.picoResqNfc.read = async () => ++reads === 1
        ? { ok: false, error: '通信失敗' } : card();
    ui.run('dataLoaded = true; selectedBoothId = 1');
    await ui.run('pollCard()');
    assert.match(ui.element('card-status-text').textContent, /読み取り失敗/);
    assert.equal(ui.element('start-quiz-section').style.display, 'none');
    await ui.run('pollCard()');
    assert.equal(reads, 2);
    assert.equal(ui.element('start-quiz-section').style.display, 'block');
});

test('正常に読めた未登録カードだけを未受付と表示する', async () => {
    const ui = createUi('frontend');
    ui.context.window.picoResqNfc.read = async () => ({ ...card(), reception: { name: '' } });
    ui.run('currentIdm = "A"');
    await ui.run('fetchProgress("A")');
    assert.match(ui.element('card-status-text').textContent, /未受付/);
});

test('読み取り失敗後にカードを外してもカード離脱を正しく処理する', async () => {
    for (const app of ['frontend', 'reception']) {
        const ui = createUi(app);
        let detects = 0;
        ui.context.window.picoResqNfc.detect = async () => ({
            ok: true, idm: ++detects === 1 ? 'A' : null
        });
        ui.context.window.picoResqNfc.read = async () => ({ ok: false });
        if (app === 'frontend') ui.run('dataLoaded = true');
        await ui.run('pollCard()');
        await ui.run('pollCard()');
        assert.equal(ui.run(app === 'frontend' ? 'currentIdm' : 'currentCardIdm'), null, app);
    }
});

test('初回読み取り中に次のポーリングを重複させない', async () => {
    const ui = createUi('frontend');
    let calls = 0;
    let finish;
    ui.context.window.picoResqNfc.detect = () => {
        calls++;
        return new Promise(resolve => { finish = resolve; });
    };
    ui.run('dataLoaded = true');
    const pending = ui.run('pollCard()');
    await ui.run('pollCard()');
    assert.equal(calls, 1);
    finish({ ok: true, idm: null });
    await pending;
});

test('受付も通信失敗後、カードを外さず再読み取りできる', async () => {
    const ui = createUi('reception');
    let reads = 0;
    ui.context.window.picoResqNfc.detect = async () => ({ ok: true, idm: 'A' });
    ui.context.window.picoResqNfc.read = async () => ++reads === 1
        ? { ok: false, error: '通信失敗' } : card();
    await ui.run('pollCard()');
    assert.match(ui.element('resident-info').innerHTML, /読み取りエラー/);
    await ui.run('pollCard()');
    assert.equal(reads, 2);
    assert.match(ui.element('resident-info').innerHTML, /テスト/);
});

test('受付は古い受付内フラグよりヘッダー由来のクリア状態を表示する', async () => {
    const ui = createUi('reception');
    ui.context.window.picoResqNfc.read = async () => card([true, false, true, false, false]);
    await ui.run('fetchResidentInfo("A")');
    ui.run('showDetailInfo()');
    assert.match(ui.element('detail-info-content').innerHTML, /ブース1: ✓クリア/);
    assert.match(ui.element('detail-info-content').innerHTML, /ブース2: 未クリア/);
    assert.match(ui.element('detail-info-content').innerHTML, /ブース3: ✓クリア/);
});

test('受付は参加者データのない管理者カードを登録済みと表示する', async () => {
    const ui = createUi('reception');
    // 直前に参加者情報を表示していても、その詳細を管理者カードに引き継がない。
    ui.context.window.picoResqNfc.read = async () => card();
    await ui.run('fetchResidentInfo("A")');
    ui.run('showDetailInfo()');
    ui.context.window.picoResqNfc.read = async () => ({ ok: true, idm: 'ADMIN', is_admin: true });
    await ui.run('fetchResidentInfo("ADMIN")');
    assert.match(ui.element('resident-info').innerHTML, /管理者カード（登録済み）/);
    assert.doesNotMatch(ui.element('resident-info').innerHTML, /未設定|未登録|読み取りエラー/);
    assert.equal(ui.run('currentResidentData'), null);
    assert.equal(ui.run('needsReadRetry'), false);
    assert.equal(ui.element('detail-button-container').style.display, 'none');
    assert.equal(ui.element('detail-modal').style.display, 'none');
    // 続けて参加者カードを読み取れることも確認する。
    ui.context.window.picoResqNfc.read = async () => card();
    await ui.run('fetchResidentInfo("A")');
    assert.match(ui.element('resident-info').innerHTML, /テスト/);
    assert.equal(ui.element('detail-button-container').style.display, 'block');
});

function prepareAnswer(ui) {
    ui.run(`setupEventListeners(); selectedAnswer = 1; currentIdm = 'A';
        currentBoothId = 1; currentQuiz = {correct_answer: 1, quiz_number: 3};
        boothCorrectCounts = {1: 2};
        showResultScreen = result => {globalThis.result = result};`);
}

test('保存失敗・読み戻し失敗ではクリア表示せず、再回答で保存を再試行できる', async () => {
    for (const failure of ['write', 'read', 'not-cleared']) {
        const ui = createUi('frontend');
        prepareAnswer(ui);
        ui.context.window.picoResqNfc.setBoothCleared = async () => ({ ok: failure !== 'write' });
        ui.context.window.picoResqNfc.read = async () => failure === 'read'
            ? { ok: false } : card();
        await ui.element('submit-answer-btn').click();
        assert.equal(ui.context.result, undefined, failure);
        assert.equal(ui.alerts.length, 1, failure);
        ui.context.window.picoResqNfc.setBoothCleared = async () => ({ ok: true });
        ui.context.window.picoResqNfc.read = async () => card([true, false, false, false, false]);
        await ui.element('submit-answer-btn').click();
        assert.equal(ui.context.result.booth_cleared, true, failure);
        assert.equal(ui.context.result.cleared_count, 1, failure);
    }
});

test('最後の保存確認後はREADME記載の認定証画面へ進む', async () => {
    const ui = createUi('frontend');
    ui.run('currentIdm = "A"; globalThis.screensShown = []; showScreen = name => screensShown.push(name)');
    await ui.run('showResultScreen({correct: true, correct_count: 3, booth_cleared: true, all_cleared: true})');
    assert.equal(ui.timers.length, 1);
    ui.timers[0]();
    assert.equal(ui.context.screensShown.at(-1), 'complete');
});

test('受付とクイズはCLIの通信エラーJSONをそのまま画面に返す', async () => {
    for (const app of ['frontend', 'reception']) {
        const message = 'カードと通信できませんでした。カードを置いたまま再試行してください';
        const context = vm.createContext({
            __dirname: path.join(__dirname, '..', app), console,
            process: { env: { PICORESQ_PYTHON: 'test-python' }, platform: process.platform },
            require(name) {
                if (name === 'electron') return {
                    app: { whenReady: () => ({ then() {} }), on() {} }, ipcMain: { handle() {} }
                };
                if (name === 'child_process') return {
                    execFile(file, args, options, callback) {
                        callback(Object.assign(new Error('CLI exited with code 1'), {
                            stdout: JSON.stringify({ ok: false, error: message })
                        }));
                    }
                };
                return require(name);
            }
        });
        vm.runInContext(fs.readFileSync(path.join(__dirname, '..', app, 'main.js'), 'utf8'), context);
        const result = await vm.runInContext('runNfcCli(["detect"])', context);
        assert.equal(result.ok, false, app);
        assert.equal(result.error, message, app);
    }
});
