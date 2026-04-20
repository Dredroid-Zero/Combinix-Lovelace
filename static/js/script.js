/**
 * script.js — Combinix Lovelace
 * Funções globais disponíveis em todas as páginas.
 * Carregado pelo base.html após jQuery e Bootstrap.
 */

/**
 * Exibe o toast de "Salvo automaticamente" no canto inferior direito.
 */
function showAutoSave() {
    var el = document.getElementById('autoSaveToast');
    if (el) {
        new bootstrap.Toast(el).show();
    }
}