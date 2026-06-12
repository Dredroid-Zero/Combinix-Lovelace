/**
 * Persistência web demonstrativa do Combinix Lovelace.
 * IndexedDB é o armazenamento principal; localStorage é apenas fallback.
 * O estado atual é sobrescrito: não existe crescimento indefinido por clique.
 */
(function () {
    'use strict';

    var DB_NAME = 'combinix-lovelace';
    var DB_VERSION = 1;
    var STORE = 'workspace';
    var CURRENT_KEY = 'current';
    var FALLBACK_KEY = 'combinix.browser.state.v2';
    var FALLBACK_MAX_CHARS = 3 * 1024 * 1024;
    var mode = window.COMBINIX_STORAGE_MODE || 'local';
    var backend = 'IndexedDB';

    function clone(value) {
        try { return JSON.parse(JSON.stringify(value || {})); }
        catch (_err) { return {}; }
    }

    function openDb() {
        return new Promise(function (resolve, reject) {
            if (!window.indexedDB) {
                reject(new Error('IndexedDB indisponível'));
                return;
            }
            var req = window.indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function () {
                var db = req.result;
                if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error || new Error('Falha ao abrir IndexedDB')); };
        });
    }

    function idbGet() {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE, 'readonly');
                var req = tx.objectStore(STORE).get(CURRENT_KEY);
                req.onsuccess = function () { resolve(req.result || {}); };
                req.onerror = function () { reject(req.error || new Error('Falha ao ler IndexedDB')); };
                tx.oncomplete = function () { db.close(); };
            });
        });
    }

    function idbSet(state) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE, 'readwrite');
                tx.objectStore(STORE).put(clone(state), CURRENT_KEY);
                tx.oncomplete = function () { db.close(); resolve(state); };
                tx.onerror = function () { db.close(); reject(tx.error || new Error('Falha ao gravar IndexedDB')); };
                tx.onabort = function () { db.close(); reject(tx.error || new Error('Gravação IndexedDB cancelada')); };
            });
        });
    }

    function idbClear() {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE, 'readwrite');
                tx.objectStore(STORE).delete(CURRENT_KEY);
                tx.oncomplete = function () { db.close(); resolve(); };
                tx.onerror = function () { db.close(); reject(tx.error || new Error('Falha ao limpar IndexedDB')); };
            });
        });
    }

    function fallbackGet() {
        try { return JSON.parse(localStorage.getItem(FALLBACK_KEY) || '{}') || {}; }
        catch (_err) { return {}; }
    }

    function fallbackSet(state) {
        var serialized = JSON.stringify(state || {});
        if (serialized.length <= FALLBACK_MAX_CHARS) {
            try { localStorage.setItem(FALLBACK_KEY, serialized); return true; } catch (_err) { return false; }
        }
        try { localStorage.removeItem(FALLBACK_KEY); } catch (_err2) {}
        return false;
    }

    function fallbackClear() {
        try {
            localStorage.removeItem(FALLBACK_KEY);
            localStorage.removeItem('combinix.selecoes.v1');
            sessionStorage.removeItem('combinix.selecoes.restore.attempted');
        } catch (_err) {}
    }

    function getState() {
        if (mode !== 'browser') return Promise.resolve({});
        return idbGet().then(function (state) {
            backend = 'IndexedDB';
            if (state && Object.keys(state).length) return state;
            return fallbackGet();
        }).catch(function () {
            backend = 'localStorage (fallback)';
            return fallbackGet();
        });
    }

    function setState(state) {
        if (mode !== 'browser') return Promise.resolve(state || {});
        state = clone(state);
        var fallbackSaved = fallbackSet(state);
        return idbSet(state).then(function () {
            backend = 'IndexedDB';
            return state;
        }).catch(function () {
            backend = 'localStorage (fallback)';
            if (!fallbackSaved) {
                throw new Error('Não foi possível salvar no armazenamento deste navegador. Exporte um backup e libere espaço.');
            }
            return state;
        });
    }

    function clearState() {
        fallbackClear();
        if (mode !== 'browser') return Promise.resolve();
        return idbClear().catch(function () {});
    }

    function bytesOf(state) {
        try { return new Blob([JSON.stringify(state || {})]).size; }
        catch (_err) { return 0; }
    }

    function formatBytes(bytes) {
        bytes = Number(bytes || 0);
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KiB';
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MiB';
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GiB';
    }

    function estimate() {
        return Promise.all([
            getState(),
            navigator.storage && navigator.storage.estimate ? navigator.storage.estimate() : Promise.resolve({}),
            navigator.storage && navigator.storage.persisted ? navigator.storage.persisted().catch(function () { return false; }) : Promise.resolve(false)
        ]).then(function (items) {
            return {
                backend: backend,
                stateBytes: bytesOf(items[0]),
                usage: Number(items[1].usage || 0),
                quota: Number(items[1].quota || 0),
                persisted: Boolean(items[2]),
                formatBytes: formatBytes
            };
        });
    }

    function requestPersistence() {
        if (!navigator.storage || !navigator.storage.persist) return Promise.resolve(false);
        return navigator.storage.persist().catch(function () { return false; });
    }

    function submitState(target) {
        return getState().then(function (state) {
            var form = document.createElement('form');
            form.method = 'POST';
            form.action = target;
            form.style.display = 'none';
            var st = document.createElement('input');
            st.type = 'hidden'; st.name = 'browser_state'; st.value = JSON.stringify(state || {});
            var csrf = document.createElement('input');
            csrf.type = 'hidden'; csrf.name = 'csrf_token'; csrf.value = window.COMBINIX_CSRF || '';
            form.appendChild(st); form.appendChild(csrf);
            document.body.appendChild(form);
            form.submit();
        });
    }

    window.CombinixBrowserStorage = {
        mode: mode,
        getState: getState,
        setState: setState,
        clearState: clearState,
        estimate: estimate,
        requestPersistence: requestPersistence,
        submitState: submitState,
        formatBytes: formatBytes,
        backend: function () { return backend; }
    };
})();
