<template>
  <div class="p-4 space-y-5">
    <h1 class="text-2xl font-bold">{{ isEdit ? L.edit : L.addExpense }}</h1>

    <form @submit.prevent="save" class="space-y-5">
      <!-- Amount -->
      <div>
        <label class="block text-xl font-semibold mb-2">{{ L.amount }}</label>
        <input v-model="form.amount" type="number" inputmode="numeric" min="1"
          class="w-full border-2 rounded-lg px-4 py-3 text-xl" required />
      </div>

      <!-- Category -->
      <div>
        <label class="block text-xl font-semibold mb-2">{{ L.category }}</label>
        <select v-model="form.category_code" class="w-full border-2 rounded-lg px-4 py-3 text-xl" required>
          <option value="" disabled>— Pilih —</option>
          <option v-for="cat in categories" :key="cat.code" :value="cat.code">{{ cat.label_id }}</option>
        </select>
      </div>

      <!-- Description -->
      <div>
        <label class="block text-xl font-semibold mb-2">{{ L.description }}</label>
        <input v-model="form.description" type="text" class="w-full border-2 rounded-lg px-4 py-3 text-xl" />
      </div>

      <!-- Payment method -->
      <div>
        <label class="block text-xl font-semibold mb-2">{{ L.paymentMethod }}</label>
        <div class="flex gap-4">
          <label v-for="opt in paymentOpts" :key="opt.value" class="flex items-center gap-2">
            <input type="radio" v-model="form.payment_method" :value="opt.value" class="w-5 h-5" />
            <span class="text-xl">{{ opt.label }}</span>
          </label>
        </div>
      </div>

      <!-- Date only -->
      <div>
        <label class="block text-xl font-semibold mb-2">{{ L.date }}</label>
        <input v-model="form.date" type="date" class="w-full border-2 rounded-lg px-4 py-3 text-xl" required />
      </div>

      <!-- Note -->
      <div>
        <label class="block text-xl font-semibold mb-2">{{ L.note }}</label>
        <textarea v-model="form.note" rows="2"
          :placeholder="L.notePlaceholder"
          class="w-full border-2 rounded-lg px-4 py-3 text-xl"></textarea>
      </div>

      <!-- Buttons -->
      <div class="flex gap-3 pt-2">
        <button type="submit" :disabled="saving"
          class="flex-1 bg-blue-600 text-white rounded-lg py-4 text-xl font-semibold disabled:opacity-50">
          {{ saving ? '...' : L.save }}
        </button>
        <router-link :to="isEdit ? '/riwayat' : '/riwayat'"
          class="flex-1 border-2 rounded-lg py-4 text-center text-xl">
          {{ L.cancel }}
        </router-link>
      </div>
    </form>

    <!-- Delete button (edit mode only) -->
    <button v-if="isEdit" @click="doDelete"
      class="w-full border-2 border-red-400 text-red-600 rounded-lg py-4 text-xl font-semibold">
      {{ L.delete }}
    </button>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchCategories, createTransaction, updateTransaction, deleteTransaction, fetchTransactions } from '../api/client.js'
import { todayLocal, nowLocal, buildTxnDatetime } from '../utils.js'
import labels from '../labels.js'

const L = labels
const route = useRoute()
const router = useRouter()
const showToast = inject('toast')

const categories = ref([])
const saving = ref(false)

const isEdit = computed(() => !!route.params.id)

const form = reactive({
  amount: '',
  category_code: '',
  description: '',
  payment_method: 'cash',
  date: todayLocal(),
  note: '',
})

const paymentOpts = [
  { value: 'cash', label: L.cash },
  { value: 'transfer', label: L.transfer },
  { value: 'ewallet', label: L.ewallet },
]

onMounted(async () => {
  categories.value = await fetchCategories()

  if (isEdit.value) {
    const txns = await fetchTransactions({ limit: 200 })
    const txn = txns.find(t => t.id === Number(route.params.id))
    if (txn) {
      form.amount = txn.amount
      form.category_code = txn.category_code
      form.description = txn.description
      form.payment_method = txn.payment_method
      form.note = txn.note
      const d = new Date(txn.txn_datetime)
      form.date = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
    }
  }
})

async function save() {
  if (!form.amount || !form.category_code) return
  if (!form.description) return

  saving.value = true
  try {
    const payload = {
      amount: Number(form.amount),
      category_code: form.category_code,
      merchant: '',
      description: form.description || '',
      payment_method: form.payment_method,
      note: form.note || '',
      txn_datetime: buildTxnDatetime(form.date, '12:00'),
    }

    if (isEdit.value) {
      await updateTransaction(Number(route.params.id), payload)
    } else {
      payload.client_txn_id = crypto.randomUUID()
      await createTransaction(payload)
    }

    showToast(L.savedOk)
    router.push('/riwayat')
  } catch {
    showToast(L.saveFailed, 'error')
  } finally {
    saving.value = false
  }
}

async function doDelete() {
  if (!confirm(L.deleteConfirm)) return
  try {
    await deleteTransaction(Number(route.params.id))
    showToast(L.deletedOk)
    router.push('/riwayat')
  } catch {
    showToast(L.saveFailed, 'error')
  }
}
</script>
