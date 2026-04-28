<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  open: Boolean,
  title: String,
  message: String,
  type: { type: String, default: 'confirm' }, // alert, confirm, prompt, suggestion, bulk_suggestions
  initialValue: [String, Number],
  suggestions: { type: Array, default: () => [] },
  preview: { type: Object, default: null }, // from suggestPreview
  confirmText: { type: String, default: 'OK' },
  cancelText: { type: String, default: 'Cancel' },
  loading: Boolean,
})

const emit = defineEmits(['close', 'confirm'])

const inputValue = ref('')

// Initialize inputValue when opening
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    inputValue.value = props.initialValue ?? ''
  }
})

const hasConflicts = computed(() => {
  return props.type === 'bulk_suggestions' && (props.preview?.conflicts?.length > 0)
})

function close() {
  if (props.loading) return
  emit('close')
}

function onConfirm() {
  if (props.loading || hasConflicts.value) return
  emit('confirm', inputValue.value)
}

function fmtNum(n) {
  if (n === null || n === undefined) return '0'
  return Number(n).toLocaleString('id-ID')
}
</script>

<template>
  <div v-if="open" 
    class="coretax-dialog-overlay" 
    @click.self="close"
    role="dialog"
    aria-modal="true"
    aria-labelledby="coretax-dialog-title"
  >
    <div class="coretax-dialog-card">
      <div id="coretax-dialog-title" class="setting-title">{{ title }}</div>
      
      <div v-if="message" class="setting-desc" style="margin-top:8px; white-space: pre-wrap;">{{ message }}</div>

      <!-- Prompt Input -->
      <div v-if="type === 'prompt'" style="margin-top:16px">
        <input 
          v-model="inputValue" 
          class="range-select" 
          style="width:100%" 
          @keyup.enter="onConfirm"
          ref="inputRef"
          autoFocus
        />
      </div>

      <!-- Single Suggestion -->
      <div v-if="type === 'suggestion' && suggestions.length" style="margin-top:16px">
        <div v-for="s in [suggestions[0]]" :key="s.target_stable_key" class="suggestion-preview">
          <div class="preview-row">
            <span class="preview-label">Target:</span>
            <span class="preview-value">{{ s.target_stable_key }}</span>
          </div>
          <div class="preview-row">
            <span class="preview-label">Rule:</span>
            <span class="preview-value">{{ s.rule }}</span>
          </div>
          <div class="preview-row">
            <span class="preview-label">Confidence:</span>
            <span class="conf-dot" :class="'conf-'+(s.confidence_level||'HIGH').toLowerCase()">{{ s.confidence_score }}</span>
          </div>
        </div>
      </div>

      <!-- Bulk Suggestions -->
      <div v-if="type === 'bulk_suggestions'" class="bulk-suggestions-container">
        <div v-if="preview" class="preview-summary">
          <div class="preview-summary__line ok">✔ {{ preview.count }} suggestions to apply</div>
          <div v-if="hasConflicts" class="preview-summary__line warn">
            ⚠ {{ preview.conflicts.length }} conflicts found. Resolve conflicts before bulk accept.
          </div>
        </div>
        <div class="bulk-table-wrap">
          <table class="data-table" style="font-size:11px">
            <thead>
              <tr><th>Rule</th><th>Target</th><th>Conf</th></tr>
            </thead>
            <tbody>
              <tr v-for="(s, idx) in suggestions" :key="idx">
                <td>{{ s.rule }}</td>
                <td class="cell-src">{{ s.target_stable_key?.slice(0,12) }}…</td>
                <td>{{ s.confidence_score }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="modal-actions">
        <button v-if="type !== 'alert'" class="btn btn-ghost" @click="close" :disabled="loading">
          {{ cancelText }}
        </button>
        <button 
          class="btn" 
          @click="onConfirm" 
          :disabled="loading || hasConflicts"
          :title="hasConflicts ? 'Conflicts must be resolved first' : ''"
        >
          {{ loading ? 'Processing...' : confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.coretax-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 200; /* Higher than normal modals if needed */
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(2px);
}

.coretax-dialog-card {
  background: #141820;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  padding: 24px;
  width: min(92vw, 640px);
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
}

.bulk-suggestions-container {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.bulk-table-wrap {
  overflow-y: auto;
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.suggestion-preview {
  background: rgba(255, 255, 255, 0.05);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.preview-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 13px;
}

.preview-label { color: var(--text-muted); }
.preview-value { font-weight: 600; }

.modal-actions {
  border-top: 1px solid var(--border);
  padding-top: 20px;
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  flex-shrink: 0;
}

.conf-dot {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 700;
}

.conf-high { background: rgba(92, 199, 129, 0.15); color: #c8ffd8; }
.conf-medium { background: rgba(255, 193, 7, 0.15); color: #fff3cd; }
.conf-low { background: rgba(255, 99, 99, 0.15); color: #ffd2d2; }

.preview-summary {
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.preview-summary__line {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.preview-summary__line.ok { color: #5cc781; }
.preview-summary__line.warn { color: #ffc107; }

/* Mobile adjustments */
@media (max-width: 600px) {
  .coretax-dialog-card {
    padding: 20px;
    border-radius: 12px;
  }
  .modal-actions {
    margin-top: 16px;
    padding-top: 16px;
  }
}
</style>
